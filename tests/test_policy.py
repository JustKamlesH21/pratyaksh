import pytest
from conftest import enforce_policy

from pratyaksh.domain import ChallengeKind, Evidence, RequestKind, Signals, Verdict
from pratyaksh.policy import Policy, PolicyError

W, P = ChallengeKind.WHISPER_PHRASE, ChallengeKind.POSSESSION_CODE


def human_whisper(**kw):
    base = dict(task_match=0.95, whisper_score=0.9, reply_latency_ms=700, spoof_score=0.05)
    return Evidence(W, Signals(**{**base, **kw}))


def code(match=True, latency=900, spoof=0.05):
    return Evidence(P, Signals(reply_latency_ms=latency, spoof_score=spoof, spoken_digits="123456", code_match=match))


@pytest.fixture(scope="module")
def policy():
    return Policy.load()


def test_plans_match_risk_tiers(policy):
    assert policy.plan(RequestKind.BALANCE_ENQUIRY).challenges == ()
    assert policy.plan(RequestKind.ADD_PAYEE).challenges == (W, P)
    assert len(policy.plan(RequestKind.SIM_SWAP).challenges) == 3
    assert policy.plan(RequestKind.HIGH_VALUE_TRANSFER).agent_review is True


def test_live_human_passes(policy):
    d = policy.decide([human_whisper(), human_whisper(), code()])
    assert d.verdict is Verdict.PASS and d.liveness >= 0.9


def test_a_genuine_caller_who_takes_time_to_find_the_code_still_passes(policy):
    # The iPhone Call of Oct 27, 19:29: perfect whisper started at 1.95 s, right code read 10.6 s after
    # the prompt (unlock, open the bank app, read). The code is judged on being right, not on speed.
    d = policy.decide([human_whisper(task_match=1.0, whisper_score=1.0, reply_latency_ms=1952), code(latency=10592)])
    assert d.verdict is Verdict.PASS
    assert not any("Possession Code" in r and "slow" in r for r in d.reasons)


def test_wrong_code_is_a_hard_block_with_a_reason(policy):
    d = policy.decide([human_whisper(), code(match=False)])
    assert d.verdict is Verdict.BLOCK
    assert any("does not match" in r for r in d.reasons)


def test_synthetic_voice_blocks_in_enforce_mode():
    d = enforce_policy().decide([human_whisper(), code(spoof=0.95)])
    assert d.verdict is Verdict.BLOCK
    assert any("synthetic" in r for r in d.reasons)


def test_a_real_whisper_the_spoof_model_calls_synthetic_still_passes(policy):
    # Measured Oct 27: the spoof model scores real human whispers >= 0.85 in 67 of 87 recordings
    # (EARS, Expresso, Hindi), so the shipped Policy uses it as advice only, and says nothing about it
    # for a Whisper Phrase, where its opinion means nothing.
    d = policy.decide([human_whisper(spoof_score=1.0), code()])
    assert d.verdict is Verdict.PASS
    assert not any("synthetic" in r for r in d.reasons)


def test_clone_like_responses_block_even_with_a_stolen_code(policy):
    # Wrong words, voiced, slow: one more Whisper Phrase, then BLOCK, whatever the code says.
    clone = human_whisper(task_match=0.4, whisper_score=0.1, reply_latency_ms=3200, spoof_score=0.6)
    assert policy.decide([clone, code(latency=3100, spoof=0.6)]).verdict is Verdict.STEP_UP
    assert policy.decide([clone, code(latency=3100, spoof=0.6), clone], step_ups_used=1).verdict is Verdict.BLOCK
    assert policy.decide([clone, code(match=False)]).verdict is Verdict.BLOCK  # and at once without it


