"""PromptVoice: what the Voice Agent says, cached on disk sentence by sentence."""

import io

import numpy as np
import pytest
import soundfile as sf
from conftest import Harness, voiced, whispered

from pratyaksh.domain import Audio, Outcome, Response
from pratyaksh.verification.verifier import spoken_lines
from pratyaksh.voice import PromptVoice

RATE = 16_000


class CountingVoice:
    """A synthesiser that speaks 0.1 s per word and remembers what it was asked to say."""

    name = "counting"

    def __init__(self):
        self.said: list[str] = []

    def synthesise(self, text: str) -> tuple[np.ndarray, int]:
        self.said.append(text)
        return np.full(int(0.1 * RATE) * len(text.split()), 0.1, dtype=np.float32), RATE


def seconds(wav: bytes) -> float:
    info = sf.info(io.BytesIO(wav))
    return info.frames / info.samplerate


class FlakyVoice(CountingVoice):
    """Fails on one sentence, like a TTS model running out of GPU memory."""

    def __init__(self, fails_on: str):
        super().__init__()
        self.fails_on = fails_on

    def synthesise(self, text: str) -> tuple[np.ndarray, int]:
        if text == self.fails_on:
            self.said.append(text)
            raise RuntimeError("CUDA out of memory")
        return super().synthesise(text)


class SlowTone:
    """A fallback at another sample rate: 0.2 s per word at 8 kHz."""

    name = "slow-tone"

    def synthesise(self, text: str) -> tuple[np.ndarray, int]:
        return np.full(1600 * len(text.split()), 0.05, dtype=np.float32), 8_000


def test_only_the_failed_sentence_falls_back_and_it_is_retried_next_time(tmp_path):
    synth = FlakyVoice(fails_on="I need one more check.")
    voice = PromptVoice(synth, tmp_path, fallback=SlowTone())
    wav = voice.render("Thank you. I need one more check.")
    # "Thank you." from the real voice (2 words x 0.1 s), the failed sentence from the fallback
    # (5 words x 0.2 s), and the pause between them.
    assert abs(seconds(wav) - (0.2 + 0.15 + 1.0)) < 0.01
    synth.fails_on = ""
    voice.render("Thank you. I need one more check.")
    assert synth.said == ["Thank you.", "I need one more check.", "I need one more check."]


def test_a_sentence_already_spoken_is_not_synthesised_again(tmp_path):
    synth = CountingVoice()
    voice = PromptVoice(synth, tmp_path)
    voice.render("Thank you. Please whisper these words: naale five baje meeting.")
    voice.render("Thank you. I need one more check. Please whisper these words: naale five baje meeting.")
    assert synth.said == [
        "Thank you.",
        "Please whisper these words: naale five baje meeting.",
        "I need one more check.",
    ]


@pytest.mark.parametrize("request_text", ["I want to add a new payee", "transfer 6 lakh to my brother", "change my sim"])
def test_every_challenge_prompt_the_verifier_issues_is_rendered_ahead_of_time(tmp_path, request_text):
    synth = CountingVoice()
    voice = PromptVoice(synth, tmp_path)
    voice.prewarm(spoken_lines())
    before = len(synth.said)

    h = Harness()
    call_id = h.verifier.start_call("cust-ananya", "r").call_id
    voice.render(h.verifier.current_step(call_id).say)
    step = h.say(call_id, request_text)
    voice.render(step.say)  # the Request's intro and the first Whisper Phrase
    step = h.say(call_id, h.current_phrase(call_id), whispered(), 800)
    voice.render(step.say)  # the next Challenge after a completed Whisper Phrase

    assert synth.said[before:] == []


class LoadingVoice(CountingVoice):
    """A synthesiser with a slow model load, like Parler (about a minute on the laptop GPU)."""

    def __init__(self):
        super().__init__()
        self.loaded = False

    def warm_up(self) -> None:
        self.loaded = True


def test_warming_up_loads_the_voice_even_when_every_prompt_is_cached(tmp_path):
    PromptVoice(CountingVoice(), tmp_path).prewarm(["Namaskara.", "How can I help you today?"])
    synth = LoadingVoice()
    PromptVoice(synth, tmp_path).prewarm(["Namaskara.", "How can I help you today?"])  # after a restart
    assert synth.loaded and synth.said == []  # ready for the first line that is not cached yet


