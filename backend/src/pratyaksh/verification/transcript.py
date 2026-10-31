"""A Call as a conversation: what the Voice Agent and the Caller said, and what the Verifier did
in between. Built only from the Audit Trail, so a transcript is as tamper-evident as its events.

Each line: {seq, at, event, speaker: "agent" | "caller" | "system", text, ...}. Caller lines may add
understood (a TurnKind), language, by_llm, by_variant, challenge, liveness, signals and timings_ms; system lines
may add tone ("pass" | "stepup" | "block") for the Console's Verdict colours.
"""

from __future__ import annotations

from datetime import datetime

CHALLENGE_NAMES = {"whisper_phrase": "Whisper Phrase", "possession_code": "Possession Code"}
REQUEST_NAMES = {
    "balance_enquiry": "Balance enquiry",
    "add_payee": "Add payee",
    "sim_swap": "SIM swap / password reset",
    "high_value_transfer": "High-value transfer",
    "account_service": "Account service",
}
OUTCOME_NAMES = {
    "passed": "passed",
    "passed_pending_review": "passed, Agent Review pending",
    "blocked": "blocked",
    "handed_to_agent": "handed to a Bank Agent",
    "approved_in_app": "approved in the bank app",
    "declined_in_app": "declined in the bank app",
    "abandoned": "abandoned",
    "ended": "ended by the Caller",
}
_TONES = {"PASS": "pass", "STEP_UP": "stepup", "BLOCK": "block"}
_SIGNALS = ("task_match", "whisper_score", "reply_latency_ms", "spoof_score", "code_match")


def lines(events: list[dict]) -> list[dict]:
    """The transcript of a Call, from its Audit Trail events (as Verifier.call() returns them)."""
    out = []
    for e in events:
        line = _line(e["kind"], e.get("data") or {})
        if line is not None:
            out.append({"seq": e["seq"], "at": e["at"], "event": e["kind"], **line})
    return out


def as_text(call: dict) -> str:
    """A plain-text transcript to download or attach to a fraud case. The Audit head lets anyone
    holding the Call's Verification Receipt check that this is the Audit Trail it signed."""
    audit = call.get("audit") or {}
    head = audit.get("head") or "-"
    request = REQUEST_NAMES.get(call.get("request") or "", call.get("request") or "-")
    out = [
        "Pratyaksh Call transcript",
        f"Call       {call['id']}",
        f"Customer   {call['customer']['name']} ({call['customer']['id']})",
        f"Started    {call['created_at']} UTC",
        f"Request    {request}",
        f"Verdict    {call.get('verdict') or '-'}   Liveness {_fmt(call.get('liveness'))}",
        f"Outcome    {OUTCOME_NAMES.get(call.get('outcome') or '', call.get('outcome') or 'in progress')}",
        f"Audit      {'intact' if audit.get('intact') else 'BROKEN'}, {audit.get('events', 0)} events, head {head}",
        "",
    ]
    for line in call.get("transcript", []):
        at = datetime.fromisoformat(line["at"]).strftime("%H:%M:%S")
        who = {"agent": "Agent", "caller": "Caller", "system": "  ·"}[line["speaker"]]
        text = line["text"] or "(silence)"
        tags = [t for t in (line.get("language"), line.get("understood")) if t and t != "en"]
        if line.get("liveness") is not None:
            tags.append(f"liveness {line['liveness']:.2f}")
        if line.get("timings_ms"):
            tags.append(f"{line['timings_ms'].get('total', 0)} ms")
        out.append(f"{at}  {who:<6}  {text}" + (f"   [{' · '.join(tags)}]" if tags else ""))
        out.extend(f"{'':18}- {r}" for r in line.get("reasons", [])[1:])
    return "\n".join(out) + "\n"


def _line(kind: str, d: dict) -> dict | None:
    if kind == "agent_said":
        return {"speaker": "agent", "text": d.get("say", "")}
    if kind in ("caller_said", "app_approval_asked", "code_retry", "code_expired", "response_scored",
                "challenge_repeated"):
        return _caller(kind, d)
    text = _system(kind, d)
    if text is None:
        return None
    line: dict = {"speaker": "system", "text": text}
    if kind == "verdict":
        line["tone"] = _TONES.get(d.get("verdict", ""))
        line["reasons"] = d.get("reasons") or []
    elif kind in ("security_alert_sent",) or (kind == "call_closed" and d.get("outcome") == "blocked"):
        line["tone"] = "block"
    return line


