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

Where things stand (Oct 28, 01:30; `main` = `claude/agent-handles-any-question` = `777a888`; 356 tests pass; ruff clean; web builds): **the software is feature-complete and the first real iPhone Calls work end to end; what remains is validation (Calls in all three languages, the live Clone, the Eval Run) and rehearsal.** Real-Call findings fixed on Oct 27: the ASUS "AI Noise-cancelling Input" sends silence and AirPods drop to 8–16 kHz (the Caller page shows a mic meter and warns); the phone played the agent's voice back into its mic, so the Caller page holds the mic while the agent is audible (250 ms hangover) and echo cancellation is off: Whisper Score 0.16 → **1.0**, Task Match 1.0; a right Possession Code is judged on being right, not timed (Kamlesh's OK); `spoof_score.mode: advisory` (the model flags 67/87 real whispers; Kamlesh's OK). Phones are Callers over HTTPS (`HTTPS=1`, local CA from `scripts/lan_https.py`, installed once per phone). Whisper Phrases come from one bank per Customer language (~350 each, digit in that language, Hindi/Kannada words in their own script for Mary's voice); all 1,272 spoken lines (fixed lines, every knowledge.yaml answer in en/hi/kn, every Whisper Phrase) are pre-rendered in Mary's voice, levelled to −14 dBFS; a slow (LLM) reply starts with "One moment, please."; the agent waits 12 s for a reply (20 s for a code) and a 1.2 s pause ends it. Red-team: DSP-whisperised TTS passes the Whisper Score (30/30), so the pitch is "the whisper proves a live person, the Possession Code proves identity". IndicF5 Clone tools work (~2.5 s/phrase on the GPU, 1.5 GB; not beside the running API; reads Devanagari via `attacker/devanagari.py`) but have **not yet been run into a live Call**. Design: Demo hub `/demo` (every Customer's live Bank App, Call state, Lift Voice Pause, phone links on LAN_IP; needs CONSOLE_KEY), iPhone call screen, landing page, stage mode `?stage=1` for the projector, OKLCH palette (all 72 colour pairs pass AA: `node web/scripts/contrast.mjs`), system documented in `docs/DESIGN.md`. Research reports (outside the repo, in the AVISHKAR folder's `reports/`): the Phase D to F plan and the demo design brief.

What exists:
- Verification: Risk Tiers from `policy.yaml`; Whisper Phrase (one bank per Customer language, ~350 each, equally likely); Possession Code (one retry; a correct code read after it expired gets one fresh code, then App Approval); Verdicts with Reasons; STEP-UP, App Approval, Agent Review. A failed Whisper Phrase never PASSes until a STEP-UP phrase after it is completed.
- Understanding: any utterance in English, Hindi or Kannada (`verification/interpreter.py`: keyword rules, then the LLM); LLM replies with numbers not in `knowledge.yaml`, outcome claims or asks for secrets are dropped (ADR-0002).
- Protection: Security Alert + Voice Pause after a BLOCK; Attack Wave (blocked Calls for 3 Customers in 15 min put Agent Review on every risky Request); insert-only, hash-chained Audit Trail; Ed25519 Verification Receipts, redeemed once (`POST /v1/receipts/redeem`); `AGENT_KEY` on agent endpoints, `CONSOLE_KEY` on Console reads and the events WebSocket; uploads refused before they are read; SQLite takes its write lock per transaction.
- Console: Transcript tab (both sides, language, Signals, hearing times, download), Customer risk strip, Attack Wave banner, `/v1/status` (says what to fix), `/v1/stats` (Added Time, hearing p50/p95).
- Web: Demo hub (`/demo`), iPhone call screen (`/call`, live captions of both sides, Whisper Phrase shown big, end screen), landing page, Console with stage view, Bank App (`/bank`), Eval page; dark by default, fonts bundled for the offline venue; design system in `docs/DESIGN.md`.

Open work, the **hackathon-ready check**. It passes when all of these hold on the demo laptops, with no code changes during the run:
1. ✅ The Console strip says **Ready**: real models loaded, no warnings (75–110 s after `start.ps1`).
2. ⏳ Genuine Callers PASS three times in a row, in English (Meera), Hindi (Rahul) and Kannada (Ananya). Whisper works on the iPhone (1.0); no PASS run yet.
3. ⏳ The IndicF5 Clone is BLOCKed three times in a row; the Bank App shows the Security Alert; calling straight back is refused (Voice Pause). Needs a consenting teammate's reference recording.
4. ⏳ Hearing p95 ≤ 1.5 s and Added Time ≤ 20 s (PRD §11), read off the Console. Hearing measured 0.45–0.75 s so far.
5. ⏳ An Eval Run on real, consented recordings (at least 10 real and 10 Clone Calls) gives a Catch Rate and False Reject Rate we are happy to show (tooling ready: Wilson intervals, "code supplied" condition, speaker check).
6. ⏳ The 5-minute demo script runs end to end without a hitch (choreography in the design brief: "Same voice, different Verdict").
7. ✅ The branch is merged into `main` (keep merging after each step).

Plan to the finale (Oct 31). Before every test Call: if the last Call was BLOCKed, lift the Voice Pause (Demo hub, or dismiss in that Customer's Bank App).
- **Oct 28:** check 2 from the iPhone (first confirm the greeting is heard, the Oct 28 audio fix), 3 PASSes per language; check 4 from the Console; Phase E: one whispered Call from the laptop Realtek mic and one from a second phone. Record the teammate's consented reference (written form + spoken statement in Hindi or Kannada).
- **Oct 29:** check 3: stop the services, build the Clone clip bank for that Customer (`attacker/make_clone_bank.py`, ~10 min), restart, play the Clone through VB-Cable ("CABLE Output" as the attacker's mic), 3× BLOCK, alert on the phone, call-back refused. Then check 5: `RETAIN_AUDIO=true` only while recording consented Eval Calls, export, `pratyaksh-eval run`.
- **Oct 30:** check 6: venue simulation on our own hotspot (`set-lan-ip.ps1`, restart, Ready), `/demo?stage=1` on a projector, five timed rehearsals with roles (narrator, Caller, attacker), backup video, then `pratyaksh-seed --reset` (also rotates the Bank App device tokens) and code freeze.
- **Oct 31:** no code changes; pre-flight, demo.
- Decisions open (Kamlesh): spoken numbered menu when a Request is not understood offline; QR code for the Bank App link (new package); Whisper "slow reply" threshold (kept at 1.2 s; revisit with check 2 timings); deleting the merged remote branch `claude/mysql-shakeout`. Native speakers to review the Hindi/Kannada texts. Ask the organisers: rubric, demo length, Q&A, projector/PA, Wi-Fi client isolation.
- Small code items left: Demo hub polls the database often; "One moment, please." is English only; brief should-dos 12, 15, 18 (call-status strip, pre-flight strip, Eval panel).

My machine: an NVIDIA GPU laptop with 6–8 GB VRAM runs MySQL, LiveKit, the verifier API and the agent. Other laptops run the web app.

Current task: **check 2: three PASSes in a row as Meera (en), Rahul (hi) and Ananya (kn) from the iPhone; read each Call's Signals from the Console and fix what breaks.**

Work in small steps. After each step, tell me what changed and how you verified it. Ask before any change that contradicts an ADR or the PRD.
