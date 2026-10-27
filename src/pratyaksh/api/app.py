"""HTTP interface of the verifier. Thin: every route delegates to the Verifier or PromptVoice.

Run:  pratyaksh-api   (or: uvicorn pratyaksh.api.app:create_app --factory)
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response as HTTPResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field

from ..config import Settings
from ..domain import Audio, Outcome, Response
from ..signals import warm_up_dsp
from ..verification import CallNotFound, DeviceNotPaired, NotAllowed, UnknownCustomer
from .container import FIXED_PROMPTS, Container, build, llm_configured

log = logging.getLogger(__name__)


class StartCall(BaseModel):
    customer_id: str
    room: str = ""


class AppApproval(BaseModel):
    customer_id: str
    approve: bool


class Review(BaseModel):
    approve: bool
    reviewer: str = Field(default="bank-agent", max_length=64)


class ReceiptCheck(BaseModel):
    receipt: str = Field(max_length=8192)


class TokenRequest(BaseModel):
    customer_id: str
    identity: str | None = None  # defaults to the customer id


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or (container.settings if container else Settings())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        c = container or build(settings)
        app.state.c = c
        if not settings.console_key:
            log.warning("CONSOLE_KEY is empty: anyone on the network can decide Agent Reviews")
        if not settings.agent_key:
            log.warning("AGENT_KEY is empty: any laptop on the network can post Responses and forge Reply Latency")
        for cust in c.verifier.customers():
            log.info("Bank App pairing for %s: /bank?customer=%s&device=%s",
                     cust["name"], cust["id"], c.verifier.pairing(cust["id"]))
        if settings.warm_up_models:
            await asyncio.to_thread(warm_up_dsp)  # ~1 s, before serving: no Caller ever pays for it
            asyncio.get_running_loop().run_in_executor(None, _warm_up, c)  # models: slow, in the background
        yield

    app = FastAPI(title="Pratyaksh verifier", version="0.1.0", lifespan=lifespan)
    app.add_middleware(_BodyGuard, settings=settings)  # inside CORS, so its refusals carry CORS headers
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["*"], allow_headers=["*"]
    )

    @app.exception_handler(CallNotFound)
    async def _nf(_: Request, e: CallNotFound):
        return JSONResponse({"detail": f"call not found: {e}"}, status_code=404)

    @app.exception_handler(UnknownCustomer)
    async def _uc(_: Request, e: UnknownCustomer):
        return JSONResponse({"detail": f"unknown customer: {e}"}, status_code=404)

    @app.exception_handler(DeviceNotPaired)
    async def _dnp(_: Request, e: DeviceNotPaired):
        return JSONResponse({"detail": "this device is not paired with the Customer"}, status_code=403)

    @app.exception_handler(NotAllowed)
    async def _na(_: Request, e: NotAllowed):
        return JSONResponse({"detail": str(e)}, status_code=409)

    def c(request: Request) -> Container:
        return request.app.state.c

    def agent_only(request: Request, x_agent_key: str = Header(default="")) -> None:
        key = c(request).settings.agent_key
        if key and not _same(key, x_agent_key):
            raise HTTPException(401, "this endpoint is for the Voice Agent only")

    agent = [Depends(agent_only)]

    def console_only(request: Request, x_console_key: str = Header(default="")) -> None:
        key = c(request).settings.console_key
        if key and not _same(key, x_console_key):
            raise HTTPException(403, "wrong console key")

    # With CONSOLE_KEY set, what Callers said and each Customer's risk are for the bank's staff only.
    # Aggregates (/v1/status, /v1/stats), the Customer picker and receipt checking stay open.
    console = [Depends(console_only)]

    def console_key_set(request: Request) -> None:
        # The Demo hub hands out Registered Device tokens: never without a key (code review, Oct 28).
        if not c(request).settings.console_key:
            raise HTTPException(403, "set CONSOLE_KEY to use the Demo hub")

    demo = [Depends(console_key_set), Depends(console_only)]

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/v1/status")
    def status(request: Request):
        """Is this setup ready for a real Call? Read it before the demo: warnings say what to fix."""
        cont = c(request)
        s = cont.settings
        try:
            with cont.db.engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False
        llm = llm_configured(s)
        # Everything a real Call needs; the LLM is optional (keyword rules answer without it).
        ready = (db_ok and not cont.missing_triggers and cont.warm and s.speech_backend == "local"
                 and s.tts_backend == "parler" and bool(s.agent_key) and bool(s.console_key))
        warnings = [w for ok, w in [
            (db_ok, "The database is not reachable."),
            (not cont.missing_triggers, "Audit Trail triggers are missing: fix the grants named in the API log, then run pratyaksh-seed."),
            (bool(s.agent_key), "AGENT_KEY is empty: any laptop on the network can post Responses."),
            (bool(s.console_key), "CONSOLE_KEY is empty: anyone can decide Agent Reviews and fetch Verification Receipts."),
            (cont.warm or cont.warm_error is not None, "Models are still warming up: the first Call will be slow."),
            (cont.warm_error is None, f"A model failed to load ({cont.warm_error}): fix it and restart pratyaksh-api."),
            (s.speech_backend == "local", "Speech models are scripted: this is not a real Call setup."),
            (s.tts_backend == "parler", "The Voice Agent beeps instead of speaking (TTS_BACKEND=tone)."),
            (llm, "No LLM is configured: unusual questions get the fallback answer."),
            (not s.retain_audio, "RETAIN_AUDIO is on: Response audio is being kept (consented Eval recordings only)."),
        ] if not ok]
        return {
            "ready": ready,
            "database": {"ok": db_ok, "dialect": cont.db.engine.dialect.name, "audit_triggers": not cont.missing_triggers},
            "speech": {"backend": s.speech_backend, "whisper_model": s.whisper_model, "warm": cont.warm,
                       "error": cont.warm_error},
            "voice": s.tts_backend,
            "llm": {"configured": llm, "model": s.ollama_model if llm else None},
            "keys": {"agent": bool(s.agent_key), "console": bool(s.console_key),
                     "receipts": cont.verifier.receipt_key()["kid"]},
            "warnings": warnings,
        }

    @app.get("/v1/stats")
    def stats(request: Request):
        return c(request).verifier.stats()

    # -- Voice Agent ---------------------------------------------------------------

    @app.post("/v1/calls", dependencies=agent)
    def start_call(body: StartCall, request: Request):
        return c(request).verifier.start_call(body.customer_id, body.room).to_dict()

    @app.post("/v1/calls/{call_id}/responses", dependencies=agent)
    async def respond(
        call_id: str,
        request: Request,
        audio: UploadFile = File(..., description="WAV of the Caller's reply"),
        reply_latency_ms: int | None = Form(default=None, ge=0),
    ):
        cont = c(request)
        limit = int(cont.settings.max_upload_mb * 1024 * 1024)
        data = await audio.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"audio is larger than {cont.settings.max_upload_mb:g} MB")
        # Check the header before decoding: a WAV claiming a tiny sample rate would be resampled into
        # gigabytes. Decoding then runs off the event loop, so other requests are not held up.
        try:
            seconds, rate = Audio.wav_info(data) if data else (0.0, 16000)
        except Exception as e:
            raise HTTPException(422, f"audio must be WAV: {e}") from e
        if not 8000 <= rate <= 48000:
            raise HTTPException(422, f"audio sample rate must be 8-48 kHz, not {rate} Hz")
        if seconds > cont.settings.max_response_s:
            raise HTTPException(413, f"audio is longer than {cont.settings.max_response_s:g} s")
        try:
            clip = await asyncio.to_thread(Audio.from_wav, data) if data else Audio.silence()
        except Exception as e:
            raise HTTPException(422, f"audio must be WAV: {e}") from e
        if cont.settings.retain_audio:
            _keep(cont.settings.audio_dir, call_id, data)
        step = await asyncio.to_thread(cont.verifier.respond, call_id, Response(clip, reply_latency_ms))
        return step.to_dict()

    @app.get("/v1/calls/{call_id}/step", dependencies=agent)
    def current_step(call_id: str, request: Request):
        return c(request).verifier.current_step(call_id).to_dict()

    @app.post("/v1/calls/{call_id}/hangup", dependencies=agent)
    def hang_up(call_id: str, request: Request):
        c(request).verifier.hang_up(call_id)
        return {"ok": True}

    @app.get("/v1/voice", response_class=HTTPResponse, dependencies=agent)
    async def voice(request: Request, text: str = Query(..., max_length=600)):
        wav = await asyncio.to_thread(c(request).voice.render, text)
        return HTTPResponse(wav, media_type="audio/wav")

    # -- Bank App -------------------------------------------------------------------

    @app.get("/v1/customers")
    def customers(request: Request):
        return c(request).verifier.customers()

    @app.get("/v1/customers/{customer_id}/inbox")
    def inbox(customer_id: str, request: Request, x_device_token: str = Header(default="")):
        return c(request).verifier.inbox(customer_id, x_device_token)

    @app.post("/v1/customers/{customer_id}/alerts/dismiss")
    def dismiss_alerts(customer_id: str, request: Request, x_device_token: str = Header(default="")):
        return {"dismissed": c(request).verifier.dismiss_alerts(customer_id, x_device_token)}

    @app.post("/v1/calls/{call_id}/app-approval")
    def app_approval(call_id: str, body: AppApproval, request: Request, x_device_token: str = Header(default="")):
        return c(request).verifier.app_approval(call_id, body.customer_id, x_device_token, body.approve).to_dict()

    # -- Console --------------------------------------------------------------------

    @app.get("/v1/calls", dependencies=console)
    def list_calls(
        request: Request, limit: int = Query(50, ge=1, le=500), outcome: str | None = None,
        customer_id: str | None = None,
    ):
        if outcome and outcome != "in_progress" and outcome not in Outcome._value2member_map_:
            raise HTTPException(422, f"outcome must be in_progress or one of {sorted(Outcome._value2member_map_)}")
        return c(request).verifier.calls(limit, outcome=outcome, customer_id=customer_id)

    @app.get("/v1/customers/{customer_id}/risk", dependencies=console)
    def customer_risk(customer_id: str, request: Request):
        return c(request).verifier.customer_risk(customer_id)

    @app.get("/v1/calls/{call_id}", dependencies=console)
    def get_call(call_id: str, request: Request):
        return c(request).verifier.call(call_id)

    @app.get("/v1/calls/{call_id}/audit", dependencies=console)
    def audit_check(call_id: str, request: Request):
        return c(request).verifier.audit_check(call_id)

    @app.get("/v1/calls/{call_id}/transcript", dependencies=console)
    def transcript(call_id: str, request: Request, fmt: str = Query("json", alias="format", pattern="^(json|text)$")):
        v = c(request).verifier
        if fmt == "text":
            return HTTPResponse(
                v.transcript(call_id), media_type="text/plain; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="pratyaksh-call-{call_id[:8]}.txt"'},
            )
        return {"call_id": call_id, "lines": v.call(call_id)["transcript"]}

    # -- Core banking: Verification Receipts ----------------------------------------------

    @app.get("/v1/calls/{call_id}/receipt", dependencies=console)
    def receipt(call_id: str, request: Request):
        return c(request).verifier.receipt(call_id)

    @app.post("/v1/receipts/verify")
    def verify_receipt(body: ReceiptCheck, request: Request):
        return c(request).verifier.verify_receipt(body.receipt)

    @app.post("/v1/receipts/redeem", dependencies=console)
    def redeem_receipt(body: ReceiptCheck, request: Request):
        return c(request).verifier.redeem_receipt(body.receipt)

    @app.get("/v1/receipts/key")
    def receipt_key(request: Request):
        return {"keys": [c(request).verifier.receipt_key()]}

    @app.post("/v1/calls/{call_id}/review", dependencies=console)
    def review(call_id: str, body: Review, request: Request):
        return c(request).verifier.review(call_id, body.approve, body.reviewer)

    # -- Demo hub (the operator's laptop) --------------------------------------------------
    # One page for every demo Customer: their Bank App, Call state and Voice Pause. It hands out
    # pairing tokens, so it sits behind CONSOLE_KEY like every other staff read.

    @app.get("/v1/demo/customers", dependencies=demo)
    def demo_customers(request: Request):
        v = c(request).verifier
        hub = []
        for cust in v.customers():
            risk = v.customer_risk(cust["id"])
            hub.append({
                **cust,
                "device_token": v.pairing(cust["id"]),
                "voice_paused": risk["voice_pause"]["active"],
                "pause_minutes_left": risk["voice_pause"]["minutes_left"],
                "open_security_alerts": risk["open_security_alerts"],
            })
        return hub

    @app.post("/v1/demo/reset", dependencies=demo)
    def demo_reset(request: Request):
        """Between demo runs: dismiss every Security Alert (as each Registered Device would) and end
        Calls left open. Both only add Audit Trail events; nothing is deleted."""
        v = c(request).verifier
        dismissed = sum(v.dismiss_alerts(cust["id"], v.pairing(cust["id"])) for cust in v.customers())
        open_calls = v.calls(500, outcome="in_progress")
        for call in open_calls:
            v.hang_up(call["id"])
        return {"dismissed": dismissed, "ended": len(open_calls)}

    @app.websocket("/v1/events")
    async def events(ws: WebSocket):
        await ws.accept()
        cont: Container = ws.app.state.c
        if cont.settings.console_key:  # browsers cannot set headers on a WebSocket: the key is the first message
            try:
                hello = await asyncio.wait_for(ws.receive_json(), 5)
            except Exception:
                hello = None
            if not isinstance(hello, dict) or not _same(cont.settings.console_key, str(hello.get("key", ""))):
                await ws.close(code=4401, reason="wrong console key")
                return
        async with cont.events.subscribe() as queue:
            calls = await asyncio.to_thread(cont.verifier.calls, 30)
            await ws.send_json({"type": "snapshot", "calls": calls})

            async def forward():
                while True:
                    await ws.send_json(await queue.get())

            async def until_closed():
                while True:  # Consoles send nothing; this returns as soon as the socket closes
                    await ws.receive_text()

            tasks = [asyncio.create_task(forward()), asyncio.create_task(until_closed())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            except (WebSocketDisconnect, RuntimeError):
                pass
            finally:
                for t in tasks:
                    t.cancel()

    @app.get("/v1/eval-runs/latest")
    def latest_eval(request: Request):
        run = c(request).db.latest_eval_run()
        if run is None:
            raise HTTPException(404, "no Eval Run yet; run pratyaksh-eval")
        return run

    # -- Caller app -----------------------------------------------------------------

    @app.post("/v1/livekit/token")
    def livekit_token(body: TokenRequest, request: Request):
        from livekit import api as lk

        cont = c(request)
        cont.verifier.pairing(body.customer_id)  # raises UnknownCustomer
        room = f"call-{body.customer_id}-{uuid.uuid4().hex[:8]}"
        identity = body.identity or body.customer_id
        token = (
            lk.AccessToken(cont.settings.livekit_api_key, cont.settings.livekit_api_secret)
            .with_identity(identity)
            .with_name(identity)
            .with_metadata(body.customer_id)
            # can_update_own_metadata: the Caller app sends its microphone capture settings as an attribute
            .with_grants(lk.VideoGrants(
                room_join=True, room=room, can_publish=True, can_subscribe=True, can_update_own_metadata=True,
            ))
            .to_jwt()
        )
        return {"url": cont.settings.livekit_public_url or cont.settings.livekit_url, "token": token, "room": room}

    return app


def _same(expected: str, given: str) -> bool:
    """Constant-time key check that also works for non-ASCII input (compare_digest refuses such str)."""
    return hmac.compare_digest(expected.encode(), given.encode())


_JSON_CAP = 64 * 1024  # the largest JSON body any route takes (a receipt to verify) is about 1 KB


class _BodyGuard:
    """Refuses keyless uploads and oversized bodies before they are read. FastAPI parses (and spools to
    disk) a request body before route dependencies run, so the checks in the routes alone come too late."""

    def __init__(self, app, settings: Settings):
        self.app = app
        self.upload_cap = int(settings.max_upload_mb * 1024 * 1024) + 64 * 1024  # + multipart framing
        self.agent_key = settings.agent_key

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        upload = scope["path"].endswith("/responses")
        cap = self.upload_cap if upload else _JSON_CAP
        headers = dict(scope["headers"])
        given = headers.get(b"x-agent-key", b"")
        if upload and self.agent_key and not hmac.compare_digest(self.agent_key.encode(), given):
            return await _reply(send, 401, "this endpoint is for the Voice Agent only")
        length = headers.get(b"content-length", b"")
        if length.isdigit() and int(length) > cap:
            return await _reply(send, 413, f"request body is larger than {cap // 1024} KB")
        seen = 0

        async def capped():  # chunked uploads have no Content-Length: count what arrives
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > cap:
                    raise StarletteHTTPException(413, f"request body is larger than {cap // 1024} KB")
            return message

        await self.app(scope, capped, send)


async def _reply(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


def _warm_up(c: Container) -> None:
    try:
        warm_up_dsp()
        warm = getattr(c.speech, "warm_up", None)
        if warm:
            warm()
        c.voice.prewarm(FIXED_PROMPTS)
        c.warm = True
        log.info("models warm")
    except Exception as e:
        c.warm_error = f"{type(e).__name__}: {e}"
        log.exception("model warm-up failed; models will load on first use")


def _keep(audio_dir: str, call_id: str, data: bytes) -> None:
    folder = Path(audio_dir) / call_id
    folder.mkdir(parents=True, exist_ok=True)
    n = len(list(folder.glob("*.wav"))) + 1
    (folder / f"{n:02d}.wav").write_bytes(data)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = Settings()
    uvicorn.run("pratyaksh.api.app:create_app", factory=True, host=s.api_host, port=s.api_port)
