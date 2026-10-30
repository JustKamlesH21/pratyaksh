import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "attacker"))
sys.path.insert(0, str(ROOT / "backend" / "src"))

from devanagari import to_devanagari  # noqa: E402
from pratyaksh.phrases import all_phrases, speakable  # noqa: E402


def test_every_whisper_phrase_becomes_pure_devanagari():
    # IndicF5 reads Latin-script text as noise (Task Match 0/10 on Oct 27) but Devanagari well (10/10).
    for phrase in {speakable(p) for p in all_phrases()}:
        out = to_devanagari(phrase)
        assert not re.search(r"[A-Za-z]", out), (phrase, out)
        assert len(out.split()) == len(phrase.split())


def test_known_phrase_matches_the_spelling_that_scored_well():
    assert to_devanagari("park alli four baje interview") == "पार्क अल्ली फोर बजे इंटरव्यू"


def test_unknown_words_and_native_script_pass_through():
    assert to_devanagari("Hello naanu") == "Hello नानु"
    assert to_devanagari("मुझे नया पेयी ऐड करना है") == "मुझे नया पेयी ऐड करना है"