def test_inconclusive_steps_up_then_hands_over_to_app(policy):
    # Barely whispered, barely the right words, a machine-slow reply: the right code alone is not enough.
    meh = human_whisper(task_match=0.7, whisper_score=0.6, reply_latency_ms=3000, spoof_score=0.4)
    first = policy.decide([meh, code(latency=2000, spoof=0.4)], step_ups_used=0)
    assert first.verdict is Verdict.STEP_UP and first.next_challenge is W
    second = policy.decide([meh, code(latency=2000, spoof=0.4), meh], step_ups_used=1)
    assert second.verdict is Verdict.STEP_UP and second.offer_app_approval


def test_unfinished_whisper_phrase_gets_one_retry_then_blocks(policy):
    # Correct code, quick replies, but the phrase was spoken normally instead of whispered.
    not_whispered = human_whisper(whisper_score=0.1)
    first = policy.decide([not_whispered, code()], step_ups_used=0)
    assert first.verdict is Verdict.STEP_UP and first.next_challenge is W
    assert policy.decide([not_whispered, code(), human_whisper()], step_ups_used=1).verdict is Verdict.PASS
    assert policy.decide([not_whispered, code(), not_whispered], step_ups_used=1).verdict is Verdict.BLOCK


def test_wrong_digit_in_the_phrase_cannot_pass(policy):
    from pratyaksh.signals import phrase_match

    replayed = human_whisper(task_match=phrase_match("naale 7 baje meeting", "naale 4 baje meeting"))
    assert policy.decide([replayed, code()]).verdict is not Verdict.PASS


def test_advisory_mode_reports_but_does_not_block(policy):
    raw = __import__("yaml").safe_load(__import__("importlib.resources").resources.files("pratyaksh")
                                       .joinpath("policy.yaml").read_text())
    raw["signals"]["spoof_score"]["mode"] = "advisory"
    d = Policy(raw).decide([human_whisper(spoof_score=0.95), code(spoof=0.95)])
    assert d.verdict is Verdict.PASS
    assert any("leans synthetic" in r for r in d.reasons)


def test_bad_policy_is_rejected():
    with pytest.raises(PolicyError):
        Policy({"requests": {}, "signals": {}, "weights": {}, "verdict": {}})


def test_an_attack_wave_is_several_blocks_in_a_short_time(policy):
    assert (policy.wave_customers, policy.wave_minutes) == (3, 15)
    assert not policy.attack_wave(2) and policy.attack_wave(3)
    import yaml
    from importlib import resources
    raw = yaml.safe_load(resources.files("pratyaksh").joinpath("policy.yaml").read_text())
    raw["protection"]["wave_customers"] = 0
    assert not Policy(raw).attack_wave(100)  # 0 turns it off


def test_a_step_up_for_an_inconclusive_call_is_not_a_retry_for_a_later_miss():
    # Inconclusive, so one more Whisper Phrase; that phrase is then missed. The mean alone would PASS.
    # (The spoof score, enforced here, is what makes the first two Responses inconclusive.)
    policy = enforce_policy()
    shaky = human_whisper(task_match=1.0, whisper_score=1.0, spoof_score=0.7)
    first = policy.decide([shaky, code(latency=1500, spoof=0.7)], step_ups_used=0)
    assert first.verdict is Verdict.STEP_UP and first.next_challenge is W
    missed = human_whisper(task_match=0.65, whisper_score=1.0, spoof_score=0.0)
    second = policy.decide([shaky, code(latency=1500, spoof=0.7), missed], step_ups_used=1)
    assert second.liveness >= 0.75 and second.verdict is Verdict.STEP_UP and second.offer_app_approval
    assert "no retry is left" in second.reasons[0]


def test_a_planned_phrase_is_not_a_retry_for_an_earlier_miss(policy):
    missed = human_whisper(task_match=0.5)
    first = policy.decide([missed, human_whisper(), code()], step_ups_used=0)
    assert first.verdict is Verdict.STEP_UP and first.next_challenge is W
    assert policy.decide([missed, human_whisper(), code(), human_whisper()], step_ups_used=1).verdict is Verdict.PASS
