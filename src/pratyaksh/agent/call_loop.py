"""run_call: drive one Call between CallAudio and the Verifier until it ends.

Hides turn-taking: speak the Step, then listen (longer for Possession Codes), wait while
App Approval is pending, or hang up; stop cleanly when the Caller leaves or anything fails.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from ..domain import Step
from ..verification.verifier import ONE_MOMENT
from .ports import CallAudio, CallerLeft, VerifierPort

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Timing:
    listen_timeout_s: float = 8.0
    code_listen_timeout_s: float = 15.0
    code_pause_s: float = 1.5
    max_reply_s: float = 12.0
    poll_s: float = 1.0
    max_wait_s: float = 300.0
    filler_after_s: float = 1.0  # a reply not voiced by then gets ONE_MOMENT first, not silence


async def run_call(
    audio: CallAudio, verifier: VerifierPort, customer_id: str, room: str, timing: Timing = Timing()
) -> Step:
    step = await verifier.start_call(customer_id, room)
    call_id = step.call_id
    log.info("call %s started for %s in %s", call_id, customer_id, room)
    try:
        while True:
            if step.say:
                await _speak(audio, verifier, step.say, timing)
            if step.end:
                return step
            if step.listen:
                if step.long_reply:
                    response = await audio.listen(timing.code_listen_timeout_s, timing.max_reply_s, timing.code_pause_s)
                else:
                    response = await audio.listen(timing.listen_timeout_s, timing.max_reply_s)
                step = await verifier.respond(call_id, response)
            elif step.wait:
                step = await _wait_for_change(audio, verifier, step, timing)
            else:
                return step
    except CallerLeft:
        log.info("call %s: caller left", call_id)
        await _safe_hang_up(verifier, call_id)
        return step
    except BaseException:
        # Never leave a Call open on the Console (or an approval prompt on a phone) after a crash.
        log.exception("call %s failed; closing it", call_id)
        await _safe_hang_up(verifier, call_id)
        raise


async def _speak(audio: CallAudio, verifier: VerifierPort, text: str, timing: Timing) -> None:
    """Play the reply. Lines voiced ahead of time come back at once; a new one (an LLM answer) takes
    seconds to synthesise, so the Caller hears ONE_MOMENT instead of silence meanwhile (Oct 27)."""
    voicing = asyncio.ensure_future(verifier.voice(text))
    try:
        wav = await asyncio.wait_for(asyncio.shield(voicing), timing.filler_after_s)
    except TimeoutError:
        await audio.play(await verifier.voice(ONE_MOMENT), ONE_MOMENT)
        wav = await voicing
    await audio.play(wav, text)


async def _wait_for_change(audio: CallAudio, verifier: VerifierPort, waiting: Step, timing: Timing) -> Step:
    """Poll while App Approval is pending. Returns the first different Step."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timing.max_wait_s
    while loop.time() < deadline:
        await asyncio.sleep(timing.poll_s)
        if audio.caller_left():
            raise CallerLeft()
        step = await verifier.current_step(waiting.call_id)
        if step != waiting:
            return step
    await verifier.hang_up(waiting.call_id)
    return await verifier.current_step(waiting.call_id)


async def _safe_hang_up(verifier: VerifierPort, call_id: str) -> None:
    try:
        await asyncio.shield(verifier.hang_up(call_id))
    except Exception:
        log.exception("could not hang up call %s", call_id)
