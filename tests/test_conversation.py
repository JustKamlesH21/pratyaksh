"""The Voice Agent handles anything a Caller says, without ever weakening Verification."""

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
    assert h.say(call_id, "who won the cricket match yesterday?").say.startswith(NO_ANSWER)


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
            if "loan" in user:
                return {"kind": "question", "reply": "Loan details are in the bank app."}
            if "account number" in user:
                return {"kind": "question", "reply": "Your account number is 1234 5678 9012."}
            return {"kind": "request", "request": "account_service"}

    h = Harness(llm=StubLLM())
    call_id = start(h)
    assert h.say(call_id, "tell me about home loans").say.startswith("Loan details are in the bank app.")
    assert h.say(call_id, "what is my account number").say.startswith(NO_ANSWER)
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
