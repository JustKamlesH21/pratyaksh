"""Script-agnostic text normalisation for Kannada, Hindi and English speech.

Speech-to-text may return Kannada script, Devanagari, another Indic script, Latin, or a mix.
Everything is romanised and folded to a rough phonetic form so "ನಾಳೆ", "नाळे" and "naale"
compare equal. sound_key() goes further, for loanwords that speech-to-text spells many ways.
language_of() tells which of the three a Caller spoke, so answers match it.
Internal to SignalExtractor and the Interpreter.
"""

from __future__ import annotations

import re
import unicodedata

from indic_transliteration import sanscript
from rapidfuzz import fuzz

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
    "8": ["eight", "ate", "aath", "entu", "yentu"],
    "9": ["nine", "nau", "ombattu", "ombatu", "onbattu"],
}
_REPEATS = {"double": 2, "dabal": 2, "triple": 3, "tripal": 3}
# How speech-to-text spells Hindi digit words in a code readout (folded; Parler reading 40 codes, Oct 30).
# Read as digits only in spoken_digits: several are ordinary words elsewhere ("आज" today, "दिन" day), so a
# Whisper Phrase or a Request never sees them. A wrong spelling here can only fail to match a code, never
# match one the Caller does not hold.
_CODE_ONLY_DIGITS = {
    "ce": "6", "cai": "6", "cek": "6", "sek": "6",               # चे, छे, चै, चेक, शेक (छह)
    "din": "3", "tim": "3", "tin": "3", "team": "3",             # दीन, तीम, tin, team (तीन)
    "pac": "5", "bac": "5", "banc": "5", "punc": "5",            # पाच, बाच, banch, punch (पाँच)
    "sar": "4",                                # शार (चार)
    "sunyo": "0", "sunyu": "0", "suniy": "0",  # शून्यो, शून्यू, शुनिय (शून्य)
    "aj": "8", "ac": "8",                      # आज, आच (आठ)
    "don": "2", "dol": "2", "dole": "2",       # डों, डोल, dole (दो), in a noisy hall (Oct 31)
}


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


def sound_key(word: str) -> str:
    """A folded word's consonant skeleton, for words speech-to-text spells many ways: English
    loanwords written in Devanagari or Kannada script ("बैलेंस", "ಬ್ಯಾಲನ್ಸ್" and "balance" all give
    "blns"). Keeps the first letter, drops later vowels and "y", and merges f/p, v/b, soft c/s."""
    w = re.sub(r"c(?=[eiy])", "s", word)
    w = w.replace("ck", "k").replace("c", "k").replace("f", "p").replace("v", "b").replace("z", "j").replace("q", "k")
    w = w[:1] + re.sub(r"[aeiouy]", "", w[1:])
    return re.sub(r"(.)\1+", r"\1", w)


def fold_with_digits(text: str) -> str:
    """fold(), then replace spoken digit words with digits ("saat" -> "7")."""
    return " ".join(_DIGIT_WORDS.get(w, w) for w in fold(text).split())


def near_digit(word: str) -> str | None:
    """The digit a folded word nearly spells ("ent" -> "8", a clipped whispered "entu"), or None. Only a
    close match that is clearly closer to one digit than to any other: "endu" is as near 2 ("erdu") as
    8, and "sone" is "sonne" (0) not "one" (1), so neither counts."""
    if not word.isalpha() or word in _DIGIT_WORDS:
        return None
    best: dict[str, float] = {}
    for spelling, digit in _DIGIT_WORDS.items():
        best[digit] = max(best.get(digit, 0.0), fuzz.ratio(word, spelling))
    (top, score), runner_up = sorted(best.items(), key=lambda kv: -kv[1])[0], sorted(best.values())[-2]
    return top if score >= 85 and score - runner_up >= 10 else None


def spoken_digits(text: str) -> str:
    """Every digit the Caller said, in order. "four 8 ondu" -> "481", "double four" -> "44"."""
    digits: list[str] = []
    repeat = 1
    for w in _split_fused_digits(fold(text).split()):
        if w in _REPEATS:
            repeat = _REPEATS[w]
            continue
        if w.isdigit():
            digits.append(w[0] * repeat + w[1:])
        elif w in _DIGIT_WORDS:
            digits.append(_DIGIT_WORDS[w] * repeat)
        elif w in _CODE_ONLY_DIGITS:
            digits.append(_CODE_ONLY_DIGITS[w] * repeat)
        repeat = 1
    return "".join(digits)


def _split_fused_digits(words: list[str]) -> list[str]:
    """Speech-to-text writes a spoken "eight" fused to the digits as the letter A ("A26701", iPhone
    Call, Oct 29). A word mixing letters and digits is split into its runs, and an "a" run is an 8."""
    out: list[str] = []
    for w in words:
        if w.isalpha() or w.isdigit():
            out.append(w)
            continue
        out.extend("8" if run == "a" else run for run in re.findall(r"[a-z]+|[0-9]+", w))
    return out


def language_of(text: str) -> str:
    """The language the Caller spoke: "hi", "kn" or "en". Native script decides; romanised Hindi
    and Kannada are recognised by their common words. Mostly-English code-mixing is English."""
    hi = kn = total = 0
    for token in text.split():
        words = fold(token).split()
        if not words:
            continue
        total += 1
        if any("ऀ" <= ch <= "ॿ" for ch in token):
            hi += 1
        elif any("ಀ" <= ch <= "೿" for ch in token):
            kn += 1
        elif words[0] in _HINDI_WORDS:
            hi += 1
        elif words[0] in _KANNADA_WORDS:
            kn += 1
    if not total or max(hi, kn) / total < 0.4:
        return "en"
    return "hi" if hi >= kn else "kn"


_DIGIT_WORDS: dict[str, str] = {
    _fold_word(w): digit for digit, words in _DIGIT_SPELLINGS.items() for w in words
}
_REPEATS = {_fold_word(k): v for k, v in _REPEATS.items()}
# Common romanised words (not "aap": it folds like "app"; not "hana": it folds like "haan").
_HINDI_WORDS = set(fold(
    "hai hain kya kyon kyu kaise kab kahan kaun mera meri mere mujhe nahi nahin karna karni karu karo kar raha "
    "rahi gaya gayi kitna kitne chahiye liye kisi dena milega batao bataiye khulta khulti hota paisa paise khata "
    "ho ya bhi aur se ko ke ki pe par insaan kho haan aaya aayi aaye mila mili hua hui karte karti karta sakte "
    "sakti sakta khole kholna kholu lagega lagta dijiye kijiye bolna bolo bolu samajh ek"
).split())
_KANNADA_WORDS = set(fold(
    "nanna nanage nimma nimage neevu naanu enu yenu yake hege yavaga elli estu illa ide ideya beku maadi madbeku "
    "agide aagutte alli hogide hoythu banthilla bandilla kaledu hosa swalpa ondu sigtilla gottilla heli helbeku "
    "jothe yaaru yaara iddini aaytu mattu barutte bartide bandide aagilla maadodu kalisi helali torisi"
).split())
