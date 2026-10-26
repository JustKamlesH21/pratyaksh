"""Smoke-test a running setup end to end, without a person: one Call over the verifier's HTTP interface.

The Caller is synthetic: every reply is spoken by the verifier's own voice (/v1/voice), so it reads
the Request, the Whisper Phrase it is actually issued, and the Possession Code from the Bank App
inbox, exactly as an attacker with a good text-to-speech voice and the phone would. It cannot
whisper, so this is a Clone attempt: expect BLOCK (or STEP-UP then BLOCK), a Security Alert on the
Registered Device, and a Voice Pause when calling straight back. Afterwards it dismisses the alert,
as the Customer would, so the demo Customer is clean again.

    python scripts/smoke_call.py                       # cust-rahul, "I want to add a new payee"
    python scripts/smoke_call.py --customer cust-meera --request "transfer six lakh to my brother"

Reads AGENT_KEY, CONSOLE_KEY, VERIFIER_URL and DATABASE_URL from .env (run it from the repo root).
Prints hearing time per step: upload to next Step, the PRD's verifier turnaround (target 1.5 s).
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx
from sqlalchemy import select

from pratyaksh.config import Settings
from pratyaksh.phrases import speakable
from pratyaksh.verification.store import CustomerRow, Database

DIGITS = "zero one two three four five six seven eight nine".split()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--customer", default="cust-rahul")
    p.add_argument("--request", default="I want to add a new payee")
    p.add_argument("--keep-alert", action="store_true", help="leave the Security Alert for the Bank App demo")
    args = p.parse_args()

    s = Settings()
    with Database(s.database_url).session() as db:
        token = db.scalars(select(CustomerRow.device_token).where(CustomerRow.id == args.customer)).first()
    if token is None:
        sys.exit(f"unknown customer {args.customer}; run pratyaksh-seed")
    agent = {"X-Agent-Key": s.agent_key}
    console = {"X-Console-Key": s.console_key}
    device = {"X-Device-Token": token}
    http = httpx.Client(base_url=s.verifier_url, timeout=180)

    def voice(text: str) -> bytes:
        r = http.get("/v1/voice", params={"text": text}, headers=agent)
        r.raise_for_status()
        return r.content

    def reply(call_id: str, text: str) -> tuple[dict, float]:
        audio = voice(text)  # synthesised before the clock starts: only the verifier is timed
        t = time.perf_counter()
        r = http.post(f"/v1/calls/{call_id}/responses", headers=agent,
                      files={"audio": ("r.wav", audio, "audio/wav")}, data={"reply_latency_ms": "700"})
        r.raise_for_status()
        return r.json(), time.perf_counter() - t

    status = http.get("/v1/status").json()
    print(f"status: ready={status['ready']} warnings={status['warnings']}")
    step = http.post("/v1/calls", json={"customer_id": args.customer, "room": "smoke"}, headers=agent).json()
    call_id = step["call_id"]
    print(f"call {call_id} for {args.customer}\n  agent: {step['say']}")
    for _ in range(10):
        if step["end"] or not step["listen"]:
            break
        call = http.get(f"/v1/calls/{call_id}", headers=console).json()
        issued = call["challenges"][-1] if call["state"] == "challenging" and call["challenges"] else None
        if issued is None:
            said = args.request
        elif issued["kind"] == "whisper_phrase":
            said = speakable(issued["phrase"])
        else:
            msgs = http.get(f"/v1/customers/{args.customer}/inbox", headers=device).json()["messages"]
            code = next(m["body"]["code"] for m in msgs if m["kind"] == "possession_code")
            said = " ".join(DIGITS[int(d)] for d in code)
        step, took = reply(call_id, said)
        print(f"  caller: {said}\n  hearing {took:.2f} s\n  agent: {step['say']}")

    call = http.get(f"/v1/calls/{call_id}", headers=console).json()
    print(f"\nverdict {call['verdict']}  outcome {call['outcome']}  liveness {call.get('liveness')}")
    for reason in call.get("reasons") or []:
        print(f"  reason: {reason}")
    print("\n" + http.get(f"/v1/calls/{call_id}/transcript", params={"format": "text"}, headers=console).text)

    if call["verdict"] == "BLOCK":
        alerts = [m for m in http.get(f"/v1/customers/{args.customer}/inbox", headers=device).json()["messages"]
                  if m["kind"] == "security_alert"]
        print(f"Security Alert on the Registered Device: {'yes' if alerts else 'NO'}")
        again = http.post("/v1/calls", json={"customer_id": args.customer, "room": "smoke-2"}, headers=agent).json()
        again, _ = reply(again["call_id"], args.request)
        print(f"calling straight back: {again['outcome']}: {again['say']}")
        if not args.keep_alert:
            n = http.post(f"/v1/customers/{args.customer}/alerts/dismiss", headers=device).json()["dismissed"]
            print(f"dismissed {n} Security Alert(s) as the Customer, on their Registered Device")
    stats = http.get("/v1/stats").json()
    print(f"\nstats: {stats}")


if __name__ == "__main__":
    main()
