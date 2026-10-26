"""Whisper Phrase bank: short phrases that mix Kannada, Hindi and English words.

Each template has a digit slot and word slots, so the phrase is unpredictable.
Internal to the Verifier; exposed only for the Eval Run tooling.
"""

from __future__ import annotations

import itertools
import random

# (template, meaning) — words: Kannada, Hindi, English. {d} is a spoken digit; every other
# {slot} is filled from WORDS, so a Clone cannot be pre-recorded for every phrase in advance.
TEMPLATES: list[tuple[str, str]] = [
    ("{when} {d} baje {event}", "{event} {when} at {d}"),
    ("{d} kilo {item} lao", "bring {d} kilos of {item}"),
    ("{food} {d} minute alli ready", "{food} ready in {d} minutes"),
    ("{ride} {d} gante late hai", "the {ride} is {d} hours late"),
    ("mane mein {d} {people}", "{d} {people} at home"),
    ("{device} {d} baar ring aaytu", "the {device} rang {d} times"),
    ("{place} alli {d} baje {event}", "{event} at the {place} at {d}"),
    ("naanu {d} baje {place} ge baruttene", "I will come to the {place} at {d}"),
]
WORDS: dict[str, list[str]] = {
    "when": ["naale", "ivattu", "sanje", "beligge", "ratri", "monday", "friday", "sunday"],
    "event": ["meeting", "dinner", "party", "class", "interview", "function", "match", "lunch"],
    "item": ["sakkare", "akki", "eerulli", "tomato", "aloo", "bele", "hannu", "kobari"],
    "food": ["chai", "coffee", "dosa", "idli", "biryani", "oota", "upma", "vada"],
    "ride": ["bus", "train", "flight", "auto", "cab", "metro"],
    "people": ["guests", "friends", "cousins", "students", "neighbours", "relatives"],
    "device": ["phone", "alarm", "bell", "mobile"],
    "place": ["office", "college", "hotel", "temple", "school", "station", "hospital", "park"],
}
DIGITS = range(2, 10)  # 0 and 1 sound alike across the three languages too often

_DIGIT_NAMES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def random_phrase(rng: random.Random) -> str:
    """Every phrase equally likely, so no small template is worth pre-recording."""
    (template, _), = rng.choices(TEMPLATES, weights=[_variants(t) for t, _ in TEMPLATES])
    words = {slot: rng.choice(options) for slot, options in WORDS.items()}
    return template.format(d=rng.choice(DIGITS), **words)


def all_phrases() -> list[str]:
    """Every Whisper Phrase random_phrase() can produce, so their prompts can be voiced ahead of time."""
    out = []
    for template, _ in TEMPLATES:
        slots = [s for s in WORDS if "{" + s + "}" in template]
        for d, words in itertools.product(DIGITS, itertools.product(*(WORDS[s] for s in slots))):
            out.append(template.format(d=d, **dict(zip(slots, words))))
    return out


def phrase_count() -> int:
    """How many different Whisper Phrases random_phrase() can produce."""
    return sum(_variants(t) for t, _ in TEMPLATES)


def _variants(template: str) -> int:
    n = len(DIGITS)
    for slot, options in WORDS.items():
        if "{" + slot + "}" in template:
            n *= len(options)
    return n


def speakable(phrase: str) -> str:
    """The phrase as the Voice Agent should say it (digits as English words)."""
    return " ".join(_DIGIT_NAMES[int(w)] if w.isdigit() and len(w) == 1 else w for w in phrase.split())
