"""Red-team backup: play pre-recorded Clone clips into the virtual microphone.

Two ways to pick a clip:

  By number, from a list of files (the original behaviour):
      python play_clip.py clips/*.wav --device "CABLE Input"

  By phrase, fuzzy-matched against a clip bank's manifest (make_clone_bank.py):
      python play_clip.py --manifest E:\\AVISHKAR\\tmp\\clone-bank\\manifest.csv \\
          --device "CABLE Input" --variant dsp-whisper
  then type or paste a Whisper Phrase; the closest Clone clip is played.

Use this if live generation is too slow on stage. List output devices with --list-devices;
if the virtual cable (e.g. "CABLE Input") is not found — VB-Cable may not be installed, or
Windows not yet rebooted — it says so and falls back to the default device.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clip_bank import VARIANTS, fuzzy_lookup, read_manifest, resolve_device  # noqa: E402


def _play(path: str, device, sd, sf) -> None:
    data, rate = sf.read(path, dtype="float32")
    sd.play(data, rate, device=device)
    sd.wait()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("clips", nargs="*", help="WAV files to play by number (number mode)")
    p.add_argument("--manifest", help="clip bank manifest.csv (phrase mode)")
    p.add_argument("--variant", choices=VARIANTS, default=None,
                   help="in phrase mode, only match this Clone variant")
    p.add_argument("--device", default=None, help='output device name/substring or index, e.g. "CABLE Input"')
    p.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
    args = p.parse_args()

    try:
        import sounddevice as sd
    except Exception as exc:  # PortAudio / driver missing
        sys.exit(f"Cannot load the audio backend (sounddevice): {exc}\n"
                 "Install VB-Cable / PortAudio, or run on a machine with audio output.")
    import soundfile as sf

    devices = list(sd.query_devices())
    if args.list_devices:
        print(sd.query_devices())
        return

    device = resolve_device(devices, args.device)
    if args.device is not None and device is None:
        print(f'Output device matching "{args.device}" not found '
              "(VB-Cable may not be installed, or Windows not rebooted yet).")
        print("Falling back to the system default. Available output devices:")
        for i, d in enumerate(devices):
            if d.get("max_output_channels", 0) > 0:
                print(f"  {i:2d}  {d['name']}")

    if args.manifest:
        rows = read_manifest(args.manifest)
        if not rows:
            sys.exit(f"empty or missing manifest: {args.manifest}")
        print(f"loaded {len(rows)} clip(s). Type or paste a phrase; empty line quits.\n", flush=True)
        for line in sys.stdin:
            query = line.strip()
            if not query:
                return
            hits = fuzzy_lookup(rows, query, variant=args.variant, n=3)
            if not hits:
                print("  no clips to match against")
                continue
            score, row = hits[0]
            alt = "".join(f"\n       alt: {s:.2f} {r['phrase']}" for s, r in hits[1:])
            print(f"  match {score:.2f} [{row['variant']}] {row['phrase']}{alt}", flush=True)
            if not Path(row["file"]).is_file():
                print(f"  !! clip file missing: {row['file']}")
                continue
            _play(row["file"], device, sd, sf)
        return

    # Number mode.
    if not args.clips:
        sys.exit("give WAV files to play, or --manifest for phrase lookup (see --help).")
    for i, c in enumerate(args.clips, start=1):
        print(f"{i:2d}  {c}")
    while True:
        choice = input("clip # (q quits): ").strip()
        if choice in ("q", ""):
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(args.clips):
            print("no such clip")
            continue
        _play(args.clips[int(choice) - 1], device, sd, sf)


if __name__ == "__main__":
    main()
