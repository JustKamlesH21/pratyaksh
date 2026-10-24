"""Red-team backup: play pre-recorded Clone clips into the virtual microphone by number.

  python play_clip.py clips/*.wav --device "CABLE Input"

Press a clip's number and Enter to play it. Use this if live generation is too slow on stage.
"""

from __future__ import annotations

import argparse

import soundfile as sf


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("clips", nargs="+")
    p.add_argument("--device", default=None)
    args = p.parse_args()

    import sounddevice as sd

    for i, c in enumerate(args.clips, start=1):
        print(f"{i:2d}  {c}")
    while True:
        choice = input("clip # (q quits): ").strip()
        if choice in ("q", ""):
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(args.clips):
            print("no such clip")
            continue
        data, rate = sf.read(args.clips[int(choice) - 1], dtype="float32")
        sd.play(data, rate, device=args.device)
        sd.wait()


if __name__ == "__main__":
    main()
