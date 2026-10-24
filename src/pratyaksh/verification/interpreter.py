"""Interpreter: understand any Caller utterance, so the Voice Agent never gets stuck.

Internal to the Verifier. Keyword rules run first (fast, offline, deterministic); the LLM
handles everything else (ADR-0002: it may talk about anything, but it never decides a Verdict,
never reveals account data and never skips a Challenge).

Seam: ChatModel (OllamaChat in production, a stub in tests).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources
from typing import Protocol

import httpx
import yaml

from ..domain import RequestKind
from ..language import fold

log = logging.getLogger(__name__)


class TurnKind(StrEnum):
    REQUEST = "request"  # the Caller asked the bank to do something
    QUESTION = "question"  # the Caller asked for information
    REPEAT = "repeat"  # "say that again"
    APP_APPROVAL = "app_approval"  # "I can't do this, use the app"
    HUMAN = "human"  # "let me talk to a person"
    GOODBYE = "goodbye"  # "that's all, thanks"
    UNCLEAR = "unclear"


@dataclass(frozen=True)
class Understanding:
    kind: TurnKind
    request: RequestKind | None = None
    reply: str | None = None  # what to say back (answers to questions, clarifications)
    wants_app_approval: bool = False


class ChatModel(Protocol):
    def complete_json(self, system: str, user: str) -> dict: ...


# Folded keywords (see language.fold). Checked in this order: the riskiest Request wins.
_REQUESTS: list[tuple[RequestKind, list[str]]] = [
    (RequestKind.SIM_SWAP, [
        "sim", "password", "reset", "pin", "mpin", "number change", "change number", "mobile number",
        "सिम", "पासवर्ड", "पिन", "ಸಿಮ್", "ಪಾಸ್ವರ್ಡ್", "ಪಿನ್",
    ]),
    (RequestKind.HIGH_VALUE_TRANSFER, [
        "transfer", "neft", "rtgs", "imps", "lakh", "lakhs", "send money", "bhejna", "bhej", "kalisu", "kalisi",
        "ट्रांसफर", "लाख", "भेजना", "पैसे भेज", "ಟ್ರಾನ್ಸ್ಫರ್", "ಲಕ್ಷ", "ಹಣ ಕಳುಹಿಸ", "ಕಳುಹಿಸು",
    ]),
    (RequestKind.ADD_PAYEE, [
        "payee", "beneficiary", "labharthi", "add account",
        "पेयी", "लाभार्थी", "बेनिफिशियरी", "ಪೇಯೀ", "ಫಲಾನುಭವಿ", "ಬೆನಿಫಿಷಿಯರಿ",
    ]),
    (RequestKind.ACCOUNT_SERVICE, [
        "block my card", "block card", "card block", "card limit", "limit", "address", "close account",
        "close my account", "cheque book", "chequebook", "checkbook", "kyc", "email change", "change email",
        "nominee", "upi", "debit card", "credit card", "new card", "unblock",
        "कार्ड", "पता", "चेक बुक", "खाता बंद", "ಕಾರ್ಡ್", "ವಿಳಾಸ", "ಚೆಕ್ ಬುಕ್", "ಖಾತೆ ಮುಚ್ಚ",
    ]),
    (RequestKind.BALANCE_ENQUIRY, [
        "balance", "bakaya", "baki", "kitna paisa", "estu hana", "mini statement",
        "बैलेंस", "बकाया", "बाकी", "ಬ್ಯಾಲೆನ್ಸ್", "ಬಾಕಿ", "ಎಷ್ಟು ಹಣ",
    ]),
]
# Multi-word on purpose: "app" alone folds to "ap", which collides with Hindi "aap" (you).
_APP = [
    "bank app", "in the app", "on the app", "use the app", "app approval", "approve in app",
    "app se", "app mein", "app par", "app nalli", "cannot", "can't", "unable", "nahi kar", "agalla", "agolla",
]
_HUMAN = [
    "human", "real person", "a person", "officer", "agent", "customer care", "talk to someone", "manager",
    "insaan", "kisi se baat", "adhikari", "ಅಧಿಕಾರಿ", "ಮನುಷ್ಯ", "अधिकारी", "इंसान",
]
_REPEAT = [
    "repeat", "again", "say again", "pardon", "sorry what", "didn't hear", "didnt hear", "come again",
    "phir se", "dobara", "fir se", "matte", "innomme", "ಮತ್ತೆ", "फिर से", "दोबारा",
]
_GOODBYE = [
    "bye", "goodbye", "that's all", "thats all", "nothing else", "no thanks", "no thank you", "bas itna",
    "bas", "saku", "ashte", "dhanyavad", "ಸಾಕು", "ಅಷ್ಟೇ", "बस", "धन्यवाद",
]
_QUESTION_MARKERS = [
    "what", "why", "how", "when", "where", "which", "who", "can you", "is it", "do you", "should", "safe",
    "kya", "kyon", "kyu", "kaise", "kab", "kahan", "kaun", "yenu", "yake", "hege", "yavaga", "elli",
    "ಏನು", "ಯಾಕೆ", "ಹೇಗೆ", "ಯಾವಾಗ", "ಎಲ್ಲಿ", "क्या", "क्यों", "कैसे", "कब", "कहाँ",
]

NO_ANSWER = (
    "I can't answer that on this secure line, but the bank app has the details, "
    "or I can connect you to a bank officer."
)


class Faq:
    """Short, general answers the Voice Agent may give (knowledge.yaml)."""

    def __init__(self, entries: list[dict]):
        self.entries = [
            {"id": e["id"], "keys": [fold(k) for k in e["keywords"]], "answer": " ".join(e["answer"].split())}
            for e in entries
        ]

    @classmethod
    def load(cls) -> "Faq":
        text = resources.files("pratyaksh").joinpath("knowledge.yaml").read_text(encoding="utf-8")
        return cls(yaml.safe_load(text))

    def match(self, transcript: str) -> str | None:
        """The answer whose keyword's words all appear in what was said (most specific wins)."""
        said = set(fold(transcript).split())
        best, best_n = None, 0
        for e in self.entries:
            for k in e["keys"]:
                need = set(k.split())
                if need and need <= said and len(need) > best_n:
                    best, best_n = e["answer"], len(need)
        return best

    def as_prompt(self) -> str:
        return "\n".join(f"- {e['answer']}" for e in self.entries)


