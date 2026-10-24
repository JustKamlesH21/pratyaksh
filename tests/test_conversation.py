"""The Voice Agent handles anything a Caller says, without ever weakening Verification."""

import pytest
from conftest import Harness, voiced, whispered

from pratyaksh.domain import CallState, Outcome, Response
from pratyaksh.verification.interpreter import NO_ANSWER

C = "cust-ananya"


def start(h: Harness) -> str:
    return h.verifier.start_call(C, "r").call_id


def test_questions_are_answered_then_the_call_continues():
    h = Harness()
    call_id = start(h)
    step = h.say(call_id, "what are your branch timings?")
    assert step.listen and "branch" in step.say and step.say.endswith("anything else I can help you with?")
    step = h.say(call_id, "ok, check my balance")
    assert step.outcome is Outcome.PASSED


def test_a_question_about_a_pin_is_not_a_pin_reset():
    h = Harness()
    call_id = start(h)
    step = h.say(call_id, "someone asked for my OTP, should I share my pin?")
    assert step.state is CallState.AWAITING_REQUEST and "Never share" in step.say


def test_other_account_changes_are_verified_not_rejected():
    h = Harness()
    call_id = start(h)
    step = h.say(call_id, "how do I block my card?")
    assert step.state is CallState.AWAITING_REQUEST and "block my card" in step.say
    step = h.say(call_id, "block my card")
    assert step.state is CallState.CHALLENGING
    assert h.verifier.call(call_id)["request"] == "account_service"


def test_goodbye_human_and_repeat():
    h = Harness()
    call_id = start(h)
    greeting = h.verifier.current_step(call_id).say
    assert h.say(call_id, "sorry, can you repeat that").say == greeting
    assert h.say(call_id, "no thanks, bye").outcome is Outcome.ENDED

    call_id = start(h)
    step = h.say(call_id, "mujhe kisi adhikari se baat karni hai")
    assert step.outcome is Outcome.HANDED_TO_AGENT and "bank officer" in step.say


def test_unknown_questions_get_a_safe_answer_without_an_llm():
    h = Harness()
    call_id = start(h)
    assert h.say(call_id, "what is the capital of Peru?").say.startswith(NO_ANSWER)


def test_questions_during_a_challenge_are_answered_but_capped():
    h = Harness()
    call_id = start(h)
    h.say(call_id, "add a payee")
    phrase = h.current_phrase(call_id)
    step = h.say(call_id, "why should I whisper?", voiced(), 900)
    assert "voice-cloning" in step.say and step.say.endswith(h.verifier.call(call_id)["challenges"][-1]["prompt"])
    assert h.verifier.call(call_id)["evidence"] == []  # not scored
    step = h.say(call_id, "say that again please", voiced(), 900)
    assert step.say.startswith("Of course.")
    # The third off-script turn on the same Challenge is scored as the Response.
    h.say(call_id, "why why why?", voiced(), 900)
    assert len(h.verifier.call(call_id)["evidence"]) == 1
    assert h.current_phrase(call_id) == phrase or h.verifier.call(call_id)["challenges"][-1]["kind"] == "possession_code"


def test_asking_for_a_person_mid_challenge_still_blocks_a_detected_clone():
    h = Harness(spoof=0.97)
    call_id = start(h)
    h.say(call_id, "SIM swap please")
    h.say(call_id, h.current_phrase(call_id), whispered(), 700)  # synthetic voice: hard fail
    step = h.say(call_id, "let me talk to a real person", voiced(), 700)
    assert step.outcome is Outcome.BLOCKED


def test_the_llm_handles_the_rest_and_cannot_leak_numbers():
    class StubLLM:
        def complete_json(self, system, user):
            if "gold bonds" in user:
                return {"kind": "question", "reply": "Gold bond details are in the bank app."}
            if "customer ID" in user:
                return {"kind": "question", "reply": "Your customer ID is 1234 5678 9012."}
            return {"kind": "request", "request": "account_service"}

    h = Harness(llm=StubLLM())
    call_id = start(h)
    assert h.say(call_id, "tell me about sovereign gold bonds").say.startswith("Gold bond details are in the bank app.")
    assert h.say(call_id, "what is my customer ID").say.startswith(NO_ANSWER)
    assert h.say(call_id, "I want to update my nominee details").state is CallState.CHALLENGING


def test_a_broken_model_never_ends_the_call_abruptly():
    h = Harness()

    def broken(_audio):
        raise RuntimeError("CUDA out of memory")

    h.models._transcribe = broken
    call_id = start(h)
    step = h.verifier.respond(call_id, Response(voiced(), 700))
    assert step.listen and step.say.startswith("Sorry, I had trouble hearing that.")
    step = h.verifier.respond(call_id, Response(voiced(), 700))
    assert step.outcome is Outcome.HANDED_TO_AGENT


def test_native_script_questions():
    h = Harness()
    call_id = start(h)
    step = h.say(call_id, "ನನ್ನ ಧ್ವನಿ record ಆಗುತ್ತಾ? is my voice stored?")
    assert "never store your voice" in step.say


