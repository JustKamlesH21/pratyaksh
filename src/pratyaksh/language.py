"""Script-agnostic text normalisation for Kannada, Hindi and English speech.

Speech-to-text may return Kannada script, Devanagari, another Indic script, Latin, or a mix.
Everything is romanised and folded to a rough phonetic form so "ನಾಳೆ", "नाळे" and "naale"
compare equal. Internal to SignalExtractor and the Request classifier.
"""

from __future__ import annotations

import re
import unicodedata

from indic_transliteration import sanscript

# Indic digits in every script sanscript knows, mapped to ASCII.
_INDIC_SCRIPTS = [
    sanscript.DEVANAGARI, sanscript.KANNADA, sanscript.TELUGU, sanscript.TAMIL, sanscript.MALAYALAM,
    sanscript.BENGALI, sanscript.GUJARATI, sanscript.GURMUKHI, sanscript.ORIYA,
]
_DIGIT_BASES = [0x0966, 0x0CE6, 0x0C66, 0x0BE6, 0x0D66, 0x09E6, 0x0AE6, 0x0A66, 0x0B66]
_INDIC_DIGITS = {base + i: str(i) for base in _DIGIT_BASES for i in range(10)}
_JOINERS = {0x200C: None, 0x200D: None}  # ZWNJ / ZWJ split words like ಪಾಸ್‌ವರ್ಡ್

# Spoken digit words in English, Hindi and Kannada (folded at import so they match fold()).
_DIGIT_SPELLINGS = {
    "0": ["zero", "oh", "shunya", "sunya", "sonne"],
    "1": ["one", "ek", "ondu"],
    "2": ["two", "do", "eradu", "erdu"],
    "3": ["three", "teen", "mooru", "muru"],
    "4": ["four", "chaar", "char", "naalku", "nalku"],
    "5": ["five", "paanch", "panch", "aidu"],
    "6": ["six", "chhe", "chah", "chhah", "aaru"],
    "7": ["seven", "saat", "elu", "yelu"],
    "8": ["eight", "aath", "entu", "yentu"],
    "9": ["nine", "nau", "ombattu", "ombatu", "onbattu"],
}
_REPEATS = {"double": 2, "dabal": 2, "triple": 3, "tripal": 3}


def romanise(text: str) -> str:
    """Indic scripts to IAST, then strip diacritics. Latin passes through."""
    text = text.translate(_INDIC_DIGITS).translate(_JOINERS)
    for script in _INDIC_SCRIPTS:
        text = sanscript.transliterate(text, script, sanscript.IAST)
    # anusvara and chandrabindu both sound like a nasal "n" here (पाँच -> panch)
    text = text.replace("ṃ", "n").replace("ṁ", "n").replace("m̐", "n").replace("~", "n")
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _fold_word(w: str) -> str:
    w = w.replace("ee", "i").replace("oo", "u").replace("aa", "a").replace("w", "v")
    w = re.sub(r"([bcdgjkpt])h", r"\1", w)  # aspiration: bh->b, th->t
    w = re.sub(r"([a-z])\1+", r"\1", w)  # doubled letters (never digits: "00" stays)
    if len(w) >= 3 and w.endswith("a") and w[-2] not in "aeiou":
        w = w[:-1]  # Hindi schwa deletion: "milna"/"miln" agree
    return w


def fold(text: str) -> str:
    """Romanise, lowercase, drop punctuation, fold spelling variants. Returns space-joined words."""
    words = re.findall(r"[a-z0-9]+", romanise(text).lower())
    return " ".join(_fold_word(w) for w in words)


def fold_with_digits(text: str) -> str:
    """fold(), then replace spoken digit words with digits ("saat" -> "7")."""
    return " ".join(_DIGIT_WORDS.get(w, w) for w in fold(text).split())


def spoken_digits(text: str) -> str:
    """Every digit the Caller said, in order. "four 8 ondu" -> "481", "double four" -> "44"."""
    digits: list[str] = []
    repeat = 1
    for w in fold(text).split():
        if w in _REPEATS:
            repeat = _REPEATS[w]
            continue
        if w.isdigit():
            digits.append(w[0] * repeat + w[1:])
        elif w in _DIGIT_WORDS:
            digits.append(_DIGIT_WORDS[w] * repeat)
        repeat = 1
    return "".join(digits)


_DIGIT_WORDS: dict[str, str] = {
    _fold_word(w): digit for digit, words in _DIGIT_SPELLINGS.items() for w in words
}
_REPEATS = {_fold_word(k): v for k, v in _REPEATS.items()}
