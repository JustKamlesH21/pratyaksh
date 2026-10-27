"""DSP whisperiser: turn ordinary (voiced) speech into a whisper by LPC noise excitation.

The idea: whispered speech has no vocal-fold buzz. Its spectral *shape* (the formants
set by the mouth and throat) is still there, but the source is turbulent noise, not a
periodic glottal pulse. So we estimate the short-time spectral envelope with frame-wise
LPC, throw away the original excitation, and re-excite the same all-pole filter with white
noise at a matched gain. Overlap-add puts the frames back together.

Used two ways:
  * as the `dsp-whisper` variant in make_clone_bank.py (whisperise an IndicF5 Clone), and
  * standalone on any WAV, e.g. the synthetic Parler voice samples:
        python dsp_whisper.py in.wav out.wav
        python dsp_whisper.py --indir samples/ --outdir out/        # batch *.wav

No network, no model, no GPU. Pure numpy + scipy + soundfile.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

# Frame geometry is defined in milliseconds so it is sample-rate independent.
WIN_MS = 25.0   # analysis frame length
HOP_FRAC = 0.5  # hop as a fraction of the window (0.5 => 50% overlap, Hann is COLA)


def _lpc(frame: np.ndarray, order: int) -> np.ndarray:
    """LPC coefficients A(z) = 1 + a1 z^-1 + ... for one frame, via Levinson-Durbin.

    Returns the array [1, a1, ..., a_order]. Computed from the windowed-frame
    autocorrelation, which is positive semi-definite, so 1/A(z) is minimum phase
    (stable) and safe to drive with noise.
    """
    n = len(frame)
    # Autocorrelation up to `order` lags.
    corr = np.correlate(frame, frame, mode="full")[n - 1:]
    r = corr[: order + 1].astype(np.float64)
    if r[0] <= 0.0:
        return np.concatenate(([1.0], np.zeros(order)))
    # Light lag-window / white-noise floor keeps the recursion well-conditioned.
    r[0] *= 1.0 + 1e-6
    a = np.zeros(order + 1)
    a[0] = 1.0
    err = r[0]
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1]) if i > 1 else r[i]
        k = -acc / err
        a_prev = a.copy()
        for j in range(1, i + 1):
            a[j] = a_prev[j] + k * a_prev[i - j]
        err *= 1.0 - k * k
        if err <= 0.0:
            break
    return a


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


def whisperise(audio: np.ndarray, sr: int, *, order: int | None = None,
               seed: int | None = 0) -> np.ndarray:
    """Return a whispered version of mono float `audio` at sample rate `sr`.

    Frame-wise LPC analysis, white-noise excitation of 1/A(z) with per-frame matched
    gain, Hann overlap-add, then a final utterance-level gain match to the input RMS.
    """
    from scipy.signal import lfilter

    audio = np.asarray(audio, dtype=np.float64).reshape(-1)
    if audio.size == 0:
        return audio.astype(np.float32)

    win = max(8, int(round(sr * WIN_MS / 1000.0)))
    hop = max(1, int(round(win * HOP_FRAC)))
    if order is None:
        order = int(sr / 1000) + 2  # ~ one pole per kHz plus a pair, classic for speech
    order = max(2, min(order, win - 1))

    window = np.hanning(win)
    rng = np.random.default_rng(seed)

    n_frames = 1 + max(0, (audio.size - win + hop - 1) // hop)
    out_len = (n_frames - 1) * hop + win
    out = np.zeros(out_len)
    norm = np.zeros(out_len)

    for f in range(n_frames):
        start = f * hop
        seg = audio[start:start + win]
        if seg.size < win:
            seg = np.pad(seg, (0, win - seg.size))
        wseg = seg * window
        target = _rms(wseg)
        if target <= 1e-7:  # silence: contribute nothing
            norm[start:start + win] += window * window
            continue
        a = _lpc(wseg, order)
        exc = rng.standard_normal(win)
        syn = lfilter([1.0], a, exc)
        scale = _rms(syn)
        syn = syn * (target / scale) if scale > 1e-12 else np.zeros(win)
        syn *= window
        out[start:start + win] += syn
        norm[start:start + win] += window * window

    nz = norm > 1e-9
    out[nz] /= norm[nz]
    out = out[: audio.size]

    # The per-frame matched gain above already carries the loudness contour (louder
    # phonemes stay louder). White-noise excitation has a high crest factor, so match
    # the overall level by peak-normalising to a safe headroom rather than by RMS — a
    # whisper is legitimately quieter than voiced speech, and forcing equal RMS would
    # drive the peaks into hard clipping.
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 1e-9:
        out *= 0.95 / peak
    return out.astype(np.float32)


def whisperise_file(src: Path, dst: Path, *, order: int | None = None,
                    seed: int | None = 0) -> None:
    """Whisperise one WAV file to another (mono; stereo is averaged to mono)."""
    import soundfile as sf

    data, sr = sf.read(str(src), dtype="float32", always_2d=False)
    if data.ndim == 2:
        data = data.mean(axis=1)
    out = whisperise(data, sr, order=order, seed=seed)
    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dst), out, sr)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src", nargs="?", help="input WAV")
    p.add_argument("dst", nargs="?", help="output WAV")
    p.add_argument("--indir", help="batch mode: whisperise every *.wav in this folder")
    p.add_argument("--outdir", help="batch mode: write the whispered WAVs here")
    p.add_argument("--order", type=int, default=None, help="LPC order (default ~ sr/kHz + 2)")
    p.add_argument("--seed", type=int, default=0, help="RNG seed for the noise excitation")
    args = p.parse_args()

    if args.indir:
        if not args.outdir:
            p.error("--indir needs --outdir")
        indir, outdir = Path(args.indir), Path(args.outdir)
        wavs = sorted(indir.glob("*.wav"))
        if not wavs:
            p.error(f"no *.wav in {indir}")
        for w in wavs:
            out = outdir / (w.stem + "_whisper.wav")
            whisperise_file(w, out, order=args.order, seed=args.seed)
            print(f"  {w.name} -> {out}")
        print(f"done: {len(wavs)} file(s)")
        return

    if not args.src or not args.dst:
        p.error("give SRC and DST, or --indir/--outdir")
    whisperise_file(Path(args.src), Path(args.dst), order=args.order, seed=args.seed)
    print(f"wrote {args.dst}")


if __name__ == "__main__":
    main()
