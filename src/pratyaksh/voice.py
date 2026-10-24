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
    def __init__(self, synth: Synthesiser, cache_dir: str | Path):
        self._synth = synth
        self._cache = Path(cache_dir)
        self._cache.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # one synthesis at a time on the GPU

    def render(self, text: str) -> bytes:
        text = " ".join(text.split())
        key = hashlib.sha1(f"{self._synth.name}|{text}".encode()).hexdigest()
        path = self._cache / f"{key}.wav"
        if path.exists():
            return path.read_bytes()
        with self._lock:
            if path.exists():
                return path.read_bytes()
            samples, rate = self._synth.synthesise(text)
            buf = io.BytesIO()
            sf.write(buf, samples.astype(np.float32), rate, format="WAV", subtype="PCM_16")
            data = buf.getvalue()
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
            log.info("loading %s on %s", self._model_id, device)
            model = ParlerTTSForConditionalGeneration.from_pretrained(self._model_id).to(device)
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
        return out.cpu().numpy().squeeze(), int(model.config.sampling_rate)


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
