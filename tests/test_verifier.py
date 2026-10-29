"""Whole Calls through the Verifier's interface, on SQLite with scripted speech models."""

import asyncio

import pytest
from conftest import Harness, enforce_policy, voiced, whispered

from pratyaksh.domain import CallState, Outcome, Response
from pratyaksh.phrases import speakable
from pratyaksh.signals import TranscriptionHint
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
    h = Harness(spoof=0.97, policy=enforce_policy())
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add payee please")
    whisper_back(h, call_id)
    step = h.say(call_id, h.code_on_device(C), voiced(), 800)
    assert step.outcome is Outcome.BLOCKED
    assert any("synthetic" in r for r in h.verifier.call(call_id)["reasons"])


def test_a_whisper_phrase_is_heard_in_latin_with_the_phrase_as_hotwords(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add payee please")
    phrase = h.current_phrase(call_id)
    whisper_back(h, call_id)
    assert h.models.hints[-1] == TranscriptionHint(language="en", hotwords=speakable(phrase, "kn"))  # C is Kannada


@pytest.mark.parametrize("customer, language", [("cust-ananya", "kn"), ("cust-rahul", "hi"), ("cust-meera", "en")])
def test_a_request_is_heard_in_the_customers_language(harness, customer, language):
    call_id = harness.verifier.start_call(customer, "r").call_id
    harness.say(call_id, "add a payee")
    assert harness.models.hints == [TranscriptionHint(language=language)]


@pytest.mark.parametrize("customer, language", [("cust-ananya", "kn"), ("cust-rahul", "en"), ("cust-meera", "en")])
def test_a_possession_code_is_heard_in_the_language_its_digits_are_best_heard_in(harness, customer, language):
    h = harness
    call_id = h.verifier.start_call(customer, "r").call_id
    h.say(call_id, "add a payee")
    whisper_back(h, call_id)
    h.say(call_id, " ".join(h.code_on_device(customer)), voiced(), 900)
    assert h.models.hints[-1] == TranscriptionHint(language=language)


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
    assert [e["kind"] for e in events] == [
        "call_started", "agent_said", "caller_said", "risk_tier_set", "verdict", "call_closed", "agent_said"]


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


def test_a_call_the_agent_abandoned_is_closed_by_the_customers_next_call(harness):
    # Oct 29: the agent was restarted while a Caller dialled in; that Call stayed "in progress" for good.
    h = harness
    orphan = h.verifier.start_call(C, "r1").call_id
    live = h.verifier.start_call(C, "r2").call_id  # a moment later: still possibly real, left alone
    assert h.verifier.call(orphan)["state"] != "closed"
    h.clock.advance(6 * 60)
    h.say(live, "add payee")  # the live Call carries on
    h.verifier.start_call(C, "r3")
    gone = h.verifier.call(orphan)
    assert (gone["state"], gone["outcome"]) == ("closed", "abandoned")
    assert "call_went_silent" in [e["kind"] for e in gone["events"]]
    assert h.verifier.call(live)["state"] != "closed"


def test_audit_trail_rejects_updates_and_deletes_in_the_database(harness):
    from sqlalchemy import text

    harness.verifier.start_call(C, "r")
    for sql in ("UPDATE audit_events SET kind = 'x'", "DELETE FROM audit_events"):
        with pytest.raises(Exception, match="insert-only"):
            with harness.db.engine.begin() as conn:
                conn.execute(text(sql))


def test_a_clone_cannot_escape_a_block_by_asking_for_the_app():
    h = Harness(spoof=0.97, policy=enforce_policy())
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


def test_a_customer_rarely_hears_the_same_whisper_phrase_twice():
    # The banks are a few hundred phrases per language (tests/test_phrases.py); the random digit and the
    # Possession Code carry the security, so the bank only has to be unpredictable, not unvoiceable.
    import random

    from pratyaksh.phrases import random_phrase

    rng = random.Random(3)
    assert len({random_phrase(rng, "en") for _ in range(50)}) >= 45


def clone_blocked(h: Harness, customer: str = C) -> str:
    """An impostor without the Registered Device: right phrase, wrong code twice."""
    call_id = h.verifier.start_call(customer, "r").call_id
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


def passed_call(h: Harness, request: str = "add a payee", customer: str = C) -> str:
    call_id = h.verifier.start_call(customer, "r").call_id
    h.say(call_id, request)
    while h.verifier.call(call_id)["state"] != "closed":
        if h.verifier.call(call_id)["challenges"][-1]["kind"] == "possession_code":
            h.say(call_id, " ".join(h.code_on_device(customer)), voiced(), 900)
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
    assert h.verifier.verify_receipt(issued["receipt"]) == {"valid": True, "reason": "", "claims": claims, "redeemed": False}
    assert claims["jti"] != h.verifier.receipt(call_id)["claims"]["jti"]  # every receipt is distinct

    # High-value transfers are executable only once a Bank Agent confirms them.
    transfer = passed_call(h, "mujhe 6 lakh transfer karna hai")
    assert h.verifier.receipt(transfer)["claims"]["executable"] is False
    h.verifier.review(transfer, approve=True, reviewer="officer-1")
    assert h.verifier.receipt(transfer)["claims"]["executable"] is True

    # A blocked Call gets a receipt that says so, and it cannot be redeemed.
    blocked = clone_blocked(h)
    assert h.verifier.receipt(blocked)["claims"]["executable"] is False
    with pytest.raises(NotAllowed):
        h.verifier.redeem_receipt(h.verifier.receipt(blocked)["receipt"])

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


def test_the_transcript_is_the_whole_conversation_in_order(harness):
    h = harness
    call_id = passed_call(h, "mujhe 6 lakh transfer karna hai")
    call = h.verifier.call(call_id)
    lines = call["transcript"]
    assert [ln["seq"] for ln in lines] == sorted(ln["seq"] for ln in lines)
    assert lines[0]["text"] == "Call started." and "How can I help" in lines[1]["text"]
    assert lines[-1]["speaker"] == "agent" and "Goodbye" in lines[-1]["text"]

    request = next(ln for ln in lines if ln["speaker"] == "caller")
    assert request["text"] == "mujhe 6 lakh transfer karna hai"
    assert (request["understood"], request["language"]) == ("request", "hi")
    assert request["timings_ms"]["total"] >= 0

    scored = [ln for ln in lines if ln.get("challenge")]
    assert [ln["challenge"] for ln in scored] == [c["kind"] for c in call["challenges"]]
    assert all(ln["liveness"] == s for ln, s in zip(scored, call["scores"], strict=True))
    assert scored[0]["text"] == call["challenges"][0]["phrase"] and "whisper_score" in scored[0]["signals"]

    # The Verifier's steps sit between the turns: the Risk Tier, each Challenge, the Verdict.
    system = [ln["text"] for ln in lines if ln["speaker"] == "system"]
    assert "Risk Tier: High-value transfer needs 2 Whisper Phrases + Possession Code, then Agent Review." in system
    assert any(call["challenges"][0]["phrase"] in s for s in system)
    assert next(ln for ln in lines if ln["event"] == "verdict")["tone"] == "pass"

    # Every agent line is something the Voice Agent was told to say.
    said = [e["data"]["say"] for e in call["events"] if e["kind"] == "agent_said"]
    assert [ln["text"] for ln in lines if ln["speaker"] == "agent"] == said


def test_a_transcript_downloads_as_text_with_its_audit_head(harness):
    h = harness
    call_id = clone_blocked(h)
    text = h.verifier.transcript(call_id)
    head = h.verifier.audit_check(call_id)["head"]
    assert text.startswith("Pratyaksh Call transcript") and head in text
    assert "Verdict    BLOCK" in text and "Caller  9 9 9 9 9 9" in text
    assert "Security Alert sent to the Registered Device" in text
    reasons = h.verifier.call(call_id)["reasons"]
    assert reasons[0] in text and all(f"- {r}" in text for r in reasons[1:])  # every Reason, once


def test_an_attack_wave_puts_a_person_on_every_risky_request(harness):
    h = harness
    clone_blocked(h)  # one Customer called again and again is Voice Pause's job, not a wave
    h.say(h.verifier.start_call(C, "r").call_id, "add a payee")
    assert h.verifier.attack_wave()["blocked"] == 2 and not h.verifier.attack_wave()["active"]
    h.clock.advance(16 * 60)

    customers = ["cust-ananya", "cust-rahul", "cust-meera"]
    for i, customer in enumerate(customers):
        h.verifier.dismiss_alerts(customer, h.verifier.pairing(customer))
        clone_blocked(h, customer)
        assert h.verifier.attack_wave()["active"] is (i == 2)
    wave = h.verifier.stats()["attack_wave"]
    assert (wave["blocked"], wave["customers"]) == (3, 3)

    # Rahul really calls, after dismissing the alert. Adding a payee normally needs no Agent Review.
    h.verifier.dismiss_alerts("cust-rahul", h.verifier.pairing("cust-rahul"))
    during = passed_call(h, "add a payee", "cust-rahul")
    call = h.verifier.call(during)
    assert call["outcome"] == "passed_pending_review" and call["agent_review"] is True
    assert any("Attack Wave" in ln["text"] for ln in call["transcript"])
    assert not h.verifier.receipt(during)["claims"]["executable"]
    assert h.verifier.calls(outcome="blocked") and all(
        c["outcome"] == "blocked" for c in h.verifier.calls(outcome="blocked"))

    h.clock.advance(16 * 60)  # the wave passes
    assert not h.verifier.attack_wave()["active"]
    after = passed_call(h, "add a payee", "cust-rahul")
    assert h.verifier.call(after)["outcome"] == "passed"


def test_customer_risk_shows_alerts_voice_pause_and_history(harness):
    h = harness
    assert h.verifier.customer_risk(C)["risk"] == "normal"
    blocked = clone_blocked(h)
    risk = h.verifier.customer_risk(C)
    assert (risk["risk"], risk["open_security_alerts"], risk["blocked_24h"]) == ("high", 1, 1)
    assert risk["voice_pause"]["active"] and 29 <= risk["voice_pause"]["minutes_left"] <= 30
    assert risk["last_blocked_call"] == blocked and risk["recent"][0]["id"] == blocked
    assert risk["by_outcome_7d"] == {"blocked": 1} and risk["customer"]["phone_masked"]

    h.verifier.dismiss_alerts(C, h.verifier.pairing(C))
    risk = h.verifier.customer_risk(C)
    assert risk["risk"] == "elevated" and not risk["voice_pause"]["active"]
    assert [c["id"] for c in h.verifier.calls(customer_id=C)] == [blocked]
    with pytest.raises(UnknownCustomer):
        h.verifier.customer_risk("nobody")


def test_a_correct_code_read_after_it_expired_gets_a_fresh_code_not_a_block(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    whisper_back(h, call_id)
    old = h.code_on_device(C)
    h.clock.advance(125)  # two questions about the code, then reading it: past the 120 s
    step = h.say(call_id, " ".join(old), voiced(), 900)
    assert "sent a new one" in step.say and not step.end
    new = h.code_on_device(C)
    assert new != old and len(h.inbox(C)["messages"]) == 1  # the old code is gone from the Bank App
    assert not h.say(call_id, " ".join(old), voiced(), 900).end  # the old code no longer works: one retry
    step = h.say(call_id, " ".join(new), voiced(), 900)
    assert step.end and step.outcome is Outcome.PASSED
    notes = [ln.get("note", "") for ln in h.verifier.call(call_id)["transcript"]]
    assert any("read after it expired" in n for n in notes)


def test_a_second_expired_code_goes_to_app_approval(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    whisper_back(h, call_id)
    for _ in range(2):
        code = h.code_on_device(C)
        h.clock.advance(125)
        step = h.say(call_id, " ".join(code), voiced(), 900)
    assert step.wait and h.verifier.call(call_id)["state"] == "awaiting_app_approval"
    assert h.verifier.customer_risk(C)["open_security_alerts"] == 0  # a slow Customer is not a Clone


def test_a_wrong_code_after_expiry_still_counts_as_wrong(harness):
    h = harness
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    whisper_back(h, call_id)
    h.clock.advance(125)
    for _ in range(2):
        h.say(call_id, "9 9 9 9 9 9", voiced(), 900)
    assert h.verifier.call(call_id)["outcome"] == "blocked"


def test_a_hang_up_during_the_apply_phase_waits_for_it(threaded):
    """respond() checks the Call did not change, then applies. A hang-up arriving between the two must
    wait for the row lock (on SQLite: BEGIN IMMEDIATE), never close the Call a second time."""
    import threading

    from sqlalchemy import event

    h = threaded
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    whisper_back(h, call_id)
    h.models.push(" ".join(h.code_on_device(C)))
    in_respond, checks, hang_ups = threading.local(), [], []

    @event.listens_for(h.db.engine, "before_cursor_execute")
    def _between_check_and_apply(conn, cursor, statement, *args):
        if getattr(in_respond, "on", False) and "max(audit_events.seq)" in statement:
            checks.append(statement)
            if len(checks) == 2:  # phase 3's version check: hang up right now
                hang_ups.append(threading.Thread(target=h.verifier.hang_up, args=(call_id,)))
                hang_ups[0].start()
                hang_ups[0].join(0.3)  # without the lock it would finish here

    def respond():
        in_respond.on = True
        h.verifier.respond(call_id, Response(voiced(), 900))

    t = threading.Thread(target=respond)
    t.start()
    t.join(10)
    hang_ups[0].join(10)
    event.remove(h.db.engine, "before_cursor_execute", _between_check_and_apply)
    call = h.verifier.call(call_id)
    assert [e["data"]["outcome"] for e in call["events"] if e["kind"] == "call_closed"] == ["passed"]
    assert call["outcome"] == "passed" and call["audit"]["intact"]


def test_a_double_tap_on_dismiss_writes_one_event(threaded):
    import threading

    h = threaded
    call_id = clone_blocked(h)
    token = h.verifier.pairing(C)
    start, results = threading.Barrier(2), []

    def tap():
        start.wait()
        results.append(h.verifier.dismiss_alerts(C, token))

    taps = [threading.Thread(target=tap) for _ in range(2)]
    for t in taps:
        t.start()
    for t in taps:
        t.join(10)
    call = h.verifier.call(call_id)
    assert sorted(results) == [0, 1] and call["audit"]["intact"]
    assert [e["kind"] for e in call["events"]].count("security_alert_dismissed") == 1


def test_each_step_carries_what_the_verifier_heard_in_the_response_it_answers(harness):
    h = harness
    step = h.verifier.start_call(C, "r")
    assert step.heard == ""  # nothing was said yet
    call_id = step.call_id
    step = h.say(call_id, "I want to add a payee")
    assert step.heard == "I want to add a payee"
    phrase = h.current_phrase(call_id)
    step = whisper_back(h, call_id)
    assert step.heard == phrase
    step = h.verifier.respond(call_id, Response(voiced(), None))  # silence
    assert step.heard == ""


def test_a_step_says_which_challenge_is_open_and_the_words_to_whisper(harness):
    from pratyaksh.domain import ChallengeKind, Step
    from pratyaksh.phrases import spoken

    h = harness  # Ananya's profile language is Kannada
    call_id = h.verifier.start_call(C, "r").call_id
    assert h.verifier.current_step(call_id).challenge is None
    step = h.say(call_id, "I want to add a payee")
    words = spoken(h.current_phrase(call_id), "kn")
    assert step.challenge is ChallengeKind.WHISPER_PHRASE and step.words == words
    assert step.say.endswith(f"{words}.")  # the same words, in the same script, as spoken
    assert h.verifier.current_step(call_id) == step
    assert Step.from_dict(step.to_dict()) == step  # as the Voice Agent gets it over HTTP

    step = whisper_back(h, call_id)
    assert step.challenge is ChallengeKind.POSSESSION_CODE and step.words == ""
    step = h.say(call_id, " ".join(h.code_on_device(C)), voiced(), 900)
    assert step.end and step.challenge is None
