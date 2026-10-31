"""Whisper Phrases are everyday sentences in the Customer's language, short and said clearly."""

import random
import re

import pytest

from pratyaksh.verification.lines import in_language
from pratyaksh.phrases import LANGUAGES, all_phrases, phrase_count, pronunciation, random_phrase, speakable, spoken

# Words of one language that must not appear in another language's phrases (a Caller would not know them).
KANNADA_ONLY = {"naale", "ivattu", "gantege", "gante", "ide", "tagondu", "baa", "maneli", "iddare", "nimishadalli",
                "banni"}
HINDI_ONLY = {"aaj", "kal", "baje", "hai", "hain", "lao", "ghar", "mein", "ghante", "pahunchna"}


@pytest.mark.parametrize("language", LANGUAGES)
def test_each_language_has_hundreds_of_phrases_each_equally_likely(language):
    assert phrase_count(language) >= 300
    rng = random.Random(3)
    drawn = [random_phrase(rng, language) for _ in range(3000)]
    assert len(set(drawn)) > 0.9 * phrase_count(language)


@pytest.mark.parametrize("language", LANGUAGES)
def test_phrases_are_short_enough_to_whisper_after_one_hearing(language):
    assert max(len(speakable(p).split()) for p in all_phrases(language)) <= 5


def test_an_english_customer_hears_only_english_words():
    for p in all_phrases("en"):
        assert not set(p.split()) & (KANNADA_ONLY | HINDI_ONLY), p


def test_hindi_and_kannada_customers_hear_their_own_language_in_every_phrase():
    assert all(set(p.split()) & HINDI_ONLY and not set(p.split()) & KANNADA_ONLY for p in all_phrases("hi"))
    assert all(set(p.split()) & KANNADA_ONLY and not set(p.split()) & HINDI_ONLY for p in all_phrases("kn"))


@pytest.mark.parametrize("language, script", [("hi", "[ऀ-ॿ]"), ("kn", "[ಀ-೿]")])
def test_every_indian_word_is_voiced_from_its_own_script(language, script):
    # The Voice Agent's voice reads romanised Hindi or Kannada poorly; native script it says clearly.
    digits = {speakable(str(d), language) for d in range(2, 10)}
    for word in {w for p in all_phrases(language) for w in speakable(p, language).split()}:
        if word in KANNADA_ONLY | HINDI_ONLY | digits:
            assert re.search(script, pronunciation(word, language)), word


@pytest.mark.parametrize("customer, language", [("cust-meera", "en"), ("cust-rahul", "hi"), ("cust-ananya", "kn")])
def test_the_verifier_gives_each_customer_a_phrase_in_their_language(customer, language):
    from conftest import Harness

    h = Harness()
    call_id = h.verifier.start_call(customer, "r").call_id
    step = h.say(call_id, "I want to add a new payee")
    phrase = h.current_phrase(call_id)
    assert phrase in all_phrases(language)
    # Its own sentence, said naturally after the instruction.
    assert step.say.endswith(f"{in_language('Please whisper these words.', language)} {spoken(phrase, language)}.")


@pytest.mark.parametrize("language, said", [
    ("en", "seven guests are coming home"), ("hi", "kal saat baje meeting hai"), ("kn", "naale ombattu gantege class ide"),
])
def test_the_digit_is_said_in_the_customers_language(language, said):
    phrase = {"en": "7 guests are coming home", "hi": "kal 7 baje meeting hai", "kn": "naale 9 gantege class ide"}[language]
    assert speakable(phrase, language) == said


@pytest.mark.parametrize("language, phrase, said", [
    ("en", "party at 7 tonight", "Party at seven tonight"),
    ("hi", "kal 7 baje meeting hai", "कल सात बजे meeting है"),
    ("kn", "naale 5 gantege class ide", "ನಾಳೆ ಐದು ಗಂಟೆಗೆ class ಇದೆ"),
])
def test_the_voice_is_given_indian_words_in_their_own_script(language, phrase, said):
    assert spoken(phrase, language) == said


@pytest.mark.parametrize("language", ["hi", "kn"])
def test_a_digit_whispered_in_hindi_or_kannada_still_matches(language):
    from pratyaksh.signals import phrase_match

    for phrase in all_phrases(language)[:: 37]:
        assert phrase_match(phrase, speakable(phrase, language)) == 1.0, phrase


def test_english_words_and_digits_are_voiced_as_written():
    assert pronunciation("meeting", "hi") == "meeting"
    assert pronunciation("five", "kn") == "five"


def test_a_phrase_pool_is_the_same_spread_of_real_phrases_every_time():
    from pratyaksh.phrases import phrase_pool

    pool = phrase_pool("hi", 24)
    assert len(set(pool)) == 24 and set(pool) <= set(all_phrases("hi")) and pool == phrase_pool("hi", 24)
    assert len({p.split()[1] for p in pool}) > 3  # across the templates, not the first few


def test_a_hindi_customer_only_gets_phrases_from_the_pool():
    import random

    from conftest import Harness
    from pratyaksh.phrases import phrase_pool

    h = Harness()
    h.verifier._hindi_phrases = phrase_pool("hi", 24)
    h.verifier._rng = random.Random(3)
    for n in range(6):
        call_id = h.verifier.start_call("cust-rahul", f"r{n}").call_id
        h.say(call_id, "I want to add a new payee")
        assert h.current_phrase(call_id) in phrase_pool("hi", 24)
        h.verifier.hang_up(call_id)
