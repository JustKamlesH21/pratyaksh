"""Seams of the Voice Agent.

VerifierPort  how the agent talks to the Verifier
    HttpVerifier       production: the verifier's HTTP interface
    InProcessVerifier  tests and single-process demos: calls the Verifier directly
CallAudio     how the agent hears and speaks on a Call
    LiveKitCallAudio   production (agent/livekit_audio.py)
    tests use a scripted fake (tests/test_call_loop.py)
"""

from __future__ import annotations

import asyncio
from typing import Protocol

import httpx

from ..domain import Response, Step


class CallerLeft(Exception):
    """The Caller disconnected."""


class VerifierPort(Protocol):
    async def start_call(self, customer_id: str, room: str) -> Step: ...
    async def respond(self, call_id: str, response: Response) -> Step: ...
    async def current_step(self, call_id: str) -> Step: ...
    async def hang_up(self, call_id: str) -> None: ...
    async def voice(self, text: str) -> bytes: ...


class CallAudio(Protocol):
    async def play(self, wav: bytes, caption: str) -> None:
        """Speak to the Caller; return when playout has finished. The caption reaches the Caller app
        as the audio starts, never before. Raises CallerLeft."""
        ...

    async def listen(self, timeout_s: float, max_reply_s: float, pause_s: float = 0.0) -> Response:
        """Record one reply. reply_latency_ms counts from this call to the start of speech;
        None if the Caller said nothing within timeout_s. Pauses shorter than pause_s do not
        end the reply. Raises CallerLeft."""
        ...

    async def show(self, message: dict) -> None:
        """Send the Caller app something to display, not to hear: {"type": "heard", "text"},
        {"type": "challenge", "kind", "words"} or {"type": "outcome", "outcome"}. Best effort."""
        ...

    def caller_left(self) -> bool: ...


class HttpVerifier:
    def __init__(self, base_url: str, agent_key: str = "", timeout_s: float = 120.0):  # first request may load models
        headers = {"X-Agent-Key": agent_key} if agent_key else {}
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_s)

    async def start_call(self, customer_id: str, room: str) -> Step:
        r = await self._http.post("/v1/calls", json={"customer_id": customer_id, "room": room})
        r.raise_for_status()
        return Step.from_dict(r.json())

    async def respond(self, call_id: str, response: Response) -> Step:
        data = {} if response.reply_latency_ms is None else {"reply_latency_ms": str(response.reply_latency_ms)}
        r = await self._http.post(
            f"/v1/calls/{call_id}/responses",
            files={"audio": ("reply.wav", response.audio.to_wav(), "audio/wav")},
            data=data,
        )
        r.raise_for_status()
        return Step.from_dict(r.json())

    async def current_step(self, call_id: str) -> Step:
        r = await self._http.get(f"/v1/calls/{call_id}/step")
        r.raise_for_status()
        return Step.from_dict(r.json())

    async def hang_up(self, call_id: str) -> None:
        r = await self._http.post(f"/v1/calls/{call_id}/hangup")
        r.raise_for_status()

    async def voice(self, text: str) -> bytes:
        r = await self._http.get("/v1/voice", params={"text": text})
        r.raise_for_status()
        return r.content

    async def aclose(self) -> None:
        await self._http.aclose()


class InProcessVerifier:
    def __init__(self, verifier, voice):
        self._v = verifier
        self._voice = voice

    async def start_call(self, customer_id: str, room: str) -> Step:
        return await asyncio.to_thread(self._v.start_call, customer_id, room)

    async def respond(self, call_id: str, response: Response) -> Step:
        return await asyncio.to_thread(self._v.respond, call_id, response)

    async def current_step(self, call_id: str) -> Step:
        return await asyncio.to_thread(self._v.current_step, call_id)

    async def hang_up(self, call_id: str) -> None:
        await asyncio.to_thread(self._v.hang_up, call_id)

    async def voice(self, text: str) -> bytes:
        return await asyncio.to_thread(self._voice.render, text)