ANSWERS = [  # (what the Caller asks before any Request, words the answer must contain)
    ("is this call genuine?", "never ask for your PIN"),
    ("why do you need to verify me?", "live person"),
    ("is my voice being recorded?", "never store your voice"),
    ("are you a real person?", "automated voice assistant"),
    ("what can you do?", "What would you like to do?"),
    ("hello?", "I'm here"),
    ("how do I open a new account?", "open a new account"),
    ("where is the nearest ATM?", "ATM finder"),
    ("what is the IFSC code of my branch?", "cheque book and passbook"),
    ("did my salary come?", "don't read out account details"),
    ("there is a transaction I did not make", "1930"),
    ("I got a suspicious message with a link", "Don't open links"),
    ("mera paisa kat gaya, kya karu?", "comes back to your account"),
    ("OTP kisi ko dena chahiye?", "Never share"),
    ("ब्रांच कब खुलती है?", "branch"),
    ("nanna hana kaledu hogide", "1930"),
    ("ನನ್ನ ಖಾತೆ ಸಂಖ್ಯೆ ಏನು?", "don't read out account details"),
]


@pytest.mark.parametrize("asked, expected", ANSWERS)
def test_questions_get_an_answer_that_fits(asked, expected):
    h = Harness()
    call_id = start(h)
    step = h.say(call_id, asked)
    assert step.listen and step.state is CallState.AWAITING_REQUEST
    assert expected in step.say


@pytest.mark.parametrize("asked", [
    "what is the transfer limit?", "what are the charges for NEFT?", "will you ask for my PIN?",
    "what is the minimum balance?", "what is the status of my transfer?", "what documents do I need for KYC?",
    "what is NEFT?", "someone transferred money from my account without asking me",
    "my UPI payment failed but money got debited",
])
def test_questions_that_mention_a_request_are_answered_not_started(asked):
    h = Harness()
    call_id = start(h)
    step = h.say(call_id, asked)
    assert step.state is CallState.AWAITING_REQUEST and h.verifier.call(call_id)["request"] is None


@pytest.mark.parametrize("said, kind", [
    ("I want to transfer six lakh", "high_value_transfer"),
    ("can you transfer money to my brother?", "high_value_transfer"),
    ("पैसे कैसे भेजें?", "high_value_transfer"),
    ("ಹಣ ಹೇಗೆ ಕಳುಹಿಸುವುದು?", "high_value_transfer"),
    ("please add a new payee", "add_payee"),
    ("I need to reset my password", "sim_swap"),
    ("I want to update my nominee", "account_service"),
])
def test_requests_are_still_requests(said, kind):
    h = Harness()
    call_id = start(h)
    assert h.say(call_id, said).state is CallState.CHALLENGING
    assert h.verifier.call(call_id)["request"] == kind


def test_a_question_and_a_request_in_one_breath_get_both():
    h = Harness()
    call_id = start(h)
    step = h.say(call_id, "is this call safe? I want to transfer 6 lakh")
    assert "never ask for your PIN" in step.say and "high-value transfer" in step.say
    assert step.state is CallState.CHALLENGING


def test_trouble_with_the_possession_code_gets_help_and_the_code_stays_valid():
    h = Harness()
    call_id = start(h)
    h.say(call_id, "add a payee")
    h.say(call_id, h.current_phrase(call_id), whispered(), 700)
    step = h.say(call_id, "I didn't get the code", voiced(), 900)
    assert "not in an SMS" in step.say and step.say.endswith("six-digit code from your bank app.")
    step = h.say(call_id, "code nahi aaya, which app?", voiced(), 900)
    assert step.state is CallState.CHALLENGING and h.verifier.call(call_id)["evidence"][-1]["kind"] == "whisper_phrase"
    step = h.say(call_id, " ".join(h.code_on_device(C)), voiced(), 900)
    assert step.outcome is Outcome.PASSED


def test_hold_on_is_not_scored_but_cannot_stall_a_challenge():
    h = Harness()
    call_id = start(h)
    h.say(call_id, "add a payee")
    for wait in ("hold on", "ek minute"):
        step = h.say(call_id, wait, voiced(), 900)
        assert step.say.startswith("Sure, take your time.") and h.verifier.call(call_id)["evidence"] == []
    h.say(call_id, "ondu nimisha", voiced(), 900)  # third off-script turn: scored as the Response
    assert len(h.verifier.call(call_id)["evidence"]) == 1


def test_cant_hear_repeats_the_challenge_instead_of_switching_to_the_app():
    h = Harness()
    call_id = start(h)
    h.say(call_id, "add a payee")
    step = h.say(call_id, "I can't hear you", voiced(), 900)
    assert step.say.startswith("Of course. Please whisper") and not step.wait


def test_the_llm_is_told_where_the_call_is():
    class StubLLM:
        def complete_json(self, system, user):
            if "whisper a random phrase" in system:
                return {"kind": "question", "reply": "It proves a live person is speaking."}
            return {"kind": "unclear", "reply": "What do you need?"}

    h = Harness(llm=StubLLM())
    call_id = start(h)
    h.say(call_id, "add a payee")
    step = h.say(call_id, "is this some kind of game?", voiced(), 900)
    assert step.say.startswith("It proves a live person is speaking.")


@pytest.mark.parametrize("answer", ["some other words", "the words are naale baje", "ok", "yes yes", "minute", "I don't know"])
def test_a_wrong_answer_to_a_challenge_is_scored_not_taken_as_a_side_turn(answer):
    h = Harness()
    call_id = start(h)
    h.say(call_id, "add a payee")
    h.say(call_id, answer, voiced(), 900)
    assert len(h.verifier.call(call_id)["evidence"]) == 1
