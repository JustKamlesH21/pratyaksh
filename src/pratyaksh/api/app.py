"""HTTP interface of the verifier. Thin: every route delegates to the Verifier or PromptVoice.

Run:  pratyaksh-api   (or: uvicorn pratyaksh.api.app:create_app --factory)
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response as HTTPResponse
from pydantic import BaseModel, Field

from ..config import Settings
from ..domain import Audio, Response
from ..verification import CallNotFound, DeviceNotPaired, NotAllowed, UnknownCustomer
from .container import FIXED_PROMPTS, Container, build

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
        for cust in c.verifier.customers():
            log.info("Bank App pairing for %s: /bank?customer=%s&device=%s",
                     cust["name"], cust["id"], c.verifier.pairing(cust["id"]))
        if settings.warm_up_models and settings.speech_backend == "local":
            asyncio.get_running_loop().run_in_executor(None, _warm_up, c)
        yield

    app = FastAPI(title="Pratyaksh verifier", version="0.1.0", lifespan=lifespan)
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

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    # -- Voice Agent ---------------------------------------------------------------

    @app.post("/v1/calls")
    def start_call(body: StartCall, request: Request):
        return c(request).verifier.start_call(body.customer_id, body.room).to_dict()

    @app.post("/v1/calls/{call_id}/responses")
    async def respond(
        call_id: str,
        request: Request,
        audio: UploadFile = File(..., description="WAV of the Caller's reply"),
        reply_latency_ms: int | None = Form(default=None),
    ):
        data = await audio.read()
        try:
            clip = Audio.from_wav(data) if data else Audio.silence()
        except Exception as e:
            raise HTTPException(422, f"audio must be WAV: {e}") from e
        cont = c(request)
        if cont.settings.retain_audio:
            _keep(cont.settings.audio_dir, call_id, data)
        step = await asyncio.to_thread(cont.verifier.respond, call_id, Response(clip, reply_latency_ms))
        return step.to_dict()

    @app.get("/v1/calls/{call_id}/step")
    def current_step(call_id: str, request: Request):
        return c(request).verifier.current_step(call_id).to_dict()

    @app.post("/v1/calls/{call_id}/hangup")
    def hang_up(call_id: str, request: Request):
        c(request).verifier.hang_up(call_id)
        return {"ok": True}

    @app.get("/v1/voice", response_class=HTTPResponse)
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

    @app.post("/v1/calls/{call_id}/app-approval")
    def app_approval(call_id: str, body: AppApproval, request: Request, x_device_token: str = Header(default="")):
        return c(request).verifier.app_approval(call_id, body.customer_id, x_device_token, body.approve).to_dict()

    # -- Console --------------------------------------------------------------------

    @app.get("/v1/calls")
    def list_calls(request: Request, limit: int = Query(50, ge=1, le=500)):
        return c(request).verifier.calls(limit)

    @app.get("/v1/calls/{call_id}")
    def get_call(call_id: str, request: Request):
        return c(request).verifier.call(call_id)

    @app.post("/v1/calls/{call_id}/review")
    def review(call_id: str, body: Review, request: Request, x_console_key: str = Header(default="")):
        key = c(request).settings.console_key
        if key and not hmac.compare_digest(key, x_console_key):
            raise HTTPException(403, "wrong console key")
        return c(request).verifier.review(call_id, body.approve, body.reviewer)

    @app.websocket("/v1/events")
    async def events(ws: WebSocket):
        await ws.accept()
        cont: Container = ws.app.state.c
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
            .with_grants(lk.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True))
            .to_jwt()
        )
        return {"url": cont.settings.livekit_public_url or cont.settings.livekit_url, "token": token, "room": room}

    return app


def _warm_up(c: Container) -> None:
    try:
        warm = getattr(c.speech, "warm_up", None)
        if warm:
            warm()
        c.voice.prewarm(FIXED_PROMPTS)
        log.info("models warm")
    except Exception:
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
