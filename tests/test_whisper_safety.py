"""A Whisper Phrase answered with silence or noise must never lead to PASS.

Room noise is aperiodic, so on its own it looks "whispered" to the whisper DSP; what stops it is the
phrase check (Task Match) and, for digital silence, the missing speech energy. These tests pin that
down through the SignalExtractor and the Verifier, whatever speech-to-text makes of the noise.
"""

import numpy as np
import pytest
from conftest import Harness, voiced, whispered

from pratyaksh.domain import SAMPLE_RATE, Audio, Challenge, ChallengeKind, Evidence, Outcome, Response
from pratyaksh.policy import Policy
from pratyaksh.signals import ScriptedSpeechModels, SignalExtractor, whisper_score

C = "cust-ananya"
PHRASE = "naale 7 baje meeting"


def white(seconds: float = 3.0, level: float = 0.05, seed: int = 1) -> Audio:
    rng = np.random.default_rng(seed)
    return Audio((level * rng.standard_normal(int(seconds * SAMPLE_RATE))).astype(np.float32))


def pink(seconds: float = 3.0, level: float = 0.05, seed: int = 2) -> Audio:
    """1/f noise: most of its energy is low, where pitch trackers look for voicing."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SAMPLE_RATE)
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)
    spec[1:] /= np.sqrt(f[1:])
    spec[0] = 0
    y = np.fft.irfft(spec, n)
    return Audio((level * y / np.abs(y).max()).astype(np.float32))


def silence(seconds: float = 3.0) -> Audio:
    return Audio.silence(seconds)


def faint_hiss(seconds: float = 3.0) -> Audio:
    """A quiet line: just above digital silence."""
    return white(seconds, level=3e-4, seed=3)


NOISES = {"silence": silence, "faint_hiss": faint_hiss, "white": white, "pink": pink}
# What speech-to-text may make of noise: nothing, a hallucinated filler, or other words.
NOT_THE_PHRASE = ["", "Thank you.", "please transfer the money now", "naale baje"]


def extract(audio: Audio, transcript: str):
    models = ScriptedSpeechModels([transcript], spoof=0.05)
    return SignalExtractor(models).extract(Challenge(ChallengeKind.WHISPER_PHRASE, "", PHRASE), Response(audio, 600))


def test_digital_silence_has_no_whisper_score():
    assert whisper_score(silence()) is None


@pytest.mark.parametrize("noise", ["white", "pink", "faint_hiss"])
def test_noise_looks_whispered_to_the_dsp_alone(noise):
    """Documents why Task Match must gate the Whisper Phrase: noise has no voicing."""
    score = whisper_score(NOISES[noise]())
    assert score is None or score >= 0.6


@pytest.mark.parametrize("noise", sorted(NOISES))
@pytest.mark.parametrize("transcript", NOT_THE_PHRASE)
def test_noise_without_the_phrase_never_passes_a_whisper_phrase(noise, transcript):
    signals = extract(NOISES[noise](), transcript)
    decision = Policy.load().decide([Evidence(ChallengeKind.WHISPER_PHRASE, signals)])
    assert decision.verdict.value != "PASS"
    assert decision.next_challenge is ChallengeKind.WHISPER_PHRASE or decision.verdict.value == "BLOCK"


def test_silence_with_the_phrase_hallucinated_still_never_passes():
    """Even if speech-to-text 'hears' the phrase in digital silence, no energy means no whisper."""
    signals = extract(silence(), PHRASE)
    assert signals.whisper_score is None
    decision = Policy.load().decide([Evidence(ChallengeKind.WHISPER_PHRASE, signals)])
    assert decision.verdict.value != "PASS"


@pytest.mark.parametrize("noise", sorted(NOISES))
@pytest.mark.parametrize("transcript", ["", "Thank you."])
def test_a_call_answered_with_noise_never_passes_even_with_the_right_code(noise, transcript):
    """The impostor holds the Registered Device (reads the code) but cannot whisper the phrase."""
    h = Harness(spoof=0.05)
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    for _ in range(6):
        call = h.verifier.call(call_id)
        if call["state"] != "challenging":
            break
        if call["challenges"][-1]["kind"] == "possession_code":
            h.say(call_id, " ".join(h.code_on_device(C)), voiced(), 800)
        else:
            h.say(call_id, transcript, NOISES[noise](), 600)
    call = h.verifier.call(call_id)
    assert call["verdict"] != "PASS"
    assert call["outcome"] not in {Outcome.PASSED.value, Outcome.PASSED_PENDING_REVIEW.value}


def syllables(seconds: float = 3.0, seed: int = 4) -> Audio:
    """Whisper-like noise bursts with pauses between them, like syllables of a whispered phrase."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    gate = (np.sin(2 * np.pi * 3 * t) > 0.2).astype(float)
    y = np.convolve(rng.standard_normal(n), np.hanning(9) / np.hanning(9).sum(), mode="same") * gate
    return Audio((0.2 * y / np.abs(y).max() + 1e-4 * rng.standard_normal(n)).astype(np.float32))


def test_whisper_detail_tells_a_phrase_from_a_line_full_of_hiss():
    """Logged-only diagnostic: speech has pauses (wide dynamic range); hiss loud enough to mask voicing does not."""
    from pratyaksh.signals import whisper_detail

    phrase = whisper_detail(syllables())
    drowned = Audio(voiced(3.0).samples + white(3.0, level=0.15).samples)
    hiss = whisper_detail(drowned)
    assert phrase["dynamic_range_db"] > 15 and hiss["dynamic_range_db"] < 8
    assert hiss["flatness"] > 0.3 and hiss["high_band_share"] > 0.3
    assert whisper_detail(silence()) is None


def test_whisper_detail_is_cheap_and_never_changes_the_whisper_score(caplog):
    import logging
    import time

    from pratyaksh.signals import whisper_detail

    audio = syllables()
    with caplog.at_level(logging.WARNING, logger="pratyaksh.signals"):
        quiet = whisper_score(audio)
    with caplog.at_level(logging.INFO, logger="pratyaksh.signals"):
        logged = whisper_score(audio)
    assert quiet == logged
    assert any("dynamic_range_db" in r.getMessage() for r in caplog.records)

    took = []
    for _ in range(5):
        t0 = time.perf_counter()
        whisper_detail(audio)
        took.append(time.perf_counter() - t0)
    assert min(took) < 0.030  # per 3 s Response, on top of ~0.5 s of pitch tracking that runs beside speech-to-text

    s = extract(audio, PHRASE)
    # Of the diagnostics, only the dynamic range became a Signal (Live Microphone, Oct 29); flatness and the
    # high-band share stay logged only: the iPhone microphone's real whispers measure like the Clone on both.
    assert set(s.to_dict()) == {"transcript", "task_match", "whisper_score", "reply_latency_ms", "spoof_score",
                                "spoken_digits", "code_match", "dynamic_range_db"}


def test_a_real_whisper_still_passes_after_noise_was_tried():
    """The gate is the phrase, not the DSP: a Caller who whispers the phrase on the extra Challenge passes."""
    h = Harness(spoof=0.05)
    call_id = h.verifier.start_call(C, "r").call_id
    h.say(call_id, "add a payee")
    h.say(call_id, "", white(), 600)
    for _ in range(4):
        call = h.verifier.call(call_id)
        if call["state"] != "challenging":
            break
        if call["challenges"][-1]["kind"] == "possession_code":
            h.say(call_id, " ".join(h.code_on_device(C)), voiced(), 800)
        else:
            h.say(call_id, h.current_phrase(call_id), whispered(), 600)
    assert h.verifier.call(call_id)["outcome"] == Outcome.PASSED.value
