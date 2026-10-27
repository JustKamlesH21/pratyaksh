# Red-team tools (attacker laptop)

These tools generate and play a **Clone** of a consenting teammate's voice into a Call so
the demo and the **Eval Run** can show Pratyaksh blocking it. IndicF5 (`ai4bharat/IndicF5`)
is the voice model.

## Consent (read first — this is not optional)

- **Clone only a person who has given written, informed consent.** Keep the signed note: who
  is being cloned, for which demo/Eval Run, that recordings and generated clips are deleted
  by a stated **deletion date**, and that consent can be withdrawn at any time. This follows
  DPDP-style data handling: a lawful purpose, the minimum data needed, and deletion on the
  agreed date.
- For development and testing, **do not clone a real person at all** — use a synthetic Parler
  voice sample from `E:\AVISHKAR\tmp\voice-samples` (e.g. `Divya_en.wav`). No consent is
  needed to clone a voice that was never a person's.
- Every tool refuses to run without `--i-have-consent`. Passing it is your attestation that
  the written consent above exists (or that the reference is a synthetic sample).
- Label every saved clip as synthetic. Never use these tools outside the demo/Eval Run, and
  never commit audio (the repo `.gitignore` already excludes WAVs). Write clips under
  `E:\AVISHKAR\tmp\clone-bank`, and delete them by the consent's deletion date.

## Setup (Windows, Python 3.11)

