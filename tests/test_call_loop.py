"""run_call with a scripted CallAudio and a real Verifier behind InProcessVerifier."""

import asyncio

from conftest import Harness, voiced, whispered

from pratyaksh.agent.call_loop import Timing, run_call
from pratyaksh.agent.ports import CallerLeft, InProcessVerifier
from pratyaksh.domain import Outcome, Response
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


def test_caller_leaving_abandons_the_call(tmp_path):
    h = Harness()
    caller = ScriptedCaller(h, [lambda _: ("add payee", voiced(), 700)], leave_after=1)
    run(h, caller, tmp_path)
    call = h.verifier.calls(1)[0]
    assert call["outcome"] == "abandoned"
