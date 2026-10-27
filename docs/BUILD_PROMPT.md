# Prompt for your AI coding agent

Paste this into Claude Code (or Cursor) from the repository root when you continue building.

---

You are working on **Pratyaksh**, our FET Aavishkar 2026 hackathon project (Team Omnitrons, problem #F1BBBA03 "Voice-clone consent verification protocol"). The finale is a 24-hour build on Oct 31 – Nov 1, 2026; pre-built code is allowed.

Before changing anything, read in this order:
1. `CONTEXT.md`: the domain vocabulary. Use these exact terms (Caller, Challenge, Whisper Phrase, Possession Code, Signal, Verdict, Reason, App Approval, Agent Review, Audit Trail, Eval Run) in code, comments, UI text and commit messages.
2. `docs/adr/`: decisions we already made. Do not re-open them unless I ask:
   - Verification state lives in the verifier; the LiveKit agent only moves audio.
   - The LLM never decides a Verdict.
   - No voice biometrics; Response audio is not kept.
   - MySQL with an insert-only Audit Trail.
   - Self-hosted LiveKit on the demo LAN.
   - A tamper-evident (hash-chained) Audit Trail and signed Verification Receipts.
3. `docs/PRD.md`: features (must / should / stretch), flows, interfaces, plan to the finale.
4. `README.md`: how to run everything.

Architecture rules:
- Keep modules **deep**: small interface, lots of behaviour behind it. The main modules are `Verifier` (`src/pratyaksh/verification/`), `SignalExtractor` (`signals.py`), `Policy` (`policy.py`), `PromptVoice` (`voice.py`) and the agent's `run_call` (`agent/call_loop.py`).
- Only add a seam (Protocol plus adapters) where two adapters exist today, such as production and test. Do not add pass-through layers.
- Tests go through module interfaces (`tests/`). A change to internals should not need a test change. Run `pytest` and `cd web && npm run build` before you say a task is done.
- Policy numbers (weights, thresholds, latency bounds) live in `policy.yaml` and are tuned from Eval Runs, never hard-coded.
- Python 3.11, FastAPI, SQLAlchemy 2, MySQL. Frontend is Vite + React + TypeScript + Tailwind 4. Do not add new frameworks without asking.

Where things stand (Oct 27): the MVP is code-complete (PRD M1–M13, S1–S12) and `main` was fast-forwarded to `claude/agent-handles-any-question`. 165 pytest tests pass (152 also on native MySQL 8.0.43; the Docker `mysql:8.4` image has not been run) and the web app builds. **Check 1 passed** on the GPU laptop (Windows 11, RTX 3060 Laptop 6 GB, ASUS Turbo mode): `/v1/status` says Ready with no warnings 75–95 s after `scripts\windows\start.ps1` (Whisper 7 s, spoof model 1.5 s, Parler 64 s; models load offline). Windows 11 runs hidden processes in efficiency mode: Parler took ~40 s a sentence instead of ~8 s until `scripts\windows\power.ps1` (called by `start.ps1`) switched that off. Measured with the real models: Whisper turbo fp16 0.45 s per 3 s clip; spoof model 0.04–0.14 s; Indic Parler-TTS in bf16 (fp32 spilled out of the 6 GB GPU at ~21 s a prompt) takes 6–7 s per sentence, so every line the Voice Agent can say, including all 1,344 Whisper Phrase prompts, is pre-rendered with `pratyaksh-voice-cache`: all 1,400 lines are cached for Mary (the default voice) and for Anu (the backup, `PARLER_DESCRIPTION` in `.env.example`), about 3.6 h per voice. `/v1/voice` serves a cached line in 7–19 ms; an unrecorded sentence still takes ~9.4 s, so new spoken text needs a `pratyaksh-voice-cache` run (it skips cached lines). VRAM with all three models: 5.7 of 6.0 GiB. `scripts/smoke_call.py` places a Call over HTTP with a synthetic (TTS) Caller: it is BLOCKed because it cannot whisper (whisper score 0.01–0.25 vs 0.60), the Security Alert shows and calling back is refused; Challenge Responses are heard in 0.53–0.67 s (Oct 27 morning rerun with every prompt cached: 0.56–0.74 s, Request included). Findings to act on: the spoof model scores Parler speech 0.0 (it does not catch Indic TTS; the Whisper Phrase does); a Hindi Request heard as "मुझे नया पाई आड़ करना है" misses the keyword rules and needs the LLM (2.0–2.5 s over the internet, unavailable offline). **Never run yet:** a real human Caller through the browser and LiveKit (checks 2 and 4), whispers on our mics, IndicF5 (gated: accept its terms), a phone on the LAN. The Hindi and Kannada answers need a native speaker's read.

What exists:
- Verification: Risk Tiers from `policy.yaml`; Whisper Phrase (1,344 equally likely); Possession Code (one retry; a correct code read after it expired gets one fresh code, then App Approval); Verdicts with Reasons; STEP-UP, App Approval, Agent Review. A failed Whisper Phrase never PASSes until a STEP-UP phrase after it is completed.
- Understanding: any utterance in English, Hindi or Kannada (`verification/interpreter.py`: keyword rules, then the LLM); LLM replies with numbers not in `knowledge.yaml`, outcome claims or asks for secrets are dropped (ADR-0002).
- Protection: Security Alert + Voice Pause after a BLOCK; Attack Wave (blocked Calls for 3 Customers in 15 min put Agent Review on every risky Request); insert-only, hash-chained Audit Trail; Ed25519 Verification Receipts, redeemed once (`POST /v1/receipts/redeem`); `AGENT_KEY` on agent endpoints, `CONSOLE_KEY` on Console reads and the events WebSocket; uploads refused before they are read; SQLite takes its write lock per transaction.
- Console: Transcript tab (both sides, language, Signals, hearing times, download), Customer risk strip, Attack Wave banner, `/v1/status` (says what to fix), `/v1/stats` (Added Time, hearing p50/p95).
- Web: landing page with live numbers, dark by default, fonts bundled for the offline venue.

Open work, the **hackathon-ready check**. It passes when all of these hold on the demo laptops, with no code changes during the run:
1. The Console strip says **Ready**: real models loaded, no warnings.
2. Genuine Callers PASS three times in a row, in English, Hindi and Kannada.
3. The IndicF5 Clone is BLOCKed three times in a row; the Bank App shows the Security Alert; calling straight back is refused (Voice Pause).
4. Hearing p95 ≤ 1.5 s and Added Time ≤ 20 s (PRD §11), read off the Console.
5. An Eval Run on real, consented recordings (at least 10 real and 10 Clone Calls) gives a Catch Rate and False Reject Rate we are happy to show.
6. The 5-minute demo script (PRD §13) runs end to end without a hitch.
7. The branch is merged into `main`.

Target: checks 1–5 by Oct 28, 6–7 by Oct 30. Policy numbers change only from measured data (Signals from our recordings or an Eval Run), with a test, after asking.

My machine: an NVIDIA GPU laptop with 6–8 GB VRAM runs MySQL, LiveKit, the verifier API and the agent. Other laptops run the web app.

Current task: **[describe the task here, e.g. "get the first real call working end to end on my GPU laptop and fix whatever breaks", or "tune whisper_score thresholds using the recordings in data/recordings"]**

Work in small steps. After each step, tell me what changed and how you verified it. Ask before any change that contradicts an ADR or the PRD.
