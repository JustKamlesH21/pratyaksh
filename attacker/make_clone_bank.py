"""Red-team tool: build a Clone clip bank (a lookup table) for Whisper Phrases.

FOR THE DEMO AND THE EVAL RUN ONLY, with the written consent of the person being cloned.
For testing, clone a synthetic Parler voice sample (no real person), e.g.
E:\\AVISHKAR\\tmp\\voice-samples\\Divya_en.wav — then no teammate is cloned at all.

Given a reference WAV and its transcript, it voices every Whisper Phrase (speakable()
form) with IndicF5 and saves one WAV per phrase, plus a manifest CSV that play_clip.py
looks clips up in. Three variants:

  normal          IndicF5 output as-is.
  whispered-ref   IndicF5 output when --ref is itself a whispered recording.
  dsp-whisper     IndicF5 output run through the LPC noise-excitation whisperiser
                  (dsp_whisper.whisperise) — no whispered reference needed.

The run is resumable: a phrase+variant already in the manifest is skipped. Audio is
written under a scratch folder and is never committed.

  python make_clone_bank.py --ref voice.wav --ref-text "exact words" \\
      --variant dsp-whisper --limit 20 --i-have-consent

Each clip prints its generation time; that delay is what the Reply Latency Signal sees.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
import time
from pathlib import Path

import numpy as np

# Make backend/src/pratyaksh importable whether or not PYTHONPATH is set.
_SRC = Path(__file__).resolve().parent.parent / "backend" / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from clip_bank import ClipRow, VARIANTS, append_row, done_keys, read_manifest  # noqa: E402
from devanagari import to_devanagari  # noqa: E402
from dsp_whisper import whisperise  # noqa: E402

OUT_RATE = 24_000  # IndicF5 output sample rate
DEFAULT_OUT = Path(r"E:\AVISHKAR\tmp\clone-bank")


def load_phrases(phrases_file: str | None, limit: int | None) -> list[str]:
    """The phrases to voice: a user file (one per line), else every Whisper Phrase."""
    if phrases_file:
        lines = [ln.strip() for ln in Path(phrases_file).read_text(encoding="utf-8").splitlines()]
        phrases = [ln for ln in lines if ln]
    else:
        from pratyaksh.phrases import all_phrases, speakable

        phrases = [speakable(p) for p in all_phrases()]
    # De-duplicate but keep order (speakable() collapses many raw phrases onto one).
    phrases = list(dict.fromkeys(phrases))
    if limit is not None:
        phrases = phrases[:limit]
    return phrases


def _slug(text: str, idx: int) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]
    return f"{idx:04d}_{s or 'phrase'}"


def _to_float_mono(audio) -> np.ndarray:
    audio = np.asarray(audio)
    if audio.ndim > 1:
        audio = audio.reshape(-1)
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    return audio.astype(np.float32)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ref", required=True, help="reference WAV (consenting teammate, or a Parler sample)")
    p.add_argument("--ref-text", required=True, help="exact transcript of --ref")
    p.add_argument("--variant", choices=VARIANTS, default="normal")
    p.add_argument("--limit", type=int, default=None, help="voice only the first N phrases")
    p.add_argument("--phrases", default=None, help="file of phrases (one per line) instead of the Whisper Phrase bank")
    p.add_argument("--out", default=str(DEFAULT_OUT), help=f"output folder (default {DEFAULT_OUT})")
    p.add_argument("--device", choices=["cpu", "cuda"], default="cpu",
                   help="where IndicF5 runs; default cpu (the GPU is held by the live API)")
    p.add_argument("--i-have-consent", action="store_true",
                   help="confirm the cloned person agreed in writing (or the ref is a synthetic sample)")
    args = p.parse_args()

    if not args.i_have_consent:
        sys.exit("Refusing to run: clone only a consenting teammate (or a synthetic Parler sample), "
                 "then pass --i-have-consent.")
    if not Path(args.ref).is_file():
        sys.exit(f"--ref not found: {args.ref}")

    out_dir = Path(args.out)
    var_dir = out_dir / args.variant
    manifest = out_dir / "manifest.csv"
    phrases = load_phrases(args.phrases, args.limit)
    already = done_keys(read_manifest(manifest))
    todo = [ph for ph in phrases if (ph, args.variant) not in already]
    print(f"{len(phrases)} phrase(s); {len(todo)} to generate for variant '{args.variant}' "
          f"(skipping {len(phrases) - len(todo)} already done).", flush=True)
    if not todo:
        return

    # IndicF5's model.py picks its device internally: cuda if torch.cuda.is_available(),
    # else cpu — a later model.to("cpu") does not move it. To force CPU (the GPU is held
    # by the live API) we hide CUDA from torch *before* it is imported.
    import os
    if args.device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        # IndicF5 wraps the model in torch.compile; on Windows CPU that needs a C++ compiler
        # and adds memory pressure. Make it a no-op (eager) for a robust CPU run.
        os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

    import soundfile as sf
    from transformers import AutoModel

    print(f"loading IndicF5 on {args.device}…", flush=True)
    model = AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)
    try:
        model = model.to(args.device)
    except Exception as exc:  # the custom model manages its own device
        print(f"  (note: .to({args.device}) failed: {exc})", flush=True)
    print("ready.", flush=True)

    var_dir.mkdir(parents=True, exist_ok=True)
    base = len(already)
    for i, phrase in enumerate(todo, start=1):
        t0 = time.perf_counter()
        # The manifest keeps the Latin phrase (what the attacker hears and types); IndicF5 reads
        # Devanagari far better (Task Match 10/10 vs 0/10 on Oct 27).
        audio = model(to_devanagari(phrase), ref_audio_path=args.ref, ref_text=args.ref_text)
        audio = _to_float_mono(audio)
        if args.variant == "dsp-whisper":
            audio = whisperise(audio, OUT_RATE)
        gen = time.perf_counter() - t0
        secs = len(audio) / OUT_RATE
        fn = var_dir / f"{_slug(phrase, base + i)}.wav"
        sf.write(str(fn), audio, OUT_RATE)
        append_row(manifest, ClipRow(
            phrase=phrase, variant=args.variant, file=str(fn), seconds=secs,
            gen_seconds=gen, sample_rate=OUT_RATE,
            created=_dt.datetime.now().isoformat(timespec="seconds"),
        ))
        print(f"  [{i}/{len(todo)}] {secs:4.1f}s audio in {gen:5.1f}s  {phrase}", flush=True)

    print(f"done. manifest: {manifest}", flush=True)


if __name__ == "__main__":
    main()
