# Pratyaksh

**Team Omnitrons · FET Aavishkar 2026 · Cybersecurity · #F1BBBA03 "Voice-clone consent verification protocol"**

Pratyaksh decides whether the person on a bank call is a **live human holding the customer's registered phone**, not an AI voice clone, without storing anyone's voice. The Voice Agent asks random live Challenges (a whispered Kannada-Hindi-English phrase, a one-time code from the bank app), measures Signals from each reply, and returns a Verdict (PASS, STEP-UP or BLOCK) with plain-language Reasons.

- Product plan, features, flows and the plan to the finale: [`docs/PRD.md`](docs/PRD.md)
- Why banks would buy it, who else would, and the plan after the hackathon: [`docs/BUSINESS.md`](docs/BUSINESS.md)
- Domain vocabulary (use these words in code and in the pitch): [`CONTEXT.md`](CONTEXT.md)
- Decisions and why: [`docs/adr/`](docs/adr/)

## Repository map

```
backend/                 Python: the verifier API, the Voice Agent, Eval Runs
  pyproject.toml
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
  tests/                 pytest, all through module interfaces
  scripts/               LAN HTTPS certificate, smoke Call, whisper red-team
frontend/                Vite + React + TS: landing page, Console, Demo hub, Deepfake view, Caller app,
                         Bank App, Eval page
attacker/                red-team Clone tools (separate laptop, consent only)
infra/                   docker-compose for MySQL + LiveKit
scripts/windows/         start, stop and LAN-IP scripts for the GPU laptop
docs/                    PRD, ADRs, design system, business case
```

The services run from the repository root, which holds the git-ignored runtime state: `.venv`, `.env`, `.cache/` (voice cache, logs) and `data/` (keys, recordings).

## How the pieces run

| Process | Where | Command |
|---|---|---|
| MySQL 8 | GPU laptop | Docker (`infra/`) or a native install |
| LiveKit server | GPU laptop | `livekit-server` binary or Docker |
| Verifier API (models live here) | GPU laptop | `pratyaksh-api` |
| Voice Agent worker | GPU laptop | `pratyaksh-agent dev` |
| Web app | any laptop | `npm run dev` in `frontend/` |
| Clone tools | attacker laptop | `attacker/clone_speak.py` |

## Setup on the GPU laptop

Prerequisites: Python 3.11+, Node 20+, an NVIDIA driver with CUDA 12, Git, and either Docker or MySQL 8.

### 1. Python

```bash
git clone https://github.com/JustKamlesH21/pratyaksh.git && cd pratyaksh
python -m venv .venv
source .venv/bin/activate                   # Windows: .venv\Scripts\activate
pip install -e "backend[agent,dev]"         # API, agent, tests
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124   # CUDA builds first; a PyPI torchaudio crashes on import (WinError 127)
pip install -e "backend[ml]"                # faster-whisper, transformers, parler-tts
pip install -e "backend[agent]" "protobuf>=6.33.5,<8"   # [ml] downgrades protobuf and LiveKit; this puts the agent's versions back
cp .env.example .env                        # then edit LAN_IP, secrets, URLs
(cd backend && pytest)                      # should be all green without a GPU
```

The last line makes pip warn that `descript-audiotools` wants `protobuf<5`. That is safe to ignore: parler-tts needs audiotools only for its audio codec, and audiotools touches protobuf only through a tensorboard import used in training. LiveKit needs protobuf 5 or newer. The CUDA libraries faster-whisper needs (cuBLAS 12, cuDNN 9) ship inside the torch wheel, so no CUDA toolkit install is needed.

Indic Parler-TTS is a gated model on Hugging Face: accept its terms on the model page, then `hf auth login` once.

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

