"""One-terminal Clone player for the live demo (replaces juggling two play_clip windows).

FOR THE DEMO / EVAL RUN ONLY, with the written consent of the person being cloned.

A human still drives every line — this just puts the fixed lines on number keys and does the
Whisper Phrase lookup in the same window, so there is one terminal, not two. It never joins the
Call or presses anything itself; the operator opens the Caller page, presses Call, and plays each
Clone line here as the Voice Agent asks for it.

    python demo_clone.py --manifest E:\\AVISHKAR\\tmp\\clone-bank\\kamlesh-hi\\manifest.csv \\
        --device "CABLE Input"

At the prompt:
    me           play the consented person's REAL voice (the reference recording) on the laptop speakers
    clone        play the Clone saying a showcase sentence on the laptop speakers (for the judges: me, then clone)
    1            play the Request      ("add a payee")                 into the Call
    2            play "code nahi mila" (the Clone has no code)          into the Call
    <phrase>     type the Whisper Phrase shown on the Caller screen; the closest whispered clip plays into the Call
    p <phrase>   play a Whisper Phrase clip on the laptop speakers instead (hear it yourself first)
    q            quit

1, 2 and phrases go into --device (the virtual cable the Caller page listens to). To HEAR the Clone
during the Call too, enable "Listen to this device" on CABLE Output in Windows Sound settings.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clip_bank import fuzzy_lookup, read_manifest, resolve_device  # noqa: E402

# The fixed lines, by number: exactly the text make_clone_bank.py voiced them from (normal variant, Devanagari).
FIXED = {
    "1": ("normal", "मुझे नया पेयी ऐड करना है", "Request: add a payee"),
    "2": ("normal", "मुझे कोड नहीं मिला", '"code nahi mila" (no code)'),
}
# What `clone` plays for the judges, on the speakers (voiced with make_clone_bank.py --variant normal).
SHOWCASE = "नमस्ते, मैं कमलेश बोल रहा हूँ। मुझे अपने खाते में एक नया पेयी जोड़ना है।"
REFERENCE = r"E:\AVISHKAR\tmp\consent\reference-hi.wav"
MIN_MATCH = 0.6  # a typed phrase must be at least this close to a clip's phrase to be played
# The bank's Whisper Phrases name the digit in Hindi (pratyaksh.phrases, speakable(.., "hi")); a typed "7"
# matched "aaj do baje dinner hai" for "aaj 7 baje dinner hai", so typed digits become those words first.
HI_DIGITS = ["shunya", "ek", "do", "teen", "chaar", "paanch", "chhah", "saat", "aath", "nau"]


def _digits_as_words(text: str) -> str:
    return " ".join(HI_DIGITS[int(w)] if w.isdigit() and len(w) == 1 else w for w in text.split())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", required=True, help="clip bank manifest.csv (make_clone_bank.py)")
    p.add_argument("--device", default="CABLE Input", help='output device for the Call (default "CABLE Input")')
    p.add_argument("--reference", default=REFERENCE, help="the consented real-voice recording `me` plays")
    p.add_argument("--i-have-consent", action="store_true",
                   help="attest that the cloned person consented in writing (or the reference is synthetic)")
    args = p.parse_args()
    if not args.i_have_consent:
        sys.exit("Refusing to run without --i-have-consent (see attacker/README.md).")
    # Hindi lines are printed; a Windows console's default code page cannot encode Devanagari.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

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

    print(f"loaded {len(rows)} clip(s). Call device: {args.device}.")
    print("  me = real voice (speakers)   clone = the Clone (speakers)\n"
          "  1 = Request   2 = code nahi mila   <phrase> = whisper   (into the Call)   p <phrase> = whisper on speakers"
          "   q = quit\n", flush=True)
    for line in sys.stdin:
        cmd = line.strip()
        if not cmd or cmd == "q":
            return
        if cmd == "me":
            print("  > the REAL voice: the consented reference recording", flush=True)
            play(args.reference, None)
            continue
        if cmd == "clone":
            hit = clip_for("normal", SHOWCASE)
            if hit and hit[0] >= 0.9:
                print(f"  > the CLONE (synthetic, made from the recording above): {hit[1]['phrase']}", flush=True)
                play(hit[1]["file"], None)
            else:
                print("  !! no showcase clip yet: voice SHOWCASE with make_clone_bank.py --variant normal")
            continue
        preview = cmd.startswith("p ")
        if preview:
            cmd = cmd[2:].strip()
        out = None if preview else cable  # preview -> laptop speakers (default device)
        if cmd in FIXED:
            variant, phrase, label = FIXED[cmd]
            hit = clip_for(variant, phrase)
            if hit and hit[0] >= 0.9:  # the exact line, never a near one
                print(f"  > {label}", flush=True)
                play(hit[1]["file"], out)
            else:
                print(f"  !! no clip for {label}")
            continue
        # anything else: a whispered Whisper Phrase. A typo must not send the wrong phrase into the Call.
        hits = fuzzy_lookup(rows, _digits_as_words(cmd), variant="dsp-whisper", n=3)
        if not hits or hits[0][0] < MIN_MATCH:
            near = ", ".join(f"{r['phrase']} ({s:.2f})" for s, r in hits)
            print(f"  !! not played: no close clip (needs {MIN_MATCH}). Nearest: {near}", flush=True)
            continue
        score, row = hits[0]
        print(f"  > whisper {score:.2f}: {row['phrase']}", flush=True)
        play(row["file"], out)


if __name__ == "__main__":
    main()
