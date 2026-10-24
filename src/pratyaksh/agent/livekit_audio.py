"""LiveKitCallAudio: the CallAudio adapter for a LiveKit room.

Speaks by publishing a 48 kHz mono track. Listens to the Caller's microphone at 16 kHz and
uses Silero VAD to find where the reply starts (Reply Latency) and ends.
Audio heard while the agent is speaking is discarded (no barge-in).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time

import numpy as np
import soundfile as sf
from livekit import rtc
from livekit.agents import vad as lk_vad

from ..domain import SAMPLE_RATE, Audio, Response
from .ports import CallerLeft

log = logging.getLogger(__name__)

OUT_RATE = 48_000
FRAME_MS = 10
PREFIX_S = 0.3  # audio kept before the detected start of speech


class LiveKitCallAudio:
    def __init__(self, room: rtc.Room, caller: rtc.RemoteParticipant, vad: lk_vad.VAD):
        self._room = room
        self._caller = caller
        self._vad = vad
        self._source = rtc.AudioSource(OUT_RATE, 1)
        self._frames: asyncio.Queue[rtc.AudioFrame] = asyncio.Queue(maxsize=3000)
        self._left = asyncio.Event()
        self._reader: asyncio.Task | None = None
        self._listening = False

    @classmethod
    async def open(cls, room: rtc.Room, caller: rtc.RemoteParticipant, vad: lk_vad.VAD) -> "LiveKitCallAudio":
        self = cls(room, caller, vad)
        track = rtc.LocalAudioTrack.create_audio_track("pratyaksh-voice-agent", self._source)
        await room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        stream = rtc.AudioStream.from_participant(
            participant=caller, track_source=rtc.TrackSource.SOURCE_MICROPHONE,
            sample_rate=SAMPLE_RATE, num_channels=1,
        )
        self._reader = asyncio.create_task(self._read(stream))

        def on_left(p: rtc.RemoteParticipant):
            if p.identity == caller.identity:
                self._left.set()

        room.on("participant_disconnected", on_left)
        return self

    def caller_left(self) -> bool:
        return self._left.is_set()

    async def _read(self, stream: rtc.AudioStream) -> None:
        async for event in stream:
            if not self._listening:
                continue  # drop audio heard while we speak
            if self._frames.full():
                self._frames.get_nowait()
            self._frames.put_nowait(event.frame)

    async def play(self, wav: bytes, caption: str) -> None:
        self._check()
        samples, rate = sf.read(io.BytesIO(wav), dtype="float32", always_2d=True)
        mono = samples.mean(axis=1)
        if rate != OUT_RATE:
            import librosa

            mono = librosa.resample(mono, orig_sr=rate, target_sr=OUT_RATE)
        pcm = (np.clip(mono, -1, 1) * 32767).astype(np.int16)
        n = OUT_RATE * FRAME_MS // 1000
        for i in range(0, len(pcm), n):
            chunk = pcm[i : i + n]
            if len(chunk) < n:
                chunk = np.pad(chunk, (0, n - len(chunk)))
            await self._source.capture_frame(rtc.AudioFrame(chunk.tobytes(), OUT_RATE, 1, n))
            if self._left.is_set():
                raise CallerLeft()
        await self._source.wait_for_playout()
        # Captions after the audio, so text never reaches a Caller earlier than speech does.
        await self._caption(caption)

    async def listen(self, timeout_s: float, max_reply_s: float, pause_s: float = 0.0) -> Response:
        """Record one reply.

        timeout_s:   silence allowed before the reply starts
        max_reply_s: longest reply kept
        pause_s:     after the VAD reports the end of speech, keep listening this long for more
                     (a Possession Code read in chunks); 0 ends at the first pause
        """
        self._check()
        while not self._frames.empty():
            self._frames.get_nowait()
        stream = self._vad.stream()
        heard: list[rtc.AudioFrame] = []
        t0 = time.monotonic()
        self._listening = True
        pump = asyncio.create_task(self._pump(stream, heard))
        latency_ms: int | None = None
        start_idx: int | None = None
        end_idx: int | None = None
        pause_until: float | None = None
        try:
            async with asyncio.timeout(timeout_s + max_reply_s + pause_s + 1.0):
                async for ev in stream:
                    now = time.monotonic()
                    if ev.type == lk_vad.VADEventType.START_OF_SPEECH:
                        if latency_ms is None:
                            latency_ms = _speech_start_ms(ev, now - t0)
                            start_idx = _index_before(heard, ev.speech_duration + PREFIX_S)
                        end_idx, pause_until = None, None  # speech resumed
                    elif ev.type == lk_vad.VADEventType.END_OF_SPEECH:
                        end_idx = len(heard)
                        if pause_s <= 0:
                            break
                        pause_until = now + pause_s
                    elif latency_ms is None and now - t0 > timeout_s:
                        break  # silence
                    elif pause_until is not None and now > pause_until:
                        break  # the pause after the reply was long enough
                    elif start_idx is not None and _seconds(heard[start_idx:]) > max_reply_s:
                        log.info("reply longer than %.0f s, keeping the first part", max_reply_s)
                        break
        except TimeoutError:
            log.info("listen window over; keeping what was heard")
        finally:
            self._listening = False
            pump.cancel()
            await stream.aclose()
        self._check()
        if latency_ms is None or start_idx is None:
            return Response(Audio.silence(), None)
        frames = heard[start_idx : end_idx if end_idx is not None else len(heard)]
        if not frames:
            return Response(Audio.silence(), None)
        frame = rtc.combine_audio_frames(frames)
        pcm = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768.0
        audio = Audio(pcm, frame.sample_rate)
        if frame.sample_rate != SAMPLE_RATE:
            audio = Audio.from_wav(audio.to_wav())
        return Response(audio, latency_ms)

    async def _pump(self, stream: lk_vad.VADStream, heard: list[rtc.AudioFrame]) -> None:
        while True:
            frame = await self._frames.get()
            heard.append(frame)
            stream.push_frame(frame)

    async def _caption(self, text: str) -> None:
        """Send the spoken text to the Caller app as captions."""
        try:
            await self._room.local_participant.publish_data(
                json.dumps({"type": "caption", "text": text}), reliable=True, topic="pratyaksh"
            )
        except Exception as e:  # captions are a nicety
            log.debug("caption failed: %r", e)

    def _check(self) -> None:
        if self._left.is_set():
            raise CallerLeft()

    async def aclose(self) -> None:
        if self._reader:
            self._reader.cancel()
        await self._source.aclose()


def _seconds(frames: list[rtc.AudioFrame]) -> float:
    return sum(f.samples_per_channel / f.sample_rate for f in frames)


def _index_before(frames: list[rtc.AudioFrame], seconds: float) -> int:
    """Index of the frame `seconds` before the end of `frames`."""
    total = 0.0
    for i in range(len(frames) - 1, -1, -1):
        total += frames[i].samples_per_channel / frames[i].sample_rate
        if total >= seconds:
            return i
    return 0


def _speech_start_ms(ev: lk_vad.VADEvent, wall_s: float) -> int:
    """When speech began, counted in audio samples since listening started.

    Sample counting ignores scheduling and buffering delays on this machine; the wall clock
    is a fallback if the VAD does not report a sample index.
    """
    heard_s = ev.samples_index / SAMPLE_RATE if ev.samples_index > 0 else wall_s
    return max(0, int((heard_s - ev.speech_duration) * 1000))
