"""Red-team the Whisper Phrase's whisper DSP (pratyaksh.signals.whisper_score). CPU only, no network.

Scores synthetic speech (the Clone side) under the conditions an attacker or a noisy hall creates:

  tts                 TTS clips as they are (normal, voiced synthetic speech)
  tts+white@SNR       TTS with white noise added (an attacker drowning voicing in hiss)
  whisperised         TTS run through LPC noise excitation: per frame, keep the vocal-tract filter,
                      replace the excitation with white noise of matched gain, overlap-add
  whisperised+babble@SNR  the above mixed with voiced babble (several other TTS clips summed);
                      stands in for a real whisper in a noisy hall, the false-reject side
  whisperised+talker@SNR  the above with one other voiced talker nearby (one TTS clip)
  noise:*             silence, white, pink and babble alone (no phrase at all)

Each condition can also go through a channel: none (16 kHz, so already band-limited to 8 kHz, like Opus
wideband speech), opus (a real Ogg/Opus round trip via libsndfile at 48 kHz) or nb (8 kHz telephone band).

    python backend/scripts/redteam_whisper.py --tts E:/AVISHKAR/pratyaksh/.cache/tts E:/AVISHKAR/tmp/voice-samples \
        --real whisper=E:/rec/whispers normal=E:/rec/normal \
        --out E:/AVISHKAR/tmp/redteam-whisper --clips 30 --channel none opus nb

--real folders are scored as they are (real:LABEL rows), so recorded Caller whispers line up with the attacks.
Every clip is trimmed of leading/trailing silence and cut to --max-seconds (a Response is a few seconds).

Writes scores.csv (one row per clip, condition and channel), summary.csv, and a few example WAVs to --out.
Never write outputs into the repository: they are audio.
"""

from __future__ import annotations

import argparse
import csv
import gc
import io
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

SR = 16_000
THRESHOLD = 0.60  # policy.yaml signals.whisper_score.min, for the "passes" column
DETAIL = ("dynamic_range_db", "flatness", "high_band_share")  # pratyaksh.signals.whisper_detail, logged only
BABBLE_TALKERS = 5
SNRS_BABBLE = (20, 10, 5, 0)
SNRS_WHITE = (30, 20, 10, 0)


# -- audio helpers --------------------------------------------------------------------------


def load(path: Path) -> np.ndarray:
    import librosa
    import soundfile as sf

    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    return y.astype(np.float32)


def rms(y: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(y, dtype=np.float64)) + 1e-20))


