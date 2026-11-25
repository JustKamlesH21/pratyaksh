<p align="center">
  <picture><source media="(max-width: 767px)" srcset="assets/readme/banner-m.png?v=secure"><img src="assets/readme/banner.svg?v=secure" width="100%" alt="Pratyaksh, runner-up at FET Aavishkar 2026: tells a bank whether the caller is a live person holding the customer's phone, or an AI voice clone."></picture>
</p>

<p align="center">
  <picture><source media="(max-width: 767px)" srcset="assets/readme/award-m.png?v=secure"><img src="assets/readme/award.svg?v=secure" width="100%" alt="Hackathon result: runner-up, 2nd place, at FET Aavishkar 2026. Team Omnitrons, Cybersecurity."></picture>
</p>

<p align="center"><b>Runner-up at FET Aavishkar 2026</b> · Team Omnitrons · Cybersecurity track<br>
Problem statement #F1BBBA03, "Voice-clone consent verification protocol" · demoed live at the 24-hour finale, 31 Oct to 1 Nov 2026</p>

A scammer needs about ten seconds of someone's voice to clone it. Then they call the bank as that person and ask for the things that move money: a new payee, a SIM swap, a big transfer. Voice ID lets the clone in, because it sounds exactly right.

Pratyaksh asks a different question: **is a live person holding the customer's registered phone on this call?** A Voice Agent sets random live Challenges (a whispered Kannada-Hindi-English phrase, and a one-time code that appears only in the customer's bank app), measures how each reply was spoken, and returns **PASS, STEP-UP or BLOCK** with reasons a bank officer can read. It never stores anyone's voice.

<p align="center"><a href="#same-voice-two-calls"><b>See two calls</b></a> · <a href="#how-a-call-works">How a call works</a> · <a href="#try-the-demo">Try the demo</a> · <a href="docs/SETUP.md">Setup guide</a> · <a href="docs/SECURITY.md">Security</a></p>

<p align="center">
  <picture><source media="(max-width: 767px)" srcset="assets/readme/glance-m.png?v=secure"><img src="assets/readme/glance.svg?v=secure" width="100%" alt="At a glance. Built: Oct - Nov 2026; Made for: FET Aavishkar 2026, Team Omnitrons; Stack: FastAPI · LiveKit · MySQL · React; Result: Runner-up, 2nd place"></picture>
</p>

## Same voice, two calls

<p align="center">
  <picture><source media="(max-width: 767px)" srcset="assets/readme/two-calls-m.png?v=secure"><img src="assets/readme/two-calls.svg?v=secure" width="100%" alt="Same voice, two calls. The real customer asks to add a payee, whispers the random phrase in 1.5 to 2.9 seconds and reads the code from the paired Bank App: PASS, and a signed Verification Receipt is issued. The voice clone says the right words (Task Match 0.92) but scores 0.01 to 0.25 on whispering where 0.60 is needed: BLOCK, a Security Alert on the real customer's phone, and repeat calls are paused."></picture>
</p>

Text-to-speech and voice-cloning models speak; they don't whisper on demand. In the team's first test runs a synthetic caller said the right words but scored 0.01-0.25 on whispering, against the 0.60 needed, and was blocked. A clone run through a whisper filter can fake the whisper, which is why the second Challenge is a code that only shows on the customer's own phone.

## Why it matters

