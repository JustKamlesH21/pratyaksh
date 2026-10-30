"""Calibrate the Whisper Score threshold from labelled recordings. Suggests; never writes policy.yaml.

    report = calibrate(samples_from(source), positive="whisper", exclude=("noise",), current_min=0.60)
    print(format_calibration(report)); Path("calibration.html").write_text(render_html(report))

A source is either a folder with one subfolder of WAVs per class (whisper/, normal/, soft/,
silence/, noise/, clone/ ...) or an exported Eval manifest. In a folder, WAVs one level further down
(whisper/kamlesh/1.wav) belong to that speaker; in a manifest the `speaker` column says. Speakers are
recorded so an Eval Run can check none of its speakers took part in calibration. In a manifest, real Whisper Phrase
Responses are "whisper", real Possession Code readouts (spoken aloud) are "normal" and Clone
Responses are "clone", unless a `class` column says otherwise.

Whisper Score is the pure-DSP Signal (share of unvoiced speech frames), so this runs on a CPU.
The Policy fails a Whisper Phrase when whisper_score < min, so a threshold t accepts score >= t.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from pathlib import Path

from ..domain import Audio, ChallengeKind
from ..signals import whisper_score
from .stats import rate, rule_of_three


@dataclass(frozen=True)
class Sample:
    cls: str
    file: str
    score: float | None  # None: no speech energy found (the Policy counts it as 0)
    speaker: str | None = None


def _recordings(source: Path) -> list[tuple[str, Path, str | None]]:
    """(class, wav, speaker) for every recording in a calibration folder or manifest."""
    if source.is_dir():
        found = []
        for sub in sorted(p for p in source.iterdir() if p.is_dir()):
            for wav in sorted(sub.rglob("*.wav")):
                parts = wav.relative_to(sub).parts
                found.append((sub.name, wav, parts[0].strip().lower() if len(parts) > 1 else None))
        if not found:
            raise SystemExit(f"{source}: no class subfolders with .wav files (e.g. whisper/, normal/, clone/)")
        return found
    from .run import read_manifest

    return [(_manifest_class(r), r.audio, r.speaker or None) for r in read_manifest(source)]


def calibration_speakers(source: Path) -> list[str]:
    """The labelled speakers of a calibration folder or manifest (no audio is decoded)."""
    return sorted({spk for _, _, spk in _recordings(source) if spk})


def samples_from(source: Path) -> list[Sample]:
    """Whisper Score of every WAV in a class-per-subfolder directory or an exported manifest."""
    return [
        Sample(cls, str(path), whisper_score(Audio.from_wav(Path(path).read_bytes())), spk)
        for cls, path, spk in _recordings(source)
    ]


def _manifest_class(row) -> str:
    if row.klass:
        return row.klass
    if row.label == "clone":
        return "clone"
    return "whisper" if row.kind is ChallengeKind.WHISPER_PHRASE else "normal"


def calibrate(
    samples: list[Sample],
    positive: str = "whisper",
    exclude: tuple[str, ...] = (),
    current_min: float | None = None,
) -> dict:
    """Per-class Whisper Score summary and a suggested threshold range.

    Every class other than `positive` and `exclude` is a negative (it must not pass as a whisper).
    The suggestion prefers zero false accepts: the threshold sits above the highest negative.
    """
    classes: dict[str, dict] = {}
    for cls in dict.fromkeys(s.cls for s in samples):
        scores = sorted(s.score for s in samples if s.cls == cls and s.score is not None)
        n = sum(1 for s in samples if s.cls == cls)
        classes[cls] = {
            "role": "positive" if cls == positive else "excluded" if cls in exclude else "negative",
            "n": n,
            "no_speech": n - len(scores),
            "min": scores[0] if scores else None,
            "median": _median(scores),
            "max": scores[-1] if scores else None,
        }
    pos = [s for s in samples if s.cls == positive]
    neg = [s for s in samples if classes[s.cls]["role"] == "negative"]
    val = lambda s: s.score if s.score is not None else 0.0  # noqa: E731  (as the Policy reads it)

    report: dict = {
        "positive": positive,
        "excluded": [c for c in exclude if c in classes],
        "classes": classes,
        "samples": [{"class": s.cls, "file": s.file, "score": s.score, "speaker": s.speaker} for s in samples],
        "speakers": sorted({s.speaker for s in samples if s.speaker}),
        "highest_negative": None,
        "lowest_positive": None,
        "gap": False,
        "suggested": None,
        "current": None,
        "notes": [],
    }
    if not pos or not neg:
        report["notes"].append(
            f"need both '{positive}' recordings and at least one negative class to suggest a threshold."
        )
    else:
        hi_neg = max(neg, key=val)
        lo_pos = min(pos, key=val)
        report["highest_negative"] = {"class": hi_neg.cls, "file": hi_neg.file, "score": val(hi_neg)}
        report["lowest_positive"] = {"class": lo_pos.cls, "file": lo_pos.file, "score": val(lo_pos)}
        report["gap"] = val(hi_neg) < val(lo_pos)
        if report["gap"]:
            t = _inside(val(hi_neg), val(lo_pos))
            report["suggested"] = {"low_exclusive": val(hi_neg), "high_inclusive": val(lo_pos), "threshold": t}
        else:
            t = _just_above(val(hi_neg))
            report["suggested"] = None if t is None else {"low_exclusive": val(hi_neg), "high_inclusive": None, "threshold": t}
            report["notes"].append(
                f"no clean gap: the highest negative ({hi_neg.cls}, {val(hi_neg):.3f}) is not below the lowest "
                f"{positive} ({val(lo_pos):.3f}); zero false accepts costs the false rejects shown."
            )
        if report["suggested"]:
            report["suggested"].update(_errors(pos, neg, report["suggested"]["threshold"], val))
    if current_min is not None and pos and neg:
        report["current"] = {"threshold": current_min, **_errors(pos, neg, current_min, val)}
    return report


def _errors(pos, neg, t: float, val) -> dict:
    fa = sum(1 for s in neg if val(s) >= t)
    fr = sum(1 for s in pos if val(s) < t)
    return {
        "false_accepts": rate(fa, len(neg)),
        "false_rejects": rate(fr, len(pos)),
        "false_accept_rule_of_three": rule_of_three(len(neg)) if fa == 0 else None,
        "false_reject_rule_of_three": rule_of_three(len(pos)) if fr == 0 else None,
    }


def _inside(lo: float, hi: float) -> float:
    """A round threshold t with lo < t <= hi, near the middle of the gap."""
    mid = (lo + hi) / 2
    for digits in (2, 3):
        t = round(mid, digits)
        if lo < t <= hi:
            return t
    return hi


def _just_above(lo: float) -> float | None:
    t = math.floor(lo * 100 + 1e-9) / 100 + 0.01
    return None if t > 1.0 + 1e-9 else round(t, 2)


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else round((xs[m - 1] + xs[m]) / 2, 3)


# -- output -------------------------------------------------------------------------------


def _f(v: float | None) -> str:
    return "-" if v is None else f"{v:.3f}"


def _rate_text(r: dict, bound: float | None) -> str:
    lo, hi = r["ci95"] if r["ci95"] else (None, None)
    text = f"{r['k']}/{r['n']}"
    if r["n"]:
        text += f" (Wilson 95% CI {lo:.2f}-{hi:.2f})"
    if bound is not None:
        text += f"; rule of three: below {bound:.0%} with 95% confidence"
    return text


def format_calibration(report: dict) -> str:
    lines = [f"Whisper Score by class (positive: {report['positive']})", ""]
    lines.append(f"{'class':<12}{'role':<10}{'n':>4}{'no speech':>11}{'min':>8}{'median':>8}{'max':>8}")
    for cls, c in report["classes"].items():
        lines.append(
            f"{cls:<12}{c['role']:<10}{c['n']:>4}{c['no_speech']:>11}{_f(c['min']):>8}{_f(c['median']):>8}{_f(c['max']):>8}"
        )
    lines.append("")
    lines.append("speakers: " + (", ".join(report.get("speakers") or []) or "none labelled (use class/<speaker>/*.wav)"))
    hn, lp = report["highest_negative"], report["lowest_positive"]
    if hn and lp:
        lines.append(f"highest negative: {hn['score']:.3f} ({hn['class']}, {Path(hn['file']).name})")
        lines.append(f"lowest {report['positive']}: {lp['score']:.3f} ({Path(lp['file']).name})")
    s = report["suggested"]
    if s:
        if report["gap"]:
            lines.append(
                f"suggested whisper_score.min: {s['threshold']:.2f}  (any value in "
                f"({s['low_exclusive']:.3f}, {s['high_inclusive']:.3f}] separates these recordings)"
            )
        else:
            lines.append(f"zero-false-accept whisper_score.min: {s['threshold']:.2f}")
        lines.append("  false accepts: " + _rate_text(s["false_accepts"], s["false_accept_rule_of_three"]))
        lines.append("  false rejects: " + _rate_text(s["false_rejects"], s["false_reject_rule_of_three"]))
    cur = report["current"]
    if cur:
        lines.append(f"current policy whisper_score.min: {cur['threshold']:.2f}")
        lines.append("  false accepts: " + _rate_text(cur["false_accepts"], cur["false_accept_rule_of_three"]))
        lines.append("  false rejects: " + _rate_text(cur["false_rejects"], cur["false_reject_rule_of_three"]))
    lines.extend(f"note: {n}" for n in report["notes"])
    lines.append("This only suggests a value: policy.yaml is not changed. Agree it with the team lead first.")
    return "\n".join(lines)


_W, _ROW, _LEFT, _RIGHT, _TOP = 760, 46, 110, 24, 44


def render_html(report: dict, title: str = "Whisper Score calibration") -> str:
    """A self-contained page (inline SVG and CSS, no scripts or CDN): one row of dots per class."""
    classes = list(report["classes"])
    plot_w = _W - _LEFT - _RIGHT
    h = _TOP + _ROW * len(classes) + 34
    x = lambda v: _LEFT + plot_w * min(1.0, max(0.0, v))  # noqa: E731
    parts: list[str] = []

    s, cur = report["suggested"], report["current"]
    if s and report["gap"]:
        x0, x1 = x(s["low_exclusive"]), x(s["high_inclusive"])
        parts.append(f'<rect class="band" x="{x0:.1f}" y="{_TOP - 8}" width="{max(1.0, x1 - x0):.1f}" '
                     f'height="{_ROW * len(classes) + 8}"><title>clean gap {s["low_exclusive"]:.3f} to '
                     f'{s["high_inclusive"]:.3f}</title></rect>')
    for tick in (0, 0.2, 0.4, 0.6, 0.8, 1.0):
        parts.append(f'<line class="grid" x1="{x(tick):.1f}" x2="{x(tick):.1f}" y1="{_TOP - 8}" '
                     f'y2="{_TOP + _ROW * len(classes)}"/>')
        parts.append(f'<text class="tick" x="{x(tick):.1f}" y="{h - 14}" text-anchor="middle">{tick:.1f}</text>')
    for i, cls in enumerate(classes):
        c = report["classes"][cls]
        cy = _TOP + _ROW * i + _ROW / 2
        parts.append(f'<text class="label" x="{_LEFT - 12}" y="{cy + 4:.1f}" text-anchor="end">{html.escape(cls)}</text>')
        pts = [smp for smp in report["samples"] if smp["class"] == cls]
        for j, smp in enumerate(pts):
            jitter = ((j * 7) % 9 - 4) * 2.4  # deterministic, so reruns draw the same picture
            v = smp["score"]
            cx = x(v if v is not None else 0.0)
            tip = f"{Path(smp['file']).name}: " + ("no speech (counted as 0)" if v is None else f"{v:.3f}")
            parts.append(f'<circle class="dot {c["role"]}{" none" if v is None else ""}" cx="{cx:.1f}" '
                         f'cy="{cy + jitter:.1f}" r="5"><title>{html.escape(tip)}</title></circle>')
    if cur:
        parts.append(f'<line class="policy" x1="{x(cur["threshold"]):.1f}" x2="{x(cur["threshold"]):.1f}" '
                     f'y1="{_TOP - 8}" y2="{_TOP + _ROW * len(classes)}"/>')
        parts.append(f'<text class="note" x="{x(cur["threshold"]) + 4:.1f}" y="{_TOP - 12}">policy now '
                     f'{cur["threshold"]:.2f}</text>')
    if s:
        parts.append(f'<line class="suggest" x1="{x(s["threshold"]):.1f}" x2="{x(s["threshold"]):.1f}" '
                     f'y1="{_TOP - 8}" y2="{_TOP + _ROW * len(classes)}"/>')
        parts.append(f'<text class="note strong" x="{x(s["threshold"]) - 4:.1f}" y="{_TOP - 28}" '
                     f'text-anchor="end">suggested {s["threshold"]:.2f}</text>')

    rows = "".join(
        f"<tr><td>{html.escape(cls)}</td><td>{c['role']}</td><td>{c['n']}</td><td>{c['no_speech']}</td>"
        f"<td>{_f(c['min'])}</td><td>{_f(c['median'])}</td><td>{_f(c['max'])}</td></tr>"
        for cls, c in report["classes"].items()
    )
    text = html.escape(format_calibration(report))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --bg:#fbfaf7; --ink:#1d1d1b; --soft:#5f5e58; --line:#dddbd3; --pos:#0f7b6c; --neg:#55534d;
  --band:#0f7b6c22; --policy:#b4531f; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16171a; --ink:#ecebe6; --soft:#a9a79f; --line:#34353a;
  --pos:#3fc1ac; --neg:#b9b7af; --band:#3fc1ac2a; --policy:#ee8a55; }} }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--ink);
  font:15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width:{_W}px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 4px; }} p {{ color:var(--soft); margin:0 0 16px; }}
.chart {{ overflow-x:auto; }} svg {{ display:block; width:100%; min-width:520px; height:auto; }}
.grid {{ stroke:var(--line); stroke-width:1; }} .tick, .note {{ fill:var(--soft); font-size:12px; }}
.label {{ fill:var(--ink); font-size:13px; }} .strong {{ fill:var(--ink); font-weight:600; }}
.band {{ fill:var(--band); }} .policy {{ stroke:var(--policy); stroke-width:2; stroke-dasharray:5 4; }}
.suggest {{ stroke:var(--ink); stroke-width:2; }}
.dot {{ stroke:var(--bg); stroke-width:2; }} .dot.positive {{ fill:var(--pos); }} .dot.negative {{ fill:var(--neg); }}
.dot.excluded {{ fill:none; stroke:var(--neg); stroke-width:1.5; }} .dot.none {{ fill:none; stroke:var(--policy); stroke-width:1.5; }}
table {{ border-collapse:collapse; width:100%; margin:20px 0; font-variant-numeric:tabular-nums; }}
th, td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); }} th {{ color:var(--soft); font-weight:600; }}
pre {{ white-space:pre-wrap; font-size:13px; background:transparent; border:1px solid var(--line); border-radius:8px; padding:12px; }}
</style></head>
<body><main>
<h1>{html.escape(title)}</h1>
<p>Whisper Score per recording (0 = fully voiced, 1 = no voicing). Filled teal: {html.escape(report['positive'])};
filled grey: must not pass as a whisper; hollow grey: excluded; hollow orange: no speech found (counted as 0).
Dashed line: current policy; solid line: suggested threshold; shaded: clean gap. Hover a dot for its file.</p>
<div class="chart"><svg viewBox="0 0 {_W} {h}" role="img" aria-label="Whisper Score dot plot by class">{''.join(parts)}</svg></div>
<table><thead><tr><th>class</th><th>role</th><th>n</th><th>no speech</th><th>min</th><th>median</th><th>max</th></tr></thead>
<tbody>{rows}</tbody></table>
<pre>{text}</pre>
</main></body></html>
"""
