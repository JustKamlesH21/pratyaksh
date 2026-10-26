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
        key = hashlib.sha1(f"{self._synth.name}|{text}".encode()).hexdigest()
        path = self._cache / f"{key}.wav"
        if path.exists():
            return path.read_bytes()
        with self._lock:
            if path.exists():
                return path.read_bytes()
            try:
                samples, rate = self._synth.synthesise(text)
            except Exception:
                if self._fallback is None:
                    raise
                log.exception("TTS failed; using the fallback voice for this prompt")
                samples, rate = self._fallback.synthesise(text)
                return _wav(samples, rate)  # not cached: retry the real voice next time
            data = _wav(samples, rate)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
            return data

    def prewarm(self, texts: Iterable[str]) -> None:
        for t in texts:
            try:
                self.render(t)
            except Exception as e:  # a missing prompt is rendered on demand later
                log.warning("could not pre-render prompt %r: %r", t[:40], e)


_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")
_GAP_S = 0.15  # pause between sentences synthesised separately


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


def _wav(samples: np.ndarray, rate: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples.astype(np.float32), rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class ParlerVoice:
    def __init__(self, model_id: str, description: str, device: str = "auto"):
        self.name = f"parler:{model_id}:{hashlib.sha1(description.encode()).hexdigest()[:8]}"
        self._model_id = model_id
        self._description = description
        self._device = device
        self._loaded = None

    def _load(self):
        if self._loaded is None:
            import torch
            from parler_tts import ParlerTTSForConditionalGeneration
            from transformers import AutoTokenizer

            device = "cuda:0" if self._device in ("auto", "cuda") and torch.cuda.is_available() else "cpu"
            # bf16 halves the model to ~1.9 GB so it fits a 6 GB GPU next to Whisper (fp32 spilled into
            # system RAM at ~21 s a prompt); fp16 risks NaNs in its T5 text encoder. SDPA attention
            # in the decoder is ~25% faster; the T5 encoder only supports eager.
            dtype = torch.bfloat16 if device != "cpu" else torch.float32
            log.info("loading %s on %s (%s)", self._model_id, device, dtype)
            model = ParlerTTSForConditionalGeneration.from_pretrained(
                self._model_id, torch_dtype=dtype, attn_implementation={"decoder": "sdpa", "text_encoder": "eager"},
            ).to(device)
            tok = AutoTokenizer.from_pretrained(self._model_id)
            desc_tok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
            desc = desc_tok(self._description, return_tensors="pt").to(device)
            self._loaded = (model, tok, desc, device)
        return self._loaded

    def synthesise(self, text: str) -> tuple[np.ndarray, int]:
        model, tok, desc, device = self._load()
        prompt = tok(text, return_tensors="pt").to(device)
        out = model.generate(
            input_ids=desc.input_ids,
            attention_mask=desc.attention_mask,
            prompt_input_ids=prompt.input_ids,
            prompt_attention_mask=prompt.attention_mask,
        )
        return out.float().cpu().numpy().squeeze(), int(model.config.sampling_rate)


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