class Interpreter:
    def __init__(self, llm: ChatModel | None = None, faq: Faq | None = None):
        self._llm = llm
        self._faq = faq or Faq.load()

    def understand(self, transcript: str, during_challenge: bool = False) -> Understanding:
        """What the Caller meant.

        during_challenge: the utterance was a reply to a Challenge. Only off-script turns are
        reported then (REPEAT, QUESTION, APP_APPROVAL, HUMAN); anything else is UNCLEAR and the
        Verifier scores it as the Challenge Response.
        """
        text = transcript.strip()
        if not text:
            return Understanding(TurnKind.UNCLEAR)
        words = f" {fold(text)} "
        has = lambda keys: any(f" {fold(k)} " in words for k in keys)  # noqa: E731
        wants_app = has(_APP)

        if has(_HUMAN):
            return Understanding(TurnKind.HUMAN, wants_app_approval=wants_app)
        if during_challenge:
            if wants_app:
                return Understanding(TurnKind.APP_APPROVAL, wants_app_approval=True)
            if has(_REPEAT):
                return Understanding(TurnKind.REPEAT)
            if self._looks_like_question(text, words):
                return Understanding(TurnKind.QUESTION, reply=self._answer(text))
            return Understanding(TurnKind.UNCLEAR)

        faq = self._faq.match(text)
        if faq and self._looks_like_question(text, words):
            # "Should I share my PIN?" is a question, not a PIN reset Request.
            return Understanding(TurnKind.QUESTION, reply=faq)
        for kind, keys in _REQUESTS:
            if has(keys):
                return Understanding(TurnKind.REQUEST, kind, wants_app_approval=wants_app)
        if wants_app:
            return Understanding(TurnKind.APP_APPROVAL, wants_app_approval=True)
        if has(_REPEAT):
            return Understanding(TurnKind.REPEAT)
        if faq:
            return Understanding(TurnKind.QUESTION, reply=faq)
        if has(_GOODBYE):
            return Understanding(TurnKind.GOODBYE)
        if self._llm is not None:
            return self._ask_llm(text)
        if self._looks_like_question(text, words):
            return Understanding(TurnKind.QUESTION, reply=NO_ANSWER)
        return Understanding(TurnKind.UNCLEAR)

    @staticmethod
    def _looks_like_question(text: str, words: str) -> bool:
        return "?" in text or any(f" {fold(q)} " in words for q in _QUESTION_MARKERS)

    def _answer(self, text: str) -> str:
        faq = self._faq.match(text)
        if faq:
            return faq
        if self._llm is not None:
            u = self._ask_llm(text)
            if u.kind is TurnKind.QUESTION and u.reply:
                return u.reply
        return NO_ANSWER

    def _ask_llm(self, text: str) -> Understanding:
        system = (
            "You are the voice assistant on a bank's secure phone line in India. The caller may mix Kannada, "
            "Hindi and English, possibly romanised. Classify the caller's words and reply with JSON only:\n"
            '{"kind": "request"|"question"|"goodbye"|"human"|"unclear", '
            '"request": "balance_enquiry"|"add_payee"|"sim_swap"|"high_value_transfer"|"account_service"|null, '
            '"reply": string|null}\n'
            "- request: they want the bank to DO something. account_service = any account change not in the other four "
            "(cards, limits, address, closing an account, cheque book, KYC, nominee).\n"
            "- question: they want information. Put a short spoken answer (under 40 words, in the caller's language) "
            "in reply, using ONLY these facts or general safe banking advice:\n"
            f"{self._faq.as_prompt()}\n"
            "  If you don't know, say the bank app has the details or offer a bank officer.\n"
            "- unclear: put one short sentence in reply asking what they need.\n"
            "Rules: never state balances, rates, account data or phone numbers other than the 1930 helpline; never ask "
            "for a PIN, password or OTP; never promise that a request is done; never say a caller is verified."
        )
        try:
            out = self._llm.complete_json(system, text)
            raw = out.get("request")
            request = RequestKind(raw) if raw in RequestKind._value2member_map_ else None
            if out.get("kind") in TurnKind._value2member_map_:
                kind = TurnKind(out["kind"])
            else:
                kind = TurnKind.REQUEST if request else TurnKind.UNCLEAR
            reply = out.get("reply")
            reply = _clean_reply(reply) if isinstance(reply, str) else None
            if kind is TurnKind.REQUEST and request is None:
                kind = TurnKind.UNCLEAR
            if kind is TurnKind.QUESTION and not reply:
                reply = NO_ANSWER
            return Understanding(kind, request if kind is TurnKind.REQUEST else None, reply)
        except Exception as e:  # the LLM is optional; never let it break a Call
            log.warning("LLM interpretation failed: %r", e)
            return Understanding(TurnKind.UNCLEAR)


_DIGITS_RUN = re.compile(r"\d[\d\s-]{5,}\d")


def _clean_reply(reply: str) -> str | None:
    """Keep LLM speech short and free of digit strings (it must never read out codes or numbers)."""
    reply = " ".join(reply.split())
    if not reply or len(reply) > 320:
        return None
    if _DIGITS_RUN.search(reply.replace("1930", "")):
        return None
    return reply


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
