"""Whisper Phrase banks, one per Customer language: short everyday sentences a Caller can whisper
after hearing them once ("party at seven tonight", "kal seven baje meeting hai").

English Customers get English phrases; Hindi and Kannada Customers get their language mixed with the
English words everyone uses. Each template has a digit slot and word slots, so the phrase is
unpredictable within a bank small enough to voice ahead of time (a few hundred per language). The
random digit and the Possession Code carry the security: a large bank never stopped a Clone, which can
voice every phrase in minutes (red-team, Oct 27).
pronunciation() gives the spelling the Voice Agent's voice reads clearly: Hindi words in Devanagari,
Kannada words in Kannada script (it reads romanised Indian words poorly).
Internal to the Verifier; exposed for the Eval Run and red-team tooling.
"""

from __future__ import annotations

import itertools
import random

LANGUAGES = ("en", "hi", "kn")

_EVENT = ["meeting", "dinner", "party", "class", "interview"]
_RIDE = ["bus", "train", "flight"]
_PLACE = ["office", "college", "station", "hospital"]

# language -> (templates, slot words). {d} is a spoken digit.
BANKS: dict[str, tuple[list[str], dict[str, list[str]]]] = {
    "en": (
        [
            "{event} on {day} at {d}",
            "{event} at {d} {daytime}",
            "{ride} is {d} hours late",
            "{food} ready in {d} minutes",
            "{d} {people} are coming home",
        ],
        {
            "event": _EVENT, "ride": _RIDE,
            "day": ["monday", "wednesday", "friday", "sunday"],
            "daytime": ["today", "tonight", "tomorrow"],
            "food": ["tea", "coffee", "dinner", "pizza"],
            "people": ["guests", "friends", "cousins"],
        },
    ),
    "hi": (
        [
            "{when} {d} baje {event} hai",
            "{d} kilo {item} lao",
            "ghar mein {d} {people} hain",
            "{food} {d} minute mein ready",
            "{ride} {d} ghante late hai",
            "{d} baje {place} pahunchna hai",
        ],
        {
            "event": _EVENT, "ride": _RIDE, "place": _PLACE,
            "when": ["aaj", "kal", "monday", "friday", "sunday"],
            "item": ["chawal", "cheeni", "aloo", "pyaaz"],
            "people": ["mehmaan", "dost", "bachche"],
            "food": ["chai", "coffee", "khana", "samosa"],
        },
    ),
    "kn": (
        [
            "{when} {d} gantege {event} ide",
            "{d} kilo {item} tagondu baa",
            "maneli {d} {people} iddare",
            "{food} {d} nimishadalli ready",
            "{ride} {d} gante late",
            "{d} gantege {place} ge banni",
        ],
        {
            "event": _EVENT, "ride": _RIDE, "place": _PLACE,
            "when": ["naale", "ivattu", "monday", "friday", "sunday"],
            "item": ["akki", "sakkare", "eerulli", "tomato"],
            "people": ["guests", "friends", "cousins"],
            "food": ["coffee", "tea", "dosa", "oota"],
        },
    ),
}
DIGITS = range(2, 10)  # 0 and 1 sound alike across the three languages too often

# The digit is said in the Customer's language (language.fold_with_digits reads all three back).
_DIGIT_NAMES = {
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"],
    "hi": ["shunya", "ek", "do", "teen", "chaar", "paanch", "chhah", "saat", "aath", "nau"],
    "kn": ["sonne", "ondu", "eradu", "mooru", "naalku", "aidu", "aaru", "elu", "entu", "ombattu"],
}

