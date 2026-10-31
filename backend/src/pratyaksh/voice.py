"""PromptVoice: text -> WAV for the Voice Agent, with a disk cache.

Interface:
    voice.render(text) -> bytes (WAV)
    voice.prewarm(texts)

Adapters:
    ParlerVoice  AI4Bharat Indic Parler-TTS (needs the `ml` extra; GPU recommended)
    ToneVoice    soft tones the length of the sentence, for machines without the model
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import threading
from pathlib import Path
from typing import Iterable, Protocol

import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)


class Synthesiser(Protocol):
    name: str

    def synthesise(self, text: str) -> tuple[np.ndarray, int]: ...


class PromptVoice:
    def __init__(self, synth: Synthesiser, cache_dir: str | Path, fallback: Synthesiser | None = None):
        self._synth = synth
        self._fallback = fallback  # used when the main model fails, so the Call keeps going
        self._cache = Path(cache_dir)
        self._cache.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # one synthesis at a time on the GPU

    def render(self, text: str) -> bytes:
        """Each sentence is synthesised once and cached, so a prompt that only adds a new lead-in, or a
        Whisper Phrase prompt rendered ahead of time, costs no synthesis on the Call."""
        sentences = _sentences(text)
        if len(sentences) == 1:
            return self._sentence(sentences[0])
        return _join([self._sentence(s) for s in sentences])

    def _sentence(self, text: str) -> bytes:
        # _CACHE_VERSION: clips cached before levelling (Oct 27) were quieter; they are not reused.
        name = self._synth.name_for(text) if hasattr(self._synth, "name_for") else self._synth.name
        key = hashlib.sha1(f"{name}|{_CACHE_VERSION}|{text}".encode()).hexdigest()
        path = self._cache / f"{key}.wav"
        if path.exists():
            return path.read_bytes()
        with self._lock:
            if path.exists():
                return path.read_bytes()
            try:
                samples, rate = self._speak(text)
            except Exception:
                if self._fallback is None:
                    raise
                log.exception("TTS failed; using the fallback voice for this prompt")
                samples, rate = self._fallback.synthesise(text)
                return _wav(_level(samples), rate)  # not cached: retry the real voice next time
            data = _wav(_level(samples), rate)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
            return data

    def _speak(self, text: str) -> tuple[np.ndarray, int]:
        """Parler samples, and now and then generates no speech for a short sentence: ask once more."""
        for attempt in (1, 2):
            samples, rate = self._synth.synthesise(text)
            samples = np.atleast_1d(np.asarray(samples, dtype=np.float32))
            if len(samples) >= _MIN_SPEECH_S * rate:
                return samples, rate
            log.warning("the voice generated no speech for %r (try %d of 2)", text[:40], attempt)
        raise RuntimeError(f"the voice generated no speech for {text[:40]!r}")

    def prewarm(self, texts: Iterable[str]) -> None:
        """Load the voice model and voice the texts. The model loads even when every text is cached, so
        the first line that is not cached never waits for it; a model that cannot load raises."""
        warm_up = getattr(self._synth, "warm_up", None)
        if warm_up:
            warm_up()
        for t in texts:
            try:
                self.render(t)
            except Exception as e:  # a missing prompt is rendered on demand later
                log.warning("could not pre-render prompt %r: %r", t[:40], e)


# A sentence ends at . ! ? or the Devanagari danda, but not after an abbreviation such as "Rs.".
_SENTENCE_END = re.compile(r"(?<=[.!?।])(?<!\bRs\.)(?<!\bNo\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bSt\.)\s+")
_GAP_S = 0.15  # pause between sentences synthesised separately
_MIN_SPEECH_S = 0.1  # shorter than any spoken sentence: the voice generated nothing


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(" ".join(text.split())) if s] or [""]


def _join(wavs: list[bytes]) -> bytes:
    parts = [sf.read(io.BytesIO(w), dtype="float32") for w in wavs]
    rate = parts[0][1]
    out = []
    for samples, r in parts:  # a fallback sentence may come at another sample rate
        if r != rate:
            samples = np.interp(np.arange(0, len(samples), r / rate), np.arange(len(samples)), samples)
        out += [samples, np.zeros(int(_GAP_S * rate), dtype=np.float32)]
    return _wav(np.concatenate(out[:-1]), rate)


_CACHE_VERSION = "levelled-2"
_SPEECH_RMS = 10 ** (-14 / 20)  # bold and clear on a phone earpiece or laptop speaker
_PEAK = 0.9


def _level(samples: np.ndarray) -> np.ndarray:
    """Every sentence at the same loudness (RMS of the speech, not the pauses), never clipping."""
    samples = np.asarray(samples, dtype=np.float32)
    speech = samples[np.abs(samples) > 1e-3]
    if speech.size == 0:
        return samples
    gain = min(_SPEECH_RMS / float(np.sqrt(np.mean(speech ** 2))), _PEAK / float(np.abs(samples).max()))
    return samples * gain


def _wav(samples: np.ndarray, rate: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples.astype(np.float32), rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class ParlerVoice:
    """One model, one speaker per description. Hindi (any Devanagari in the sentence) has its own speaker, a
    native Hindi voice (Oct 31: an English speaker read Hindi artificially); everything else keeps
    `description`, and its cached sentences, because a sentence's cache key names its speaker."""

    def __init__(self, model_id: str, description: str, device: str = "auto", hindi_description: str | None = None):
        self.name = self._named(model_id, description)
        self._model_id = model_id
        self._description = description
        self._hindi_description = hindi_description or description
        self._hindi_name = self._named(model_id, self._hindi_description)
        self._device = device
        self._loaded = None
        self._load_lock = threading.Lock()  # warm-up and a first /v1/voice request must not both load (OOM)

    @staticmethod
    def _named(model_id: str, description: str) -> str:
        return f"parler:{model_id}:{hashlib.sha1(description.encode()).hexdigest()[:8]}"

    @staticmethod
    def _is_hindi(text: str) -> bool:
        return any("ऀ" <= ch <= "ॿ" for ch in text)

    def name_for(self, text: str) -> str:
        return self._hindi_name if self._is_hindi(text) else self.name

    def _load(self):
        with self._load_lock:
            return self._load_locked()

    def _load_locked(self):
        if self._loaded is None:
            import torch
            from parler_tts import ParlerTTSForConditionalGeneration
            from transformers import AutoTokenizer

            device = "cuda:0" if self._device in ("auto", "cuda") and torch.cuda.is_available() else "cpu"
            # bf16 halves the model to ~1.9 GB so it fits a 6 GB GPU next to Whisper (fp32 spilled into
            # system RAM at ~21 s a prompt); fp16 risks NaNs in its T5 text encoder. SDPA attention
            # in the decoder is ~25% faster; the T5 encoder only supports eager.
            dtype = torch.bfloat16 if device != "cpu" and torch.cuda.is_bf16_supported() else torch.float32
            log.info("loading %s on %s (%s)", self._model_id, device, dtype)
            model = ParlerTTSForConditionalGeneration.from_pretrained(
                self._model_id, torch_dtype=dtype, attn_implementation={"decoder": "sdpa", "text_encoder": "eager"},
            ).to(device)
            tok = AutoTokenizer.from_pretrained(self._model_id)
            desc_tok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
            default = desc_tok(self._description, return_tensors="pt").to(device)
            hindi = desc_tok(self._hindi_description, return_tensors="pt").to(device)
            self._loaded = (model, tok, default, hindi, device)
        return self._loaded

    def warm_up(self) -> None:
        self._load()

    def synthesise(self, text: str) -> tuple[np.ndarray, int]:
        model, tok, default, hindi, device = self._load()
        desc = hindi if self._is_hindi(text) else default
        prompt = tok(text, return_tensors="pt").to(device)
        out = model.generate(
            input_ids=desc.input_ids,
            attention_mask=desc.attention_mask,
            prompt_input_ids=prompt.input_ids,
            prompt_attention_mask=prompt.attention_mask,
        )
        return np.atleast_1d(out.float().cpu().numpy().squeeze()), int(model.config.sampling_rate)


class ToneVoice:
    """No speech: a gentle tone per word so the Call flow still works without the TTS model."""

    name = "tone"

    def synthesise(self, text: str) -> tuple[np.ndarray, int]:
        rate = 16_000
        parts = []
        for i, _ in enumerate(text.split()[:40]):
            t = np.arange(int(0.16 * rate)) / rate
            f = 440.0 if i % 2 == 0 else 523.25
            env = np.sin(np.pi * t / t[-1])
            parts += [0.12 * env * np.sin(2 * np.pi * f * t), np.zeros(int(0.06 * rate))]
        return (np.concatenate(parts) if parts else np.zeros(rate // 4)).astype(np.float32), rate
