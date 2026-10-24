import pytest

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


def test_wrong_code_is_a_hard_block_with_a_reason(policy):
    d = policy.decide([human_whisper(), code(match=False)])
    assert d.verdict is Verdict.BLOCK
    assert any("does not match" in r for r in d.reasons)


def test_synthetic_voice_blocks_in_enforce_mode(policy):
    d = policy.decide([human_whisper(spoof_score=0.95), code()])
    assert d.verdict is Verdict.BLOCK
    assert any("synthetic" in r for r in d.reasons)


def test_clone_like_responses_block(policy):
    clone = human_whisper(task_match=0.4, whisper_score=0.1, reply_latency_ms=3200, spoof_score=0.6)
    assert policy.decide([clone, code(latency=3100, spoof=0.6)]).verdict is Verdict.BLOCK


def test_inconclusive_steps_up_then_hands_over_to_app(policy):
    meh = human_whisper(task_match=0.75, whisper_score=0.65, reply_latency_ms=2100, spoof_score=0.4)
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
