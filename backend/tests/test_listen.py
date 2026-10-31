"""LiveKitCallAudio.listen: what counts as a reply, driven by a scripted VAD (no LiveKit server)."""

import asyncio
from dataclasses import dataclass

import numpy as np
import pytest
from livekit import rtc
from livekit.agents import vad as lk_vad

from pratyaksh.agent import livekit_audio
from pratyaksh.agent.livekit_audio import LiveKitCallAudio

RATE = 16_000
SAMPLES = RATE // 100  # 10 ms frames
START, END, TICK = (
    lk_vad.VADEventType.START_OF_SPEECH, lk_vad.VADEventType.END_OF_SPEECH, lk_vad.VADEventType.INFERENCE_DONE,
)


@dataclass
class Event:
    type: lk_vad.VADEventType
    samples_index: int = 0
    speech_duration: float = 0.05


class ScriptedVad:
    """Yields its events after the given delays, then ticks as Silero does between events."""

    def __init__(self, script):
        self._script = script

    def stream(self):
        return self

    def push_frame(self, frame):
        pass

    async def aclose(self):
        pass

    async def __aiter__(self):
        for delay, event in self._script:
            await asyncio.sleep(delay)
            yield event
        while True:
            await asyncio.sleep(0.01)
            yield Event(TICK)


def frames(seconds, level):
    n = round(seconds * 100)
    return [rtc.AudioFrame(np.full(SAMPLES, level, np.int16).tobytes(), RATE, 1, SAMPLES) for _ in range(n)]


def audio_with(script):
    audio = LiveKitCallAudio.__new__(LiveKitCallAudio)
    audio._vad = ScriptedVad(script)
    audio._frames = asyncio.Queue()
    audio._left = asyncio.Event()
    audio._listening = False
    audio._loudest = 0
    audio._caller = type("Caller", (), {"identity": "caller"})()
    return audio


async def hear(audio, sound, live=(), **kw):
    """`sound` is already there when listening starts; `live` arrives in real time, as a microphone's does."""

    async def feed():
        await asyncio.sleep(0)
        for f in sound:
            audio._frames.put_nowait(f)
            await asyncio.sleep(0)
        for f in live:
            audio._frames.put_nowait(f)
            await asyncio.sleep(0.01)

    feeder = asyncio.create_task(feed())
    response = await audio.listen(kw.get("timeout_s", 1.0), kw.get("max_reply_s", 5.0), kw.get("pause_s", 0.0))
    await feeder
    return response


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(livekit_audio, "MIN_REPLY_S", 0.6)


async def test_a_blip_when_the_microphone_opens_does_not_end_the_turn(quick):
    # Oct 31, venue: the VAD fired on the hall as the microphone opened and ended the turn before the Caller spoke.
    audio = audio_with([(0.05, Event(START, RATE // 2 + 800)), (0.05, Event(END))])
    response = await hear(audio, frames(0.5, 0), live=frames(1.0, 800))
    assert response.reply_latency_ms is not None
    # Held zeros are not part of the reply, and what came after the blip is kept (it ended at 0.1 s before).
    assert abs(float(response.audio.samples[0])) > 0
    assert response.audio.seconds > 0.2


async def test_the_reply_latency_counts_from_when_the_microphone_opened(quick):
    held, voice = frames(0.8, 0), frames(0.5, 800)
    audio = audio_with([(0.05, Event(START, int(1.0 * RATE)))])
    response = await hear(audio, held + voice, timeout_s=0.3, max_reply_s=0.1)
    assert response.reply_latency_ms < 500  # 0.95 s after listening began, 0.15 s after the microphone opened


async def test_speech_that_resumes_after_the_blip_is_one_reply(quick):
    audio = audio_with([
        (0.05, Event(START, 800)), (0.05, Event(END)), (0.05, Event(START, 3200)), (0.4, Event(END)),
    ])
    response = await hear(audio, [], live=frames(1.0, 800))
    assert response.audio.seconds > 0.2


async def test_a_long_enough_reply_ends_at_the_first_pause(monkeypatch):
    monkeypatch.setattr(livekit_audio, "MIN_REPLY_S", 0.05)
    audio = audio_with([(0.02, Event(START, 800)), (0.1, Event(END))])
    response = await hear(audio, frames(1.0, 800))
    assert response.reply_latency_ms is not None


def ready_audio():
    audio = audio_with([])
    audio._subscribed, audio._mic_on = asyncio.Event(), asyncio.Event()
    return audio


async def test_the_greeting_waits_for_the_phone_to_receive_and_its_microphone_to_come_up():
    # Oct 31: the microphone came up 1.7-5.7 s after joining and the greeting lost its first words.
    audio = ready_audio()
    waiting = asyncio.create_task(audio.wait_for_caller(timeout_s=1.0, settle_s=0))
    await asyncio.sleep(0.02)
    audio._subscribed.set()
    await asyncio.sleep(0.02)
    assert not waiting.done()  # receiving alone is not enough: the microphone is still to come
    audio._mic_on.set()
    await asyncio.wait_for(waiting, 0.5)


async def test_a_phone_that_never_reports_ready_still_gets_its_greeting():
    await asyncio.wait_for(ready_audio().wait_for_caller(timeout_s=0.05, settle_s=0), 0.5)
