"""Whole Calls through the Verifier's interface, on SQLite with scripted speech models."""

import asyncio

import pytest
from conftest import Harness, voiced, whispered

from pratyaksh.domain import CallState, Outcome, Response
from pratyaksh.verification import CallNotFound, Database, DeviceNotPaired, NotAllowed, UnknownCustomer

C = "cust-ananya"


def whisper_back(h: Harness, call_id: str, latency_ms: int = 700):
    phrase = h.current_phrase(call_id)
    return h.say(call_id, phrase, whispered(), latency_ms)


def test_balance_enquiry_needs_no_challenges(harness):
    step = harness.verifier.start_call(C, "room-1")
    assert step.listen and "How can I help" in step.say
    step = harness.say(step.call_id, "I want to check my balance")
    assert step.end and step.outcome is Outcome.PASSED
    call = harness.verifier.call(step.call_id)
    assert call["request"] == "balance_enquiry" and call["challenges"] == []


def test_real_customer_high_value_transfer_passes_into_agent_review(harness):
    h = harness
    call_id = h.verifier.start_call(C, "room-1").call_id
    step = h.say(call_id, "mujhe 6 lakh transfer karna hai")
    assert step.state is CallState.CHALLENGING and "whisper" in step.say
    step = whisper_back(h, call_id)
    assert "whisper" in step.say
    step = whisper_back(h, call_id)
    assert "code" in step.say
    step = h.say(call_id, " ".join(h.code_on_device(C)), voiced(), 900)
    assert step.end and step.outcome is Outcome.PASSED_PENDING_REVIEW

    call = h.verifier.call(call_id)
    assert call["verdict"] == "PASS" and call["review_status"] == "pending"
    assert len(call["scores"]) == 3 and min(call["scores"]) > 0.8
    assert h.inbox(C)["messages"] == []  # the code was consumed

    reviewed = h.verifier.review(call_id, approve=True, reviewer="officer-1")
    assert reviewed["review_status"] == "approved"
    with pytest.raises(NotAllowed):
        h.verifier.review(call_id, approve=True, reviewer="officer-1")


def test_clone_without_the_phone_is_blocked_with_reasons():
    h = Harness(spoof=0.7)
    call_id = h.verifier.start_call(C, "room-x").call_id
    h.say(call_id, "I need to add a new payee", latency_ms=2800)
    # A typed-then-cloned reply: slow, voiced (not whispered), wrong words.
    h.say(call_id, "now seven bye meeting", voiced(), 3300)
    step = h.say(call_id, "one two three four five six", voiced(), 3400)
    assert step.listen and step.long_reply and "didn't match" in step.say  # one retry
    step = h.say(call_id, "six five four three two one", voiced(), 3400)
    assert step.end and step.outcome is Outcome.BLOCKED
    reasons = " ".join(h.verifier.call(call_id)["reasons"])
    assert "does not match" in reasons
    assert "not whispered" in reasons and "slow reply" in reasons


def test_synthetic_voice_alone_blocks_even_with_the_right_code():
    h = Harness(spoof=0.97)
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add payee please")
    whisper_back(h, call_id)
    step = h.say(call_id, h.code_on_device(C), voiced(), 800)
    assert step.outcome is Outcome.BLOCKED
    assert any("synthetic" in r for r in h.verifier.call(call_id)["reasons"])


