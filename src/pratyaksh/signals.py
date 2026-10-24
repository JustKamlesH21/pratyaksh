"""SignalExtractor: turn a Response into Signals.

Interface:
    SignalExtractor(models)
    .transcribe(audio)            -> str
    .extract(challenge, response) -> Signals   (code_match is left None; the Verifier
                                                compares spoken_digits to the stored hash)

Seam: SpeechModels (speech-to-text + spoof probability).
    LocalSpeechModels    faster-whisper + a transformers audio classifier (GPU or CPU)
    ScriptedSpeechModels fixed transcripts and spoof scores, for tests
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Protocol

import numpy as np
from rapidfuzz import fuzz

from .domain import SAMPLE_RATE, Audio, Challenge, ChallengeKind, Response, Signals
from .language import fold_with_digits, spoken_digits

log = logging.getLogger(__name__)


class SpeechModels(Protocol):
    def transcribe(self, audio: Audio) -> str: ...

    def spoof_probability(self, audio: Audio) -> float | None:
        """P(audio is synthetic) in [0, 1], or None if no spoof model is loaded."""
        ...


class SignalExtractor:
    def __init__(self, models: SpeechModels):
        self._models = models

    def transcribe(self, audio: Audio) -> str:
        if audio.seconds < 0.2:
            return ""
        return self._models.transcribe(audio).strip()

    def extract(self, challenge: Challenge, response: Response) -> Signals:
        audio = response.audio
        if response.reply_latency_ms is None or audio.seconds < 0.2:
            return Signals(reply_latency_ms=None)

        # The whisper DSP is CPU work; speech-to-text and the spoof model release the GIL while they
        # infer, so the two overlap instead of adding up.
        whisper = _DSP.submit(whisper_score, audio) if challenge.kind is ChallengeKind.WHISPER_PHRASE else None
        transcript = self.transcribe(audio)
        spoof = self._models.spoof_probability(audio)

        if whisper is not None:
            return Signals(
                transcript=transcript,
                task_match=phrase_match(challenge.phrase, transcript),
                whisper_score=whisper.result(),
                reply_latency_ms=response.reply_latency_ms,
                spoof_score=spoof,
            )
        digits = spoken_digits(transcript)
        return Signals(
            transcript=transcript,
            reply_latency_ms=response.reply_latency_ms,
            spoof_score=spoof,
            spoken_digits=digits or None,
        )


def phrase_match(expected: str, transcript: str) -> float:
    """0..1: how much of the phrase was said, independent of script, spelling and filler words.

    Each expected word scores its best fuzzy match among the heard words; digits must match
    exactly. A phrase whose digit is missing or wrong scores at most 0.5, because the digit is
    the random part that stops replayed recordings.
    """
    want = fold_with_digits(expected).split()
    heard = fold_with_digits(transcript).split()
    if not want or not heard:
        return 0.0
    scores = []
    digit_ok = True
    for w in want:
        if w.isdigit():
            hit = w in heard
            digit_ok = digit_ok and hit
            scores.append(1.0 if hit else 0.0)
        else:
            scores.append(max(fuzz.ratio(w, h) for h in heard) / 100.0)
    score = sum(scores) / len(scores)
    if not digit_ok:
        score = min(score, 0.5)
    return round(score, 3)


_dsp_lock = threading.Lock()
_dsp_ready = False
_DSP = ThreadPoolExecutor(max_workers=2, thread_name_prefix="whisper-dsp")


def warm_up_dsp() -> None:
    """Import and compile the whisper DSP (librosa + numba, ~1 s) once. Callers that arrive meanwhile
    wait for it rather than compiling the same code again in parallel."""
    global _dsp_ready
    if _dsp_ready:
        return
    with _dsp_lock:
        if not _dsp_ready:
            rng = np.random.default_rng(0)
            _whisper_score(Audio((0.1 * rng.standard_normal(SAMPLE_RATE)).astype(np.float32)))
            _dsp_ready = True


def whisper_score(audio: Audio) -> float | None:
    """Share of speech frames with no voicing (vocal folds not vibrating). Whispers score high.

    None when no speech energy is found.
    """
    warm_up_dsp()
    return _whisper_score(audio)


def _whisper_score(audio: Audio) -> float | None:
    import librosa

    y = audio.samples
    if audio.sample_rate != SAMPLE_RATE:
        y = librosa.resample(y, orig_sr=audio.sample_rate, target_sr=SAMPLE_RATE)
    frame, hop = 1024, 256
    rms = librosa.feature.rms(y=y, frame_length=frame, hop_length=hop)[0]
    if rms.size == 0 or float(rms.max()) < 1e-4:
        return None
    speech = rms > max(0.1 * float(rms.max()), 1e-3)
    if not speech.any():
        return None
    _, voiced, _ = librosa.pyin(
        y, fmin=65.0, fmax=400.0, sr=SAMPLE_RATE, frame_length=frame, hop_length=hop, center=True
    )
    n = min(len(voiced), len(speech))
    voiced, speech = voiced[:n], speech[:n]
    voiced_share = float(np.count_nonzero(voiced & speech)) / float(np.count_nonzero(speech))
    return round(1.0 - voiced_share, 3)


# -- adapters ---------------------------------------------------------------------------


class ScriptedSpeechModels:
    """Test and demo-replay adapter: returns transcripts and spoof scores in order."""

    def __init__(
        self,
        transcripts: Iterable[str] | Callable[[Audio], str] = (),
        spoof: Iterable[float | None] | float | None = None,
    ):
        self._transcribe = transcripts if callable(transcripts) else None
        self._queue = deque([] if callable(transcripts) else transcripts)
        self._spoof = deque(spoof) if isinstance(spoof, (list, tuple, deque)) else None
        self._spoof_const = None if self._spoof is not None else spoof

    def push(self, transcript: str, spoof: float | None = None) -> None:
        self._queue.append(transcript)
        if self._spoof is not None:
            self._spoof.append(spoof)

    def transcribe(self, audio: Audio) -> str:
        if self._transcribe:
            return self._transcribe(audio)
        return self._queue.popleft() if self._queue else ""

    def spoof_probability(self, audio: Audio) -> float | None:
        if self._spoof is not None:
            return self._spoof.popleft() if self._spoof else None
        return self._spoof_const


class LocalSpeechModels:
    """faster-whisper for speech-to-text and a transformers audio classifier for spoofing.

    Needs the `ml` extra. Models load lazily on first use, then stay in memory.
    """

    def __init__(
        self,
        whisper_model: str = "large-v3-turbo",
        device: str = "auto",
        compute_type: str = "default",
        spoof_model: str | None = "MelodyMachine/Deepfake-audio-detection-V2",
        spoof_fake_labels: tuple[str, ...] = ("fake", "spoof", "synthetic", "bonafide_false"),
    ):
        self._whisper_name = whisper_model
        self._device = device
        self._compute_type = compute_type
        self._spoof_name = spoof_model
        self._fake_labels = {l.lower() for l in spoof_fake_labels}
        self._whisper = None
        self._spoof = None
        self._load_lock = threading.Lock()  # warm-up and the first request must not both load

    def warm_up(self) -> None:
        self._load_whisper()
        if self._spoof_name:
            self._load_spoof()

    def _load_whisper(self):
        with self._load_lock:
            return self._load_whisper_locked()

    def _load_whisper_locked(self):
        if self._whisper is None:
            from faster_whisper import WhisperModel

            log.info("loading faster-whisper %s on %s", self._whisper_name, self._device)
            self._whisper = WhisperModel(self._whisper_name, device=self._device, compute_type=self._compute_type)
        return self._whisper

    def _load_spoof(self):
        with self._load_lock:
            return self._load_spoof_locked()

    def _load_spoof_locked(self):
        if self._spoof is None:
            from transformers import pipeline

            device = 0 if self._device in ("cuda", "auto") and _cuda_available() else -1
            log.info("loading spoof model %s", self._spoof_name)
            self._spoof = pipeline("audio-classification", model=self._spoof_name, device=device)
        return self._spoof

    def transcribe(self, audio: Audio) -> str:
        model = self._load_whisper()
        segments, _info = model.transcribe(
            audio.samples, beam_size=1, vad_filter=False, condition_on_previous_text=False
        )
        return " ".join(s.text.strip() for s in segments)

    def spoof_probability(self, audio: Audio) -> float | None:
        if not self._spoof_name:
            return None
        clf = self._load_spoof()
        results = clf({"raw": audio.samples, "sampling_rate": audio.sample_rate}, top_k=None)
        fake = sum(r["score"] for r in results if r["label"].lower() in self._fake_labels)
        return round(float(fake), 3)


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False
