"""The Interpreter understands Requests that speech-to-text mangled, and never waits on a dead LLM."""

import httpx
import pytest

from pratyaksh.domain import RequestKind
from pratyaksh.verification.interpreter import NO_ANSWER, Faq, Interpreter, OllamaChat, TurnKind

FAQ = Faq.load()


class NoLLM:
    """Fails the test if the LLM is asked: these must be understood offline."""

    def complete_json(self, system, user):
        raise AssertionError(f"the LLM was asked about {user!r}")


# What faster-whisper wrote for loanwords said in Hindi or Kannada (Devanagari, Kannada script or
# romanised). The exact keyword rules miss every one of these.
MANGLED = [
    ("मुझे नया पाई आड़ करना है", RequestKind.ADD_PAYEE),  # heard on the real system for "मुझे नया पेयी ऐड करना है"
    ("I want to add a new bee.", RequestKind.ADD_PAYEE),  # heard from an iPhone Caller, Oct 27, for "payee"
    ("Add a new P.", RequestKind.ADD_PAYEE),  # heard from an iPhone Caller, Oct 27
    ("Add a P", RequestKind.ADD_PAYEE),  # heard from an iPhone Caller, Oct 27
    ("add a bee", RequestKind.ADD_PAYEE),
    ("add a new pee", RequestKind.ADD_PAYEE),
    ("पेई ऐड करना है", RequestKind.ADD_PAYEE),
    ("नया पे ऐड करना है", RequestKind.ADD_PAYEE),
    ("मुझे नया पेई जोड़ना है", RequestKind.ADD_PAYEE),
    ("नया पाई जोड़ना है", RequestKind.ADD_PAYEE),
    ("naya pai add karna hai", RequestKind.ADD_PAYEE),
    ("pei jodna hai", RequestKind.ADD_PAYEE),
    ("add a new pay please", RequestKind.ADD_PAYEE),
    ("ಹೊಸ ಪೇ ಆಡ್ ಮಾಡಬೇಕು", RequestKind.ADD_PAYEE),
    ("ಹೊಸ ಪೇ ಸೇರಿಸಿ", RequestKind.ADD_PAYEE),
    ("बेनिफिशरी ऐड करो", RequestKind.ADD_PAYEE),
    ("ಬೆನಿಫಿಷರಿ ಸೇರಿಸಬೇಕು", RequestKind.ADD_PAYEE),
    ("पासवड रिसेट करना है", RequestKind.SIM_SWAP),
    ("मुझे पासबर्ड बदलना है", RequestKind.SIM_SWAP),
    ("ನನ್ನ ಪಾಸ್ವಡ್ ಬದಲಾಯಿಸಬೇಕು", RequestKind.SIM_SWAP),
    ("रीसेट करना है", RequestKind.SIM_SWAP),
    ("एमपिन बदलना है", RequestKind.SIM_SWAP),
    ("मोबाइल नंबर बदलना है", RequestKind.SIM_SWAP),
    ("ಮೊಬೈಲ್ ನಂಬರ್ ಚೇಂಜ್ ಮಾಡಿ", RequestKind.SIM_SWAP),
    ("सिमकार्ड बदलना है", RequestKind.SIM_SWAP),
    ("टांसफर करना है", RequestKind.HIGH_VALUE_TRANSFER),
    ("मुझे पैसे ट्रैन्स्फर करने हैं", RequestKind.HIGH_VALUE_TRANSFER),
    ("ಟ್ರಾಸ್ಫರ್ ಮಾಡಬೇಕು", RequestKind.HIGH_VALUE_TRANSFER),
    ("five lacs to my brother please", RequestKind.HIGH_VALUE_TRANSFER),
    ("बेलेंस कितना है?", RequestKind.BALANCE_ENQUIRY),
    ("मेरा बैलन्स बताओ", RequestKind.BALANCE_ENQUIRY),
    ("ಬ್ಯಾಲನ್ಸ್ ಎಷ್ಟು ಇದೆ?", RequestKind.BALANCE_ENQUIRY),
    ("ಬ್ಯಾಲನ್ಸನ್ನು ಚೆಕ್ ಮಾಡಿ", RequestKind.BALANCE_ENQUIRY),
    ("belence check karo", RequestKind.BALANCE_ENQUIRY),
    # Heard from an iPhone Caller on AirPods, Oct 29.
    ("Harder pay.", RequestKind.ADD_PAYEE),
    ("I want to change myself.", RequestKind.SIM_SWAP),
    ("I want to change my sin.", RequestKind.SIM_SWAP),
    # Natural sentences with the key word misheard (Indian-accented English through speech-to-text).
    ("I would like to change my scene card", RequestKind.SIM_SWAP),
    ("I want to change my same card", RequestKind.SIM_SWAP),
    ("I want to change my simcard", RequestKind.SIM_SWAP),
    ("I want to change my pass word", RequestKind.SIM_SWAP),
    ("I want to add a new payday", RequestKind.ADD_PAYEE),
    ("I'd like to add a new benefit sherry", RequestKind.ADD_PAYEE),
    ("I want to add a benefactor", RequestKind.ADD_PAYEE),
    ("I want to trans for money", RequestKind.HIGH_VALUE_TRANSFER),
    ("चेक्ट बार्णस", RequestKind.BALANCE_ENQUIRY),  # heard on the iPhone, Oct 29: "check balance"
    # The riskiest Request still wins.
    ("पासवड रिसेट करना है और बेलेंस भी", RequestKind.SIM_SWAP),
    ("पेई ऐड करके टांसफर करना है", RequestKind.HIGH_VALUE_TRANSFER),
]


