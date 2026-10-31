"""Shared value types. Names match CONTEXT.md."""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field
from enum import StrEnum

import numpy as np
import soundfile as sf

SAMPLE_RATE = 16_000  # every Response is scored at 16 kHz mono


class RequestKind(StrEnum):
    BALANCE_ENQUIRY = "balance_enquiry"
    ADD_PAYEE = "add_payee"
    SIM_SWAP = "sim_swap"
    HIGH_VALUE_TRANSFER = "high_value_transfer"
    ACCOUNT_SERVICE = "account_service"  # any other account change: cards, limits, address, closing…


class ChallengeKind(StrEnum):
    WHISPER_PHRASE = "whisper_phrase"
    POSSESSION_CODE = "possession_code"


class Verdict(StrEnum):
    PASS = "PASS"
    STEP_UP = "STEP_UP"
    BLOCK = "BLOCK"


class CallState(StrEnum):
    AWAITING_REQUEST = "awaiting_request"
    CHALLENGING = "challenging"
    AWAITING_APP_APPROVAL = "awaiting_app_approval"
    CLOSED = "closed"


class Outcome(StrEnum):
    """How a Call ended. Set only when the Call is CLOSED."""

    PASSED = "passed"
    PASSED_PENDING_REVIEW = "passed_pending_review"
    APPROVED_IN_APP = "approved_in_app"
    BLOCKED = "blocked"
    DECLINED_IN_APP = "declined_in_app"
    HANDED_TO_AGENT = "handed_to_agent"  # a Bank Agent takes over (and verifies the Caller themselves)
    ENDED = "ended"  # the Caller only had questions, or said goodbye
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class Audio:
    """Mono float32 samples in [-1, 1] at SAMPLE_RATE."""

    samples: np.ndarray
    sample_rate: int = SAMPLE_RATE

    @property
    def seconds(self) -> float:
        return len(self.samples) / self.sample_rate

    @classmethod
    def from_wav(cls, data: bytes) -> "Audio":
        """Decode any WAV/FLAC bytes, downmix to mono and resample to 16 kHz."""
        samples, rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        mono = samples.mean(axis=1)
        if rate != SAMPLE_RATE:
            import librosa

            mono = librosa.resample(mono, orig_sr=rate, target_sr=SAMPLE_RATE)
        return cls(np.ascontiguousarray(mono, dtype=np.float32), SAMPLE_RATE)

    @staticmethod
    def wav_info(data: bytes) -> tuple[float, int]:
        """(seconds, sample rate) from the header alone, without decoding."""
        info = sf.info(io.BytesIO(data))
        return info.frames / info.samplerate, int(info.samplerate)

    def to_wav(self) -> bytes:
        buf = io.BytesIO()
        sf.write(buf, self.samples, self.sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    @classmethod
    def silence(cls, seconds: float = 0.0) -> "Audio":
        return cls(np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32))


@dataclass(frozen=True)
class Response:
    """The Caller's reply to one Challenge. reply_latency_ms is None when no speech was heard."""

    audio: Audio
    reply_latency_ms: int | None


@dataclass(frozen=True)
class Challenge:
    kind: ChallengeKind
    prompt: str
    # Whisper Phrase: the romanised phrase. Possession Code: empty (only the hash is stored).
    phrase: str = ""


@dataclass(frozen=True)
class Signals:
    """Measurements from one Response. None means the Signal does not apply or was unavailable."""

    transcript: str = ""
    task_match: float | None = None  # 0..1, Whisper Phrase only
    whisper_score: float | None = None  # 0..1, share of unvoiced speech frames
    reply_latency_ms: int | None = None
    spoof_score: float | None = None  # 0..1, probability the audio is synthetic
    spoken_digits: str | None = None  # Possession Code only
    other_digits: str | None = None  # Possession Code only: a second reading of the same audio, when it differs
    code_match: bool | None = None  # Possession Code only
    # Whisper Phrase only (Live Microphone): dB between the reply's loud and quiet moments. A live microphone
    # always hears its room, so this stays low; audio played in digitally has exact silence around the words.
    dynamic_range_db: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Signals":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})


@dataclass(frozen=True)
class Evidence:
    """One answered Challenge."""

    kind: ChallengeKind
    signals: Signals


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    liveness: float | None
    reasons: list[str]
    per_response: list[float] = field(default_factory=list)
    # When verdict is STEP_UP: either one more Challenge, or hand over to App Approval.
    next_challenge: ChallengeKind | None = None
    offer_app_approval: bool = False


@dataclass(frozen=True)
class Step:
    """What the Voice Agent must do next on a Call.

    say:        text to speak (may be empty)
    listen:     after speaking, record one Response and send it back
    long_reply: the Response is a Possession Code readout: allow more time and pauses
    wait:       after speaking, poll for the next Step (App Approval pending)
    end:        after speaking, hang up
    challenge:  the Challenge the Caller is answering while this Step listens (None outside one)
    words:      Whisper Phrase only: the words to whisper, as spoken and captioned (native script)
    heard:      the transcript of the Response this Step answers ("" for none). It is about the
                Response, not what to do next, so it is neither stored nor compared.
    """

    call_id: str
    say: str
    listen: bool = False
    long_reply: bool = False
    wait: bool = False
    end: bool = False
    state: CallState = CallState.AWAITING_REQUEST
    outcome: Outcome | None = None
    challenge: ChallengeKind | None = None
    words: str = ""
    heard: str = field(default="", compare=False)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Step":
        return cls(
            call_id=d["call_id"],
            say=d.get("say", ""),
            listen=bool(d.get("listen")),
            long_reply=bool(d.get("long_reply")),
            wait=bool(d.get("wait")),
            end=bool(d.get("end")),
            state=CallState(d.get("state", CallState.AWAITING_REQUEST)),
            outcome=Outcome(d["outcome"]) if d.get("outcome") else None,
            challenge=ChallengeKind(d["challenge"]) if d.get("challenge") else None,
            words=d.get("words") or "",
            heard=d.get("heard") or "",
        )
