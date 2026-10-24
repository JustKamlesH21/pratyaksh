"""Interpreter: understand any Caller utterance, so the Voice Agent never gets stuck.

Internal to the Verifier. Keyword rules run first (fast, offline, deterministic); the LLM
handles everything else (ADR-0002: it may talk about anything, but it never decides a Verdict,
never reveals account data and never skips a Challenge). Questions are answered from
knowledge.yaml with the answer that fits where the Call is: before a Request, during a Whisper
Phrase or during a Possession Code.

Seam: ChatModel (OllamaChat in production, a stub in tests).
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources
from typing import Protocol

import httpx
import yaml

from ..domain import ChallengeKind, RequestKind
from ..language import fold

log = logging.getLogger(__name__)


class TurnKind(StrEnum):
    REQUEST = "request"  # the Caller asked the bank to do something
    QUESTION = "question"  # the Caller asked for information
    CHAT = "chat"  # small talk: "hello?", "thanks", "what can you do?"
    REPEAT = "repeat"  # "say that again", "I can't hear you"
    WAIT = "wait"  # "hold on", "let me open the app"
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


@dataclass(frozen=True)
class Context:
    """Where the Call is, so answers fit the moment."""

    challenge: ChallengeKind | None = None  # the Challenge the Caller is answering, if any
    request: RequestKind | None = None
    last_said: str = ""  # the Voice Agent's last prompt


class ChatModel(Protocol):
    def complete_json(self, system: str, user: str) -> dict: ...


_Phrase = tuple[tuple[str, int | None], ...]  # folded words, each with the stem length it may match from


def _phrase(text: str, stems_from: int | None = None) -> _Phrase:
    """Fold a keyword phrase. A word ending in "*" matches as a stem: Kannada and Hindi add
    suffixes ("ಅಧಿಕಾರಿ*" matches "ಅಧಿಕಾರಿಯ"). stems_from: every word this long matches as a stem."""
    out: list[tuple[str, int | None]] = []
    for token in text.split():
        words = fold(token.rstrip("*")).split()
        out += [(w, stems_from) for w in words[:-1]]
        if words:
            out.append((words[-1], 1 if token.endswith("*") else stems_from))
    return tuple(out)


def _same(key: str, stem: int | None, word: str) -> bool:
    return word == key or (stem is not None and len(key) >= stem and word.startswith(key))


class _Keys:
    """Keyword phrases, folded once. A phrase matches when its words appear in a row."""

    def __init__(self, phrases: list[str]):
        self._phrases = [p for p in map(_phrase, phrases) if p]

    def found_in(self, said: list[str]) -> bool:
        for words in self._phrases:
            for i in range(len(said) - len(words) + 1):
                if all(_same(w, stem, said[i + j]) for j, (w, stem) in enumerate(words)):
                    return True
        return False


# Checked in this order: the riskiest Request wins.
_REQUESTS: list[tuple[RequestKind, _Keys]] = [
    (RequestKind.SIM_SWAP, _Keys([
        "sim", "password", "reset", "pin", "mpin", "number change", "change number", "mobile number",
        "सिम", "पासवर्ड", "पिन", "ಸಿಮ್", "ಪಾಸ್ವರ್ಡ್", "ಪಿನ್",
    ])),
    (RequestKind.HIGH_VALUE_TRANSFER, _Keys([
        "transfer", "neft", "rtgs", "imps", "lakh", "lakhs", "send money", "bhejna", "bhej", "kalisu", "kalisi",
        "ट्रांसफर", "लाख", "भेज*", "ಟ್ರಾನ್ಸ್ಫರ್*", "ಲಕ್ಷ", "ಕಳುಹಿಸ*",
    ])),
    (RequestKind.ADD_PAYEE, _Keys([
        "payee", "beneficiary", "labharthi", "add account",
        "पेयी", "लाभार्थी*", "बेनिफिशियरी", "ಪೇಯೀ", "ಫಲಾನುಭವಿ*", "ಬೆನಿಫಿಷಿಯರಿ",
    ])),
    (RequestKind.ACCOUNT_SERVICE, _Keys([
        "block my card", "block card", "card block", "card limit", "limit", "address", "close account",
        "close my account", "cheque book", "chequebook", "checkbook", "kyc", "email change", "change email",
        "nominee", "upi", "debit card", "credit card", "new card", "unblock",
        "कार्ड", "पता", "चेक बुक", "खाता बंद", "ಕಾರ್ಡ್*", "ವಿಳಾಸ*", "ಚೆಕ್ ಬುಕ್", "ಖಾತೆ ಮುಚ್ಚ*",
    ])),
    (RequestKind.BALANCE_ENQUIRY, _Keys([
        "balance", "bakaya", "baki", "kitna paisa", "estu hana", "mini statement", "how much money",
        "बैलेंस", "बकाया", "बाकी", "ಬ್ಯಾಲೆನ್ಸ್*", "ಬಾಕಿ", "ಎಷ್ಟು ಹಣ",
    ])),
]
# Asking for the app, or saying a voice task is not possible. Multi-word on purpose: "app"
# alone folds to "ap", which collides with Hindi "aap" (you); a bare "can't" may be "can't hear".
_APP = _Keys([
    "bank app", "in the app", "on the app", "use the app", "app approval", "approve in app",
    "app se", "app mein", "app par", "app nalli",
    "can't whisper", "cannot whisper", "can not whisper", "can't speak", "cannot speak", "can't talk",
    "can't do this", "can't do it", "can't do that", "cannot do this", "cannot do it", "unable to",
    "not comfortable", "uncomfortable", "sore throat", "nahi kar", "nahi bol", "agalla", "agolla",
    "नहीं कर", "नहीं बोल", "ಆಗಲ್ಲ", "ಆಗೋಲ್ಲ",
])
# Asking for a person: someone to talk to ("let me talk to a real person", "officer please").
_PERSON = _Keys([
    "human", "person", "someone", "somebody", "officer", "agent", "executive", "customer care", "manager",
    "staff", "insaan", "adhikari", "kisi se", "ಅಧಿಕಾರಿ*", "ಮನುಷ್ಯ*", "ವ್ಯಕ್ತಿ*", "अधिकारी", "इंसान", "किसी से",
])
_CONNECT = _Keys([
    "talk", "speak", "connect", "put me through", "transfer me", "transfer the call", "want a", "need a",
    "please", "baat", "matad*", "matanad*", "ಮಾತಾಡ*", "ಮಾತನಾಡ*", "बात",
])
_OFFICER = _Keys(["officer", "adhikari", "ಅಧಿಕಾರಿ*", "अधिकारी"])
_CANT_HEAR = _Keys([
    "can't hear", "cannot hear", "can not hear", "couldn't hear", "could not hear", "didn't hear", "did not hear",
    "not audible", "voice is breaking", "sunai nahi", "sunayi nahi", "kelisutilla", "kelstilla", "kelsalilla",
    "ಕೇಳಿಸುತ್ತಿಲ್ಲ", "ಕೇಳಿಸ್ತಿಲ್ಲ", "ಕೇಳಿಸಲಿಲ್ಲ", "सुनाई नहीं",
])
_REPEAT = _Keys([
    "repeat", "again", "say again", "pardon", "sorry what", "come again", "slowly", "slower", "too fast",
    "slow down", "huh", "what were the words", "what was the word", "which word", "which words", "what words",
    "first word", "second word", "third word", "last word", "what do i say", "what should i say",
    "what do i have to say", "what do i have to whisper", "what should i whisper",
    "don't understand", "didn't understand", "do not understand", "not understood",
    "phir se", "fir se", "dobara", "dheere", "kya bolna", "kya bolu", "samajh nahi",
    "matte", "innomme", "nidhana", "enu helbeku", "enu helali", "artha agilla",
    "ಮತ್ತೆ", "ಅರ್ಥ ಆಗಿಲ್ಲ", "ಏನು ಹೇಳಬೇಕು", "फिर से", "दोबारा", "समझ नहीं", "क्या बोलना",
])
_WAIT = _Keys([
    "wait", "hold on", "one second", "one sec", "a second", "one moment", "a moment", "just a moment",
    "one minute", "a minute", "give me a", "let me check", "let me open", "let me think", "let me see",
    "opening the app", "ek second", "ek minute", "ek min", "ruko", "rukiye", "ruk", "thoda ruk",
    "ondu nimisha", "ondu second", "swalpa iri", "iri", "ಒಂದು ನಿಮಿಷ", "ಸ್ವಲ್ಪ ಇರಿ", "एक मिनट", "रुको", "रुकिए",
])
_GOODBYE = _Keys([
    "bye", "goodbye", "that's all", "thats all", "nothing else", "no thanks", "no thank you", "bas itna",
    "bas", "saku", "ashte", "dhanyavad", "ಸಾಕು", "ಅಷ್ಟೇ", "बस", "धन्यवाद",
])
# The Caller wants it done, not explained ("is it safe? I want to transfer 6 lakh").
_DO_IT = _Keys([  # "I need to", not "I need": "what documents do I need?" is only a Question
    "i want to", "i wanna", "i need to", "i would like to", "i d like to", "please", "can you", "could you", "help me",
    "mujhe", "karna hai", "karni hai", "kar do", "kardo", "kar dijiye", "kijiye", "chahta", "chahti",
    "beku", "madbeku", "madi", "ಬೇಕು", "ಮಾಡಿ", "करना है", "करनी है", "कर दो", "चाहता", "चाहती", "मुझे",
])
_QUESTION_MARKERS = _Keys([
    "what", "why", "how", "when", "where", "which", "who", "can you", "can i", "is it", "is there", "are there",
    "are you", "will you", "do you", "do i", "does", "should", "safe", "tell me", "want to know",
    "kya", "kyon", "kyu", "kaise", "kab", "kahan", "kaun", "kitna", "kitne", "kaunsa", "batao", "bataiye",
    "yenu", "enu", "yake", "hege", "yavaga", "elli", "estu", "yava",
    "ಏನು", "ಯಾಕೆ", "ಹೇಗೆ", "ಯಾವಾಗ", "ಎಲ್ಲಿ", "ಎಷ್ಟು", "ಯಾವ", "क्या", "क्यों", "कैसे", "कब", "कहाँ", "कितना", "कौन",
])

NO_ANSWER = (
    "I can't answer that on this secure line, but the bank app has the details, "
    "or I can connect you to a bank officer."
)


@dataclass(frozen=True)
class _Entry:
    id: str
    keys: list[_Phrase]
    answer: str
    during: ChallengeKind | None  # only during this Challenge
    small_talk: bool
    report: bool  # a problem report: answered even when it mentions a Request


class Faq:
    """Short, general answers the Voice Agent may give (knowledge.yaml)."""

    def __init__(self, entries: list[dict]):
        self.entries = [
            _Entry(
                e["id"],
                [k for k in (_phrase(str(k), stems_from=4) for k in e["keywords"]) if k],  # "record" ~ "recorded"
                " ".join(e["answer"].split()),
                ChallengeKind(e["during"]) if e.get("during") else None,
                bool(e.get("small_talk")),
                bool(e.get("report")),
            )
            for e in entries
        ]
        # Rare keyword words count for more than common ones, so "ifsc code" beats "what code".
        df = Counter(w for e in self.entries for w in {w for key in e.keys for w, _ in key})
        self._weight = {w: math.log(1 + len(self.entries) / n) for w, n in df.items()}

    @classmethod
    def load(cls) -> "Faq":
        text = resources.files("pratyaksh").joinpath("knowledge.yaml").read_text(encoding="utf-8")
        return cls(yaml.safe_load(text))

    def match(self, said: list[str], challenge: ChallengeKind | None = None, small_talk: bool = False) -> _Entry | None:
        """The entry whose keyword's words all appear in what was said. Entries for the current
        Challenge are preferred; entries for another Challenge are never used."""
        best, best_score = None, 0.0
        for e in self.entries:
            if e.small_talk != small_talk or (e.during is not None and e.during is not challenge):
                continue
            for key in e.keys:
                if all(any(_same(w, stem, s) for s in said) for w, stem in key):
                    score = sum(self._weight[w] for w, _ in key) * (2 if e.during is not None else 1)
                    if score > best_score:
                        best, best_score = e, score
        return best

    def as_prompt(self) -> str:
        return "\n".join(f"- {answer}" for answer in dict.fromkeys(e.answer for e in self.entries))


class Interpreter:
    def __init__(self, llm: ChatModel | None = None, faq: Faq | None = None):
        self._llm = llm
        self._faq = faq or Faq.load()

    def understand(self, transcript: str, context: Context = Context()) -> Understanding:
        """What the Caller meant, given where the Call is.

        During a Challenge only off-script turns are reported (QUESTION, CHAT, REPEAT, WAIT,
        APP_APPROVAL, HUMAN); anything else is UNCLEAR and the Verifier scores it as the Response.
        """
        text = transcript.strip()
        if not text:
            return Understanding(TurnKind.UNCLEAR)
        said = fold(text).split()
        wants_app = _APP.found_in(said)
        if _OFFICER.found_in(said) or (_PERSON.found_in(said) and _CONNECT.found_in(said)):
            return Understanding(TurnKind.HUMAN, wants_app_approval=wants_app)
        if _CANT_HEAR.found_in(said):
            return Understanding(TurnKind.REPEAT)
        question = "?" in text or _QUESTION_MARKERS.found_in(said)
        if context.challenge is not None:
            return self._during_challenge(text, said, question, wants_app, context)

        answer = self._faq.match(said)
        request = next((kind for kind, keys in _REQUESTS if keys.found_in(said)), None)
        if answer and (question or answer.report):
            # "Should I share my PIN?" is a Question, not a PIN reset Request, and "someone transferred
            # money from my account" is a fraud report. "Is this safe? I want to transfer 6 lakh" is
            # both: answer it, then carry on with the Request.
            if request and _DO_IT.found_in(said):
                return Understanding(TurnKind.REQUEST, request, answer.answer, wants_app)
            return Understanding(TurnKind.QUESTION, reply=answer.answer)
        if request:
            return Understanding(TurnKind.REQUEST, request, wants_app_approval=wants_app)
        if wants_app:
            return Understanding(TurnKind.APP_APPROVAL, wants_app_approval=True)
        if _REPEAT.found_in(said):
            return Understanding(TurnKind.REPEAT)
        if _WAIT.found_in(said):
            return Understanding(TurnKind.WAIT)
        if answer:  # "I lost my phone", "there's a transaction I didn't make"
            return Understanding(TurnKind.QUESTION, reply=answer.answer)
        if _GOODBYE.found_in(said):
            return Understanding(TurnKind.GOODBYE)
        if self._llm is not None:  # before canned small talk: it handles "hello, my money went…" better
            return self._ask_llm(text, context)
        chat = self._faq.match(said, small_talk=True)
        if chat:
            return Understanding(TurnKind.CHAT, reply=chat.answer)
        if question:
            return Understanding(TurnKind.QUESTION, reply=NO_ANSWER)
        return Understanding(TurnKind.UNCLEAR)

    def _during_challenge(self, text: str, said: list[str], question: bool, wants_app: bool,
                          context: Context) -> Understanding:
        answer = self._faq.match(said, context.challenge)
        if answer and answer.during is not None:  # about this Challenge: "I didn't get the code"
            return Understanding(TurnKind.QUESTION, reply=answer.answer)
        if wants_app:
            return Understanding(TurnKind.APP_APPROVAL, wants_app_approval=True)
        if _REPEAT.found_in(said):
            return Understanding(TurnKind.REPEAT)
        if _WAIT.found_in(said):
            return Understanding(TurnKind.WAIT)
        if answer and (question or answer.report):
            return Understanding(TurnKind.QUESTION, reply=answer.answer)
        chat = self._faq.match(said, small_talk=True)
        if chat:
            return Understanding(TurnKind.CHAT, reply=chat.answer)
        if not question:
            return Understanding(TurnKind.UNCLEAR)
        if self._llm is not None:  # only Questions, Repeats and Waits: keywords alone change the Call's path
            u = self._ask_llm(text, context)
            if u.kind in (TurnKind.REPEAT, TurnKind.WAIT):
                return Understanding(u.kind)
            if u.kind is TurnKind.QUESTION and u.reply:
                return u
        return Understanding(TurnKind.QUESTION, reply=NO_ANSWER)

    def _ask_llm(self, text: str, context: Context) -> Understanding:
        system = (
            "You are the voice assistant on a bank's secure phone line in India. The caller may mix Kannada, "
            "Hindi and English, possibly romanised. Classify the caller's words and reply with JSON only:\n"
            '{"kind": "request"|"question"|"repeat"|"wait"|"goodbye"|"human"|"unclear", '
            '"request": "balance_enquiry"|"add_payee"|"sim_swap"|"high_value_transfer"|"account_service"|null, '
            '"reply": string|null}\n'
            f"Where the call is: {_where(context)}\n"
            "- request: they want the bank to DO something. account_service = any account change not in the other four "
            "(cards, limits, address, closing an account, cheque book, KYC, nominee).\n"
            "- question: they want information, or are making small talk. Put a short spoken answer (under 40 words, "
            "in the language the caller used) in reply, using ONLY these facts or general safe banking advice:\n"
            f"{self._faq.as_prompt()}\n"
            "  If you don't know, say the bank app has the details or offer a bank officer.\n"
            "- repeat: they want to hear the last thing again. wait: they need a moment.\n"
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
            if kind in (TurnKind.QUESTION, TurnKind.CHAT) and not reply:
                kind, reply = TurnKind.QUESTION, NO_ANSWER
            return Understanding(kind, request if kind is TurnKind.REQUEST else None, reply)
        except Exception as e:  # the LLM is optional; never let it break a Call
            log.warning("LLM interpretation failed: %r", e)
            return Understanding(TurnKind.UNCLEAR)


def _where(context: Context) -> str:
    if context.challenge is ChallengeKind.WHISPER_PHRASE:
        where = "in a security check; the caller was asked to whisper a random phrase."
    elif context.challenge is ChallengeKind.POSSESSION_CODE:
        where = ("in a security check; the caller was asked to read out a six-digit code shown in the bank app "
                 "on their registered phone.")
    else:
        where = "the caller has not said what they need yet."
    if context.request is not None:
        where += f" Their request: {context.request.value.replace('_', ' ')}."
    if context.last_said:
        where += f' You last said: "{context.last_said}"'
    return where


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
