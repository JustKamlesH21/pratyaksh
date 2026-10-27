"""pratyaksh-eval: measure Catch Rate, False Reject Rate and Added Time.

  pratyaksh-eval export --label real  [--since 2026-10-29T10:00] [--channel cable] [--language kn]
  pratyaksh-eval export --label clone [--since ...] [--condition code_supplied]
  pratyaksh-eval run data/eval/manifest.csv [--label "venue mics"] [--policy tuned.yaml] [--speech scripted]
                     [--calibration data/eval/calibration/]   # warns if a speaker was also calibrated on
  pratyaksh-eval calibrate data/eval/calibration/ [--exclude noise] [--html calibration.html]

Recording: run the verifier with RETAIN_AUDIO=true (with consent), place Calls, then export.
Manifest columns (one row per Response):
  session_id, label (real|clone), request, kind (whisper_phrase|possession_code), audio,
  reply_latency_ms, expected (Whisper Phrase), code_match (true|false|blank), transcript (optional)
Optional columns (older manifests without them still work):
  condition   Clone Calls only: code_withheld | code_supplied (the attacker read the right Possession
              Code, so the voice Signals are measured on their own). Blank: code_supplied when any
              Possession Code row has code_match true, else code_withheld.
  channel     mic | cable (real Calls replayed through the virtual cable: a channel control). Blank: mic.
  language    e.g. en, hi, kn, mixed. Blank: unspecified.
  hearing_ms  how long the live Verifier took to hear the Response (export fills it in).
  speaker     who spoke, e.g. ravi; `run --calibration` warns when a speaker was also in calibration.
  class       calibrate only: overrides the class of the recording (whisper, normal, soft, clone ...).

Catch Rate and False Reject Rate are reported as x/n with a Wilson 95% confidence interval.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Callable

import yaml

from ..config import Settings
from ..domain import Audio, Challenge, ChallengeKind, Evidence, RequestKind, Response, Signals, Verdict
from ..policy import Policy
from ..signals import LocalSpeechModels, ScriptedSpeechModels, SignalExtractor, SpeechModels, warm_up_dsp
from ..verification.store import AuditEventRow, CallRow, Database
from .stats import format_rate, rate, spread

FIELDS = [
    "session_id", "label", "request", "kind", "audio", "reply_latency_ms", "expected", "code_match", "transcript",
    "condition", "channel", "language", "hearing_ms", "speaker",
]
PROMPT_SECONDS = 4.0  # rough time the Voice Agent spends saying each Challenge
CONDITIONS = ("code_withheld", "code_supplied")
CHANNELS = ("mic", "cable")


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
    condition: str = ""  # blank: inferred per Clone Call
    channel: str = ""  # blank: mic
    language: str = ""  # blank: unspecified
    hearing_ms: int | None = None  # live Verifier's hearing time, when exported
    klass: str = ""  # calibrate only
    speaker: str = ""  # blank: not labelled


def _choice(value: str | None, allowed: tuple[str, ...], name: str) -> str:
    v = (value or "").strip().lower()
    if v and v not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)} or blank, not {value!r}")
    return v


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
                    expected=r.get("expected", "") or "",
                    code_match={"true": True, "false": False}.get((r.get("code_match") or "").lower()),
                    transcript=r.get("transcript", "") or "",
                    condition=_choice(r.get("condition"), CONDITIONS, "condition"),
                    channel=_choice(r.get("channel"), CHANNELS, "channel"),
                    language=(r.get("language") or "").strip().lower(),
                    hearing_ms=int(float(r["hearing_ms"])) if r.get("hearing_ms") else None,
                    klass=(r.get("class") or "").strip().lower(),
                    speaker=(r.get("speaker") or "").strip().lower(),
                ))
            except (KeyError, ValueError) as e:
                raise SystemExit(f"{path}:{i}: {e}") from e
    return rows


# Factors a Clone BLOCK can be caught by, found in the Verdict's Reasons (Policy wording).
CAUGHT_BY = {
    "possession_code": ("code read out does not match", "no code was read out"),
    "whisper_score": ("was not whispered",),
    "task_match": ("phrase did not match",),
    "spoof_score": ("voice looks synthetic", "spoof model leans synthetic"),
    "reply_latency": ("slow reply",),
    "no_reply": ("no reply was heard",),
}


def caught_by(reasons: list[str]) -> list[str]:
    """The Signals the Reasons of a BLOCK name, in CAUGHT_BY order; ["other"] if none is named."""
    text = "\n".join(reasons)
    found = [factor for factor, phrases in CAUGHT_BY.items() if any(p in text for p in phrases)]
    return found or ["other"]


def _session_value(srows: list[Row], attr: str) -> str:
    values = {getattr(r, attr) for r in srows if getattr(r, attr)}
    if len(values) > 1:
        raise SystemExit(f"session {srows[0].session_id}: rows disagree on {attr}: {sorted(values)}")
    return values.pop() if values else ""


def evaluate(
    rows: list[Row],
    policy: Policy,
    models_for: Callable[[Row], SpeechModels],
    prompt_seconds: float = PROMPT_SECONDS,
    calibration_speakers: list[str] | None = None,
) -> dict:
    """Score every session with the same Signals and Policy code the live Verifier uses.

    calibration_speakers: who recorded the calibration set (None: not given). Eval Run speakers
    among them are reported in summary["speakers"]["overlap"].
    """
    sessions: OrderedDict[str, list[Row]] = OrderedDict()
    for r in rows:
        sessions.setdefault(r.session_id, []).append(r)

    warm_up_dsp()  # so the first Response's hearing time is not the one-off DSP compile
    results = []
    for sid, srows in sessions.items():
        evidence, added, hearing = [], 0.0, []
        for r in srows:
            audio = Audio.from_wav(r.audio.read_bytes())
            extractor = SignalExtractor(models_for(r))
            started = time.perf_counter()
            signals = extractor.extract(Challenge(r.kind, "", r.expected), Response(audio, r.reply_latency_ms),
                                        r.language if r.language in ("en", "hi", "kn") else None)
            hearing.append(round((time.perf_counter() - started) * 1000))
            if r.kind is ChallengeKind.POSSESSION_CODE:
                signals = Signals.from_dict({**signals.to_dict(), "code_match": r.code_match})
            evidence.append(Evidence(r.kind, signals))
            added += prompt_seconds + (r.reply_latency_ms or 0) / 1000 + audio.seconds
        d = policy.decide(evidence, step_ups_used=1)  # judge the recorded answers as final
        label = srows[0].label
        condition = None
        if label == "clone":
            condition = _session_value(srows, "condition") or (
                "code_supplied" if any(r.code_match for r in srows if r.kind is ChallengeKind.POSSESSION_CODE)
                else "code_withheld"
            )
        results.append({
            "session_id": sid,
            "label": label,
            "request": srows[0].request.value,
            "condition": condition,
            "channel": _session_value(srows, "channel") or "mic",
            "language": _session_value(srows, "language") or "unspecified",
            "speaker": _session_value(srows, "speaker") or None,
            "verdict": d.verdict.value,
            "liveness": None if d.liveness is None else round(d.liveness, 3),
            "added_seconds": round(added, 1),
            "hearing_ms": hearing,
            "live_hearing_ms": [r.hearing_ms for r in srows if r.hearing_ms is not None],
            "caught_by": caught_by(d.reasons) if label == "clone" and d.verdict is Verdict.BLOCK else [],
            "reasons": d.reasons,
        })
    summary = summarize(results)
    summary["speakers"] = speaker_check(results, calibration_speakers)
    return {"summary": summary, "rows": results}


def speaker_check(results: list[dict], calibration: list[str] | None) -> dict:
    """Eval Run speakers, calibration speakers (None: no calibration set given) and their overlap."""
    ours = sorted({r["speaker"] for r in results if r.get("speaker")})
    return {
        "eval": ours,
        "calibration": None if calibration is None else sorted(calibration),
        "overlap": sorted(set(ours) & set(calibration or [])),
        "unlabelled_calls": sum(1 for r in results if not r.get("speaker")),
    }


def speaker_warning(summary: dict) -> str | None:
    """A loud warning when an Eval Run speaker was also a calibration speaker."""
    sp = summary.get("speakers") or {}
    if not sp.get("overlap"):
        return None
    bar = "!" * 72
    return "\n".join([
        bar,
        f"WARNING: Eval Run speaker(s) also in the calibration set: {', '.join(sp['overlap'])}.",
        "The whisper threshold was tuned on their voices, so their Calls overstate the results.",
        "Drop their Calls or record other speakers before showing these numbers.",
        bar,
    ])


def _caught(rows: list[dict]) -> dict:
    return rate(sum(1 for r in rows if r["verdict"] == Verdict.BLOCK.value), len(rows))


def _rejected(rows: list[dict]) -> dict:
    return rate(sum(1 for r in rows if r["verdict"] != Verdict.PASS.value), len(rows))


def _by(results: list[dict], key: str) -> dict:
    out = {}
    for value in sorted({r[key] for r in results}):
        group = [r for r in results if r[key] == value]
        out[value] = {
            "false_reject": _rejected([r for r in group if r["label"] == "real"]),
            "catch": _caught([r for r in group if r["label"] == "clone"]),
        }
    return out


def summarize(results: list[dict]) -> dict:
    """Catch Rate, False Reject Rate (x/n with Wilson 95% CI), breakdowns, caught-by and latency."""
    real = [r for r in results if r["label"] == "real"]
    clone = [r for r in results if r["label"] == "clone"]
    blocked = [r for r in clone if r["verdict"] == Verdict.BLOCK.value]
    catch, false_reject = _caught(clone), _rejected(real)
    factors = Counter(f for r in blocked for f in r["caught_by"])
    only = Counter(r["caught_by"][0] for r in blocked if len(r["caught_by"]) == 1)
    live = [ms for r in results for ms in r.get("live_hearing_ms", [])]
    return {
        "calls": len(results),
        "real_calls": len(real),
        "clone_calls": len(clone),
        # Plain shares, kept for older readers of the Eval page.
        "catch_rate": catch["rate"],
        "false_reject_rate": false_reject["rate"],
        "avg_added_seconds_real": round(sum(r["added_seconds"] for r in real) / len(real), 1) if real else None,
        "catch": catch,
        "false_reject": false_reject,
        # Clone Calls that PASSed: the attacker got through (STEP-UP is neither caught nor passed).
        "clone_pass": rate(sum(1 for r in clone if r["verdict"] == Verdict.PASS.value), len(clone)),
        "by_condition": {c: _caught([r for r in clone if r["condition"] == c]) for c in CONDITIONS
                         if any(r["condition"] == c for r in clone)},
        "by_channel": _by(results, "channel"),
        "by_language": _by(results, "language"),
        "caught_by": dict(sorted(factors.items(), key=lambda kv: -kv[1])),
        "caught_by_only": dict(sorted(only.items(), key=lambda kv: -kv[1])),
        "added_seconds": {"real": spread([r["added_seconds"] for r in real]),
                          "clone": spread([r["added_seconds"] for r in clone])},
        "hearing_ms": spread([ms for r in results for ms in r["hearing_ms"]], digits=0),
        "live_hearing_ms": spread(live, digits=0) if live else None,
    }


def format_report(summary: dict) -> str:
    """The summary as text for the terminal."""
    s = summary
    lines = [
        f"Calls: {s['calls']} ({s['real_calls']} real, {s['clone_calls']} Clone)",
        f"Catch Rate:        {format_rate(s['catch'])}",
        f"False Reject Rate: {format_rate(s['false_reject'])}",
        f"Clone Calls PASSed: {format_rate(s['clone_pass'])}",
    ]
    if s["by_condition"]:
        lines.append("Catch Rate by condition:")
        lines += [f"  {c:<14} {format_rate(r)}" for c, r in s["by_condition"].items()]
    for key, title in (("by_channel", "channel"), ("by_language", "language")):
        if len(s[key]) > 1:
            lines.append(f"By {title}:")
            for v, g in s[key].items():
                lines.append(f"  {v:<14} False Reject {format_rate(g['false_reject'])} | Catch {format_rate(g['catch'])}")
    if s["caught_by"]:
        lines.append(f"Caught by ({s['catch']['k']} Clone BLOCKs; one Call can name several Signals):")
        for f, n in s["caught_by"].items():
            lines.append(f"  {f:<16} {n:>3}   (the only factor in {s['caught_by_only'].get(f, 0)})")
    a = s["added_seconds"]["real"]
    if a["n"]:
        lines.append(f"Added Time per real Call: median {a['median']} s, p95 {a['p95']} s, max {a['max']} s")
    h = s["hearing_ms"]
    if h["n"]:
        lines.append(f"Hearing time per Response (this Eval Run): median {h['median']:.0f} ms, "
                     f"p95 {h['p95']:.0f} ms, max {h['max']:.0f} ms over {h['n']}")
    lh = s.get("live_hearing_ms")
    if lh:
        lines.append(f"Hearing time per Response (live Calls): median {lh['median']:.0f} ms, "
                     f"p95 {lh['p95']:.0f} ms, max {lh['max']:.0f} ms over {lh['n']}")
    sp = s.get("speakers")
    if sp and (sp["eval"] or sp["calibration"] is not None):
        lines.append(f"Speakers: {', '.join(sp['eval']) or 'none labelled'}"
                     + (f" ({sp['unlabelled_calls']} Calls unlabelled)" if sp["unlabelled_calls"] else ""))
        if sp["calibration"] is not None:
            lines.append("Overlap with calibration speakers: " + (", ".join(sp["overlap"]) or "none"))
    return "\n".join(lines)


# -- export recorded Calls -------------------------------------------------------------

# Audit kinds written exactly once per posted Response (keeps recordings and events aligned).
_RESPONSE_EVENTS = {
    "caller_said", "challenge_repeated", "code_retry", "app_approval_asked", "response_scored", "processing_error",
    "response_ignored", "code_expired",
}


def _as_utc(text: str) -> datetime:
    """--since as naive UTC, like created_at. Without an offset it is the laptop's local time (IST at the venue)."""
    return datetime.fromisoformat(text).astimezone(timezone.utc).replace(tzinfo=None)


