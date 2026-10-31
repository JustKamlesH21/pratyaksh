from pathlib import Path

import numpy as np
import pytest

from pratyaksh import signals
import yaml
from conftest import voiced, whispered

import pratyaksh.policy
from pratyaksh.domain import SAMPLE_RATE, Audio, Challenge, ChallengeKind, Response
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


def test_a_digit_word_heard_slightly_wrong_still_counts_but_never_as_another_digit():
    # A whispered Kannada "entu" (8) comes out clipped ("ent"); the digit is the anti-replay part, so a
    # near miss counts only when it is clearly that digit and no other.
    assert phrase_match("8 gantege hospital ge banni", "ent gantege hospital ge banni") >= 0.95
    assert phrase_match("naale 2 gantege class ide", "naale endu gantege class ide") <= 0.5  # 8 or 2?
    assert phrase_match("naale 7 baje meeting", "naale at baje meeting") <= 0.5  # "aath" is 8, not 7
    assert phrase_match("naale 1 baje meeting", "naale sone baje meeting") <= 0.5  # "sonne" is 0


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


def test_a_whisper_played_in_digitally_has_no_microphone_background_noise():
    # Oct 29: the Clone, played through a virtual cable, arrived with exact digital silence around the words
    # (dynamic range 177-192 dB). Every live microphone measured 8.6-40.2 dB (30 real whispers on the
    # iPhone and AirPods) and recorded human whispers 9.8-45.6 dB: a room is never that quiet.
    models = ScriptedSpeechModels(["naale seven baje meeting"] * 2)
    challenge = Challenge(ChallengeKind.WHISPER_PHRASE, "", "naale 7 baje meeting")
    live = SignalExtractor(models).extract(challenge, Response(whispered(), 650))
    assert live.dynamic_range_db is not None and live.dynamic_range_db < 60

    gap = Audio.silence(0.6).samples  # exact zeros, as the cable delivers between clips
    injected = Audio(np.concatenate([gap, whispered().samples, gap]))
    played = SignalExtractor(models).extract(challenge, Response(injected, 650))
    assert played.dynamic_range_db > 60
    assert played.whisper_score == live.whisper_score  # the whisper itself is just as convincing


def test_a_possession_code_has_no_live_microphone_signal():
    s = SignalExtractor(ScriptedSpeechModels(["4 8 1 9 2 7"])).extract(
        Challenge(ChallengeKind.POSSESSION_CODE, ""), Response(voiced(), 900)
    )
    assert s.dynamic_range_db is None


def test_a_hindi_caller_who_talks_instead_of_reading_the_code_is_heard_in_hindi():
    # Oct 29: "मैं OTP क्यों दूँ? आप स्कैम भी हो सकते हो", heard in English as the code step then was, came
    # out "I can't do OTP, you can do an upscam." Heard in Hindi, the Interpreter can answer it.
    models = ScriptedSpeechModels(["मैं OTP क्यूंदू, आप स्कैम भी हो सकते हो।"])
    s = SignalExtractor(models).extract(Challenge(ChallengeKind.POSSESSION_CODE, ""), Response(voiced(), 900), "hi")
    assert s.transcript == "मैं OTP क्यूंदू, आप स्कैम भी हो सकते हो।"
    assert len(s.spoken_digits or "") < 4  # not a code attempt: the Interpreter answers it


@pytest.mark.parametrize("heard, code", [
    # Hindi digit words as speech-to-text spelled them (Parler reading codes, Oct 30).
    ("शून्य चे पांच तीन तीन पांच", "065335"),
    ("पाँच दीन पाँच दीन सात शून्यू", "535370"),
    ("चार पाँच एक दीन एक दीन", "451313"),
    ("चे पाच तीन चे शून्य सात", "653607"),
    ("चे तीन आज तीन नौ सात", "638397"),
    ("शार साथ पाँच दो पाँच एक", "475251"),
    ("टीन शून्यो नौ पाँच एक छह", "309516"),
    # In hall chatter (Parler with other speech mixed in, Oct 31).
    ("आठ चै तीन नौ एक एक", "863911"),
    ("डों एक आठ तीन दो दो", "218322"),
    ("Shunya Che, punch din din punch.", "065335"),
])
def test_hindi_digit_words_as_speech_to_text_spells_them_read_as_the_code(heard, code):
    assert spoken_digits(heard) == code


def test_code_only_digit_spellings_never_change_a_whisper_phrase():
    # "आज" (today) and "दिन" (day) are read as 8 and 3 only in a Possession Code readout.
    assert phrase_match("aaj 7 baje dinner hai", "aaj saat baje dinner hai") == 1.0
    assert phrase_match("aaj 7 baje dinner hai", "aaj aath baje dinner hai") <= 0.5


@pytest.mark.parametrize("heard", ["8, 2, 3, 7, 1, 5.", "823-715", "आठ दो तीन सात एक पाँच।"])
def test_a_hindi_caller_reading_the_code_in_english_or_hindi_words_is_read(heard):
    models = ScriptedSpeechModels([heard])
    s = SignalExtractor(models).extract(Challenge(ChallengeKind.POSSESSION_CODE, ""), Response(voiced(), 900), "hi")
    assert s.spoken_digits == "823715"


def _read_code(transcripts, language):
    models = ScriptedSpeechModels(transcripts)
    challenge = Challenge(ChallengeKind.POSSESSION_CODE, "")
    return SignalExtractor(models).extract(challenge, Response(voiced(), 900), language), models