def active_rms(y: np.ndarray, frame: int = 400) -> float:
    """RMS over the louder half of 25 ms frames: speech level without the pauses."""
    n = len(y) // frame
    if n == 0:
        return rms(y)
    e = np.mean(np.square(y[: n * frame].reshape(n, frame), dtype=np.float64), axis=1)
    top = np.sort(e)[n // 2 :]
    return float(np.sqrt(top.mean() + 1e-20))


def at_level(y: np.ndarray, peak: float = 0.5) -> np.ndarray:
    m = float(np.abs(y).max())
    return (y * (peak / m)).astype(np.float32) if m > 0 else y.astype(np.float32)


def mix(target: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """target + noise scaled so active-speech power over noise power is snr_db."""
    noise = noise[: len(target)]
    gain = active_rms(target) / (rms(noise) * 10 ** (snr_db / 20))
    return at_level(target + gain * noise)


def white_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.standard_normal(n).astype(np.float32)


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec[1:] /= np.sqrt(f[1:])
    spec[0] = 0
    return np.fft.irfft(spec, n).astype(np.float32)


def babble(others: list[np.ndarray], n: int, rng: np.random.Generator) -> np.ndarray:
    """Sum of several talkers at equal level, each looped and started at a random offset."""
    out = np.zeros(n, dtype=np.float64)
    for y in others:
        y = y / (active_rms(y) + 1e-9)
        reps = int(np.ceil((n + len(y)) / len(y)))
        loop = np.tile(y, reps)
        start = int(rng.integers(0, len(y)))
        out += loop[start : start + n]
    return out.astype(np.float32)


def whisperise(y: np.ndarray, rng: np.random.Generator, order: int = 18, frame: int = 512, hop: int = 256) -> np.ndarray:
    """LPC noise-excitation whisperisation, the cheap DSP an attacker would try first.

    Per frame (pre-emphasised, Hann-windowed): fit an all-pole vocal-tract filter, drive it with white
    noise instead of the glottal pulses, scale to the frame's energy, overlap-add, de-emphasise.
    """
    import librosa
    from scipy.signal import get_window, lfilter

    x = lfilter([1.0, -0.97], [1.0], y.astype(np.float64))
    x = np.concatenate([np.zeros(frame), x, np.zeros(frame)])
    win = get_window("hann", frame, fftbins=True)  # periodic Hann: sums to 1 at hop = frame / 2
    out = np.zeros_like(x)
    warm = 4 * order
    for start in range(0, len(x) - frame + 1, hop):
        seg = x[start : start + frame] * win
        energy = rms(seg)
        if energy < 1e-6:
            continue
        seg = seg + 1e-9 * rng.standard_normal(frame)  # keeps LPC well-conditioned on digital silence
        a = librosa.lpc(seg, order=order)
        if not np.all(np.isfinite(a)):
            continue
        synth = lfilter([1.0], a, rng.standard_normal(frame + warm))[warm:]
        synth *= win
        synth *= energy / rms(synth)
        out[start : start + frame] += synth
    out = lfilter([1.0], [1.0, -0.97], out[frame:-frame])
    return at_level(out, peak=float(np.abs(y).max()) or 0.5)


# -- channels -------------------------------------------------------------------------------


def channel(y: np.ndarray, kind: str) -> np.ndarray:
    import librosa

    if kind == "none":
        return y  # already 16 kHz: band-limited to 8 kHz, as Opus wideband speech is
    if kind == "nb":  # telephone narrowband: 8 kHz sampling, 4 kHz band
        return librosa.resample(librosa.resample(y, orig_sr=SR, target_sr=8000), orig_sr=8000, target_sr=SR)
    if kind == "opus":
        import soundfile as sf

        y48 = librosa.resample(y, orig_sr=SR, target_sr=48_000)
        buf = io.BytesIO()
        with sf.SoundFile(buf, "w", 48_000, 1, format="OGG", subtype="OPUS", compression_level=0.7) as f:
            f.write(np.clip(y48, -1, 1))
        buf.seek(0)
        dec, sr = sf.read(buf, dtype="float32")
        return librosa.resample(dec, orig_sr=sr, target_sr=SR).astype(np.float32)
    raise ValueError(kind)


# -- the run --------------------------------------------------------------------------------


def score(y: np.ndarray) -> float | None:
    from pratyaksh.domain import Audio
    from pratyaksh.signals import whisper_score

    for attempt in range(4):  # a shared machine can run out of memory for a moment; that is not a result
        try:
            return whisper_score(Audio(np.ascontiguousarray(y, dtype=np.float32)))
        except MemoryError:
            if attempt == 3:
                raise
            gc.collect()
            time.sleep(3 * (attempt + 1))
    return None


def conditions(target: np.ndarray, others: list[np.ndarray], seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = len(target)
    target = at_level(target)
    wh = whisperise(target, rng)
    bab = babble(others, n, rng)
    out = {"tts": target}
    for snr in SNRS_WHITE:
        out[f"tts+white@{snr}dB"] = mix(target, white_noise(n, rng), snr)
    out["whisperised"] = wh
    for snr in SNRS_BABBLE:
        out[f"whisperised+babble@{snr}dB"] = mix(wh, bab, snr)
    talker = babble(others[:1], n, rng)
    for snr in SNRS_BABBLE:
        out[f"whisperised+talker@{snr}dB"] = mix(wh, talker, snr)
    out["noise:silence"] = np.zeros(n, dtype=np.float32)
    out["noise:white"] = 0.05 * white_noise(n, rng)
    out["noise:pink"] = at_level(pink_noise(n, rng), 0.2)
    out["noise:babble"] = at_level(bab, 0.3)
    return out


def trimmed(y: np.ndarray, max_seconds: float) -> np.ndarray:
    """Leading/trailing silence off, then at most max_seconds: a Response is a few seconds long."""
    import librosa

    yt, _ = librosa.effects.trim(y, top_db=35)
    return yt[: int(max_seconds * SR)]


def run_clip(job: dict) -> list[dict]:
    """One TTS clip under every condition, or one real recording (job["label"]) as it is."""
    target = trimmed(load(Path(job["path"])), job["max_seconds"])
    if job.get("label"):
        named = {f"real:{job['label']}": target}
    else:
        others = [load(Path(p)) for p in job["others"]]
        named = conditions(target, others, seed=job["idx"])
    rows = []
    for name, y in named.items():
        for ch in job["channels"]:
            z = channel(y, ch)
            t0 = time.perf_counter()
            s = score(z)
            ms = (time.perf_counter() - t0) * 1000
            from pratyaksh.domain import Audio
            from pratyaksh.signals import whisper_detail

            detail = whisper_detail(Audio(np.ascontiguousarray(z, dtype=np.float32))) or {}
            rows.append({"clip": Path(job["path"]).name, "condition": name, "channel": ch,
                         "seconds": round(len(z) / SR, 2), "whisper_score": "" if s is None else s, "ms": round(ms, 1),
                         **{k: detail.get(k, "") for k in DETAIL}})
            if job.get("save") and ch == job["channels"][0]:
                import soundfile as sf

                safe = name.replace(":", "_").replace("@", "_").replace("+", "_")
                sf.write(str(Path(job["save"]) / f"{job['idx']:03d}_{safe}_{ch}.wav"), np.clip(z, -1, 1), SR,
                         subtype="PCM_16")
    return rows


def summarise(rows: list[dict]) -> list[dict]:
    keys: dict[tuple[str, str], list[float | None]] = {}
    for r in rows:
        keys.setdefault((r["condition"], r["channel"]), []).append(r["whisper_score"] if r["whisper_score"] != "" else None)
    out = []
    for (cond, ch), vals in keys.items():
        got = np.array([v for v in vals if v is not None], dtype=float)
        out.append({
            "condition": cond, "channel": ch, "n": len(vals), "none": len(vals) - len(got),
            "mean": round(float(got.mean()), 3) if len(got) else "",
            "p10": round(float(np.percentile(got, 10)), 3) if len(got) else "",
            "median": round(float(np.median(got)), 3) if len(got) else "",
            "p90": round(float(np.percentile(got, 90)), 3) if len(got) else "",
            # None counts as 0 in the Policy, so it never passes.
            "passes_0.60": f"{int(np.sum(got >= THRESHOLD))}/{len(vals)}",
        })
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tts", nargs="*", default=[], help="folders of synthetic speech WAVs (read only)")
    ap.add_argument("--real", nargs="*", default=[], metavar="LABEL=DIR",
                    help="folders of real recordings to score as they are, e.g. whisper=E:/rec/whispers")
    ap.add_argument("--out", required=True, help="output folder (outside the repo)")
    ap.add_argument("--clips", type=int, default=30, help="TTS clips sampled across all --tts folders")
    ap.add_argument("--max-seconds", type=float, default=6.0, help="score at most this much of each clip")
    ap.add_argument("--channel", nargs="+", default=["none"], choices=["none", "opus", "nb"])
    ap.add_argument("--save-audio", type=int, default=3, help="write example WAVs for the first N TTS clips")
    ap.add_argument("--jobs", type=int, default=2, help="worker processes (each needs about 1 GB)")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    out = Path(args.out)
    repo = Path(__file__).resolve().parents[2]
    if (repo / ".git").exists() and repo in out.resolve().parents:
        ap.error("--out must be outside the repository: it holds audio")
    out.mkdir(parents=True, exist_ok=True)

    jobs: list[dict] = []
    common = {"channels": args.channel, "max_seconds": args.max_seconds}
    files = sorted(p for d in args.tts for p in Path(d).glob("*.wav"))
    if args.tts:
        if len(files) < BABBLE_TALKERS + 1:
            ap.error(f"need at least {BABBLE_TALKERS + 1} TTS WAVs, found {len(files)}")
        rng = random.Random(args.seed)
        for i, t in enumerate(rng.sample(files, min(args.clips, len(files)))):
            others = [str(o) for o in rng.sample([f for f in files if f != t], BABBLE_TALKERS)]
            jobs.append({**common, "idx": i, "path": str(t), "others": others,
                         "save": str(out) if i < args.save_audio else None})
    for spec in args.real:
        label, _, folder = spec.partition("=")
        if not folder:
            ap.error(f"--real wants LABEL=DIR, got {spec!r}")
        for j, f in enumerate(sorted(Path(folder).glob("*.wav"))):
            jobs.append({**common, "idx": 1000 + j, "path": str(f), "label": label})
    if not jobs:
        ap.error("nothing to score: give --tts and/or --real")

    t0 = time.perf_counter()
    rows: list[dict] = []
    fields = ["clip", "condition", "channel", "seconds", "whisper_score", "ms", *DETAIL]
    with open(out / "scores.csv", "w", newline="", encoding="utf-8") as f, \
            ProcessPoolExecutor(max_workers=args.jobs) as pool:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for done, fut in enumerate(as_completed([pool.submit(run_clip, j) for j in jobs]), start=1):
            got = fut.result()
            w.writerows(got)
            f.flush()  # a run cut short still leaves its rows
            rows.extend(got)
            print(f"  {done}/{len(jobs)} clips", file=sys.stderr, flush=True)
    took = time.perf_counter() - t0

    summary = summarise(rows)
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)

    cols = ["condition", "channel", "n", "none", "mean", "p10", "median", "p90", "passes_0.60"]
    widths = {c: max(len(c), *(len(str(r[c])) for r in summary)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in summary:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))
    secs = np.array([r["seconds"] for r in rows], dtype=float)
    ms = np.array([r["ms"] for r in rows], dtype=float)
    ok = secs > 0
    print(f"\n{len(jobs)} clips, {len(rows)} scores in {took:.0f} s with {args.jobs} workers; whisper_score "
          f"{np.median(ms[ok] / secs[ok]) * 3:.0f} ms per 3 s of audio (median, under parallel load). Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