def export(
    db: Database, audio_dir: Path, label: str, since: datetime | None, out: Path,
    condition: str = "", channel: str = "", language: str = "", speaker: str = "",
) -> int:
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
                heard = (ev.data.get("timings_ms") or {}).get("total")
                new_rows.append({
                    "session_id": call.id, "label": label, "request": call.request, "kind": ev.data["kind"],
                    "audio": str(wav.resolve()), "reply_latency_ms": sig.get("reply_latency_ms") or "",
                    "expected": expected,
                    "code_match": "" if sig.get("code_match") is None else str(sig["code_match"]).lower(),
                    "transcript": sig.get("transcript", ""),
                    "condition": condition if label == "clone" else "", "channel": channel, "language": language,
                    "hearing_ms": "" if heard is None else round(heard), "speaker": speaker.strip().lower(),
                })
    header = FIELDS
    if out.exists() and out.stat().st_size:
        with out.open(newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), FIELDS)  # an older manifest keeps its columns
        dropped = {k for r in new_rows for k, v in r.items() if v not in ("", None) and k not in header}
        if dropped:
            print(f"note: {out} has no {', '.join(sorted(dropped))} column(s); add them to keep those values",
                  file=sys.stderr)
    write_header = not out.exists() or not out.stat().st_size
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerows(new_rows)
    return len(new_rows)


