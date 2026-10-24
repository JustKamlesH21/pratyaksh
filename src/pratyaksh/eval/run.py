"""pratyaksh-eval: measure Catch Rate, False Reject Rate and Added Time.

  pratyaksh-eval export --label real  [--since 2026-10-29T10:00]   # recorded Calls -> manifest rows
  pratyaksh-eval export --label clone [--since ...]
  pratyaksh-eval run data/eval/manifest.csv [--label "venue mics"] [--policy tuned.yaml] [--speech scripted]

Recording: run the verifier with RETAIN_AUDIO=true (with consent), place Calls, then export.
Manifest columns (one row per Response):
  session_id, label (real|clone), request, kind (whisper_phrase|possession_code), audio,
  reply_latency_ms, expected (Whisper Phrase), code_match (true|false|blank), transcript (optional)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..config import Settings
from ..domain import Audio, Challenge, ChallengeKind, Evidence, RequestKind, Response, Signals, Verdict
from ..policy import Policy
from ..signals import LocalSpeechModels, ScriptedSpeechModels, SignalExtractor, SpeechModels
from ..verification.store import AuditEventRow, CallRow, Database

FIELDS = ["session_id", "label", "request", "kind", "audio", "reply_latency_ms", "expected", "code_match", "transcript"]
PROMPT_SECONDS = 4.0  # rough time the Voice Agent spends saying each Challenge


@dataclass
class Row:
    session_id: str
    label: str
    request: RequestKind
    kind: ChallengeKind
    audio: Path
    reply_latency_ms: int | None
    expected: str
    code_match: bool | None
    transcript: str


def read_manifest(path: Path) -> list[Row]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            try:
                if r["label"] not in ("real", "clone"):
                    raise ValueError("label must be real or clone")
                audio = Path(r["audio"])
                rows.append(Row(
                    session_id=r["session_id"],
                    label=r["label"],
                    request=RequestKind(r["request"]),
                    kind=ChallengeKind(r["kind"]),
                    audio=audio if audio.is_absolute() else (path.parent / audio),
                    reply_latency_ms=int(r["reply_latency_ms"]) if r.get("reply_latency_ms") else None,
                    expected=r.get("expected", ""),
                    code_match={"true": True, "false": False}.get((r.get("code_match") or "").lower()),
                    transcript=r.get("transcript", "") or "",
                ))
            except (KeyError, ValueError) as e:
                raise SystemExit(f"{path}:{i}: {e}") from e
    return rows


def evaluate(
    rows: list[Row],
    policy: Policy,
    models_for: Callable[[Row], SpeechModels],
    prompt_seconds: float = PROMPT_SECONDS,
) -> dict:
    """Score every session with the same Signals and Policy code the live Verifier uses."""
    sessions: OrderedDict[str, list[Row]] = OrderedDict()
    for r in rows:
        sessions.setdefault(r.session_id, []).append(r)

    results = []
    for sid, srows in sessions.items():
        evidence, added = [], 0.0
        for r in srows:
            audio = Audio.from_wav(r.audio.read_bytes())
            extractor = SignalExtractor(models_for(r))
            signals = extractor.extract(Challenge(r.kind, "", r.expected), Response(audio, r.reply_latency_ms))
            if r.kind is ChallengeKind.POSSESSION_CODE:
                signals = Signals.from_dict({**signals.to_dict(), "code_match": r.code_match})
            evidence.append(Evidence(r.kind, signals))
            added += prompt_seconds + (r.reply_latency_ms or 0) / 1000 + audio.seconds
        d = policy.decide(evidence, step_ups_used=1)  # judge the recorded answers as final
        results.append({
            "session_id": sid,
            "label": srows[0].label,
            "request": srows[0].request.value,
            "verdict": d.verdict.value,
            "liveness": None if d.liveness is None else round(d.liveness, 3),
            "added_seconds": round(added, 1),
            "reasons": d.reasons,
        })

    real = [r for r in results if r["label"] == "real"]
    clone = [r for r in results if r["label"] == "clone"]
    summary = {
        "calls": len(results),
        "real_calls": len(real),
        "clone_calls": len(clone),
        "catch_rate": _share(clone, lambda r: r["verdict"] == Verdict.BLOCK.value),
        "false_reject_rate": _share(real, lambda r: r["verdict"] != Verdict.PASS.value),
        "avg_added_seconds_real": round(sum(r["added_seconds"] for r in real) / len(real), 1) if real else None,
    }
    return {"summary": summary, "rows": results}


def _share(rows: list[dict], pred) -> float | None:
    return round(sum(1 for r in rows if pred(r)) / len(rows), 3) if rows else None


# -- export recorded Calls -------------------------------------------------------------

_RESPONSE_EVENTS = {"request_heard", "challenge_repeated", "code_retry", "app_approval_asked", "response_scored"}


def export(db: Database, audio_dir: Path, label: str, since: datetime | None, out: Path) -> int:
    """Append manifest rows for every closed, recorded Call (one row per scored Response)."""
    from sqlalchemy import select

    new_rows = []
    with db.session() as s:
        q = select(CallRow).where(CallRow.state == "closed", CallRow.request.is_not(None))
        if since:
            q = q.where(CallRow.created_at >= since)
        for call in s.scalars(q.order_by(CallRow.created_at)).all():
            folder = audio_dir / call.id
            files = sorted(folder.glob("*.wav")) if folder.exists() else []
            events = [
                e for e in s.scalars(
                    select(AuditEventRow).where(AuditEventRow.call_id == call.id).order_by(AuditEventRow.seq)
                ).all()
                if e.kind in _RESPONSE_EVENTS
            ]
            if not files or len(files) != len(events):
                print(f"skip {call.id}: {len(files)} recordings for {len(events)} responses", file=sys.stderr)
                continue
            for wav, ev in zip(files, events):
                if ev.kind != "response_scored":
                    continue
                sig = ev.data["signals"]
                idx = int(ev.data["challenge"]) - 1
                expected = call.challenges[idx].get("phrase", "") if idx < len(call.challenges) else ""
                new_rows.append({
                    "session_id": call.id, "label": label, "request": call.request, "kind": ev.data["kind"],
                    "audio": str(wav.resolve()), "reply_latency_ms": sig.get("reply_latency_ms") or "",
                    "expected": expected,
                    "code_match": "" if sig.get("code_match") is None else str(sig["code_match"]).lower(),
                    "transcript": sig.get("transcript", ""),
                })
    write_header = not out.exists()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(new_rows)
    return len(new_rows)


def main(argv: list[str] | None = None) -> None:
    settings = Settings()
    p = argparse.ArgumentParser(prog="pratyaksh-eval", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="evaluate a manifest and store the Eval Run")
    pr.add_argument("manifest", type=Path)
    pr.add_argument("--label", default="")
    pr.add_argument("--notes", default="")
    pr.add_argument("--policy", default=settings.policy_path)
    pr.add_argument("--speech", choices=["local", "scripted"], default="local",
                    help="scripted uses the manifest's transcript column instead of speech-to-text")
    pr.add_argument("--no-save", action="store_true")
    pr.add_argument("--json", type=Path, help="also write the full report here")

    pe = sub.add_parser("export", help="turn recorded Calls into manifest rows")
    pe.add_argument("--label", choices=["real", "clone"], required=True)
    pe.add_argument("--since", type=datetime.fromisoformat)
    pe.add_argument("--out", type=Path, default=Path("data/eval/manifest.csv"))

    args = p.parse_args(argv)
    db = Database(settings.database_url)
    db.create_schema()

    if args.cmd == "export":
        n = export(db, Path(settings.audio_dir), args.label, args.since, args.out)
        print(f"added {n} rows to {args.out}")
        return

    rows = read_manifest(args.manifest)
    if args.speech == "scripted":
        def models_for(r: Row) -> SpeechModels:
            return ScriptedSpeechModels([r.transcript])
    else:
        shared = LocalSpeechModels(
            settings.whisper_model, settings.whisper_device, settings.whisper_compute_type,
            settings.spoof_model or None,
            tuple(l.strip() for l in settings.spoof_fake_labels.split(",") if l.strip()),
        )

        def models_for(r: Row) -> SpeechModels:
            return shared

    report = evaluate(rows, Policy.load(args.policy), models_for)
    print(json.dumps(report["summary"], indent=2))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if not args.no_save:
        run_id = db.save_eval_run(args.label or args.manifest.name, report["summary"], report["rows"], args.notes,
                                  datetime.now(timezone.utc).replace(tzinfo=None))
        print(f"saved Eval Run #{run_id}; see the Eval page")


if __name__ == "__main__":
    main()
