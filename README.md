# Pratyaksh

**Team Omnitrons · FET Aavishkar 2026 · Cybersecurity · #F1BBBA03 "Voice-clone consent verification protocol"**

Pratyaksh decides whether the person on a bank call is a **live human holding the customer's registered phone**, not an AI voice clone, without storing anyone's voice. The Voice Agent asks random live Challenges (a whispered Kannada-Hindi-English phrase, a one-time code from the bank app), measures Signals from each reply, and returns a Verdict (PASS, STEP-UP or BLOCK) with plain-language Reasons.

- Product plan, features, flows and the plan to the finale: [`docs/PRD.md`](docs/PRD.md)
- Domain vocabulary (use these words in code and in the pitch): [`CONTEXT.md`](CONTEXT.md)
- Decisions and why: [`docs/adr/`](docs/adr/)

## Repository map

```
src/pratyaksh/
  domain.py            value types (Step, Signals, Verdict…)
  policy.py + .yaml    Requests → Challenges, Signals → Verdict + Reasons
  knowledge.yaml       answers the Voice Agent may give to Questions (edit freely)
  signals.py           SignalExtractor + speech model adapters (faster-whisper, spoof classifier)
  language.py          Kannada/Devanagari/Latin folding, spoken digits
  phrases.py           Whisper Phrase bank
  verification/        Verifier: Call state machine, Interpreter (any utterance), Possession Codes,
                       Device Inbox, Audit Trail
  voice.py             PromptVoice: Indic Parler-TTS with a disk cache
  api/                 FastAPI verifier (HTTP + WebSocket)
  agent/               LiveKit Voice Agent worker (thin; ADR-0001)
  eval/                Eval Runs: export recordings, measure Catch Rate
web/                   Vite + React + TS: Console, Caller app, Bank App, Eval page
attacker/              red-team Clone tools (separate laptop, consent only)
infra/                 docker-compose for MySQL + LiveKit
tests/                 pytest, all through module interfaces
```

## How the pieces run

| Process | Where | Command |
|---|---|---|
| MySQL 8 | GPU laptop | Docker (`infra/`) or a native install |
| LiveKit server | GPU laptop | `livekit-server` binary or Docker |
| Verifier API (models live here) | GPU laptop | `pratyaksh-api` |
| Voice Agent worker | GPU laptop | `pratyaksh-agent dev` |
| Web app | any laptop | `npm run dev` in `web/` |
| Clone tools | attacker laptop | `attacker/clone_speak.py` |

## Setup on the GPU laptop

Prerequisites: Python 3.11+, Node 20+, an NVIDIA driver with CUDA 12, Git, and either Docker or MySQL 8.

### 1. Python

```bash
git clone https://github.com/JustKamlesH21/pratyaksh.git && cd pratyaksh
python -m venv .venv
source .venv/bin/activate                   # Windows: .venv\Scripts\activate
pip install -e ".[agent,dev]"               # API, agent, tests
pip install torch --index-url https://download.pytorch.org/whl/cu124   # CUDA build of torch first
pip install -e ".[ml]"                      # faster-whisper, transformers, parler-tts
cp .env.example .env                        # then edit LAN_IP, secrets, URLs
pytest                                      # should be all green without a GPU
```

Indic Parler-TTS is a gated model on Hugging Face: accept its terms on the model page, then `huggingface-cli login` once.

### 2. MySQL

Docker: `cd infra && docker compose --env-file ../.env up -d mysql`

Native install: create the database and user, then grant them:
```sql
CREATE DATABASE pratyaksh CHARACTER SET utf8mb4;
CREATE USER 'pratyaksh'@'%' IDENTIFIED BY 'pratyaksh-dev';
GRANT ALL PRIVILEGES ON pratyaksh.* TO 'pratyaksh'@'%';
SET PERSIST log_bin_trust_function_creators = 1;  -- lets the app add the Audit Trail triggers; survives restarts
```
Then `pratyaksh-seed` creates the tables, triggers and three demo Customers (the API also does this on start). If it cannot add the Audit Trail triggers it says why and exits with an error; fix the grant or setting it names and run it again. `pratyaksh-seed --reset` drops everything first: use it to clear demo data, or when the API says the database is older than the code.

### 3. LiveKit server

Download `livekit-server` for your OS from https://github.com/livekit/livekit/releases, then:
```bash
livekit-server --bind 0.0.0.0 --node-ip <LAN_IP> --keys "pratyaksh: <LIVEKIT_API_SECRET>"
```
On Linux you can use `docker compose --env-file ../.env up -d livekit` from `infra/` instead. Allow TCP 7880–7881 and UDP 50000–50200 through the firewall.

### 4. Verifier and Voice Agent

Two terminals, both with the venv active:
```bash
pratyaksh-api             # http://<LAN_IP>:8000/docs ; first start downloads and warms the models
pratyaksh-agent dev       # registers with LiveKit and waits for Calls
```

### 5. Web app

```bash
cd web
npm install
cp .env.example .env      # VITE_API_URL=http://<LAN_IP>:8000
npm run dev               # http://localhost:5173
```

Open:
- **Console** (projector): `http://localhost:5173/console`. Type `CONSOLE_KEY` into the Agent Review or Verification Receipt box when asked. The strip at the top says **Ready** only when the setup can take a real Call; its warnings say what to fix.
- **Caller app**: `http://localhost:5173/call`
- **Bank App** on the Customer's phone: the **pairing link** printed by `pratyaksh-seed` (and in the API log), opened as `http://<LAN_IP>:5173/bank?customer=…&device=…`. Without the link the Bank App shows nothing, which is the point: the attacker laptop can't read codes or approve requests.
- **Eval**: `http://localhost:5173/eval`