class SometimesSilentVoice(CountingVoice):
    """Like Parler, which samples and now and then generates no speech at all for a short sentence."""

    def __init__(self, silent_times: int):
        super().__init__()
        self.silent_times = silent_times

    def synthesise(self, text: str) -> tuple[np.ndarray, int]:
        samples, rate = super().synthesise(text)
        if self.silent_times:
            self.silent_times -= 1
            return np.zeros(1, dtype=np.float32), rate
        return samples, rate


def test_a_voice_that_generates_no_speech_is_asked_again(tmp_path):
    synth = SometimesSilentVoice(silent_times=1)
    voice = PromptVoice(synth, tmp_path)
    assert abs(seconds(voice.render("Thank you.")) - 0.2) < 0.01
    assert seconds(voice.render("Thank you.")) > 0.1 and synth.said == ["Thank you.", "Thank you."]


def test_no_speech_twice_falls_back_and_is_not_cached(tmp_path):
    synth = SometimesSilentVoice(silent_times=2)
    voice = PromptVoice(synth, tmp_path, fallback=SlowTone())
    assert abs(seconds(voice.render("Thank you.")) - 0.4) < 0.01  # the fallback's 2 words x 0.2 s
    voice.render("Thank you.")
    assert synth.said == ["Thank you.", "Thank you.", "Thank you."]  # tried again: nothing silent was cached


@pytest.fixture(scope="module")
def voiced_ahead(tmp_path_factory):
    """Every line in spoken_lines() voiced once, shared by the tests below (about 1,400 small WAVs)."""
    synth = CountingVoice()
    voice = PromptVoice(synth, tmp_path_factory.mktemp("tts"))
    voice.prewarm(spoken_lines())
    return voice, synth


def _no_synthesis_on_the_call(voiced_ahead, steps) -> list[str]:
    voice, synth = voiced_ahead
    before = len(synth.said)
    for step in steps:
        voice.render(step.say)
    return synth.said[before:]


def test_repeats_retries_and_endings_are_rendered_ahead_of_time(voiced_ahead):
    h = Harness()
    call_id = h.verifier.start_call("cust-ananya", "r").call_id
    steps = [h.say(call_id, "I want to add a new payee")]
    steps.append(h.verifier.respond(call_id, Response(Audio.silence(2.0), None)))  # heard nothing
    steps.append(h.say(call_id, "sorry, can you repeat that?"))
    steps.append(h.say(call_id, h.current_phrase(call_id), whispered(), 800))
    steps.append(h.say(call_id, "one one one one one one", voiced(), 900))  # misread code
    steps.append(h.say(call_id, h.code_on_device("cust-ananya"), voiced(), 900))
    assert steps[-1].outcome is not None and steps[-1].end
    assert _no_synthesis_on_the_call(voiced_ahead, steps) == []


def test_a_step_up_and_a_block_are_rendered_ahead_of_time(voiced_ahead):
    h = Harness()
    call_id = h.verifier.start_call("cust-rahul", "r").call_id
    steps = [h.say(call_id, "I want to change my SIM")]
    for _ in range(6):
        if steps[-1].end:
            break
        call = h.verifier.call(call_id)
        if call["challenges"][-1]["kind"] == "possession_code":
            steps.append(h.say(call_id, h.code_on_device("cust-rahul"), voiced(), 900))
        else:
            steps.append(h.say(call_id, h.current_phrase(call_id), voiced(), 800))  # said aloud, not whispered
    assert steps[-1].outcome is Outcome.BLOCKED
    assert _no_synthesis_on_the_call(voiced_ahead, steps) == []


def test_app_approval_is_rendered_ahead_of_time(voiced_ahead):
    h = Harness()
    call_id = h.verifier.start_call("cust-meera", "r").call_id
    steps = [h.say(call_id, "transfer 7 lakh to my brother")]
    steps.append(h.say(call_id, "I can't do this, use the bank app"))
    steps.append(h.approve(call_id, "cust-meera"))
    assert steps[-1].end
    assert _no_synthesis_on_the_call(voiced_ahead, steps) == []


def test_an_abbreviation_does_not_end_a_sentence(tmp_path):
    synth = CountingVoice()
    PromptVoice(synth, tmp_path).render("Daily UPI transfers are capped at Rs. 1 lakh. Is there anything else?")
    assert synth.said == ["Daily UPI transfers are capped at Rs. 1 lakh.", "Is there anything else?"]