def test_inconclusive_responses_get_one_extra_whisper_phrase(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a beneficiary")
    h.say(call_id, h.current_phrase(call_id), voiced(), 1900)  # said, but not whispered, a bit slow
    step = h.say(call_id, h.code_on_device(C), voiced(), 1900)
    assert step.state is CallState.CHALLENGING and "one more check" in step.say
    assert h.verifier.call(call_id)["step_ups"] == 1


def test_caller_can_switch_to_app_approval(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "SIM card change karna hai")
    step = h.say(call_id, "I cannot whisper, please send it to the bank app")
    assert step.wait and step.state is CallState.AWAITING_APP_APPROVAL
    kinds = [m["kind"] for m in h.inbox(C)["messages"]]
    assert kinds == ["app_approval"]

    with pytest.raises(NotAllowed):
        h.approve(call_id, "cust-rahul")  # another Customer's (paired) device
    with pytest.raises(DeviceNotPaired):
        h.verifier.app_approval(call_id, C, "guessed-token", True)  # the Clone's laptop
    with pytest.raises(DeviceNotPaired):
        h.verifier.inbox(C, "")
    assert h.verifier.current_step(call_id).wait  # still waiting
    step = h.approve(call_id, C)
    assert step.end and step.outcome is Outcome.APPROVED_IN_APP
    assert h.verifier.current_step(call_id).outcome is Outcome.APPROVED_IN_APP


def test_app_approval_expires(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "password reset, I can't do this, use the bank app")
    h.clock.advance(121)
    step = h.verifier.current_step(call_id)
    assert step.end and step.outcome is Outcome.ABANDONED
    with pytest.raises(NotAllowed):
        h.approve(call_id, C)


def test_silence_repeats_the_challenge_once_then_counts(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add payee")
    step = h.verifier.respond(call_id, __import__("pratyaksh.domain", fromlist=["Response"]).Response(voiced(0.1), None))
    assert step.listen and step.say.startswith("Sorry, I didn't hear you")
    h.say(call_id, "", voiced(0.1), None)
    step = h.say(call_id, h.code_on_device(C), voiced(), 800)
    assert step.outcome is Outcome.BLOCKED
    assert any("no reply" in r for r in h.verifier.call(call_id)["reasons"])


def test_unclear_requests_use_the_llm_then_hand_over():
    class StubLLM:
        def __init__(self):
            self.calls = 0

        def complete_json(self, system, user):
            self.calls += 1
            if "kaasu" in user:
                return {"request": "high_value_transfer"}
            return {"request": None, "reply": "I can help with a few banking requests."}

    llm = StubLLM()
    h = Harness(llm=llm)
    call_id = h.verifier.start_call(C, "r").call_id
    step = h.say(call_id, "hello hello")
    assert step.listen and step.say.startswith("I can help with a few banking requests.")
    step = h.say(call_id, "nanna kaasu bere account ge")
    assert step.state is CallState.CHALLENGING and llm.calls == 2

    call_id = h.verifier.start_call(C, "r2").call_id
    for _ in range(2):
        h.say(call_id, "umm")
    step = h.say(call_id, "umm")
    assert step.end and step.outcome is Outcome.HANDED_TO_AGENT  # never a dead end


def test_audit_trail_is_ordered_and_events_reach_consoles(harness):
    h = harness

    async def run():
        async with h.events.subscribe() as queue:
            call_id = await asyncio.to_thread(h.verifier.start_call, C, "r")
            call_id = call_id.call_id
            await asyncio.to_thread(h.say, call_id, "balance")
            await asyncio.sleep(0.05)
            got = []
            while not queue.empty():
                got.append(queue.get_nowait())
            return call_id, got

    call_id, got = asyncio.run(run())
    assert got and got[-1]["call"]["outcome"] == "passed"
    events = h.verifier.call(call_id)["events"]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert [e["kind"] for e in events] == ["call_started", "caller_said", "risk_tier_set", "verdict", "call_closed"]


def test_hang_up_and_errors(harness):
    h = harness
    with pytest.raises(UnknownCustomer):
        h.verifier.start_call("nobody", "r")
    with pytest.raises(CallNotFound):
        h.verifier.call("missing")
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add payee")
    h.verifier.hang_up(call_id)
    call = h.verifier.call(call_id)
    assert call["outcome"] == "abandoned" and call["state"] == "closed"
    # Responses after close are ignored and the closing Step is returned again.
    assert h.say(call_id, "hello").end


def test_audit_trail_rejects_updates_and_deletes_in_the_database(harness):
    from sqlalchemy import text

    harness.verifier.start_call(C, "r")
    for sql in ("UPDATE audit_events SET kind = 'x'", "DELETE FROM audit_events"):
        with pytest.raises(Exception, match="insert-only"):
            with harness.db.engine.begin() as conn:
                conn.execute(text(sql))


def test_a_clone_cannot_escape_a_block_by_asking_for_the_app():
    h = Harness(spoof=0.97)
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "SIM swap please")
    whisper_back(h, call_id)  # synthetic voice: hard fail already in the evidence
    step = h.say(call_id, "I can't do this, use the bank app")
    assert step.outcome is Outcome.BLOCKED
    assert [m["kind"] for m in h.inbox(C)["messages"]] == ["security_alert"]  # no approval prompt to push


def test_a_misread_code_gets_one_retry(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    whisper_back(h, call_id)
    code = h.code_on_device(C)
    step = h.say(call_id, code[:3], voiced(), 900)  # paused halfway
    assert step.listen and step.long_reply
    step = h.say(call_id, f"{code[:3]} {code[3:]}", voiced(), 900)
    assert step.outcome is Outcome.PASSED


def test_reading_out_a_long_run_of_digits_cannot_guess_the_code(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    whisper_back(h, call_id)
    code = h.code_on_device(C)
    # 27 digits hold 22 six-digit windows; one of them is the real code.
    spray = " ".join("1234567890" + code + "09876543210"[:14])
    step = h.say(call_id, spray, voiced(), 900)
    assert "didn't match" in step.say
    step = h.say(call_id, spray, voiced(), 900)
    assert step.outcome is Outcome.BLOCKED


def test_a_stray_digit_around_the_code_still_matches(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    whisper_back(h, call_id)
    step = h.say(call_id, f"my code is {' '.join(h.code_on_device(C))} 2", voiced(), 900)
    assert step.outcome is Outcome.PASSED


def test_whisper_phrases_are_too_many_to_pre_record():
    import random

    from pratyaksh.phrases import phrase_count, random_phrase

    assert phrase_count() >= 1000
    rng = random.Random(3)
    assert len({random_phrase(rng) for _ in range(300)}) >= 250


def clone_blocked(h: Harness) -> str:
    """An impostor without the Registered Device: right phrase, wrong code twice."""
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    whisper_back(h, call_id)
    for _ in range(2):
        h.say(call_id, "9 9 9 9 9 9", voiced(), 900)
    assert h.verifier.call(call_id)["outcome"] == "blocked"
    return call_id


def test_after_a_block_the_customer_is_alerted_and_voice_requests_pause(harness):
    h = harness
    clone_blocked(h)
    alert = h.inbox(C)["messages"][0]
    assert alert["kind"] == "security_alert" and alert["body"]["request_text"] == "add a new payee"

    # The impostor calls straight back: refused on voice, no prompt pushed to the victim's phone.
    call_id = h.verifier.start_call(C, "r").call_id
    step = h.say(call_id, "add a payee, use the bank app")
    assert step.outcome is Outcome.BLOCKED and "paused" in h.verifier.call(call_id)["reasons"][0]
    assert {m["kind"] for m in h.inbox(C)["messages"]} == {"security_alert"}
    # Questions and balance enquiries still work.
    call_id = h.verifier.start_call(C, "r").call_id
    assert h.say(call_id, "check my balance").outcome is Outcome.PASSED

    # Only the Customer's own phone can lift the pause.
    with pytest.raises(DeviceNotPaired):
        h.verifier.dismiss_alerts(C, "stolen-guess")
    assert h.verifier.dismiss_alerts(C, h.verifier.pairing(C)) == 2
    call_id = h.verifier.start_call(C, "r").call_id
    assert h.say(call_id, "add a payee").state is CallState.CHALLENGING


def test_the_voice_pause_ends_by_itself(harness):
    h = harness
    clone_blocked(h)
    h.clock.advance(31 * 60)
    call_id = h.verifier.start_call(C, "r").call_id
    assert h.say(call_id, "add a payee").state is CallState.CHALLENGING


def test_the_audit_trail_is_hash_chained_so_edits_show_even_without_triggers(harness):
    from sqlalchemy import text

    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    whisper_back(h, call_id)
    check = h.verifier.audit_check(call_id)
    assert check["intact"] and check["events"] >= 5 and len(check["head"]) == 64
    assert h.verifier.call(call_id)["audit"] == check

    # Someone with database access drops the triggers and rewrites what the Caller said.
    with h.db.engine.begin() as conn:
        conn.execute(text("DROP TRIGGER audit_events_no_update"))
        conn.execute(text("DROP TRIGGER audit_events_no_delete"))
        conn.execute(text("UPDATE audit_events SET data = :d WHERE call_id = :c AND seq = 2"),
                      {"d": '{"transcript": "check my balance"}', "c": call_id})
    assert h.verifier.audit_check(call_id) == {"intact": False, "events": check["events"], "broken_at": 2, "head": None}

    other = h.verifier.start_call(C, "r2").call_id
    h.say(other, "add a payee")
    with h.db.engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_events WHERE call_id = :c AND seq = 2"), {"c": other})
    assert h.verifier.audit_check(other)["broken_at"] == 2


def test_an_old_database_is_refused_with_the_fix_named():
    from sqlalchemy import text

    from pratyaksh.verification.store import SchemaOutOfDate

    db = Database("sqlite://")
    with db.engine.begin() as conn:
        conn.execute(text("CREATE TABLE audit_events (id INTEGER PRIMARY KEY, call_id VARCHAR(36), seq INTEGER, "
                          "kind VARCHAR(40), data JSON, created_at DATETIME)"))
    with pytest.raises(SchemaOutOfDate, match="pratyaksh-seed --reset"):
        db.create_schema()
    db.reset()
    assert db.create_schema() == []


def passed_call(h: Harness, request: str = "add a payee") -> str:
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, request)
    while h.verifier.call(call_id)["state"] != "closed":
        if h.verifier.call(call_id)["challenges"][-1]["kind"] == "possession_code":
            h.say(call_id, " ".join(h.code_on_device(C)), voiced(), 900)
        else:
            whisper_back(h, call_id)
    return call_id


def test_a_verification_receipt_says_whether_the_request_may_be_carried_out(harness):
    h = harness
    call_id = passed_call(h)
    issued = h.verifier.receipt(call_id)
    claims = issued["claims"]
    assert claims["executable"] and claims["verdict"] == "PASS" and claims["request"] == "add_payee"
    assert claims["audit_head"] == h.verifier.audit_check(call_id)["head"]
    assert h.verifier.verify_receipt(issued["receipt"]) == {"valid": True, "reason": "", "claims": claims}

    # High-value transfers are executable only once a Bank Agent confirms them.
    transfer = passed_call(h, "mujhe 6 lakh transfer karna hai")
    assert h.verifier.receipt(transfer)["claims"]["executable"] is False
    h.verifier.review(transfer, approve=True, reviewer="officer-1")
    assert h.verifier.receipt(transfer)["claims"]["executable"] is True

    # A blocked Call gets a receipt that says so.
    blocked = clone_blocked(h)
    assert h.verifier.receipt(blocked)["claims"]["executable"] is False

    # No receipt while a Call is still going.
    live = h.verifier.start_call("cust-meera", "r").call_id
    with pytest.raises(NotAllowed):
        h.verifier.receipt(live)


def test_a_forged_expired_or_out_of_date_receipt_is_rejected(harness):
    import base64
    import json

    from sqlalchemy import text

    h = harness
    call_id = passed_call(h)
    token = h.verifier.receipt(call_id)["receipt"]
    head, body, sig = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=="))
    forged_body = base64.urlsafe_b64encode(json.dumps({**claims, "sub": "cust-rahul"}).encode()).rstrip(b"=").decode()
    assert not h.verifier.verify_receipt(f"{head}.{forged_body}.{sig}")["valid"]
    assert not h.verifier.verify_receipt("not a receipt")["valid"]

    h.clock.advance(11 * 60)
    assert h.verifier.verify_receipt(token)["reason"] == "the receipt has expired"

    fresh = h.verifier.receipt(call_id)["receipt"]
    with h.db.engine.begin() as conn:
        conn.execute(text("DROP TRIGGER audit_events_no_update"))
        conn.execute(text("UPDATE audit_events SET kind = 'x' WHERE call_id = :c AND seq = 3"), {"c": call_id})
    assert "Audit Trail" in h.verifier.verify_receipt(fresh)["reason"]


def test_the_database_is_free_while_a_response_is_heard_and_a_late_one_is_ignored(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id

    def slow_model(_audio):
        # While speech-to-text runs, no transaction or row lock is held: the Console can read the
        # Call and the Caller can hang up.
        assert h.verifier.call(call_id)["state"] == "awaiting_request"
        h.verifier.hang_up(call_id)
        return "add a payee"

    h.models._transcribe = slow_model
    step = h.verifier.respond(call_id, Response(voiced(), 700))
    call = h.verifier.call(call_id)
    assert step.end and call["outcome"] == "abandoned" and call["request"] is None
    kinds = [e["kind"] for e in call["events"]]
    assert "caller_said" not in kinds and kinds[-1] == "response_ignored"
