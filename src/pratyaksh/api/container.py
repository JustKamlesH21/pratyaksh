"""Wiring: build the Verifier and its adapters from Settings."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..policy import Policy
from ..signals import LocalSpeechModels, ScriptedSpeechModels, SignalExtractor, SpeechModels
from ..verification import Database, EventHub, Interpreter, OllamaChat, Verifier
from ..verification.verifier import CLARIFY, GREETING
from ..voice import ParlerVoice, PromptVoice, ToneVoice


@dataclass
class Container:
    settings: Settings
    db: Database
    events: EventHub
    speech: SpeechModels
    verifier: Verifier
    voice: PromptVoice


FIXED_PROMPTS = [GREETING, CLARIFY]


def build(settings: Settings, speech: SpeechModels | None = None) -> Container:
    db = Database(settings.database_url)
    db.create_schema()
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

    llm = (
        OllamaChat(settings.ollama_host, settings.ollama_model, settings.ollama_api_key)
        if settings.ollama_api_key or "localhost" in settings.ollama_host or "127.0.0.1" in settings.ollama_host
        else None
    )
    events = EventHub()
    verifier = Verifier(
        db,
        Policy.load(settings.policy_path),
        SignalExtractor(speech),
        Interpreter(llm),
        events,
        code_ttl_s=settings.code_ttl_seconds,
        approval_ttl_s=settings.approval_ttl_seconds,
    )
    synth = (
        ParlerVoice(settings.parler_model, settings.parler_description, settings.whisper_device)
        if settings.tts_backend == "parler"
        else ToneVoice()
    )
    voice = PromptVoice(synth, settings.tts_cache_dir, fallback=ToneVoice())
    return Container(settings, db, events, speech, verifier, voice)
