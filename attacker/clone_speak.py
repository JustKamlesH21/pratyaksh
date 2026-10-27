"""Red-team tool: speak typed text in a cloned voice, live, into a virtual microphone.

FOR THE DEMO ONLY, with the written consent of the person being cloned. Runs on a separate
"attacker" laptop. The Caller app on that laptop uses the virtual cable as its microphone.

  python clone_speak.py --ref teammate.wav --ref-text "exact words said in teammate.wav" \
      --device "CABLE Input" --i-have-consent

Type a line and press Enter: it is synthesised with IndicF5 and played into the call.
Each line prints how long generation took; that delay is what the Reply Latency Signal sees.
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from devanagari import to_devanagari

OUT_RATE = 24_000  # IndicF5 output sample rate


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ref", required=True, help="5-15 s WAV of the consenting teammate's voice")
    p.add_argument("--ref-text", required=True, help="exact transcript of --ref")
    p.add_argument("--device", default=None, help="output device name or index (the virtual cable); see --list")
    p.add_argument("--list", action="store_true", help="list audio devices and exit")
    p.add_argument("--save", default=None, help="folder to also save each clip as WAV")
    p.add_argument("--i-have-consent", action="store_true", help="confirm the cloned person agreed in writing")
    args = p.parse_args()

    import sounddevice as sd

    if args.list:
        print(sd.query_devices())
        return
    if not args.i_have_consent:
        sys.exit("Refusing to run: clone only a teammate who agreed in writing, then pass --i-have-consent.")

    from transformers import AutoModel

    print("loading IndicF5 (first run downloads the model)…", flush=True)
    model = AutoModel.from_pretrained("ai4bharat/IndicF5", trust_remote_code=True)
    print("ready. Type what the Clone should say; empty line or Ctrl-D quits.\n", flush=True)

    n = 0
    for line in sys.stdin:
        text = line.strip()
        if not text:
            break
        t0 = time.perf_counter()
        # Typed Whisper Phrase words go to IndicF5 in Devanagari: it reads Latin script as noise.
        audio = model(to_devanagari(text), ref_audio_path=args.ref, ref_text=args.ref_text)
        audio = np.asarray(audio)
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        took = time.perf_counter() - t0
        print(f"  generated {len(audio) / OUT_RATE:.1f}s of speech in {took:.1f}s", flush=True)
        if args.save:
            import soundfile as sf
            from pathlib import Path

            n += 1
            Path(args.save).mkdir(parents=True, exist_ok=True)
            sf.write(Path(args.save) / f"clone_{n:03d}.wav", audio, OUT_RATE)
        sd.play(audio.astype(np.float32), OUT_RATE, device=args.device)
        sd.wait()


if __name__ == "__main__":
    main()