Once per machine, with the API stopped, voice everything the Voice Agent can say into the cache (`.cache/tts`), including the prompt for every one of the 1,344 Whisper Phrases:
```bash
pratyaksh-voice-cache     # ~3.6 h per voice with Parler on a laptop GPU (API stopped; unthrottle with power.ps1 -Match); cached lines are skipped
```
Parler takes about 6–7 s per sentence on an RTX 3060, so without this every Challenge prompt would add that to the Call. Speech is cached sentence by sentence, so a new lead-in in front of a cached prompt costs only the new sentence. Answers to Questions are voiced on first use and then cached.

The default voice is Mary; Anu is the backup (`PARLER_DESCRIPTION` in `.env.example`). Each voice has its own cache, so run `pratyaksh-voice-cache` once per voice you may switch to.

**Windows: one command for everything.** `scripts\windows\` starts and stops LiveKit, the API, the agent and the web app in the background, with logs in `.cache\run`:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1        # -Only api|agent|web|livekit; -Online on the very first start
powershell -ExecutionPolicy Bypass -File scripts\windows\stop.ps1
powershell -ExecutionPolicy Bypass -File scripts\windows\set-lan-ip.ps1   # new Wi-Fi or the venue hotspot: then stop + start
```
Set `LIVEKIT_SERVER` to the path of `livekit-server.exe` once. Models load offline from the Hugging Face cache, which matters on slow Wi-Fi. On the RTX 3060 laptop in Turbo mode, `/v1/status` says Ready 75–110 s after start: Whisper 7 s, spoof model 1.5 s, Parler 64 s.

### 5. Web app

```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_URL=http://<LAN_IP>:8000
npm run dev               # http://localhost:5173
```

Open:
- **Landing page** (open first for the judges): `http://localhost:5173/`. The hero plays a labelled simulation of a real Customer and a Clone; the numbers below it are live from the verifier. Dark by default; the header button switches to light or the system setting.
- **Console** (projector): `http://localhost:5173/console`. It asks for `CONSOLE_KEY` once per tab. The Transcript tab shows both sides of each Call with Signals and hearing times (Download .txt for a fraud case); the strip above each Call shows the Customer's risk and any Voice Pause. The strip at the top says **Ready** only when the setup can take a real Call; its warnings say what to fix.
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

Answers come from `backend/src/pratyaksh/knowledge.yaml` (its header explains the keyword format; add an entry to teach the agent a new question). Anything the keywords miss goes to the LLM (`OLLAMA_API_KEY`, `OLLAMA_MODEL=gpt-oss:120b`), which is told where the Call is and uses the same answers as its facts.

## Security, in one place

- **Only the Voice Agent talks to the agent endpoints.** Set `AGENT_KEY` (and `CONSOLE_KEY`) in `.env`; the agent sends the key, so another laptop cannot post Responses with a forged Reply Latency. A keyless or oversized upload is refused before a byte of it is read; WAV headers are checked (8–48 kHz, `MAX_RESPONSE_S`) before decoding, which runs off the event loop.
- **Console reads are for bank staff.** With `CONSOLE_KEY` set, Calls, Transcripts, the Audit Trail and Customer risk need the key (the Console asks once; the WebSocket takes it as its first message). `/v1/status`, `/v1/stats` and receipt checking stay open.
- **Security Alert and Voice Pause.** Every BLOCK shows "Blocked call attempt" on the Customer's Bank App. Until they dismiss it there (or `protection.pause_minutes` in `policy.yaml` passes), risky Requests for that Customer are refused on voice, so an impostor cannot keep calling back. Dismiss the alert before re-running the demo.
- **Tamper-evident Audit Trail.** Events are insert-only (database triggers) and hash-chained; `GET /v1/calls/{id}/audit` and the Console badge show whether anything was edited or deleted.
- **Verification Receipts.** `GET /v1/calls/{id}/receipt` (console key) returns an Ed25519-signed JWT of a closed Call's result; `executable` says whether core banking may act. Check it with `POST /v1/receipts/verify` or any JWT library and `GET /v1/receipts/key`. Before acting, core banking calls `POST /v1/receipts/redeem` (console key): it works once per Call and goes on the Audit Trail, so a receipt cannot be replayed. The signing key is created in `data/keys/` on first start; keep it off git (it is ignored).
- **Attack Wave.** Blocked Calls for 3 different Customers within 15 minutes (`protection.wave_customers`, `wave_minutes`) look like a Clone campaign: until it passes, every risky Request also needs Agent Review and the Console shows a banner. Re-running the clone demo three times trips it; wait it out or set `wave_customers: 0`.
- **Transcripts.** Every line the Voice Agent says is an Audit Trail event too, so `GET /v1/calls/{id}/transcript?format=text` is a complete, tamper-evident record with the Audit head to match a Verification Receipt.
- **Guessing is bounded.** 1,344 equally likely Whisper Phrases; a code readout with more than 8 digits never matches; LLM replies are dropped if they contain any number not in `knowledge.yaml` (1930 aside), claim an outcome ("has been added"), or ask for a PIN, OTP or password rather than warn about it.
- **Slow is not suspicious.** A correct Possession Code read after it expired gets a fresh code once, then App Approval; only a wrong code BLOCKs. A failed Whisper Phrase never PASSes until a STEP-UP phrase after it is completed.
- **One Outcome per Call.** On SQLite every transaction takes the write lock up front (`BEGIN IMMEDIATE`), on MySQL the row lock; Audit Trail sequence numbers are unique per Call.