# How the Voice Agent's voice should read each Hindi or Kannada word (see the module docstring).
_SPELLING: dict[str, dict[str, str]] = {
    "hi": {
        "aaj": "आज", "kal": "कल", "baje": "बजे", "hai": "है", "hain": "हैं", "kilo": "किलो", "lao": "लाओ",
        "ghar": "घर", "mein": "में", "ghante": "घंटे", "pahunchna": "पहुँचना", "chawal": "चावल", "cheeni": "चीनी",
        "aloo": "आलू", "pyaaz": "प्याज़", "mehmaan": "मेहमान", "dost": "दोस्त", "bachche": "बच्चे",
        "chai": "चाय", "khana": "खाना", "samosa": "समोसा",
        "do": "दो", "teen": "तीन", "chaar": "चार", "paanch": "पाँच", "chhah": "छह", "saat": "सात", "aath": "आठ",
        "nau": "नौ",
    },
    "kn": {
        "naale": "ನಾಳೆ", "ivattu": "ಇವತ್ತು", "gantege": "ಗಂಟೆಗೆ", "gante": "ಗಂಟೆ", "ide": "ಇದೆ", "kilo": "ಕಿಲೋ",
        "tagondu": "ತಗೊಂಡು", "baa": "ಬಾ", "maneli": "ಮನೇಲಿ", "iddare": "ಇದ್ದಾರೆ", "nimishadalli": "ನಿಮಿಷದಲ್ಲಿ",
        "ge": "ಗೆ", "banni": "ಬನ್ನಿ", "akki": "ಅಕ್ಕಿ", "sakkare": "ಸಕ್ಕರೆ", "eerulli": "ಈರುಳ್ಳಿ", "dosa": "ದೋಸೆ",
        "oota": "ಊಟ",
        "eradu": "ಎರಡು", "mooru": "ಮೂರು", "naalku": "ನಾಲ್ಕು", "aidu": "ಐದು", "aaru": "ಆರು", "elu": "ಏಳು",
        "entu": "ಎಂಟು", "ombattu": "ಒಂಬತ್ತು",
    },
}


def random_phrase(rng: random.Random, language: str = "en") -> str:
    """A Whisper Phrase in the Customer's language. Every phrase of that bank is equally likely."""
    templates, words = BANKS[_bank(language)]
    (template,) = rng.choices(templates, weights=[_variants(t, words) for t in templates])
    return template.format(d=rng.choice(DIGITS), **{slot: rng.choice(options) for slot, options in words.items()})


def all_phrases(language: str | None = None) -> list[str]:
    """Every Whisper Phrase random_phrase() can produce (for one language, or all), so their prompts
    can be voiced ahead of time."""
    out = []
    for lang in [language] if language else LANGUAGES:
        templates, words = BANKS[_bank(lang)]
        for template in templates:
            slots = [s for s in words if "{" + s + "}" in template]
            for d, filled in itertools.product(DIGITS, itertools.product(*(words[s] for s in slots))):
                out.append(template.format(d=d, **dict(zip(slots, filled))))
    return list(dict.fromkeys(out))


def phrase_pool(language: str, size: int) -> list[str]:
    """`size` phrases spread evenly across the bank, the same ones every time, so they can be voiced first."""
    phrases = all_phrases(language)
    return phrases[:: max(1, len(phrases) // size)][:size]


def phrase_count(language: str | None = None) -> int:
    """How many different Whisper Phrases random_phrase() can produce (for one language, or all)."""
    return len(all_phrases(language))


def speakable(phrase: str, language: str = "en") -> str:
    """The phrase as the Voice Agent should say it: the digit as a word in the Customer's language."""
    names = _DIGIT_NAMES[_bank(language)]
    return " ".join(names[int(w)] if w.isdigit() and len(w) == 1 else w for w in phrase.split())


def pronunciation(word: str, language: str) -> str:
    """The spelling the voice reads clearly: native script for a Hindi or Kannada word, else the word."""
    return _SPELLING.get(language, {}).get(word, word)


def spoken(phrase: str, language: str) -> str:
    """The phrase as the Voice Agent says and captions it: Hindi or Kannada words (the digit too) in
    their own script, English words as written. "kal 7 baje meeting hai" -> "कल सात बजे meeting है"."""
    text = " ".join(pronunciation(w, language) for w in speakable(phrase, language).split())
    return text[:1].upper() + text[1:]


def _bank(language: str) -> str:
    return language if language in BANKS else "en"


def _variants(template: str, words: dict[str, list[str]]) -> int:
    n = len(DIGITS)
    for slot, options in words.items():
        if "{" + slot + "}" in template:
            n *= len(options)
    return n
