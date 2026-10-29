"""One-terminal Clone player for the live demo (replaces juggling two play_clip windows).

FOR THE DEMO / EVAL RUN ONLY, with the written consent of the person being cloned.

A human still drives every line — this just puts the fixed lines on number keys and does the
Whisper Phrase lookup in the same window, so there is one terminal, not two. It never joins the
Call or presses anything itself; the operator opens the Caller page, presses Call, and plays each
Clone line here as the Voice Agent asks for it.

    python demo_clone.py --manifest E:\\AVISHKAR\\tmp\\clone-bank\\kamlesh-hi\\manifest.csv \\
        --device "CABLE Input"

At the prompt:
    1            play the Request      ("add a payee")
    2            play "code nahi mila" (the Clone has no code, as an attacker would not)
    <phrase>     type the Whisper Phrase shown on the Caller screen; the closest whispered clip plays
    p <phrase>   preview a clip on the laptop speakers instead of the cable (hear it yourself first)
    q            quit

Everything is played into --device (the virtual cable the Caller page listens to). To HEAR the
Clone too, enable "Listen to this device" on CABLE Output in Windows Sound settings, or use `p`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clip_bank import fuzzy_lookup, read_manifest, resolve_device  # noqa: E402

# The fixed lines, by number. These phrases match the clips make_clone_bank.py voiced (normal variant).
FIXED = {
    "1": ("normal", "mujhe naya peyi add karna hai", "Request: add a payee"),
    "2": ("normal", "mujhe code nahi mila", '"code nahi mila" (no code)'),
}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", required=True, help="clip bank manifest.csv (make_clone_bank.py)")
    p.add_argument("--device", default="CABLE Input", help='output device for the Call (default "CABLE Input")')
    p.add_argument("--i-have-consent", action="store_true",
                   help="attest that the cloned person consented in writing (or the reference is synthetic)")
    args = p.parse_args()
    if not args.i_have_consent:
        sys.exit("Refusing to run without --i-have-consent (see attacker/README.md).")

    try:
        import sounddevice as sd
        import soundfile as sf
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Cannot load the audio backend: {exc}")

    rows = read_manifest(args.manifest)
    if not rows:
        sys.exit(f"empty or missing manifest: {args.manifest}")
    devices = list(sd.query_devices())
    cable = resolve_device(devices, args.device)
    if cable is None:
        print(f'!! "{args.device}" not found (VB-Cable installed? Windows rebooted?); using the default output.')

    def play(path: str, device) -> None:
        if not Path(path).is_file():
            print(f"  !! clip file missing: {path}")
            return
        data, rate = sf.read(path, dtype="float32")
        sd.play(data, rate, device=device)
        sd.wait()

    def clip_for(variant: str | None, query: str):
        hits = fuzzy_lookup(rows, query, variant=variant, n=1)
        return hits[0] if hits else None

    print(f"loaded {len(rows)} clip(s). Device: {args.device}.")
    print("  1 = Request (add a payee)   2 = code nahi mila   <phrase> = whisper   p <phrase> = preview   q = quit\n",
          flush=True)
    for line in sys.stdin:
        cmd = line.strip()
        if not cmd or cmd == "q":
            return
        preview = cmd.startswith("p ")
        if preview:
            cmd = cmd[2:].strip()
        out = None if preview else cable  # preview -> laptop speakers (default device)
        if cmd in FIXED:
            variant, phrase, label = FIXED[cmd]
            hit = clip_for(variant, phrase)
            if hit:
                print(f"  > {label}", flush=True)
                play(hit[1]["file"], out)
            else:
                print(f"  !! no clip for {label}")
            continue
        hit = clip_for("dsp-whisper", cmd)  # anything else: a whispered Whisper Phrase
        if not hit:
            print("  no clip matched")
            continue
        score, row = hit
        print(f"  > whisper {score:.2f}: {row['phrase']}", flush=True)
        play(row["file"], out)


if __name__ == "__main__":
    main()
