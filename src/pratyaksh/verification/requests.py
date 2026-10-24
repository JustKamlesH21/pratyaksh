"""Understanding what the Caller asked for. Keyword rules first, LLM fallback (ADR-0002).

Internal to the Verifier. Seam: ChatModel (OllamaChat in production, a stub in tests).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..domain import RequestKind
from ..language import fold

log = logging.getLogger(__name__)

# Folded keywords (see language.fold). Checked in this order: the riskiest Request wins.
_KEYWORDS: list[tuple[RequestKind, list[str]]] = [
    (RequestKind.SIM_SWAP, [
        "sim", "password", "reset", "pin", "mpin", "number change",
        "सिम", "पासवर्ड", "पिन", "ಸಿಮ್", "ಪಾಸ್ವರ್ಡ್", "ಪಿನ್",
    ]),
    (RequestKind.ADD_PAYEE, [
        "payee", "beneficiary", "labharthi", "add account",
        "पेयी", "लाभार्थी", "बेनिफिशियरी", "ಪೇಯೀ", "ಫಲಾನುಭವಿ", "ಬೆನಿಫಿಷಿಯರಿ",
    ]),
    (RequestKind.HIGH_VALUE_TRANSFER, [
        "transfer", "neft", "rtgs", "imps", "lakh", "lakhs", "send money", "bhejna", "bhej", "kalisu", "kalisi",
        "ट्रांसफर", "लाख", "भेजना", "पैसे भेज", "ಟ್ರಾನ್ಸ್ಫರ್", "ಲಕ್ಷ", "ಹಣ ಕಳುಹಿಸ", "ಕಳುಹಿಸು",
    ]),
    (RequestKind.BALANCE_ENQUIRY, [
        "balance", "bakaya", "baki", "kitna paisa", "estu hana",
        "बैलेंस", "बकाया", "बाकी", "ಬ್ಯಾಲೆನ್ಸ್", "ಬಾಕಿ", "ಎಷ್ಟು ಹಣ",
    ]),
]
# Multi-word on purpose: "app" alone folds to "ap", which collides with Hindi "aap" (you).
_APP_WORDS = [
    "bank app", "in the app", "on the app", "use the app", "app approval", "approve in app",
    "app se", "app mein", "app par", "app nalli", "cannot", "can't", "unable", "nahi kar", "agalla", "agolla",
]


@dataclass(frozen=True)
class Understanding:
    request: RequestKind | None
    wants_app_approval: bool
    reply: str | None = None  # a short clarifying sentence from the LLM, if any


class ChatModel(Protocol):
    def complete_json(self, system: str, user: str) -> dict: ...


class RequestClassifier:
    def __init__(self, llm: ChatModel | None = None):
        self._llm = llm

    def understand(self, transcript: str) -> Understanding:
        words = f" {fold(transcript)} "
        wants_app = self.wants_app_approval(transcript)
        for kind, keys in _KEYWORDS:
            if any(f" {fold(k)} " in words for k in keys):
                return Understanding(kind, wants_app)
        if self._llm is None or not transcript.strip():
            return Understanding(None, wants_app)
        return self._ask_llm(transcript, wants_app)

    def wants_app_approval(self, transcript: str) -> bool:
        words = f" {fold(transcript)} "
        return any(f" {fold(k)} " in words for k in _APP_WORDS)

    def _ask_llm(self, transcript: str, wants_app: bool) -> Understanding:
        system = (
            "You classify what a bank customer asked for on a phone call. The text may mix Kannada, "
            "Hindi and English, possibly romanised. Reply with JSON only: "
            '{"request": one of ["balance_enquiry","add_payee","sim_swap","high_value_transfer"] or null, '
            '"reply": a friendly sentence under 25 words asking them to choose one of those, used only when request is null}. '
            "Never ask for passwords, PINs or codes."
        )
        try:
            out = self._llm.complete_json(system, transcript)
            raw = out.get("request")
            request = RequestKind(raw) if raw in RequestKind._value2member_map_ else None
            reply = out.get("reply") if request is None else None
            if reply is not None and (not isinstance(reply, str) or len(reply) > 240):
                reply = None
            return Understanding(request, wants_app, reply)
        except Exception as e:  # the LLM is optional; any failure falls back to the scripted reply
            log.warning("LLM classification failed: %r", e)
            return Understanding(None, wants_app)


class OllamaChat:
    """Ollama chat API. Works with Ollama Cloud (https://ollama.com + API key) or a local server."""

    def __init__(self, host: str, model: str, api_key: str | None = None, timeout_s: float = 6.0):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(base_url=host.rstrip("/"), headers=headers, timeout=timeout_s)
        self._model = model

    def complete_json(self, system: str, user: str) -> dict:
        r = self._client.post(
            "/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
        )
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])
