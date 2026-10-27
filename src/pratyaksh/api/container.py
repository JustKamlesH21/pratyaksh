"""Wiring: build the Verifier and its adapters from Settings."""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field

from ..config import Settings
from ..policy import Policy
from ..signals import LocalSpeechModels, ScriptedSpeechModels, SignalExtractor, SpeechModels
from ..verification import Database, EventHub, Interpreter, OllamaChat, ReceiptSigner, Verifier
from ..verification.verifier import CLARIFY, GREETING, spoken_lines
from ..voice import ParlerVoice, PromptVoice, ToneVoice

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    db: Database
    events: EventHub
    speech: SpeechModels
    verifier: Verifier
    voice: PromptVoice
    missing_triggers: list[str] = field(default_factory=list)  # Audit Trail triggers the database lacks
    warm: bool = False  # models and the whisper DSP have been loaded once
    warm_error: str | None = None  # why warm-up failed, for /v1/status


FIXED_PROMPTS = [GREETING, CLARIFY]


def build(settings: Settings, speech: SpeechModels | None = None) -> Container:
    db = Database(settings.database_url)
    missing_triggers = db.create_schema()
    db.seed_demo_customers()

    if speech is None:
        if settings.speech_backend == "scripted":
            speech = ScriptedSpeechModels()
        else:
            speech = LocalSpeechModels(
                whisper_model=settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
                spoof_model=settings.spoof_model or None,
                spoof_fake_labels=tuple(l.strip() for l in settings.spoof_fake_labels.split(",") if l.strip()),
            )

    llm = OllamaChat(settings.ollama_host, settings.ollama_model, settings.ollama_api_key) if llm_configured(settings) else None
    events = EventHub()
    verifier = Verifier(
        db,
        Policy.load(settings.policy_path),
        SignalExtractor(speech),
        Interpreter(llm),
        events,
        code_ttl_s=settings.code_ttl_seconds,
        approval_ttl_s=settings.approval_ttl_seconds,
        signer=ReceiptSigner.load_or_create(settings.receipt_key_path),
        receipt_ttl_s=settings.receipt_ttl_seconds,
    )
    voice = PromptVoice(_synth(settings), settings.tts_cache_dir, fallback=ToneVoice())
    return Container(settings, db, events, speech, verifier, voice, missing_triggers)


def _synth(settings: Settings):
    if settings.tts_backend == "parler":
        return ParlerVoice(settings.parler_model, settings.parler_description, settings.whisper_device)
    return ToneVoice()


def voice_cache_main() -> None:
    """pratyaksh-voice-cache: voice every line the Voice Agent can say (all Whisper Phrase prompts
    included) into the TTS cache, so Calls never wait for speech synthesis. Lines already cached are
    skipped, so it can be stopped and run again. With Parler on the laptop GPU this takes about 3.6 hours per voice."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()
    voice = PromptVoice(_synth(settings), settings.tts_cache_dir)  # no fallback: a failure must show
    lines = spoken_lines()
    voice.prewarm([])  # load the model once, up front
    failed = []
    start = time.perf_counter()
    for i, line in enumerate(lines, 1):
        try:
            voice.render(line)
        except Exception as e:  # one bad line must not end a two-hour run; it is voiced on first use instead
            failed.append(line)
            log.warning("could not voice %r: %s", line[:60], e)
        if i % 25 == 0 or i == len(lines):
            took = time.perf_counter() - start
            log.info("voiced %d of %d lines (%.0f s so far, about %.0f min left)",
                     i, len(lines), took, took / i * (len(lines) - i) / 60)
    if failed:
        sys.exit(f"{len(failed)} lines could not be voiced; run pratyaksh-voice-cache again to retry them:\n  "
                 + "\n  ".join(failed))


def llm_configured(settings: Settings) -> bool:
    """Ollama Cloud needs a key; a local Ollama server does not."""
    host = settings.ollama_host
    return bool(settings.ollama_api_key) or "localhost" in host or "127.0.0.1" in host
