from __future__ import annotations

import random
from datetime import datetime, timedelta

import numpy as np
import pytest

from pratyaksh.domain import SAMPLE_RATE, Audio, Response
from pratyaksh.policy import Policy
from pratyaksh.signals import ScriptedSpeechModels, SignalExtractor
from pratyaksh.verification import Database, EventHub, Interpreter, Verifier


def voiced(seconds: float = 1.5, f0: float = 140.0, seed: int = 0) -> Audio:
    """A buzzy harmonic signal, like normal (voiced) speech."""
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    wobble = 1 + 0.03 * np.sin(2 * np.pi * 3 * t)
    sig = sum((0.6 / k) * np.sin(2 * np.pi * f0 * k * wobble * t) for k in range(1, 8))
    sig = sig * (0.5 + 0.5 * np.sin(2 * np.pi * 2 * t) ** 2)
    return Audio((0.3 * sig / np.abs(sig).max()).astype(np.float32))


def whispered(seconds: float = 1.5, seed: int = 0) -> Audio:
    """Band-limited noise with a syllable envelope, like a whisper (no voicing)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SAMPLE_RATE)
    noise = rng.normal(0, 1, n)
    kernel = np.hanning(9)
    noise = np.convolve(noise, kernel / kernel.sum(), mode="same")
    t = np.arange(n) / SAMPLE_RATE
    sig = noise * (0.5 + 0.5 * np.sin(2 * np.pi * 2 * t) ** 2)
    return Audio((0.2 * sig / np.abs(sig).max()).astype(np.float32))


def reply(audio: Audio, latency_ms: int | None = 700) -> Response:
    return Response(audio, latency_ms)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 31, 10, 0, 0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Harness:
    """A Verifier on in-memory SQLite with scripted speech models."""

    def __init__(self, spoof=None, llm=None):
        self.db = Database("sqlite://")
        self.db.create_schema()
        self.db.seed_demo_customers()
        self.models = ScriptedSpeechModels(spoof=spoof)
        self.clock = Clock()
        self.events = EventHub()
        self.verifier = Verifier(
            self.db,
            Policy.load(),
            SignalExtractor(self.models),
            Interpreter(llm),
            self.events,
            rng=random.Random(7),
            clock=self.clock,
        )

    def say(self, call_id: str, transcript: str, audio: Audio | None = None, latency_ms: int | None = 700):
        audio = audio or voiced()
        if latency_ms is not None and audio.seconds >= 0.2:  # only then is speech-to-text run
            self.models.push(transcript)
        return self.verifier.respond(call_id, Response(audio, latency_ms))

    def inbox(self, customer_id: str) -> dict:
        return self.verifier.inbox(customer_id, self.verifier.pairing(customer_id))

    def approve(self, call_id: str, customer_id: str, ok: bool = True):
        return self.verifier.app_approval(call_id, customer_id, self.verifier.pairing(customer_id), ok)

    def code_on_device(self, customer_id: str) -> str:
        msgs = self.inbox(customer_id)["messages"]
        return next(m["body"]["code"] for m in msgs if m["kind"] == "possession_code")

    def current_phrase(self, call_id: str) -> str:
        return self.verifier.call(call_id)["challenges"][-1]["phrase"]


@pytest.fixture
def harness() -> Harness:
    return Harness()