## Gotchas

- **Microphone needs a secure page.** Browsers allow the mic only on `https://` or `localhost`. Run the Caller app from `localhost` on each calling laptop (with `VITE_API_URL` pointing at the GPU laptop), or in Chrome add `http://<LAN_IP>:5173` under `chrome://flags/#unsafely-treat-insecure-origin-as-secure`. The Bank App needs no mic.
- **HTTP proxies break the agent's WebSocket** to LiveKit. Unset `HTTP_PROXY`/`HTTPS_PROXY` for the agent if you see `405 Invalid response status`.
- **Test whispers on day one.** `VAD_ACTIVATION=0.15` caught 64 of 66 recorded human whispers (0.35 missed 11); if room noise triggers it, raise it a little.
- **Calibrate Reply Latency on the real setup.** The 2500/6000 ms bounds in `policy.yaml` come from real iPhone Calls (genuine whispers took 1.5–2.9 s); run an Eval Run with the finale mics and adjust.
- **Without a GPU** set `WHISPER_MODEL=small WHISPER_DEVICE=cpu WHISPER_COMPUTE_TYPE=int8 TTS_BACKEND=tone`. Calls work; the agent beeps instead of speaking.
- **The LLM is optional.** With no `OLLAMA_API_KEY`, unclear Requests get a scripted clarification. Set `OLLAMA_MODEL` to a model your Ollama account can run.

## Tests

```bash
cd backend && pytest     # Policy, Signals, whole Calls through the Verifier, HTTP interface, call loop, Eval Runs
cd frontend && npm run build
```
The same suite runs on MySQL (tables in that database are dropped before each test, so use a spare one):
```bash
mysql -uroot -p -e "CREATE DATABASE pratyaksh_test CHARACTER SET utf8mb4; GRANT ALL PRIVILEGES ON pratyaksh_test.* TO 'pratyaksh'@'%';"
cd backend && PRATYAKSH_TEST_DATABASE_URL=mysql+pymysql://pratyaksh:pratyaksh-dev@127.0.0.1:3306/pratyaksh_test pytest
```
The Voice Agent's LiveKit adapter was verified against a local `livekit-server` with a scripted caller; it is not part of `pytest` because it needs the server binary.

## Eval Runs

See [`data/eval/README.md`](data/eval/README.md): record consented real and Clone Calls with `RETAIN_AUDIO=true`, export them, run `pratyaksh-eval run`, read the Eval page, tune `policy.yaml`.
