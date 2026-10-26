"""PromptVoice: what the Voice Agent says, cached on disk sentence by sentence."""

import io

import numpy as np
import pytest
import soundfile as sf
from conftest import Harness, whispered

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
