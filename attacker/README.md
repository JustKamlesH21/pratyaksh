# Red-team tools (attacker laptop)

These tools play a **Clone** of a teammate's voice into a Call so the demo can show Pratyaksh blocking it.

**Rules**
- Clone only a teammate who has agreed in writing. Keep the signed note.
- Label every saved clip as synthetic. Never use these tools outside the demo.
- Run them on a **separate laptop** from the verifier, so the GPU there is not shared.

## Setup

IndicF5 needs Python 3.10 and an NVIDIA GPU for live generation (the model is 1.4 GB; on a CPU each line takes far too long for a live Call).

```bash
cd attacker
py -3.10 -m venv .venv && .venv\Scripts\activate       # macOS/Linux: python3.10 -m venv .venv && source .venv/bin/activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

`ai4bharat/IndicF5` is gated on Hugging Face: open the model page, accept its terms (approval is automatic), then `hf auth login` once with a read token.

IndicF5 is trained on 11 Indian languages, not English. Type the Request in Hindi or Kannada for the most convincing Clone, and check how it says the English words in a Whisper Phrase before the demo.

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

Generate clips beforehand with `--save clips/` (this needs the GPU once). Playing them needs only `soundfile` and `sounddevice`, so any laptop with the virtual cable can run the backup, even without a GPU. On stage:

```bash
python play_clip.py clips/*.wav --device "CABLE Input"
```
