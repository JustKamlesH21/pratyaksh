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

Where things stand (Oct 24): the verifier, Voice Agent, web apps, Eval Runs and red-team tools are written; 124 pytest tests pass (on SQLite and MySQL) and the web app builds; a scripted call ran end to end through a real LiveKit server. MySQL 8.0 (native install) ran the whole pytest suite and 7 parallel Calls with a live Console, Audit Trail triggers included; the Docker `mysql:8.4` image has not been run. Since then (PRD S4–S9): answers in English, Hindi and Kannada that fit the moment; Security Alert + Voice Pause after a BLOCK; hash-chained Audit Trail; signed Verification Receipts; `AGENT_KEY` on agent endpoints; 1,344 Whisper Phrases; `/v1/status` and `/v1/stats` on the Console. Performance: a Response is heard (speech models, LLM) outside any database transaction and applied under the row lock only if the Call did not change meanwhile (else `response_ignored`); the whisper DSP runs alongside speech-to-text and is compiled once before serving; Console reads are a constant number of queries. The web app was redesigned: neutral palette with one cobalt accent, dark mode, bundled Geist fonts, motion only under `prefers-reduced-motion: no-preference`, one chunk per page. The Hindi and Kannada answers need a native speaker's read. Never run yet: the real speech models (faster-whisper, the spoof classifier, Indic Parler-TTS) and IndicF5. The Voice Agent understands any utterance through `verification/interpreter.py` (keyword rules, then the Ollama LLM) and answers Questions from `src/pratyaksh/knowledge.yaml`.

Open work, in order:
1. On the GPU laptop: install the `ml` extra, run MySQL + LiveKit + API + agent, make one real call, fix what breaks.
2. Check that whispers are detected (tune `VAD_ACTIVATION`) and that `whisper_score` separates real whispers from normal speech on our mics.
3. Record consented real and Clone calls, run `pratyaksh-eval`, and tune `policy.yaml`.
4. Polish the Console for the projector and rehearse the demo in `docs/PRD.md` §13.

My machine: an NVIDIA GPU laptop with 6–8 GB VRAM runs MySQL, LiveKit, the verifier API and the agent. Other laptops run the web app.

Current task: **[describe the task here, e.g. "get the first real call working end to end on my GPU laptop and fix whatever breaks", or "tune whisper_score thresholds using the recordings in data/recordings"]**

Work in small steps. After each step, tell me what changed and how you verified it. Ask before any change that contradicts an ADR or the PRD.
