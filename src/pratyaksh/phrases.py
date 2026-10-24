"""Whisper Phrase bank: short phrases that mix Kannada, Hindi and English words.

Each template has one digit slot so the phrase space is large and unpredictable.
Internal to the Verifier; exposed only for the Eval Run tooling.
"""

from __future__ import annotations

import random

# (template, meaning) — words: Kannada, Hindi, English. {d} is a spoken digit.
TEMPLATES: list[tuple[str, str]] = [
    ("naale {d} baje meeting", "meeting tomorrow at {d}"),
    ("ivattu {d} baje payment", "payment today at {d}"),
    ("sanje {d} baje dinner", "dinner in the evening at {d}"),
    ("naanu {d} baje baruttene", "I will come at {d}"),
    ("{d} kilo sakkare lao", "bring {d} kilos of sugar"),
    ("chai {d} minute alli ready", "tea ready in {d} minutes"),
    ("bus {d} gante late hai", "the bus is {d} hours late"),
    ("mane mein {d} guests", "{d} guests at home"),
    ("phone {d} baar ring aaytu", "the phone rang {d} times"),
    ("beligge {d} baje office", "office at {d} in the morning"),
]

_DIGIT_NAMES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def random_phrase(rng: random.Random) -> str:
    template, _ = rng.choice(TEMPLATES)
    return template.format(d=rng.randint(2, 9))


def speakable(phrase: str) -> str:
    """The phrase as the Voice Agent should say it (digits as English words)."""
    return " ".join(_DIGIT_NAMES[int(w)] if w.isdigit() and len(w) == 1 else w for w in phrase.split())
