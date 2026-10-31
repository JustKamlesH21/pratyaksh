"""Policy: map Requests to Challenges, and Signals to a Verdict with Reasons.

Interface:
    Policy.load(path=None)                     -> Policy
    policy.plan(request)                       -> Plan
    policy.decide(evidence, step_ups_used)     -> Decision
    policy.voice_paused(minutes_since_block)   -> Decision | None   (after a BLOCK for the Customer)
    policy.attack_wave(customers_blocked)      -> bool   (Customers with a blocked Call in wave_minutes)
    policy.max_code_digits, pause_minutes, alert_hours, wave_customers, wave_minutes

Pure and in-process: no I/O after loading.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml

from .domain import ChallengeKind, Decision, Evidence, RequestKind, Signals, Verdict


@dataclass(frozen=True)
class Plan:
    challenges: tuple[ChallengeKind, ...]
    agent_review: bool


class PolicyError(ValueError):
    pass


class Policy:
    def __init__(self, raw: dict):
        try:
            self._plans = {
                RequestKind(name): Plan(
                    challenges=tuple(ChallengeKind(c) for c in spec.get("challenges", [])),
                    agent_review=bool(spec.get("agent_review", False)),
                )
                for name, spec in raw["requests"].items()
            }
            s = raw["signals"]
            self._task_min = float(s["task_match"]["min"])
            self._whisper_min = float(s["whisper_score"]["min"])
            self._human_ms = float(s["reply_latency"]["human_ms"])
            self._machine_ms = float(s["reply_latency"]["machine_ms"])
            self._spoof_mode = str(s["spoof_score"]["mode"])
            self._spoof_block_at = float(s["spoof_score"]["block_at"])
            mic = s.get("live_microphone", {"mode": "off"})
            self._mic_mode = str(mic["mode"])
            self._mic_max_db = float(mic.get("max_range_db", 60))
            self.max_code_digits = int(s.get("code_match", {}).get("max_digits", 8))
            self._weights = {k: float(v) for k, v in raw["weights"].items()}
            v = raw["verdict"]
            self._pass_at = float(v["pass_at"])
            self._block_at = float(v["block_at"])
            self._max_step_ups = int(v["max_step_ups"])
            p = raw.get("protection", {})
            self.pause_minutes = float(p.get("pause_minutes", 30))
            self.alert_hours = float(p.get("alert_hours", 24))
            self.wave_customers = int(p.get("wave_customers", 3))
            self.wave_minutes = float(p.get("wave_minutes", 15))
        except (KeyError, TypeError, ValueError) as e:
            raise PolicyError(f"invalid policy: {e!r}") from e
        missing = set(RequestKind) - set(self._plans)
        if missing:
            raise PolicyError(f"policy has no plan for: {sorted(missing)}")
        if self._weights.get("code_match", 0.0) <= 0:
            raise PolicyError("weights.code_match must be positive: a right Possession Code would score 0")
        if self._spoof_mode not in {"enforce", "advisory", "off"}:
            raise PolicyError("signals.spoof_score.mode must be enforce, advisory or off")
        if self._mic_mode not in {"enforce", "advisory", "off"}:
            raise PolicyError("signals.live_microphone.mode must be enforce, advisory or off")
        if not self._block_at < self._pass_at:
            raise PolicyError("verdict.block_at must be lower than verdict.pass_at")
        if self._machine_ms <= self._human_ms:
            raise PolicyError("reply_latency.machine_ms must exceed human_ms")
        if self.max_code_digits < 6:
            raise PolicyError("code_match.max_digits must be at least 6, the length of a Possession Code")
        if self.pause_minutes < 0 or self.alert_hours <= 0:
            raise PolicyError("protection.pause_minutes must be >= 0 and alert_hours > 0")
        if self.wave_customers < 0 or self.wave_minutes <= 0:
            raise PolicyError("protection.wave_customers must be >= 0 and wave_minutes > 0")

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Policy":
        if path:
            text = Path(path).read_text(encoding="utf-8")
        else:
            text = resources.files("pratyaksh").joinpath("policy.yaml").read_text(encoding="utf-8")
        return cls(yaml.safe_load(text))

    def plan(self, request: RequestKind) -> Plan:
        return self._plans[request]

    @property
    def uses_spoof_score(self) -> bool:
        """False when spoof_score.mode is off: the Spoof Score is then neither scored nor shown."""
        return self._spoof_mode != "off"

    def voice_paused(self, minutes_since_block: float | None) -> Decision | None:
        """BLOCK for a risky Request when a recent Call for the same Customer was blocked and the
        Customer has not dismissed the Security Alert yet; None when voice Verification may go ahead."""
        if minutes_since_block is None or minutes_since_block >= self.pause_minutes:
            return None
        return Decision(Verdict.BLOCK, None, [
            f"A call for this Customer was blocked {minutes_since_block:.0f} min ago; voice requests are paused "
            f"for {self.pause_minutes:.0f} min or until the Customer dismisses the alert on their Registered Device.",
        ])

    def attack_wave(self, customers_blocked: int) -> bool:
        """Blocked Calls for several different Customers within wave_minutes look like a Clone
        campaign: while it lasts every risky Request also needs Agent Review."""
        return self.wave_customers > 0 and customers_blocked >= self.wave_customers

    def decide(self, evidence: list[Evidence], step_ups_used: int = 0) -> Decision:
        """Verdict over all answered Challenges of a Call."""
        if not evidence:
            return Decision(Verdict.PASS, None, ["No Challenges needed for this Request."])

        reasons: list[str] = []
        hard_fails: list[str] = []
        scores: list[float] = []
        failed = 0  # Whisper Phrases not completed (wrong words or not whispered)
        # Failed Whisper Phrases not yet made up for by a completed STEP-UP phrase after them. STEP-UP
        # phrases are the last step_ups_used Challenges; planned ones never count as a retry.
        owed = 0
        extra_from = len(evidence) - step_ups_used
        for i, ev in enumerate(evidence, start=1):
            score, why, hard, task_failed = self._assess(ev.kind, ev.signals)
            scores.append(score)
            failed += task_failed
            if ev.kind is ChallengeKind.WHISPER_PHRASE:
                if task_failed:
                    owed += 1
                elif owed and i > extra_from:
                    owed -= 1
            label = f"Challenge {i} ({_kind_label(ev.kind)})"
            reasons.extend(f"{label}: {w}" for w in why)
            hard_fails.extend(f"{label}: {h}" for h in hard)

        mean = sum(scores) / len(scores)
        if hard_fails:
            return Decision(Verdict.BLOCK, mean, hard_fails + reasons, scores)
        if mean <= self._block_at:
            return Decision(
                Verdict.BLOCK, mean, [f"Liveness {mean:.2f} is at or below {self._block_at:.2f}."] + reasons, scores
            )
        # A failed Whisper Phrase never PASSes until a STEP-UP phrase after it is completed, whatever the mean.
        if owed:
            if step_ups_used < self._max_step_ups:
                return Decision(
                    Verdict.STEP_UP, mean, ["A Whisper Phrase was not completed; asking one more."] + reasons,
                    scores, next_challenge=ChallengeKind.WHISPER_PHRASE,
                )
            # The right Possession Code, a Liveness Score that would PASS and a real whisper whose words were
            # lost: a noisy line, not a Clone (Oct 31, venue: two genuine Callers BLOCKed at 0.81). App Approval
            # asks the real phone. A voiced Clone with a stolen code never whispers and is still BLOCKed.
            noisy_line = (
                mean >= self._pass_at
                and any(ev.signals.code_match is True for ev in evidence)
                and any(
                    (ev.signals.whisper_score or 0.0) >= self._whisper_min
                    and (ev.signals.task_match or 0.0) < self._task_min
                    for ev in evidence
                )
            )
            if failed >= 2 and not noisy_line:
                return Decision(
                    Verdict.BLOCK, mean, [f"{failed} Whisper Phrases not completed, even after a retry."] + reasons,
                    scores,
                )
            return Decision(
                Verdict.STEP_UP, mean,
                ["A Whisper Phrase was not completed and no retry is left.", "Handing over to App Approval."] + reasons,
                scores, offer_app_approval=True,
            )
        if mean >= self._pass_at:
            return Decision(
                Verdict.PASS, mean, [f"Liveness {mean:.2f} is at or above {self._pass_at:.2f}."] + reasons, scores
            )
        head = f"Liveness {mean:.2f} is inconclusive."
        if step_ups_used < self._max_step_ups:
            return Decision(
                Verdict.STEP_UP, mean, [head, "Asking one more Whisper Phrase."] + reasons, scores,
                next_challenge=ChallengeKind.WHISPER_PHRASE,
            )
        return Decision(
            Verdict.STEP_UP, mean, [head, "Handing over to App Approval."] + reasons, scores,
            offer_app_approval=True,
        )

    # -- internals -------------------------------------------------------------------

    def _latency_component(self, ms: int | None) -> float:
        if ms is None:
            return 0.0
        if ms <= self._human_ms:
            return 1.0
        if ms >= self._machine_ms:
            return 0.0
        return 1.0 - (ms - self._human_ms) / (self._machine_ms - self._human_ms)

    def _assess(self, kind: ChallengeKind, s: Signals) -> tuple[float, list[str], list[str], bool]:
        """Liveness Score for one Response, with Reasons, hard fails, and whether the task failed."""
        why: list[str] = []
        hard: list[str] = []
        parts: dict[str, float] = {}
        task_failed = False

        if s.reply_latency_ms is None:
            hard.append("no reply was heard.")
        elif kind is not ChallengeKind.POSSESSION_CODE:
            # A Possession Code is not timed: unlocking the phone and opening the bank app takes anyone
            # 5-15 s (a genuine Caller read it after 10.6 s on Oct 27 and was BLOCKed for it).
            parts["reply_latency"] = self._latency_component(s.reply_latency_ms)
            if s.reply_latency_ms > self._human_ms:
                why.append(f"slow reply ({s.reply_latency_ms} ms; people usually answer within {self._human_ms:.0f} ms).")

        if kind is ChallengeKind.WHISPER_PHRASE:
            tm = s.task_match if s.task_match is not None else 0.0
            parts["task_match"] = tm
            if tm < self._task_min:
                task_failed = True
                why.append(f"phrase did not match (match {tm:.2f}, needs {self._task_min:.2f}).")
            ws = s.whisper_score if s.whisper_score is not None else 0.0
            parts["whisper_score"] = ws
            if ws < self._whisper_min:
                task_failed = True
                why.append(f"phrase was not whispered (whisper score {ws:.2f}, needs {self._whisper_min:.2f}).")
            # Live Microphone: a synthetic whisper scores like a real one, but audio played in digitally has
            # none of the room noise a microphone always hears. Not completed, like a phrase not whispered.
            dr = s.dynamic_range_db
            if dr is not None and dr > self._mic_max_db and self._mic_mode != "off":
                if self._mic_mode == "enforce":
                    task_failed = True
                why.append(
                    f"no live microphone: no background noise between the words (dynamic range {dr:.0f} dB; "
                    f"a live microphone stays under {self._mic_max_db:.0f} dB), so the audio was played in digitally."
                )
        elif kind is ChallengeKind.POSSESSION_CODE:
            if s.code_match is False:
                hard.append("the code read out does not match the code sent to the Registered Device.")
            elif s.code_match is None:
                hard.append("no code was read out.")
            else:
                parts["code_match"] = 1.0  # the right code: proof the Caller holds the Registered Device

        if s.spoof_score is not None and self._spoof_mode != "off":
            if self._spoof_mode == "enforce":
                parts["spoof_score"] = 1.0 - s.spoof_score
                if s.spoof_score >= self._spoof_block_at:
                    hard.append(f"voice looks synthetic (spoof score {s.spoof_score:.2f}).")
            # The spoof model calls most real whispers synthetic (Oct 27), so for a Whisper Phrase its
            # lean is noise; in enforce mode the hard fail above still applies.
            if s.spoof_score >= 0.5 and kind is not ChallengeKind.WHISPER_PHRASE:
                why.append(f"spoof model leans synthetic ({s.spoof_score:.2f}).")

        total_w = sum(self._weights.get(k, 0.0) for k in parts)
        score = sum(self._weights.get(k, 0.0) * v for k, v in parts.items()) / total_w if total_w else 0.0
        return score, why, hard, task_failed


def _kind_label(kind: ChallengeKind) -> str:
    return "Whisper Phrase" if kind is ChallengeKind.WHISPER_PHRASE else "Possession Code"