@pytest.mark.parametrize("said, kind", MANGLED)
def test_mangled_loanwords_are_understood_offline(said, kind):
    u = Interpreter(NoLLM(), FAQ).understand(said)
    assert (u.kind, u.request, u.by_llm, u.by_variant) == (TurnKind.REQUEST, kind, False, True)


@pytest.mark.parametrize("said", ["please add a new payee", "मुझे नया पेयी जोड़ना है", "मुझे पासवर्ड रिसेट करना है"])
def test_a_request_matched_by_its_keywords_is_not_marked_as_a_variant(said):
    u = Interpreter(NoLLM(), FAQ).understand(said)
    assert u.kind is TurnKind.REQUEST and not u.by_variant


def test_the_transcript_shows_a_request_understood_from_a_mangled_loanword():
    from conftest import Harness

    h = Harness()
    for said, variant in [("मुझे नया पाई आड़ करना है", True), ("please add a new payee", False)]:
        call_id = h.verifier.start_call("cust-ananya", "r").call_id
        h.say(call_id, said)
        call = h.verifier.call(call_id)
        event = next(e["data"] for e in call["events"] if e["kind"] == "caller_said")
        line = next(ln for ln in call["transcript"] if ln["speaker"] == "caller")
        assert (call["request"], event["by_variant"], line.get("by_variant", False)) == ("add_payee", variant, variant)


