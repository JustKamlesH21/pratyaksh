"""LiveKit Agents worker. One job per room: the Caller joins, the Voice Agent runs the Call.

Run:  pratyaksh-agent dev     (or: python -m pratyaksh.agent.worker dev)
Env:  LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, VERIFIER_URL
"""

from __future__ import annotations

import logging

from livekit import rtc
from livekit.agents import AgentServer, AutoSubscribe, JobContext, JobProcess, cli
from livekit.plugins import silero

from ..config import Settings
from .call_loop import Timing, run_call
from .livekit_audio import LiveKitCallAudio
from .ports import HttpVerifier

log = logging.getLogger("pratyaksh.agent")


def prewarm(proc: JobProcess) -> None:
    s = Settings()
    # A low activation threshold so whispers count as speech; tune VAD_ACTIVATION on the real mics.
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=s.vad_min_silence_s, activation_threshold=s.vad_activation, sample_rate=16000
    )


server = AgentServer(setup_fnc=prewarm)


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    settings = Settings()
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    caller = await ctx.wait_for_participant(kind=rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD)
    customer_id = caller.metadata or caller.identity
    log.info("caller %s joined %s as customer %s", caller.identity, ctx.room.name, customer_id)

    audio = await LiveKitCallAudio.open(ctx.room, caller, ctx.proc.userdata["vad"])
    verifier = HttpVerifier(settings.verifier_url)
    try:
        await run_call(
            audio, verifier, customer_id, ctx.room.name,
            Timing(
                listen_timeout_s=settings.listen_timeout_s,
                code_listen_timeout_s=settings.code_listen_timeout_s,
                code_pause_s=settings.code_pause_s,
                max_reply_s=settings.max_reply_s,
            ),
        )
    finally:
        await verifier.aclose()
        await audio.aclose()
        ctx.shutdown(reason="call finished")


def main() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    main()
