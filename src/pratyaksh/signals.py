"""SignalExtractor: turn a Response into Signals.

Interface:
    SignalExtractor(models)
    .transcribe(audio, language=None)            -> str       (a Request, in the Customer's language)
    .extract(challenge, response, language=None) -> Signals   (code_match is left None; the Verifier
                                                               compares spoken_digits to the stored hash)

Which language speech-to-text is told to use (measured Oct 27 with large-v3-turbo; Parler voices, indicative):
    Request          the Customer's profile language. Detection heard Kannada as Hindi, Tamil or English in
                     6 of 6 Requests; told "kn", it wrote Kannada. English stays English whatever it is told,
                     and a forced language saves the detection pass (a second encoder run).
    Whisper Phrase   "en" with the phrase as hotwords: the code-mixed phrase comes out in Latin letters.
    Possession Code  "kn" for a Kannada Customer, else "en": Hindi digit words forced to Hindi came out as
                     other words, in English as digits; Kannada digit words only survive in Kannada.

Seam: SpeechModels (speech-to-text + spoof probability), steered by a TranscriptionHint.
    LocalSpeechModels    faster-whisper + a transformers audio classifier (GPU or CPU)
    ScriptedSpeechModels fixed transcripts and spoof scores, for tests
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Protocol

import numpy as np
from rapidfuzz import fuzz

from .domain import SAMPLE_RATE, Audio, Challenge, ChallengeKind, Response, Signals
from .language import fold_with_digits, spoken_digits
from .phrases import speakable

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptionHint:
    """What speech-to-text should expect from a Response.

    language: transcribe in this language ("en", "hi", "kn"); None lets the model decide.
    hotwords: words the Response should contain (a Whisper Phrase), to bias decoding toward them.
    """

    language: str | None = None
    hotwords: str | None = None


class SpeechModels(Protocol):
    def transcribe(self, audio: Audio, hint: TranscriptionHint | None = None) -> str: ...

    def spoof_probability(self, audio: Audio) -> float | None:
        """P(audio is synthetic) in [0, 1], or None if no spoof model is loaded."""
        ...


class SignalExtractor:
    def __init__(self, models: SpeechModels):
        self._models = models

    def transcribe(self, audio: Audio, language: str | None = None) -> str:
        """A Request, heard in `language` (the Customer's profile language); None lets the model detect it."""
        return self._transcribe(audio, TranscriptionHint(language=language))

    def _transcribe(self, audio: Audio, hint: TranscriptionHint) -> str:
        if audio.seconds < 0.2:
            return ""
        return self._models.transcribe(audio, hint).strip()

    def extract(self, challenge: Challenge, response: Response, language: str | None = None) -> Signals:
        """Signals of a Response; `language` is the Customer's profile language."""
        audio = response.audio
        if response.reply_latency_ms is None or audio.seconds < 0.2:
            return Signals(reply_latency_ms=None)

        # The whisper DSP is CPU work; speech-to-text and the spoof model release the GIL while they
        # infer, so the two overlap instead of adding up.
        whisper = _DSP.submit(whisper_score, audio) if challenge.kind is ChallengeKind.WHISPER_PHRASE else None
        if whisper is not None:
            # The phrase mixes Kannada, Hindi and English words; asked for English, speech-to-text writes all
            # of it in Latin letters, and the expected words steer it toward the right spelling.
            hint = TranscriptionHint(language="en", hotwords=speakable(challenge.phrase, language or "en"))
        else:
            hint = TranscriptionHint(language=_CODE_LANGUAGE.get(language or "", "en"))
        transcript = self._transcribe(audio, hint)
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


# The language a Possession Code readout is heard in, by the Customer's language (default "en").
_CODE_LANGUAGE = {"kn": "kn"}


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
    score = _whisper_score(audio)
    if log.isEnabledFor(logging.INFO):
        # Runs on the DSP thread beside speech-to-text, so it adds no latency to the Response.
        log.info("whisper DSP: whisper_score=%s detail=%s (logged only; the Policy does not use it)",
                 score, whisper_detail(audio))
    return score


def whisper_detail(audio: Audio) -> dict | None:
    """Diagnostic measurements for red-team review, never used for a Verdict (~5 ms per 3 s).

    The whisper score alone is fooled by voiced synthetic speech drowned in loud noise (<= 5 dB SNR):
    that leaves few pauses (TTS + white noise at 0 dB: dynamic_range_db ~5) and a flat, hissy spectrum
    (flatness ~0.5). Recorded human whispers (EARS, Expresso, Claris Hindi; some with two background
    talkers) measured dynamic_range_db 9.8-26 and flatness 0.03-0.11. Logged so real Calls show whether
    a gate on these is safe; see scripts/redteam_whisper.py. None without speech energy.
    """
    import librosa

    y = audio.samples
    if audio.sample_rate != SAMPLE_RATE:
        y = librosa.resample(y, orig_sr=audio.sample_rate, target_sr=SAMPLE_RATE)
    n_fft, hop = 1024, 256
    power = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop)) ** 2
    rms = np.sqrt(power.sum(axis=0) / n_fft)
    if rms.size == 0 or float(rms.max()) < 1e-4:
        return None
    db = 20 * np.log10(rms + 1e-9)
    speech = power[:, rms > 0.1 * float(rms.max())]
    freqs = librosa.fft_frequencies(sr=SAMPLE_RATE, n_fft=n_fft)
    band = speech[(freqs > 100) & (freqs < 7500)] + 1e-12
    flatness = np.exp(np.mean(np.log(band), axis=0)) / np.mean(band, axis=0)
    high = speech[freqs >= 4000].sum(axis=0) / (speech.sum(axis=0) + 1e-12)
    return {
        "dynamic_range_db": round(float(np.percentile(db, 95) - np.percentile(db, 10)), 1),
        "flatness": round(float(np.median(flatness)), 3),
        "high_band_share": round(float(np.median(high)), 3),
    }


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
    """Test and demo-replay adapter: returns transcripts and spoof scores in order, and records the
    TranscriptionHint of every transcription in .hints."""

    def __init__(
        self,
        transcripts: Iterable[str] | Callable[[Audio], str] = (),
        spoof: Iterable[float | None] | float | None = None,
    ):
        self._transcribe = transcripts if callable(transcripts) else None
        self._queue = deque([] if callable(transcripts) else transcripts)
        self._spoof = deque(spoof) if isinstance(spoof, (list, tuple, deque)) else None
        self._spoof_const = None if self._spoof is not None else spoof
        self.hints: list[TranscriptionHint] = []

    def push(self, transcript: str, spoof: float | None = None) -> None:
        self._queue.append(transcript)
        if self._spoof is not None:
            self._spoof.append(spoof)

    def transcribe(self, audio: Audio, hint: TranscriptionHint | None = None) -> str:
        self.hints.append(hint or TranscriptionHint())
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
        # Responses for different Calls are heard on parallel threads. CTranslate2 (whisper) allows
        # concurrent calls; a transformers pipeline is not documented as thread-safe, so it runs one at a time.
        self._spoof_lock = threading.Lock()

    def warm_up(self) -> None:
        # Run each model once: CUDA libraries load and GPU kernels compile on first use, so a missing
        # library fails here, where /v1/status reports it, and the first Caller's Response is not the
        # one that pays ~1.5 s extra for it (measured: 1,988 ms cold, then ~545 ms).
        second = np.random.default_rng(0).standard_normal(SAMPLE_RATE).astype(np.float32) * 0.01
        list(self._load_whisper().transcribe(second, beam_size=1)[0])
        if self._spoof_name:
            self._load_spoof()
            self.spoof_probability(Audio(second))

    def _load_whisper(self):
        with self._load_lock:
            return self._load_whisper_locked()

    def _load_whisper_locked(self):
        if self._whisper is None:
            if self._device != "cpu":
                try:  # on Windows, CTranslate2 finds cuBLAS 12 only if torch has already loaded its copy
                    import torch  # noqa: F401
                except Exception:  # not installed, or a broken DLL (OSError): Whisper may still load
                    pass
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

    def transcribe(self, audio: Audio, hint: TranscriptionHint | None = None) -> str:
        hint = hint or TranscriptionHint()
        model = self._load_whisper()
        segments, _info = model.transcribe(
            audio.samples, beam_size=1, vad_filter=False, condition_on_previous_text=False,
            language=hint.language, hotwords=hint.hotwords,
        )
        return " ".join(s.text.strip() for s in segments)

    def spoof_probability(self, audio: Audio) -> float | None:
        if not self._spoof_name:
            return None
        clf = self._load_spoof()
        with self._spoof_lock:
            results = clf({"raw": audio.samples, "sampling_rate": audio.sample_rate}, top_k=None)
        fake = sum(r["score"] for r in results if r["label"].lower() in self._fake_labels)
        return round(float(fake), 3)


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False