# Ordinary words that look like a mangled loanword, and Questions about a Request: none of these is
# that Request. ("pai" is a Hindi word; "pe" means "on".)
NOT_A_REQUEST = [
    ("mujhe pai khana hai", RequestKind.ADD_PAYEE),
    ("ek pai bhi nahi bachi", RequestKind.ADD_PAYEE),
    ("पाई का मान क्या होता है?", RequestKind.ADD_PAYEE),
    ("मुझे पे करना है", RequestKind.ADD_PAYEE),
    ("mere account pe paise add karo", RequestKind.ADD_PAYEE),
    ("फोन पे जोर से बोलो", RequestKind.ADD_PAYEE),
    ("पाई जोड़ के रखा है", RequestKind.ADD_PAYEE),  # saved every paisa
    ("ek ek pai jod ke rakha hai", RequestKind.ADD_PAYEE),
    ("मुझे बिल पे करना है", RequestKind.ADD_PAYEE),
    ("मेरे फोन पे मैसेज नहीं आया", RequestKind.ADD_PAYEE),
    ("I want to add money to my wallet", RequestKind.ADD_PAYEE),
    ("a bee stung me", RequestKind.ADD_PAYEE),
    ("add a new B2B account to my profile", RequestKind.ADD_PAYEE),
    ("can you spell P for me", RequestKind.ADD_PAYEE),
    ("रिसीट चाहिए", RequestKind.SIM_SWAP),  # receipt, not reset
    ("पेई ऐड करना सेफ है क्या?", RequestKind.ADD_PAYEE),
    ("pai add karne ka tarika kya hai?", RequestKind.ADD_PAYEE),
    ("ಪೇ ಮಾಡಬೇಕು", RequestKind.ADD_PAYEE),
    ("मिनिमम बेलेंस क्या है?", RequestKind.BALANCE_ENQUIRY),
    ("ಕನಿಷ್ಠ ಬ್ಯಾಲನ್ಸ್ ಎಷ್ಟು?", RequestKind.BALANCE_ENQUIRY),
    ("मेरा पासपोर्ट खो गया", RequestKind.SIM_SWAP),
    ("मेरा परिवार ठीक है", RequestKind.SIM_SWAP),
    ("टांसफर में कितना टाइम लगता है?", RequestKind.HIGH_VALUE_TRANSFER),
    ("transport ka kharcha bahut hai", RequestKind.HIGH_VALUE_TRANSFER),
    ("tension mat lo", RequestKind.HIGH_VALUE_TRANSFER),
    ("रास्ता बताओ", RequestKind.SIM_SWAP),
    # Near-sound rules (Oct 29) must not fire on ordinary sentences.
    ("I want the same card again", RequestKind.SIM_SWAP),
    ("my son carted the boxes", RequestKind.SIM_SWAP),
    ("is there some card offer", RequestKind.SIM_SWAP),
    ("I want to add a payment reminder", RequestKind.ADD_PAYEE),
    ("I got the benefit already", RequestKind.ADD_PAYEE),
    ("Barnes and Noble", RequestKind.BALANCE_ENQUIRY),
    ("trans people", RequestKind.HIGH_VALUE_TRANSFER),
    ("हेलो, आप कैसे हो?", None),
    ("ನಮಸ್ಕಾರ, ಹೇಗಿದ್ದೀರಾ?", None),
]


@pytest.mark.parametrize("said, kind", NOT_A_REQUEST)
def test_lookalike_words_and_questions_are_not_taken_as_a_request(said, kind):
    u = Interpreter(faq=FAQ).understand(said)
    assert u.kind is not TurnKind.REQUEST or (kind is not None and u.request is not kind)


class FlakyLLM:
    """An LLM that is down (raises) until told otherwise, counting calls."""

    def __init__(self, error: Exception):
        self.error, self.calls = error, 0

    def complete_json(self, system, user):
        self.calls += 1
        if self.error:
            raise self.error
        return {"kind": "request", "request": "account_service"}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize("error", [httpx.ConnectTimeout("no route"), httpx.ConnectError("refused"),
                                   httpx.ReadTimeout("slow"), RuntimeError("boom")])
def test_after_the_llm_fails_it_is_skipped_for_a_while(error):
    llm, clock = FlakyLLM(error), Clock()
    interpreter = Interpreter(llm, FAQ, clock=clock)
    first = interpreter.understand("please sort out my standing instructions")
    assert first.kind is TurnKind.UNCLEAR and llm.calls == 1

    clock.now += 30  # the LLM is not asked again during the cool-down; answers still come offline
    assert interpreter.understand("please sort out my standing instructions").kind is TurnKind.UNCLEAR
    assert interpreter.understand("hmm so tell me about the zebra thing?").reply == NO_ANSWER
    assert interpreter.understand("hello?").kind is TurnKind.CHAT
    assert interpreter.understand("मुझे नया पाई आड़ करना है").request is RequestKind.ADD_PAYEE
    assert llm.calls == 1

    clock.now += 31  # after the cool-down it is tried once more
    llm.error = None
    u = interpreter.understand("please sort out my standing instructions")
    assert (u.request, u.by_llm, llm.calls) == (RequestKind.ACCOUNT_SERVICE, True, 2)


