from pathlib import Path

import pytest
import yaml
from conftest import voiced, whispered

import pratyaksh.policy
from pratyaksh.domain import Challenge, ChallengeKind, Response
from pratyaksh.language import spoken_digits
from pratyaksh.signals import (
    ScriptedSpeechModels, SignalExtractor, TranscriptionHint, phrase_match, whisper_score,
)


def test_whisper_score_separates_whispers_from_normal_speech():
    assert whisper_score(whispered()) >= 0.8
    assert whisper_score(voiced()) <= 0.3


def test_phrase_match_ignores_script_and_number_words():
    phrase = "naale 7 baje meeting"
    assert phrase_match(phrase, "naale seven baje meeting") >= 0.95
    assert phrase_match(phrase, "ನಾಳೆ ಏಳು ಬಜೆ ಮೀಟಿಂಗ್") >= 0.95
    assert phrase_match(phrase, "nale saat baje meting hai") >= 0.80
    assert phrase_match(phrase, "meeting") < 0.70
    assert phrase_match(phrase, "please transfer the money now") < 0.50


def test_spoken_digits_in_three_languages():
    assert spoken_digits("my code is four eight ondu nine do saat") == "481927"
    assert spoken_digits("चार आठ १ ೨ six aath") == "481268"
    assert spoken_digits("4 8 1 9 2 7") == "481927"


def test_extract_whisper_phrase_signals():
    models = ScriptedSpeechModels(["naale seven baje meeting"], spoof=0.1)
    s = SignalExtractor(models).extract(
        Challenge(ChallengeKind.WHISPER_PHRASE, "", "naale 7 baje meeting"), Response(whispered(), 650)
    )
    assert s.task_match >= 0.95
    assert s.whisper_score >= 0.8
    assert s.reply_latency_ms == 650
    assert s.spoof_score == 0.1
    assert s.code_match is None


def test_extract_possession_code_reads_digits_only():
    models = ScriptedSpeechModels(["the code is 4 8 1 nine two seven"])
    s = SignalExtractor(models).extract(Challenge(ChallengeKind.POSSESSION_CODE, ""), Response(voiced(), 900))
    assert s.spoken_digits == "481927"
    assert s.task_match is None and s.whisper_score is None


def test_no_speech_gives_no_signals():
    s = SignalExtractor(ScriptedSpeechModels(["ignored"])).extract(
        Challenge(ChallengeKind.WHISPER_PHRASE, "", "x"), Response(voiced(0.05), None)
    )
    assert s.reply_latency_ms is None and s.transcript == ""


def test_repeated_digits_survive_folding():
    assert spoken_digits("414002") == "414002"
    assert spoken_digits("double check: 7 7 0 0 one one") == "770011"


def test_whisper_phrase_is_heard_in_latin_with_the_phrase_as_hotwords():
    models = ScriptedSpeechModels(["School ally 8 Bajay Party"], spoof=0.1)
    s = SignalExtractor(models).extract(
        Challenge(ChallengeKind.WHISPER_PHRASE, "", "school alli 8 baje party"), Response(whispered(), 650)
    )
    assert models.hints == [TranscriptionHint(language="en", hotwords="school alli eight baje party")]
    assert s.task_match >= 0.70


@pytest.mark.parametrize("phrase, heard", [
    ("school alli 8 baje party", "School ally 8 Bajay Party"),  # whispered, heard on the real system (Oct 27)
    ("beligge 7 baje match", "Belik 7 Baji match."),
])
def test_whispered_phrases_as_really_heard_pass_task_match(phrase, heard):
    assert phrase_match(phrase, heard) >= _policy_task_min()


@pytest.mark.parametrize("heard", ["School ally 9 Bajay Party", "School ally Bajay Party"])
def test_a_wrong_or_missing_digit_still_fails_task_match(heard):
    assert phrase_match("school alli 8 baje party", heard) < _policy_task_min()


def _policy_task_min() -> float:
    raw = yaml.safe_load((Path(pratyaksh.policy.__file__).with_name("policy.yaml")).read_text(encoding="utf-8"))
    return float(raw["signals"]["task_match"]["min"])


@pytest.mark.parametrize("language", ["kn", "hi", "en"])
def test_a_request_is_transcribed_in_the_given_language(language):
    models = ScriptedSpeechModels(["add a payee"])
    assert SignalExtractor(models).transcribe(voiced(), language) == "add a payee"
    assert models.hints == [TranscriptionHint(language=language)]


@pytest.mark.parametrize("customer_language, heard_in", [("kn", "kn"), ("hi", "en"), ("en", "en"), (None, "en")])
def test_possession_code_digits_are_heard_where_they_transcribe_best(customer_language, heard_in):
    # Measured (Oct 27): Hindi digit words forced to Hindi came out as "aart", "naav", "do", "sait"; in English as
    # 481927. Kannada digit words in English came out as "4N2,197"; in Kannada, as Kannada digit words.
    models = ScriptedSpeechModels(["4 8 1 9 2 7"])
    challenge = Challenge(ChallengeKind.POSSESSION_CODE, "")
    SignalExtractor(models).extract(challenge, Response(voiced(), 900), customer_language)
    assert models.hints == [TranscriptionHint(language=heard_in)]


def test_a_whisper_phrase_is_heard_in_latin_whatever_the_customers_language():
    models = ScriptedSpeechModels(["naale elu gantege meeting ide"])
    SignalExtractor(models).extract(
        Challenge(ChallengeKind.WHISPER_PHRASE, "", "naale 7 gantege meeting ide"), Response(whispered(), 650), "kn"
    )
    # Latin letters, and the digit as the Customer was asked to say it (in Kannada).
    assert models.hints == [TranscriptionHint(language="en", hotwords="naale elu gantege meeting ide")]