def test_a_hindi_callers_code_is_heard_in_hindi_and_in_english():
    # Oct 31, venue: Rahul read 740065; heard in Hindi alone it came out 7400-065, then 540065.
    s, models = _read_code(["7400-065", "7 4 0 0 6 5"], "hi")
    assert [h.language for h in models.hints] == ["hi", "en"]
    assert (s.spoken_digits, s.other_digits) == ("7400065", "740065")
    assert s.transcript == "7400-065"  # what the Caller sees and the Interpreter hears stays the Hindi reading


def test_when_only_the_english_reading_has_digits_it_is_the_reading():
    s, _ = _read_code(["कृपया रुकिए", "8 2 3 7 1 5"], "hi")
    assert (s.spoken_digits, s.other_digits) == ("823715", None)


def test_two_readings_that_agree_are_one_reading():
    s, _ = _read_code(["8 2 3 7 1 5", "823715"], "kn")
    assert (s.spoken_digits, s.other_digits) == ("823715", None)


def test_an_english_customers_code_is_heard_once():
    s, models = _read_code(["8 2 3 7 1 5"], "en")
    assert len(models.hints) == 1 and s.other_digits is None


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


def test_eight_heard_as_the_letter_a_still_reads_the_code():
    # iPhone Call, Oct 29: code 826701 read as "eight two six..." was written "A26701", which read as no
    # digits at all. A letter fused with digits never counts as nothing.
    assert spoken_digits("A26701") == "826701"
    assert spoken_digits("5A3, 2A1") == "583281"
    assert spoken_digits("It's A26701.") == "826701"
    assert spoken_digits("two six ate one") == "2681"
    assert spoken_digits("I have a code") == ""  # an ordinary "a" is not a digit


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


@pytest.mark.parametrize("customer_language, heard_in", [("kn", "kn"), ("hi", "hi"), ("en", "en"), (None, "en")])
def test_possession_code_digits_are_heard_where_they_transcribe_best(customer_language, heard_in):
    # Measured (Oct 27): Kannada digit words in English came out as "4N2,197"; in Kannada, as Kannada digit words.
    # Hindi (Oct 30, Parler reading 52 codes): heard in Hindi with the Hindi digit words as hotwords, 27/40 codes
    # read in Hindi words came out right (in English 10/40) and 12/12 read in English words (in English 12/12).
    models = ScriptedSpeechModels(["4 8 1 9 2 7"])
    challenge = Challenge(ChallengeKind.POSSESSION_CODE, "")
    SignalExtractor(models).extract(challenge, Response(voiced(), 900), customer_language)
    assert models.hints[0].language == heard_in
    assert ("सात" in (models.hints[0].hotwords or "")) == (heard_in == "hi")


def test_a_whisper_phrase_is_heard_in_latin_whatever_the_customers_language():
    models = ScriptedSpeechModels(["naale elu gantege meeting ide"])
    SignalExtractor(models).extract(
        Challenge(ChallengeKind.WHISPER_PHRASE, "", "naale 7 gantege meeting ide"), Response(whispered(), 650), "kn"
    )
    # Latin letters, and the digit as the Customer was asked to say it (in Kannada).
    assert models.hints == [TranscriptionHint(language="en", hotwords="naale elu gantege meeting ide")]


def test_the_logged_whisper_diagnostic_can_never_fail_a_response(monkeypatch):
    import logging

    import pratyaksh.signals as signals

    def broken(audio):
        raise ValueError("odd sample rate")

    monkeypatch.setattr(signals, "whisper_detail", broken)
    logging.getLogger("pratyaksh.signals").setLevel(logging.INFO)
    assert signals.whisper_score(whispered()) is not None


def _hum(pitch_hz):
    """Voiced sound whose pitch follows pitch_hz(t)."""
    t = np.arange(int(3 * SAMPLE_RATE)) / SAMPLE_RATE
    phase = 2 * np.pi * np.cumsum(pitch_hz(t)) / SAMPLE_RATE
    return Audio(sum((0.3 / k) * np.sin(k * phase) for k in range(1, 6)).astype(np.float32))


def test_a_voice_with_dead_steady_pitch_is_flagged():
    assert signals.voice_check(_hum(lambda t: 150 + 0 * t))["score"] == 1.0


def test_a_voice_whose_pitch_moves_like_speech_is_in_the_human_range():
    assert signals.voice_check(_hum(lambda t: 150 + 25 * np.sin(2 * np.pi * 0.7 * t)))["score"] == 0.0


def test_a_shaky_pitch_is_flagged():
    shaky = np.random.default_rng(1).normal(0, 16, int(3 * SAMPLE_RATE) // 256 + 2)
    assert signals.voice_check(_hum(lambda t: 150 + shaky[(t * SAMPLE_RATE / 256).astype(int)]))["score"] > 0.5


def test_silence_has_no_pitch_to_check():
    assert signals.voice_check(Audio(np.zeros(SAMPLE_RATE, dtype=np.float32))) is None


@pytest.mark.parametrize("scores, label", [([0.0, 0.1], "likely_human"), ([0.0, 0.8], "unsure"), ([0.9, 0.8], "likely_ai")])
def test_a_calls_ai_voice_check_is_the_mean_of_its_spoken_turns(scores, label):
    summary = signals.ai_voice_summary([{"wobble": 0.01, "score": s} for s in scores])
    assert summary["label"] == label and summary["turns"] == 2


def test_no_spoken_turn_means_no_ai_voice_check():
    assert signals.ai_voice_summary([]) is None
