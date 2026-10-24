from conftest import voiced, whispered

from pratyaksh.domain import Challenge, ChallengeKind, Response
from pratyaksh.language import spoken_digits
from pratyaksh.signals import ScriptedSpeechModels, SignalExtractor, phrase_match, whisper_score


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