def _caller(kind: str, d: dict) -> dict:
    signals = d.get("signals") or {}
    line: dict = {"speaker": "caller", "text": d.get("transcript", signals.get("transcript", ""))}
    if kind == "caller_said":
        line["understood"] = d.get("kind")
        if d.get("language"):
            line["language"] = d["language"]
        if d.get("by_llm"):
            line["by_llm"] = True
        if d.get("by_variant"):
            line["by_variant"] = True
    elif kind == "app_approval_asked":
        line["understood"] = "app_approval"
    elif kind == "code_retry":
        line["note"] = "The code didn't match. One more try."
    elif kind == "code_expired":
        line["note"] = ("The right code, read after it expired. A new one was sent." if d.get("reissued")
                        else "The new code expired too. Handing over to App Approval.")
    elif kind == "challenge_repeated":
        line["note"] = "No speech heard. The Challenge is repeated once."
    elif kind == "response_scored":
        line["challenge"] = d.get("kind")
        line["liveness"] = d.get("liveness")
        line["signals"] = {k: signals.get(k) for k in _SIGNALS if signals.get(k) is not None}
    if d.get("timings_ms"):
        line["timings_ms"] = d["timings_ms"]
    return line


def _system(kind: str, d: dict) -> str | None:
    if kind == "call_started":
        return "Call started."
    if kind == "risk_tier_set":
        checks = " + ".join(_counted(d.get("challenges", []))) or "no Challenges"
        review = ", then Agent Review" if d.get("agent_review") else ""
        review += " (Attack Wave under way)" if d.get("attack_wave") else ""
        return f"Risk Tier: {REQUEST_NAMES.get(d.get('request', ''), d.get('request'))} needs {checks}{review}."
    if kind == "challenge_issued":
        name = CHALLENGE_NAMES.get(d.get("kind", ""), d.get("kind"))
        if d.get("kind") == "possession_code":
            return f"{name} sent to the Registered Device."
        return f"{name} issued: “{d.get('phrase', '')}”."
    if kind == "verdict":
        liveness = "" if d.get("liveness") is None else f" (liveness {d['liveness']:.2f})"
        head = (d.get("reasons") or [""])[0]  # the deciding Reason; all of them are in line["reasons"]
        return f"Verdict {d.get('verdict')}{liveness}. {head}".strip()
    if kind == "app_approval_requested":
        return "App Approval request sent to the Registered Device."
    if kind == "app_approval_answered":
        return "Approved in the bank app." if d.get("approved") else "Declined in the bank app."
    if kind == "app_approval_expired":
        return "The App Approval request expired."
    if kind == "security_alert_sent":
        return "Security Alert sent to the Registered Device. Voice Pause is on."
    if kind == "next_step_sent":
        return "Next steps sent to the Registered Device."
    if kind == "next_step_done":
        return "The Customer finished the next steps."
    if kind == "security_alert_dismissed":
        return "The Customer dismissed the Security Alert."
    if kind == "handed_to_agent":
        return "Handed to a Bank Agent."
    if kind == "caller_hung_up":
        return "The Caller hung up."
    if kind == "call_went_silent":
        return f"The Voice Agent went silent for {d.get('minutes', 5)} minutes; the Call was closed."
    if kind == "review_decided":
        verb = "approved" if d.get("approved") else "rejected"
        return f"Agent Review {verb} by {d.get('reviewer') or 'a bank officer'}."
    if kind == "processing_error":
        return f"Couldn't process that Response (attempt {d.get('attempt', 1)})."
    if kind == "response_ignored":
        return f"A late Response was ignored: {d.get('reason', '')}."
    if kind == "receipt_redeemed":
        return "Core banking redeemed the Verification Receipt and carried out the Request."
    if kind == "call_closed":
        return f"Call closed: {OUTCOME_NAMES.get(d.get('outcome', ''), d.get('outcome'))}."
    return None


def _counted(kinds: list[str]) -> list[str]:
    """["whisper_phrase", "whisper_phrase", "possession_code"] -> ["2 Whisper Phrases", "Possession Code"]."""
    out = []
    for kind in dict.fromkeys(kinds):
        n, name = kinds.count(kind), CHALLENGE_NAMES.get(kind, kind)
        out.append(f"{n} {name}s" if n > 1 else name)
    return out


def _fmt(x: float | None) -> str:
    return "-" if x is None else f"{x:.2f}"