The verified environment is **Python 3.11** in a venv **outside the repo** at
`E:\AVISHKAR\attacker-venv`, created with `uv`. (The old note said 3.10; 3.11 works —
IndicF5's `setup.py` is `python_requires>=3.7` — and it reuses the cached cu124 torch wheels.)
Do **not** install into the main project venv at `E:\AVISHKAR\pratyaksh\.venv`.

```bash
# uv caches and its managed Pythons live off the repo:
export UV_CACHE_DIR='E:\AVISHKAR\uv-cache'
export UV_PYTHON_INSTALL_DIR='E:\AVISHKAR\tools\uv-python'

uv venv E:\AVISHKAR\attacker-venv --python 3.11
PY=E:\AVISHKAR\attacker-venv\Scripts\python.exe

# torch first (cu124 wheels are cached), then the rest:
uv pip install --python "$PY" torch==2.6.0+cu124 torchaudio==2.6.0+cu124 \
    --index-url https://download.pytorch.org/whl/cu124
uv pip install --python "$PY" -r requirements.txt
```

Resolved versions on our box: torch 2.6.0+cu124, torchaudio 2.6.0+cu124, transformers 4.49.0,
numpy 1.26.4, scipy 1.17.1, f5_tts @ the pinned commit.

`ai4bharat/IndicF5` is gated on Hugging Face: open the model page, accept its terms, then
`hf auth login` once with a read token. The weights (~1.4 GB `model.safetensors`) and the
`charactr/vocos-mel-24khz` vocoder download into `HF_HOME=E:\AVISHKAR\hf-cache`.

IndicF5 is trained on 11 Indian languages, not English, and reads only Indic scripts: given
Latin "park alli four baje interview" it made 0.5 s of noise (Task Match 0/10, Oct 27), given
"पार्क अल्ली फोर बजे इंटरव्यू" it said the phrase clearly (10/10). `clone_speak.py` and
`make_clone_bank.py` therefore send every Whisper Phrase word in Devanagari (`devanagari.py`);
type the phrase in Latin as you hear it. Type a Request in Hindi or Kannada script.

### CPU vs GPU

Measured on the RTX 3060 (Oct 27): **~2.5 s per Whisper Phrase on the GPU, 1.5 GB VRAM peak**.
The live API holds ~5 GB of the 6 GB GPU, so the two do not fit together: run IndicF5 on a
second laptop, or build the clip bank on this one with the services stopped
(`scripts\windows\stop.ps1`, then `start.ps1` again). `--device cpu` works but needs several
GB of free RAM and is much slower.

### Virtual audio cable

Route the Clone's audio into the browser's microphone with a virtual cable:

| OS | Tool | Output device | Browser microphone |
|---|---|---|---|
| Windows | VB-Audio Virtual Cable | `CABLE Input` | `CABLE Output` |
| macOS | BlackHole 2ch | `BlackHole 2ch` | `BlackHole 2ch` |
| Linux | `pactl load-module module-null-sink sink_name=clone` | `clone` | `Monitor of clone` |

VB-Cable needs a **reboot** before `CABLE Input` appears. List devices with
`python play_clip.py --list-devices`; the players fall back to the default device (with a
warning) if the cable is not found yet.

## Tools

### `clone_speak.py` — live, type-to-speak

Synthesise typed text in the cloned voice and play it straight into the cable, live:

```bash
python clone_speak.py --ref teammate.wav --ref-text "exact sentence" \
    --device "CABLE Input" --i-have-consent
```

Each line prints how long generation took; that delay is what the Reply Latency Signal sees.

### `make_clone_bank.py` — a Clone lookup table for Whisper Phrases

Voice every Whisper Phrase (`speakable()` form) ahead of time into one WAV per phrase, plus a
manifest CSV. Resumable (a phrase+variant already in the manifest is skipped). Variants:

- `normal` — IndicF5 output as-is.
- `whispered-ref` — same, but `--ref` is a **whispered** recording of the consenting person.
- `dsp-whisper` — IndicF5 output run through the LPC noise-excitation whisperiser (no
  whispered reference needed).

```bash
# Testing with a synthetic sample (no real person cloned):
python make_clone_bank.py \
    --ref E:\AVISHKAR\tmp\voice-samples\Divya_en.wav \
    --ref-text "Sure, I can help you add a new payee. For your security I'll ask you two quick things." \
    --variant dsp-whisper --limit 20 --device cpu --i-have-consent
```

Output goes under `E:\AVISHKAR\tmp\clone-bank\<variant>\` with `manifest.csv` alongside
(columns: `phrase, variant, file, seconds, gen_seconds, sample_rate, created`).

### `dsp_whisper.py` — whisperiser, standalone

Frame-wise LPC analysis, white-noise excitation of the all-pole filter at a per-frame matched
gain, Hann overlap-add. Works on any WAV, no model or GPU:

```bash
python dsp_whisper.py in.wav out.wav
python dsp_whisper.py --indir E:\AVISHKAR\tmp\voice-samples --outdir E:\AVISHKAR\tmp\clone-bank\dsp-test
```

### `play_clip.py` — backup player (phrase lookup or by number)

Fuzzy-match a typed/pasted phrase against a clip bank and play the closest Clone clip:

```bash
python play_clip.py --manifest E:\AVISHKAR\tmp\clone-bank\manifest.csv \
    --device "CABLE Input" --variant dsp-whisper
```

Or play a list of files by number (the original mode):

```bash
python play_clip.py clips/*.wav --device "CABLE Input"
```

Playing needs only `soundfile` + `sounddevice`, so any laptop with the cable can run the
backup even without a GPU.

## Measured generation times

IndicF5 on **CPU** (RTX 3060 box, API running), reference `Divya_en.wav`:

- _Blocked on this box while the live API runs:_ the fp32 model is ~1.4 GB but only ~1.3 GB
  RAM and ~1 GB VRAM are free, so model load fails (segfault, or with the CPU fixes below
  `OSError: paging file is too small (os error 1455)`; a larger Windows pagefile may help). `make_clone_bank.py --device cpu` now
  hides CUDA and disables `torch.compile` so it genuinely runs on CPU; measure with a single
  clip once a few GB of RAM are free (e.g. the API paused, or on another machine), or on the
  GPU when `nvidia-smi` shows ≥2.5 GB free (`--device cuda`). The dependency stack, import
  chain and whisperiser are verified end-to-end; only the model forward pass awaits free
  memory.

## Tests

```bash
E:\AVISHKAR\attacker-venv\Scripts\python.exe -m pytest -q attacker/tests
```

Pure-Python helpers (`dsp_whisper.py`, `clip_bank.py`) are covered. These tests live under
`attacker/tests` and are **not** part of the main Pratyaksh suite (`testpaths = ["tests"]`).

## Live attack (main demo)

1. Open the Caller app on this laptop, pick the teammate's Customer, set the microphone to the
   cable.
2. Start `clone_speak.py` (live) or `play_clip.py` (backup bank).
3. Press **Call**. Give the Request, then the Whisper Phrase. You will not know the Possession
   Code — it goes to the real teammate's Registered Device.