- Indians lost about **₹22,846 crore to cyber fraud in 2024**, roughly three times 2023 (MHA reply in Parliament, I4C data, [PTI via The Week](https://www.theweek.in/wire-updates/business/2025/07/22/del23-lsq-cyber-fraud.html)).
- In McAfee's 2023 survey, **69% of Indian adults could not tell a cloned voice from a real one** ([BusinessWorld](https://businessworld.in/article/ai-voice-scams-more-prevalent-in-india-affects-almost-50-indians-mcafee-report-475192)).
- In 2023 a journalist **got into his own Lloyds Bank account by playing an AI clone of his voice** to its Voice ID ([IT Brew](https://www.itbrew.com/stories/2023/03/31/voice-generation-ai-blows-through-bank-s-voice-id-security)).

Who would buy it, how it plugs into a bank and why RBI's 2025 rules point this way: [business case](docs/BUSINESS.md).

## How a call works

<p align="center">
  <picture><source media="(max-width: 767px)" srcset="assets/readme/how-it-works-m.png?v=secure"><img src="assets/readme/how-it-works.svg?v=secure" width="100%" alt="One call: the caller is asked live Challenges by the Voice Agent, the speech model and a whisper score measure Signals, policy.yaml turns them into a Verdict with Reasons."></picture>
</p>

1. **Request.** The caller says what they want, in English, Hindi, Kannada or a mix. `policy.yaml` sets the Challenges: none for a balance check, two for a new payee, three for a SIM swap or a transfer over ₹5 lakh.
2. **Challenges.** The Voice Agent asks for a random Whisper Phrase (one of 1,344) and a six-digit Possession Code shown on the paired Bank App.
3. **Signals.** faster-whisper checks the words (Task Match), the audio is scored for whispering (Whisper Score), and the reply time is measured.
4. **Verdict.** Rules combine the Signals into PASS, STEP-UP (one more phrase, then app approval) or BLOCK, each with a plain-language Reason. An LLM helps understand off-script callers but never decides a Verdict.
5. **Record.** Every step goes on an insert-only, hash-chained Audit Trail, and a PASS comes with a signed, one-time Verification Receipt.

<p align="center">
  <picture><source media="(max-width: 767px)" srcset="assets/readme/proof-m.png?v=secure"><img src="assets/readme/proof.svg?v=secure" width="100%" alt="In numbers: 1,344 equally likely Whisper Phrases; clone Whisper Scores of 0.01 to 0.25 where 0.60 is needed; 64 of 66 recorded human whispers detected; under 20 seconds of added time is the target for a real caller."></picture>
</p>

## Built to be trusted

<p align="center">
  <picture><source media="(max-width: 767px)" srcset="assets/readme/trust-m.png?v=secure"><img src="assets/readme/trust.svg?v=secure" width="100%" alt="Built to be trusted. No voiceprint stored. The LLM never decides a Verdict. Tamper-evident, hash-chained audit trail. One-time signed receipts that core banking redeems once. A Security Alert and Voice Pause after every block. An Attack Wave alarm when 3 customers are blocked within 15 minutes."></picture>
</p>

The details are in [docs/SECURITY.md](docs/SECURITY.md) and the seven [decision records](docs/adr/).

## Architecture

<p align="center">
  <picture><source media="(max-width: 767px)" srcset="assets/readme/architecture-m.png?v=secure"><img src="assets/readme/architecture.svg?v=secure" width="100%" alt="Architecture. phones · frontend/: Caller app, Bank App, Console; LiveKit: Voice room, Voice Agent; verifier · FastAPI: Call state machine, Signals, Policy; data: MySQL 8, Voice cache"></picture>
</p>

Everything runs on one LAN for the demo: a GPU laptop hosts the speech models, LiveKit and the verifier API, and phones and laptops join through the browser. A bank would connect its phone lines by adding a SIP trunk to LiveKit; verification stays the same ([ADR-0005](docs/adr/0005-self-hosted-livekit-on-the-demo-lan.md)).

## Try the demo

With the stack running (see [Run it](#run-it)), open these screens:

| Screen | Who it's for |
|---|---|
| `/` landing page | Judges: a labelled simulation of a real customer and a clone, with live numbers from the verifier |
| `/console` | The bank's fraud team: live Signals, Verdicts, Reasons and transcripts |
| `/call` | The caller |
| `/bank` | The customer's paired phone, opened from the pairing link `pratyaksh-seed` prints |
| `/eval` | Eval Run results |

1. Caller app: pick *Ananya Rao*, press **Call**.
2. Say *"I want to add a new payee"*.
3. Whisper the phrase the Voice Agent asks for.
4. Read out the code shown on the paired Bank App. A misread code gets one retry.
5. Watch the Signals, Verdict and Reasons on the Console.

Demo customers: `cust-ananya`, `cust-rahul`, `cust-meera`.

Try going off-script too: ask "why should I whisper?" in the middle of a Challenge, say "hold on" or "code nahi aaya" while reading the code, ask "is this call genuine?" or "what is the transfer limit?", report "there's a transaction I didn't make", or say "let me talk to an officer". The agent answers to fit the moment and carries on; it never hangs up on a Caller it doesn't understand.

Answers come from `backend/src/pratyaksh/knowledge.yaml` (its header explains the keyword format; add an entry to teach the agent a new question). Anything the keywords miss goes to the LLM (`OLLAMA_API_KEY`, `OLLAMA_MODEL=gpt-oss:120b`), which is told where the Call is and uses the same answers as its facts.

## Run it

It needs a GPU laptop (NVIDIA, CUDA 12), Python 3.11+, Node 20+, MySQL 8 and a `livekit-server` binary. The full walkthrough, including a one-command start on Windows, is in **[docs/SETUP.md](docs/SETUP.md)**. What runs where:

| Process | Where | Command |
|---|---|---|
| MySQL 8 | GPU laptop | Docker (`infra/`) or a native install |
| LiveKit server | GPU laptop | `livekit-server` binary or Docker |
| Verifier API (models live here) | GPU laptop | `pratyaksh-api` |
| Voice Agent worker | GPU laptop | `pratyaksh-agent dev` |
| Web app | any laptop | `npm run dev` in `frontend/` |
| Clone tools | attacker laptop | `attacker/clone_speak.py` |

## Tests

```bash
cd backend && pytest       # Policy, Signals, whole Calls through the Verifier, HTTP API, call loop, Eval Runs
cd frontend && npm run build
```

The suite needs no GPU. It can also run against MySQL; see [docs/SETUP.md](docs/SETUP.md#tests).

## Project docs

| Doc | What's in it |
|---|---|
| [PRD](docs/PRD.md) | Goals for the finale, features and acceptance checks |
| [Business case](docs/BUSINESS.md) | The fraud problem, buyers, integration path and pricing ideas, with sources |
| [Vocabulary](CONTEXT.md) | What Caller, Challenge, Signal, Verdict and the rest mean here |
| [Decisions](docs/adr/) | Seven ADRs, from "no voice biometrics" to signed receipts |
| [Setup](docs/SETUP.md) | Installing and running every piece, plus gotchas |
| [Security](docs/SECURITY.md) | Keys, the audit trail, receipts, Voice Pause and Attack Wave |
| [Eval Runs](data/eval/README.md) | Recording consented calls and measuring Catch Rate |

## Team

Built by Team Omnitrons for FET Aavishkar 2026, led by [Kamlesh Choudhary](https://github.com/JustKamlesH21).

No license file has been added yet, so default copyright applies.

<p align="center">
  <a href="https://github.com/JustKamlesH21"><picture><source media="(max-width: 767px)" srcset="assets/readme/footer-m.png?v=secure"><img src="assets/readme/footer.svg?v=secure" width="100%" alt="Part of Kamlesh OS. More projects on github.com/JustKamlesH21"></picture></a>
</p>
