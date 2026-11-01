"""run_call with a scripted CallAudio and a real Verifier behind InProcessVerifier."""

import asyncio

from conftest import Harness, voiced, whispered

from pratyaksh.agent.call_loop import Timing, run_call
from pratyaksh.agent.ports import CallerLeft, InProcessVerifier
from pratyaksh.domain import Outcome, Response
from pratyaksh.verification.verifier import ONE_MOMENT, spoken_lines
from pratyaksh.voice import PromptVoice, ToneVoice

C = "cust-meera"


class ScriptedCaller:
    """Answers each prompt with a function of what it just heard."""

    def __init__(self, h: Harness, answers, leave_after: int | None = None):
        self.h = h
        self.answers = list(answers)
        self.heard: list[str] = []
        self.leave_after = leave_after

    async def play(self, wav: bytes, caption: str) -> None:
        assert wav[:4] == b"RIFF"
        self.heard.append(caption)

    async def show(self, message: dict) -> None:
        pass

    def caller_left(self) -> bool:
        return False

    async def listen(self, timeout_s: float, max_reply_s: float, pause_s: float = 0.0) -> Response:
        if self.leave_after is not None and len(self.heard) > self.leave_after:
            raise CallerLeft()
        transcript, audio, latency = self.answers.pop(0)(self.heard[-1])
        self.h.models.push(transcript)
        return Response(audio, latency)


def run(h: Harness, caller: ScriptedCaller, tmp_path, **kw):
    port = InProcessVerifier(h.verifier, PromptVoice(ToneVoice(), tmp_path))
    return asyncio.run(run_call(caller, port, C, "room-t", Timing(poll_s=0.01), **kw))


def test_genuine_caller_end_to_end(tmp_path):
    h = Harness()

    def phrase(_):
        calls = h.verifier.calls(1)
        return h.verifier.call(calls[0]["id"])["challenges"][-1]["phrase"], whispered(), 650

    caller = ScriptedCaller(h, [
        lambda _: ("I want to add a payee", voiced(), 800),
        phrase,
        lambda _: (h.code_on_device(C), voiced(), 900),
    ])
    final = run(h, caller, tmp_path)
    assert final.end and final.outcome is Outcome.PASSED
    assert "How can I help" in caller.heard[0] and caller.heard[-1].endswith("Goodbye.")


def test_app_approval_wait_then_result_is_spoken(tmp_path):
    h = Harness()

    async def scenario():
        port = InProcessVerifier(h.verifier, PromptVoice(ToneVoice(), tmp_path))
        caller = ScriptedCaller(h, [lambda _: ("reset my password, I can't, use the bank app", voiced(), 700)])
        task = asyncio.create_task(run_call(caller, port, C, "r", Timing(poll_s=0.01)))
        for _ in range(1000):
            await asyncio.sleep(0.01)
            msgs = h.inbox(C)["messages"]
            if msgs:
                await asyncio.to_thread(h.approve, msgs[0]["call_id"], C)
                break
        return await task, caller

    final, caller = asyncio.run(scenario())
    assert final.outcome is Outcome.APPROVED_IN_APP
    assert "approve it there" in caller.heard[-2] and "approved this request" in caller.heard[-1]


class SlowVoice(InProcessVerifier):
    """Synthesises lines it has not voiced before slowly, like Parler on a new LLM answer (~6 s)."""

    def __init__(self, h: Harness, tmp_path, slow: str):
        super().__init__(h.verifier, PromptVoice(ToneVoice(), tmp_path))
        self.slow = slow

    async def voice(self, text: str) -> bytes:
        if self.slow in text:
            await asyncio.sleep(0.3)
        return await super().voice(text)


def test_a_reply_that_is_slow_to_voice_starts_with_one_moment_not_silence(tmp_path):
    h = Harness()
    caller = ScriptedCaller(h, [lambda _: ("add payee", voiced(), 700)], leave_after=1)
    port = SlowVoice(h, tmp_path, slow="whisper these words")
    asyncio.run(run_call(caller, port, C, "r", Timing(poll_s=0.01, filler_after_s=0.05)))
    assert caller.heard[1] == ONE_MOMENT and "whisper these words" in caller.heard[2]


def test_a_reply_voiced_in_time_has_no_filler(tmp_path):
    h = Harness()
    caller = ScriptedCaller(h, [lambda _: ("add payee", voiced(), 700)], leave_after=1)
    port = SlowVoice(h, tmp_path, slow="never said")
    asyncio.run(run_call(caller, port, C, "r", Timing(poll_s=0.01, filler_after_s=0.05)))
    assert ONE_MOMENT not in caller.heard


def test_one_moment_is_voiced_ahead_of_time():
    assert ONE_MOMENT in spoken_lines()


def test_caller_leaving_abandons_the_call(tmp_path):
    h = Harness()
    caller = ScriptedCaller(h, [lambda _: ("add payee", voiced(), 700)], leave_after=1)
    run(h, caller, tmp_path)
    call = h.verifier.calls(1)[0]
    assert call["outcome"] == "abandoned"


class WatchingCaller(ScriptedCaller):
    """Also records what the Caller app is shown, in order with what is played."""

    def __init__(self, h: Harness, answers, leave_after: int | None = None):
        super().__init__(h, answers, leave_after)
        self.events: list[tuple[str, object]] = []

    async def play(self, wav: bytes, caption: str) -> None:
        await super().play(wav, caption)
        self.events.append(("play", caption))

    async def show(self, message: dict) -> None:
        self.events.append(("show", message))


def test_what_the_verifier_heard_is_shown_before_the_reply_is_played(tmp_path):
    h = Harness()
    caller = WatchingCaller(h, [lambda _: ("I want to add a payee", voiced(), 800)], leave_after=1)
    run(h, caller, tmp_path)
    heard = caller.events.index(("show", {"type": "heard", "text": "I want to add a payee"}))
    reply = next(i for i, (what, x) in enumerate(caller.events) if what == "play" and "whisper these words" in x)
    assert caller.events.index(("play", caller.heard[0])) < heard < reply


def test_the_caller_app_is_shown_the_open_challenge_and_the_outcome(tmp_path):
    h = Harness()

    def phrase(_):
        calls = h.verifier.calls(1)
        return h.verifier.call(calls[0]["id"])["challenges"][-1]["phrase"], whispered(), 650

    caller = WatchingCaller(h, [
        lambda _: ("I want to add a payee", voiced(), 800),
        phrase,
        lambda _: (h.code_on_device(C), voiced(), 900),
    ])
    run(h, caller, tmp_path)
    shown = [m for what, m in caller.events if what == "show" and m["type"] in ("challenge", "outcome")]
    whisper = caller.heard[1].split("whisper these words. ", 1)[1].rstrip(".")
    assert shown == [
        # Sent at once, so the Caller app never guesses a Challenge from a caption (code review, Oct 28).
        {"type": "challenge", "kind": None, "words": ""},
        {"type": "challenge", "kind": "whisper_phrase", "words": whisper},
        {"type": "challenge", "kind": "possession_code", "words": ""},
        {"type": "challenge", "kind": None, "words": ""},
        {"type": "outcome", "outcome": "passed"},
    ]
    whisper_shown = caller.events.index(("show", shown[1]))
    assert caller.events[whisper_shown + 1] == ("play", caller.heard[1])  # just before it is spoken


def test_a_whisper_and_a_code_cannot_record_for_long_in_a_loud_hall():
    timing = Timing()
    assert timing.whisper_max_reply_s <= 7 and timing.code_max_reply_s <= 8 and timing.max_reply_s >= 12
