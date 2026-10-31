"""The Voice Agent speaks the Customer's language, whole Call."""

import pytest
from conftest import voiced, whispered

from pratyaksh.domain import Outcome
from pratyaksh.phrases import spoken
from pratyaksh.verification.lines import in_language, untranslated
from pratyaksh.verification.verifier import GREETING, fixed_lines, spoken_lines


def has_latin_sentence(text: str) -> bool:
    """Whole English words left in a line (payee, SIM and code-mixed phrases are fine)."""
    return any(w in text for w in ("Thank", "Please", "Sorry", "Sure", "your", "I'll", "code"))


@pytest.mark.parametrize("language", ["hi", "kn"])
def test_every_line_the_voice_agent_composes_is_translated(language):
    missing = [s for line in fixed_lines() for s in untranslated(line, language)]
    assert missing == []


def test_english_passes_through_unchanged():
    assert in_language(GREETING, "en") == GREETING
    assert in_language(GREETING, None) == GREETING


def test_a_sentence_with_no_translation_passes_through():
    assert in_language("Thank you. कल सात बजे meeting है.", "hi") == "धन्यवाद। कल सात बजे meeting है."


@pytest.mark.parametrize("language", ["hi", "kn"])
def test_every_translated_line_is_voiced_ahead_of_time(language):
    lines = spoken_lines()
    assert all(in_language(line, language) in lines for line in fixed_lines())


@pytest.mark.parametrize("customer, language", [("cust-rahul", "hi"), ("cust-ananya", "kn")])
def test_a_whole_call_is_in_the_customers_language(harness, customer, language):
    h = harness
    start = h.verifier.start_call(customer, "r")
    assert start.say == in_language(GREETING, language) and not has_latin_sentence(start.say)
    said = [h.say(start.call_id, "add a payee").say]
    phrase = h.current_phrase(start.call_id)
    assert spoken(phrase, language) in said[0]  # the Whisper Phrase, in the language the Caller reads it
    said.append(h.say(start.call_id, phrase, whispered(), 700).say)
    h.models.push("")  # the Possession Code's second reading
    code = h.code_on_device(customer)
    final = h.say(start.call_id, " ".join(code), voiced(), 900)
    assert final.outcome is Outcome.PASSED
    assert not any(has_latin_sentence(line) for line in [*said, final.say])


def test_a_repeated_prompt_does_not_stack_apologies_in_hindi(harness):
    h = harness
    call_id = h.verifier.start_call("cust-rahul", "r").call_id
    h.say(call_id, "add a payee")
    first = h.say(call_id, "", voiced(), None)
    second = h.say(call_id, "", voiced(), None)
    assert first.say.count("माफ़ कीजिए") <= 1 and second.say.count("माफ़ कीजिए") <= 1
