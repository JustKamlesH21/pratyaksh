"""Settings from environment variables (or a .env file). See .env.example."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Verifier HTTP server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    lan_ip: str = ""  # the laptop on the demo LAN (set-lan-ip.ps1 keeps it current): phone links use it
    console_key: str = ""  # required in X-Console-Key to decide Agent Reviews; set it for the demo
    # Required in X-Agent-Key on the Voice Agent's endpoints, so no other laptop can post Responses
    # (and forge Reply Latency) or start Calls directly. Set it for the demo; the agent sends it.
    agent_key: str = ""
    max_upload_mb: float = 8.0  # largest Response upload accepted
    max_response_s: float = 60.0  # longest Response audio accepted

    # Storage (ADR-0004). SQLite works for a quick look; use MySQL for the demo.
    database_url: str = "sqlite:///./pratyaksh.db"
    policy_path: str | None = None  # default: the policy.yaml bundled with the package

    # Speech models (SignalExtractor). "local" needs the `ml` extra; "scripted" is for tests only.
    speech_backend: Literal["local", "scripted"] = "local"
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "auto"  # auto | cuda | cpu
    whisper_compute_type: str = "default"  # the model's own float16 on GPU (float32 on CPU); int8 only on a CPU laptop
    spoof_model: str = "MelodyMachine/Deepfake-audio-detection-V2"  # empty string disables
    spoof_fake_labels: str = "fake,spoof,synthetic"
    warm_up_models: bool = True

    # Voice Agent's voice (PromptVoice)
    tts_backend: Literal["parler", "tone"] = "parler"
    parler_model: str = "ai4bharat/indic-parler-tts"
    # A named speaker keeps the voice the same across separately generated sentences. Mary was the
    # clearest in our listening test; Anu is the backup (see .env.example). The speech cache is keyed
    # on this text, so changing it means running pratyaksh-voice-cache again.
    parler_description: str = (
        "Mary speaks in a calm, warm and friendly voice at a moderate pace with a moderate pitch. "
        "Very clear audio, with a very close recording that has no background noise."
    )
    parler_hindi_description: str = (  # chosen by ear on Oct 31 from the native Hindi speakers
        "Aman's voice is warm, friendly and calm, at a moderate pace, with a very close recording that has "
        "no background noise."
    )
    # Hindi Whisper Phrases in play; 0 = all 344. Set in .env for the finale: only phrases already voiced with the
    # new voice are used, so no prompt pauses to synthesise. A demo setting: the digit and the code carry the security.
    hindi_phrase_pool: int = 0
    tts_cache_dir: str = "./.cache/tts"

    # LLM fallback for Request classification (ADR-0002). Leave the key empty to disable.
    ollama_host: str = "https://ollama.com"
    ollama_api_key: str = ""
    ollama_model: str = "gpt-oss:120b"

    # Verification timing
    code_ttl_seconds: int = 120
    approval_ttl_seconds: int = 120

    # Verification Receipts: signed with this Ed25519 key (created on first start; keep it private)
    receipt_key_path: str = "./data/keys/receipt-ed25519.pem"
    receipt_ttl_seconds: int = 600  # how long core banking may act on a receipt

    # Privacy (ADR-0003): keep Response audio only when collecting Eval Run data with consent.
    retain_audio: bool = False
    audio_dir: str = "./data/recordings"

    # LiveKit
    livekit_url: str = "ws://localhost:7880"  # how the API and agent reach LiveKit
    livekit_public_url: str = ""  # what browsers use; defaults to livekit_url
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    # Voice Agent worker
    verifier_url: str = "http://localhost:8000"
    listen_timeout_s: float = 12.0  # silence before a reply counts as "no reply": time to think (Oct 27)
    code_listen_timeout_s: float = 20.0  # Possession Codes: time to unlock the phone, open the app and read
    code_pause_s: float = 1.5  # Possession Codes: pauses this long do not end the reply
    max_reply_s: float = 15.0
    # Silero thresholds. Measured Oct 29 on 66 real human whispers (EARS, Expresso, CLARIS Hindi): 0.35
    # missed 11 (the "no speech heard" of that day's iPhone Calls), 0.15 missed 2, starting 0.3-0.8 s
    # into the whisper; voiced speech triggers the same at both. A reply ends below vad_deactivation:
    # Silero's default (activation - 0.15) would be 0.01, under the 0.05-0.12 of background noise alone.
    vad_activation: float = 0.15
    vad_deactivation: float = 0.10
    vad_min_silence_s: float = 1.2  # a pause this long ends a reply; 0.8 s cut real Callers off mid-phrase

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
