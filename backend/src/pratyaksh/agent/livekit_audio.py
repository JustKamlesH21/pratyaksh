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
SILENCE_LSB = 4  # a device sending zeros arrives after Opus as ±1 LSB (measured); speech peaks in the thousands


class LiveKitCallAudio:
    def __init__(self, room: rtc.Room, caller: rtc.RemoteParticipant, vad: lk_vad.VAD):
        self._room = room
        self._caller = caller
        self._vad = vad
        self._source = rtc.AudioSource(OUT_RATE, 1)
        self._frames: asyncio.Queue[rtc.AudioFrame] = asyncio.Queue(maxsize=3000)
        self._left = asyncio.Event()
        self._stream: rtc.AudioStream | None = None
        self._reader: asyncio.Task | None = None
        self._listening = False
        self._loudest = 0  # loudest sample heard from the Caller during this Call

    @classmethod
    async def open(cls, room: rtc.Room, caller: rtc.RemoteParticipant, vad: lk_vad.VAD) -> "LiveKitCallAudio":
        self = cls(room, caller, vad)
        track = rtc.LocalAudioTrack.create_audio_track("pratyaksh-voice-agent", self._source)
        await room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        self._stream = rtc.AudioStream.from_participant(
            participant=caller, track_source=rtc.TrackSource.SOURCE_MICROPHONE,
            sample_rate=SAMPLE_RATE, num_channels=1,
        )
        self._reader = asyncio.create_task(self._read(self._stream))

        def on_left(p: rtc.RemoteParticipant):
            if p.identity == caller.identity:
                self._left.set()

        room.on("participant_disconnected", on_left)

        # The Caller app sends the capture settings its browser applied (noise suppression, auto
        # gain…) as the "audio" attribute just after joining; one log line explains weak whispers.
        def on_attributes(changed: dict[str, str], p: rtc.Participant):
            if p.identity == caller.identity and "audio" in changed:
                log.info("caller %s audio capture: %.300r", caller.identity, changed["audio"])

        if "audio" in caller.attributes:
            on_attributes(caller.attributes, caller)
        room.on("participant_attributes_changed", on_attributes)
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
            if i == 0:
                # The caption as the audio starts (the source buffers ahead, so this costs no playout):
                # the Caller reads along instead of waiting for the end, and text never leads speech.
                await self.show({"type": "caption", "text": caption})
            if self._left.is_set():
                raise CallerLeft()
        await self._source.wait_for_playout()

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
        self._loudest = max(self._loudest, _peak(heard))
        if latency_ms is None and heard and self._loudest <= SILENCE_LSB:
            # Measured Oct 27: the ASUS "AI Noise-cancelling Input" sends zeros, so the Caller talks and
            # nothing is heard. A quiet room can also be near zero (the Realtek array gates it), so only a
            # microphone that has carried no sound at all during the Call is reported.
            log.warning("caller %s: no sound from the microphone at all so far (%.1f s silent now); "
                        "wrong input device?", self._caller.identity, _seconds(heard))
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

    async def show(self, message: dict) -> None:
        """Send the Caller app a data message (captions, what was heard, the open Challenge, the Outcome)."""
        try:
            await self._room.local_participant.publish_data(
                json.dumps(message), reliable=True, topic="pratyaksh"
            )
        except Exception as e:  # what the app shows is a nicety; the Call goes on without it
            log.debug("data message %s failed: %r", message.get("type"), e)

    def _check(self) -> None:
        if self._left.is_set():
            raise CallerLeft()

    async def aclose(self) -> None:
        if self._reader:
            self._reader.cancel()
        # Closing the stream unsubscribes it from the process-wide LiveKit event queue. Left open, it
        # outlived the job's event loop and every later Call's audio frame logged "error putting to
        # queue: Event loop is closed" (~100 lines a second per finished Call, Oct 29).
        if self._stream:
            try:
                await asyncio.wait_for(self._stream.aclose(), timeout=2.0)
            except TimeoutError:
                log.warning("caller audio stream did not close within 2 s")
        await self._source.aclose()


def _peak(frames: list[rtc.AudioFrame]) -> int:
    return max((int(np.abs(np.frombuffer(f.data, dtype=np.int16)).max(initial=0)) for f in frames), default=0)


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