def _policy_whisper_min(path: str | None) -> float | None:
    """Read (never write) signals.whisper_score.min from the Policy file."""
    text = Path(path).read_text(encoding="utf-8") if path else \
        resources.files("pratyaksh").joinpath("policy.yaml").read_text(encoding="utf-8")
    try:
        return float(yaml.safe_load(text)["signals"]["whisper_score"]["min"])
    except (KeyError, TypeError, ValueError):
        return None


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
    pr.add_argument("--calibration", type=Path,
                    help="calibration folder or manifest: warn if any speaker of this Eval Run is in it")

    pe = sub.add_parser("export", help="turn recorded Calls into manifest rows")
    pe.add_argument("--label", choices=["real", "clone"], required=True)
    pe.add_argument("--since", type=_as_utc, help="local time unless it has an offset, e.g. 2026-10-31T10:00")
    pe.add_argument("--out", type=Path, default=Path("data/eval/manifest.csv"))
    pe.add_argument("--condition", choices=CONDITIONS, default="",
                    help="Clone Calls: was the right Possession Code supplied? (blank: inferred from Code Match)")
    pe.add_argument("--channel", choices=CHANNELS, default="", help="blank: mic")
    pe.add_argument("--language", default="", help="e.g. en, hi, kn, mixed")
    pe.add_argument("--speaker", default="", help="who spoke on these Calls, e.g. ravi")

    pc = sub.add_parser("calibrate", help="Whisper Score per class of recordings; suggests whisper_score.min")
    pc.add_argument("source", type=Path, help="folder with one subfolder of WAVs per class, or a manifest")
    pc.add_argument("--positive", default="whisper", help="the class that must pass as a whisper")
    pc.add_argument("--exclude", default="", help="comma-separated classes left out of the threshold, e.g. noise")
    pc.add_argument("--policy", default=settings.policy_path, help="read-only: shows how the current min does")
    pc.add_argument("--html", type=Path, help="dot plot page (default: calibration.html next to the source)")
    pc.add_argument("--json", type=Path, help="also write the full calibration report here")

    args = p.parse_args(argv)

    if args.cmd == "calibrate":
        from .calibrate import calibrate, format_calibration, render_html, samples_from

        if not args.source.exists():
            raise SystemExit(f"{args.source}: not found")
        report = calibrate(
            samples_from(args.source), positive=args.positive,
            exclude=tuple(c.strip() for c in args.exclude.split(",") if c.strip()),
            current_min=_policy_whisper_min(args.policy),
        )
        print(format_calibration(report))
        out = args.html or (args.source if args.source.is_dir() else args.source.parent) / "calibration.html"
        out.write_text(render_html(report), encoding="utf-8")
        print(f"dot plot: {out}")
        if args.json:
            args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return

    def database() -> Database:
        db = Database(settings.database_url)
        db.create_schema()
        return db

    if args.cmd == "export":
        n = export(database(), Path(settings.audio_dir), args.label, args.since, args.out,
                   args.condition, args.channel, args.language, args.speaker)
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

    cal_speakers = None
    if args.calibration:
        from .calibrate import calibration_speakers

        if not args.calibration.exists():
            raise SystemExit(f"{args.calibration}: not found")
        cal_speakers = calibration_speakers(args.calibration)
    report = evaluate(rows, Policy.load(args.policy), models_for, calibration_speakers=cal_speakers)
    print(format_report(report["summary"]))
    sp = report["summary"]["speakers"]
    warning = speaker_warning(report["summary"])
    if warning:
        print(warning, file=sys.stderr)
    elif cal_speakers is not None and (sp["unlabelled_calls"] or not cal_speakers):
        print(f"note: speaker check incomplete: {sp['unlabelled_calls']} Eval Run Calls without a speaker, "
              f"{len(cal_speakers)} labelled calibration speakers", file=sys.stderr)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if not args.no_save:
        run_id = database().save_eval_run(args.label or args.manifest.name, report["summary"], report["rows"], args.notes,
                                  datetime.now(timezone.utc).replace(tzinfo=None))
        print(f"saved Eval Run #{run_id}; see the Eval page")


if __name__ == "__main__":
    main()