## First Call

1. Caller app: pick *Ananya Rao*, press **Call**.
2. Say *"I want to add a new payee"*.
3. Whisper the phrase the Voice Agent asks for.
4. Read out the code shown on the paired Bank App. A misread code gets one retry.
5. Watch the Signals, Verdict and Reasons on the Console.

Demo customers: `cust-ananya`, `cust-rahul`, `cust-meera`.

Try going off-script too: ask "why should I whisper?" in the middle of a Challenge, say "hold on" or "code nahi aaya" while reading the code, ask "is this call genuine?" or "what is the transfer limit?", report "there's a transaction I didn't make", or say "let me talk to an officer". The agent answers to fit the moment and carries on; it never hangs up on a Caller it doesn't understand.

Answers come from `src/pratyaksh/knowledge.yaml` (its header explains the keyword format; add an entry to teach the agent a new question). Anything the keywords miss goes to the LLM (`OLLAMA_API_KEY`, `OLLAMA_MODEL=gpt-oss:120b`), which is told where the Call is and uses the same answers as its facts.

## Security, in one place

- **Only the Voice Agent talks to the agent endpoints.** Set `AGENT_KEY` (and `CONSOLE_KEY`) in `.env`; the agent sends the key, so another laptop cannot post Responses with a forged Reply Latency.
- **Security Alert and Voice Pause.** Every BLOCK shows "Blocked call attempt" on the Customer's Bank App. Until they dismiss it there (or `protection.pause_minutes` in `policy.yaml` passes), risky Requests for that Customer are refused on voice, so an impostor cannot keep calling back. Dismiss the alert before re-running the demo.
- **Tamper-evident Audit Trail.** Events are insert-only (database triggers) and hash-chained; `GET /v1/calls/{id}/audit` and the Console badge show whether anything was edited or deleted.
- **Verification Receipts.** `GET /v1/calls/{id}/receipt` (console key) returns an Ed25519-signed JWT of a closed Call's result; `executable` says whether core banking may act. Check it with `POST /v1/receipts/verify` or any JWT library and `GET /v1/receipts/key`. The signing key is created in `data/keys/` on first start; keep it off git (it is ignored).
- **Attack Wave.** Blocked Calls for 3 different Customers within 15 minutes (`protection.wave_customers`, `wave_minutes`) look like a Clone campaign: until it passes, every risky Request also needs Agent Review and the Console shows a banner. Re-running the clone demo three times trips it; wait it out or set `wave_customers: 0`.
- **Transcripts.** Every line the Voice Agent says is an Audit Trail event too, so `GET /v1/calls/{id}/transcript?format=text` is a complete, tamper-evident record with the Audit head to match a Verification Receipt.
- **Guessing is bounded.** 1,344 equally likely Whisper Phrases; a code readout with more than 8 digits never matches; LLM replies that claim an outcome or ask for a PIN, OTP or password are dropped.

## Gotchas

- **Microphone needs a secure page.** Browsers allow the mic only on `https://` or `localhost`. Run the Caller app from `localhost` on each calling laptop (with `VITE_API_URL` pointing at the GPU laptop), or in Chrome add `http://<LAN_IP>:5173` under `chrome://flags/#unsafely-treat-insecure-origin-as-secure`. The Bank App needs no mic.
- **HTTP proxies break the agent's WebSocket** to LiveKit. Unset `HTTP_PROXY`/`HTTPS_PROXY` for the agent if you see `405 Invalid response status`.
- **Test whispers on day one.** If the agent treats a whisper as silence, lower `VAD_ACTIVATION` (try 0.25); if room noise triggers it, raise it.
- **Calibrate Reply Latency on the real setup.** The default 1200/3000 ms bounds in `policy.yaml` are a starting point; run an Eval Run with the finale mics and adjust.
- **Without a GPU** set `WHISPER_MODEL=small WHISPER_DEVICE=cpu WHISPER_COMPUTE_TYPE=int8 TTS_BACKEND=tone`. Calls work; the agent beeps instead of speaking.
- **The LLM is optional.** With no `OLLAMA_API_KEY`, unclear Requests get a scripted clarification. Set `OLLAMA_MODEL` to a model your Ollama account can run.

## Tests

```bash
pytest            # Policy, Signals, whole Calls through the Verifier, HTTP interface, call loop, Eval Runs
cd web && npm run build
```
The same suite runs on MySQL (tables in that database are dropped before each test, so use a spare one):
```bash
mysql -uroot -p -e "CREATE DATABASE pratyaksh_test CHARACTER SET utf8mb4; GRANT ALL PRIVILEGES ON pratyaksh_test.* TO 'pratyaksh'@'%';"
PRATYAKSH_TEST_DATABASE_URL=mysql+pymysql://pratyaksh:pratyaksh-dev@127.0.0.1:3306/pratyaksh_test pytest
```
The Voice Agent's LiveKit adapter was verified against a local `livekit-server` with a scripted caller; it is not part of `pytest` because it needs the server binary.

## Eval Runs

See [`data/eval/README.md`](data/eval/README.md): record consented real and Clone Calls with `RETAIN_AUDIO=true`, export them, run `pratyaksh-eval run`, read the Eval page, tune `policy.yaml`.