def test_an_llm_that_is_still_down_after_the_cool_down_is_skipped_again():
    llm, clock = FlakyLLM(httpx.ConnectTimeout("no route")), Clock()
    interpreter = Interpreter(llm, FAQ, clock=clock)
    interpreter.understand("please sort out my standing instructions")
    clock.now += 61
    interpreter.understand("please sort out my standing instructions")
    clock.now += 30
    interpreter.understand("please sort out my standing instructions")
    assert llm.calls == 2


def test_a_reply_the_llm_got_wrong_does_not_take_it_offline():
    class Garbled:
        calls = 0

        def complete_json(self, system, user):
            self.calls += 1
            return {"kind": 42, "request": ["nonsense"]}

    llm = Garbled()
    interpreter = Interpreter(llm, FAQ, clock=Clock())
    interpreter.understand("please sort out my standing instructions")
    interpreter.understand("please sort out my standing instructions")
    assert llm.calls == 2


def test_an_unreachable_llm_is_given_up_on_within_a_second_but_may_take_its_time_to_answer():
    timeout = OllamaChat("http://127.0.0.1:9", "m")._client.timeout
    assert timeout.connect <= 1.0 and timeout.read >= 6.0


@pytest.mark.parametrize("said", ["From where to read the OTP?", "where do I find the code?", "OTP kahan milega?",
                                  "ಕೋಡ್ ಎಲ್ಲಿ ಸಿಗುತ್ತೆ?"])
def test_where_is_the_code_is_answered_offline_during_the_code_challenge(said):
    # Asked on a real iPhone Call (Oct 27): the LLM's answer mentioned "OTP" and was dropped.
    from pratyaksh.domain import ChallengeKind
    from pratyaksh.verification.interpreter import Context

    u = Interpreter(NoLLM(), faq=FAQ).understand(said, Context(challenge=ChallengeKind.POSSESSION_CODE))
    assert u.kind is TurnKind.QUESTION and "bank app" in FAQ.entries[[e.id for e in FAQ.entries].index("why_code")].answers["en"]
    assert u.reply in [a for e in FAQ.entries if e.id == "why_code" for a in e.answers.values()]


@pytest.mark.parametrize("said, lang", [
    ("मैं OTP क्यूंदू, आप स्कैम भी हो सकते हो।", "hi"),  # heard in Hindi on the iPhone, Oct 29 (said with no "?")
    ("main otp kyun du, aap scam bhi ho sakte ho", "hi"),
    ("Why should I give you the OTP? You could be a scam.", "en"),
    ("how do I know you are not a fraud", "en"),
    ("ನಾನು ಯಾಕೆ ಒಟಿಪಿ ಹೇಳಬೇಕು, ನೀವು ಮೋಸ ಮಾಡಬಹುದು", "kn"),
])
def test_a_caller_worried_the_code_request_is_a_scam_is_reassured_at_the_code_step(said, lang):
    # The worry, not a fraud report: the answer is the scam-safety rule and why this code is different.
    from pratyaksh.domain import ChallengeKind
    from pratyaksh.verification.interpreter import Context

    u = Interpreter(NoLLM(), faq=FAQ).understand(said, Context(challenge=ChallengeKind.POSSESSION_CODE))
    worry = next(e for e in FAQ.entries if e.id == "code_scam_worry")
    assert u.kind is TurnKind.QUESTION and u.reply == worry.answers[lang]


@pytest.mark.parametrize("said", ["pai add kaise hota hai? mera balance batao", "पाई ऐड कैसे होता है? मेरा बैलेंस बताओ"])
def test_a_question_that_only_sounds_risky_does_not_hide_a_plain_request(said):
    # Code review (Oct 28): a payee sound-alike inside a Question stopped the search before "balance".
    u = Interpreter(NoLLM(), faq=FAQ).understand(said)
    assert u.kind is TurnKind.REQUEST and u.request is RequestKind.BALANCE_ENQUIRY
