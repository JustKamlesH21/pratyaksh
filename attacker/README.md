# Red-team tools (attacker laptop)

These tools play a **Clone** of a teammate's voice into a Call so the demo can show Pratyaksh blocking it.

**Rules**
- Clone only a teammate who has agreed in writing. Keep the signed note.
- Label every saved clip as synthetic. Never use these tools outside the demo.
- Run them on a **separate laptop** from the verifier, so the GPU there is not shared.

## Setup

```bash
cd attacker
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Install a virtual audio cable so the Clone's audio becomes the browser's microphone:

| OS | Tool | Output device to use | Browser microphone |
|---|---|---|---|
| Windows | VB-Audio Virtual Cable | `CABLE Input` | `CABLE Output` |
| macOS | BlackHole 2ch | `BlackHole 2ch` | `BlackHole 2ch` |
| Linux | `pactl load-module module-null-sink sink_name=clone` | `clone` | `Monitor of clone` |

Check device names with `python clone_speak.py --ref x --ref-text x --list`.

## Record the reference

Record the teammate reading one sentence for 8–12 seconds in a quiet room, saved as `teammate.wav`. Write down exactly what they said.

## Live attack (main demo)

1. Open the Caller app on this laptop, pick the **teammate's** Customer, and set the microphone to the cable.
2. Start the clone tool:
   ```bash
   python clone_speak.py --ref teammate.wav --ref-text "exact sentence" --device "CABLE Input" --i-have-consent
   ```
3. Press **Call**. Type replies as the Voice Agent asks: the Request ("I want to transfer six lakh"), then the Whisper Phrase. You will not know the Possession Code, because it goes to the real teammate's phone.

## Backup clips

Generate clips beforehand with `--save clips/`, then on stage:

```bash
python play_clip.py clips/*.wav --device "CABLE Input"
```
