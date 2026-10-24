from __future__ import annotations

import hashlib
import hmac
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain import (
    CallState,
    Challenge,
    ChallengeKind,
    Evidence,
    Outcome,
    RequestKind,
    Response,
    Signals,
    Step,
    Verdict,
)
from ..phrases import random_phrase, speakable
from ..policy import Policy
from ..signals import SignalExtractor
from .errors import CallNotFound, DeviceNotPaired, NotAllowed, UnknownCustomer
from .events import EventHub
from .interpreter import Context, Interpreter, TurnKind
from .store import AuditEventRow, CallRow, CustomerRow, Database, DeviceMessageRow, PossessionCodeRow

log = logging.getLogger(__name__)

MAX_REQUEST_ATTEMPTS = 3  # unclear turns before handing over to a Bank Agent
MAX_SIDE_TURNS = 6  # questions and repeats answered per Call
MAX_SIDE_TURNS_PER_CHALLENGE = 2  # so stalling never buys a Clone extra tries

_REQUEST_NAMES = {
    RequestKind.BALANCE_ENQUIRY: "check your balance",
    RequestKind.ADD_PAYEE: "add a new payee",
    RequestKind.SIM_SWAP: "change your SIM or reset your password",
    RequestKind.HIGH_VALUE_TRANSFER: "make a high-value transfer",
    RequestKind.ACCOUNT_SERVICE: "make that change to your account",
}

_DONE = {
    RequestKind.BALANCE_ENQUIRY: "Your balance has been sent to the bank app on your registered phone.",
}
ANYTHING_ELSE = "Is there anything else I can help you with?"
TAKE_YOUR_TIME = "Sure, take your time."
WHEN_READY = "Tell me when you're ready."
# What the Voice Agent says around an answer, in the language the Caller asked in (answers: knowledge.yaml).
_IN_LANGUAGE = {
    "hi": {
        ANYTHING_ELSE: "क्या मैं आपकी और कोई मदद कर सकती हूँ?",
        TAKE_YOUR_TIME: "ज़रूर, आराम से।",
        WHEN_READY: "जब तैयार हों, बता दीजिए।",
    },
    "kn": {
        ANYTHING_ELSE: "ನಾನು ನಿಮಗೆ ಇನ್ನೇನಾದರೂ ಸಹಾಯ ಮಾಡಬಹುದೇ?",
        TAKE_YOUR_TIME: "ಪರವಾಗಿಲ್ಲ, ನಿಧಾನವಾಗಿ ಮಾಡಿ.",
        WHEN_READY: "ಸಿದ್ಧವಾದಾಗ ಹೇಳಿ.",
    },
}
# Asking a Challenge again after a side turn; the full Possession Code prompt would say "I've sent" twice.
_REASK = {ChallengeKind.POSSESSION_CODE: "When you're ready, please read out the six-digit code from your bank app."}
HANDOFF = "I'll connect you to a bank officer now. They will verify you again before making any change. Please stay on the line."

GREETING = (
    "Namaskara, you have reached your bank's secure line. "
    "You can ask to check your balance, add a payee, change your SIM or password, or transfer money. "
    "How can I help you today?"
)
CLARIFY = (
    "Sorry, I didn't catch that. You can ask me a question, or ask to check your balance, add a payee, "
    "change your SIM or password, transfer money, or make another change to your account."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_code(call_id: str, code: str) -> str:
    return hashlib.sha256(f"{call_id}:{code}".encode()).hexdigest()


class Verifier:
    def __init__(
        self,
        db: Database,
        policy: Policy,
        signals: SignalExtractor,
        interpreter: Interpreter | None = None,
        events: EventHub | None = None,
        rng: random.Random | None = None,
        clock: Callable[[], datetime] = _utcnow,
        code_ttl_s: int = 120,
        approval_ttl_s: int = 120,
    ):
        self._db = db
        self._policy = policy
        self._signals = signals
        self._interpreter = interpreter or Interpreter()
        self._events = events or EventHub()
        self._rng = rng or random.SystemRandom()
        self._now = clock
        self._code_ttl = timedelta(seconds=code_ttl_s)
        self._approval_ttl = timedelta(seconds=approval_ttl_s)

    # ------------------------------------------------------------------ commands

    def start_call(self, customer_id: str, room: str) -> Step:
        with self._db.session() as s:
            if s.get(CustomerRow, customer_id) is None:
                raise UnknownCustomer(customer_id)
            now = self._now()
            call = CallRow(
                id=str(uuid.uuid4()),
                customer_id=customer_id,
                room=room,
                state=CallState.AWAITING_REQUEST,
                planned=[],
                challenges=[],
                evidence=[],
                scores=[],
                reasons=[],
                pending_step={},
                created_at=now,
                updated_at=now,
            )
            s.add(call)
            s.flush()
            self._audit(s, call, "call_started", {"customer_id": customer_id, "room": room})
            step = self._set_step(call, Step(call.id, GREETING, listen=True, state=CallState.AWAITING_REQUEST))
        self._publish_after(call.id)
        return step

    def respond(self, call_id: str, response: Response) -> Step:
        try:
            with self._db.session() as s:
                call = self._lock(s, call_id)
                if call.state == CallState.AWAITING_REQUEST:
                    step = self._on_request(s, call, response)
                elif call.state == CallState.CHALLENGING:
                    step = self._on_challenge_response(s, call, response)
                else:  # Responses after close or while waiting for the app are ignored
                    step = self._pending(call)
        except CallNotFound:
            raise
        except Exception:
            # A model or LLM failure must not end the Call: ask again once, then hand over.
            log.exception("could not process a Response on call %s", call_id)
            step = self._recover(call_id)
        self._publish_after(call_id)
        return step

    def _recover(self, call_id: str) -> Step:
        with self._db.session() as s:
            call = self._lock(s, call_id)
            if call.state == CallState.CLOSED:
                return self._pending(call)
            errors = sum(1 for e in s.scalars(select(AuditEventRow).where(
                AuditEventRow.call_id == call.id, AuditEventRow.kind == "processing_error")))
            self._audit(s, call, "processing_error", {"attempt": errors + 1})
            if errors >= 1:
                return self._hand_over(s, call, "I'm having trouble on this line.")
            last = self._pending(call)
            return self._set_step(call, Step(
                call.id, f"Sorry, I had trouble hearing that. {_strip_lead(last.say)}", listen=True,
                long_reply=last.long_reply, state=CallState(call.state),
            ))

    def current_step(self, call_id: str) -> Step:
        with self._db.session() as s:
            call = self._lock(s, call_id)
            changed = False
            if call.state == CallState.AWAITING_APP_APPROVAL:
                msg = self._open_approval(s, call)
                if msg is None or msg.expires_at <= self._now():
                    if msg is not None:
                        msg.resolved_at = self._now()
                    self._audit(s, call, "app_approval_expired", {})
                    self._close(
                        s, call, Outcome.ABANDONED,
                        "The approval request expired. For your safety nothing was changed. Goodbye.",
                    )
                    changed = True
            step = self._pending(call)
        if changed:
            self._publish_after(call_id)
        return step

    def app_approval(self, call_id: str, customer_id: str, device_token: str, approve: bool) -> Step:
        with self._db.session() as s:
            self._check_device(s, customer_id, device_token)
            call = self._lock(s, call_id)
            if call.customer_id != customer_id:
                raise NotAllowed("this Call belongs to a different Customer")
            if call.state != CallState.AWAITING_APP_APPROVAL:
                raise NotAllowed("this Call is not waiting for App Approval")
            msg = self._open_approval(s, call)
            if msg is None or msg.expires_at <= self._now():
                raise NotAllowed("the approval request has expired")
            msg.resolved_at = self._now()
            self._audit(s, call, "app_approval_answered", {"approved": approve})
            if approve:
                if call.agent_review:
                    call.review_status = "pending"
                say = "Thank you. You approved this request in your bank app."
                if call.agent_review:
                    say += " A bank officer will confirm it shortly."
                step = self._close(s, call, Outcome.APPROVED_IN_APP, say + " Goodbye.")
            else:
                step = self._close(
                    s, call, Outcome.DECLINED_IN_APP,
                    "You declined this request in your bank app, so it has been stopped. Goodbye.",
                )
        self._publish_after(call_id)
        return step

    def review(self, call_id: str, approve: bool, reviewer: str) -> dict:
        with self._db.session() as s:
            call = self._lock(s, call_id)
            if call.review_status != "pending":
                raise NotAllowed("this Call has no pending Agent Review")
            call.review_status = "approved" if approve else "rejected"
            call.updated_at = self._now()
            self._audit(s, call, "review_decided", {"approved": approve, "reviewer": reviewer})
        self._publish_after(call_id)
        return self.call(call_id)

    def hang_up(self, call_id: str) -> None:
        with self._db.session() as s:
            call = self._lock(s, call_id)
            if call.state == CallState.CLOSED:
                return
            for msg in self._open_messages(s, call):
                msg.resolved_at = self._now()
            self._audit(s, call, "caller_hung_up", {})
            self._close(s, call, Outcome.ABANDONED, "")
        self._publish_after(call_id)

    # ------------------------------------------------------------------ reads

    def call(self, call_id: str, with_events: bool = True) -> dict:
        with self._db.session() as s:
            call = s.get(CallRow, call_id)
            if call is None:
                raise CallNotFound(call_id)
            return self._view(s, call, with_events)

    def calls(self, limit: int = 50) -> list[dict]:
        with self._db.session() as s:
            rows = s.scalars(select(CallRow).order_by(CallRow.created_at.desc()).limit(limit)).all()
            return [self._view(s, c, with_events=False) for c in rows]

    def pairing(self, customer_id: str) -> str:
        """The device token the Bank App needs. Show it only on the operator's own machine."""
        with self._db.session() as s:
            customer = s.get(CustomerRow, customer_id)
            if customer is None:
                raise UnknownCustomer(customer_id)
            return customer.device_token

    def customers(self) -> list[dict]:
        with self._db.session() as s:
            rows = s.scalars(select(CustomerRow).order_by(CustomerRow.name)).all()
            return [{"id": c.id, "name": c.name, "phone_masked": c.phone_masked, "language": c.language} for c in rows]

    def inbox(self, customer_id: str, device_token: str) -> dict:
        """What the Customer's Registered Device currently shows (Bank App)."""
        with self._db.session() as s:
            customer = self._check_device(s, customer_id, device_token)
            now = self._now()
            msgs = s.scalars(
                select(DeviceMessageRow)
                .where(
                    DeviceMessageRow.customer_id == customer_id,
                    DeviceMessageRow.resolved_at.is_(None),
                    DeviceMessageRow.expires_at > now,
                )
                .order_by(DeviceMessageRow.id.desc())
            ).all()
            return {
                "customer": {"id": customer.id, "name": customer.name, "phone_masked": customer.phone_masked},
                "messages": [
                    {
                        "id": m.id,
                        "call_id": m.call_id,
                        "kind": m.kind,
                        "body": m.body,
                        "created_at": m.created_at.isoformat(),
                        "expires_at": m.expires_at.isoformat(),
                        "seconds_left": max(0, int((m.expires_at - now).total_seconds())),
                    }
                    for m in msgs
                ],
            }

    # ------------------------------------------------------------------ state machine

    def _on_request(self, s: Session, call: CallRow, response: Response) -> Step:
        transcript = self._signals.transcribe(response.audio) if response.reply_latency_ms is not None else ""
        heard = self._interpreter.understand(transcript, Context(last_said=self._pending(call).say))
        self._audit(
            s, call, "caller_said",
            {"transcript": transcript, "kind": heard.kind.value, "request": heard.request,
             "wants_app_approval": heard.wants_app_approval},
        )
        listen = lambda say: self._set_step(  # noqa: E731
            call, Step(call.id, say, listen=True, state=CallState.AWAITING_REQUEST)
        )

        if heard.kind is TurnKind.HUMAN:
            return self._hand_over(s, call, "Sure.")
        if heard.kind is TurnKind.GOODBYE:
            return self._close(s, call, Outcome.ENDED, "Thank you for calling. Goodbye.")
        if heard.kind in (TurnKind.QUESTION, TurnKind.CHAT, TurnKind.REPEAT, TurnKind.WAIT):
            call.side_turns += 1
            if call.side_turns > MAX_SIDE_TURNS:
                return self._hand_over(s, call, "You have a few questions, so")
            if heard.kind is TurnKind.REPEAT:
                return listen(_strip_lead(self._pending(call).say))
            if heard.kind is TurnKind.WAIT:
                return listen(f"{_said_in(heard, TAKE_YOUR_TIME)} {_said_in(heard, WHEN_READY)}")
            if heard.kind is TurnKind.CHAT:
                return listen(heard.reply)
            return listen(f"{heard.reply} {_said_in(heard, ANYTHING_ELSE)}")
        if heard.kind is TurnKind.APP_APPROVAL and heard.request is None:
            return listen("Sure, I can send it to your bank app. Which request is it: a payee, a SIM or password change, "
                          "a transfer, or another account change?")
        if heard.request is None:  # UNCLEAR
            call.request_attempts += 1
            if call.request_attempts >= MAX_REQUEST_ATTEMPTS:
                return self._hand_over(s, call, "I'm sorry, I couldn't understand.")
            return listen(f"{heard.reply} {CLARIFY}" if heard.reply else CLARIFY)

        request = heard.request
        answered = f"{heard.reply} " if heard.reply else ""  # "Is this safe? I want to transfer…": answer first
        plan = self._policy.plan(request)
        call.request = request.value
        call.agent_review = plan.agent_review
        call.planned = [k.value for k in plan.challenges]
        self._audit(
            s, call, "risk_tier_set",
            {"request": request.value, "challenges": call.planned, "agent_review": plan.agent_review},
        )
        if not plan.challenges:
            call.verdict = Verdict.PASS.value
            call.reasons = ["No Challenges needed for this Request."]
            self._audit(s, call, "verdict", {"verdict": "PASS", "liveness": None, "reasons": call.reasons})
            done = _DONE.get(request, "That's done.")
            return self._close(s, call, Outcome.PASSED, f"{answered}Sure. {done} Thank you for calling. Goodbye.")
        call.state = CallState.CHALLENGING
        if heard.wants_app_approval:
            return self._start_app_approval(s, call, f"{answered}You asked to use the app.")
        n = len(plan.challenges)
        intro = (
            f"{answered}Sure, I can help you {_REQUEST_NAMES[request]}. "
            f"For your security I'll ask you {n} quick thing{'s' if n > 1 else ''}."
        )
        return self._issue_next(s, call, intro)

    def _hand_over(self, s: Session, call: CallRow, lead_in: str) -> Step:
        """A Bank Agent takes over. Evidence that already says BLOCK still blocks."""
        if call.evidence:
            so_far = self._policy.decide(_evidence(call.evidence), call.step_ups)
            if so_far.verdict is Verdict.BLOCK:
                return self._block(s, call, so_far)
        for msg in self._open_messages(s, call):
            msg.resolved_at = self._now()
        self._audit(s, call, "handed_to_agent", {})
        return self._close(s, call, Outcome.HANDED_TO_AGENT, f"{lead_in} {HANDOFF}")

    def _on_challenge_response(self, s: Session, call: CallRow, response: Response) -> Step:
        issued = call.challenges[-1]
        challenge = Challenge(ChallengeKind(issued["kind"]), issued["prompt"], issued.get("phrase", ""))
        if response.reply_latency_ms is None and not issued.get("repeated"):
            # Silence once is not evidence; repeat the same Challenge a single time.
            call.challenges = call.challenges[:-1] + [{**issued, "repeated": True}]
            self._audit(s, call, "challenge_repeated", {"reason": "no speech heard"})
            return self._set_step(
                call, Step(call.id, f"Sorry, I didn't hear you. {challenge.prompt}", listen=True,
                           long_reply=challenge.kind is ChallengeKind.POSSESSION_CODE, state=CallState.CHALLENGING),
            )
        signals = self._signals.extract(challenge, response)

        off_script = self._off_script(call, challenge, signals)
        if off_script is not None:
            heard = off_script
            if heard.kind is TurnKind.APP_APPROVAL:
                self._audit(s, call, "app_approval_asked", {"transcript": signals.transcript})
                # Evidence already gathered still counts: a Clone cannot escape a BLOCK by asking for the app.
                if call.evidence:
                    so_far = self._policy.decide(_evidence(call.evidence), call.step_ups)
                    if so_far.verdict is Verdict.BLOCK:
                        return self._block(s, call, so_far)
                return self._start_app_approval(s, call, "No problem.")
            if heard.kind is TurnKind.HUMAN:
                return self._hand_over(s, call, "Sure.")
            asked = int(issued.get("side_turns", 0))
            if asked < MAX_SIDE_TURNS_PER_CHALLENGE:  # QUESTION, CHAT, REPEAT or WAIT: reply, then ask again
                call.challenges = call.challenges[:-1] + [{**issued, "side_turns": asked + 1}]
                call.side_turns += 1
                self._audit(s, call, "caller_said", {"transcript": signals.transcript, "kind": heard.kind.value})
                reask = _REASK.get(challenge.kind, challenge.prompt)
                if heard.kind is TurnKind.REPEAT:
                    say = f"Of course. {challenge.prompt}"
                elif heard.kind is TurnKind.WAIT:
                    say = f"{_said_in(heard, TAKE_YOUR_TIME)} {reask}"
                else:
                    say = f"{heard.reply} {reask}"
                return self._set_step(call, Step(
                    call.id, say, listen=True,
                    long_reply=challenge.kind is ChallengeKind.POSSESSION_CODE, state=CallState.CHALLENGING,
                ))
            # Out of side turns: whatever was said is scored as the Response.

        if challenge.kind is ChallengeKind.POSSESSION_CODE:
            match = self._check_code(s, call, signals.spoken_digits, final=bool(issued.get("retried")))
            if match is not True and not issued.get("retried"):
                # One more try: people mis-read or pause mid-code. The code stays valid.
                call.challenges = call.challenges[:-1] + [{**issued, "retried": True}]
                self._audit(s, call, "code_retry", {"heard_digits": signals.spoken_digits})
                return self._set_step(call, Step(
                    call.id, "That didn't match. Please read the six digits from your bank app again, slowly.",
                    listen=True, long_reply=True, state=CallState.CHALLENGING,
                ))
            signals = _with_code_match(signals, match)

        evidence = list(call.evidence) + [{"kind": challenge.kind.value, "signals": signals.to_dict()}]
        call.evidence = evidence
        decision = self._policy.decide(_evidence(evidence), call.step_ups)
        call.scores = [round(x, 3) for x in decision.per_response]
        self._audit(
            s, call, "response_scored",
            {"challenge": len(evidence), "kind": challenge.kind.value, "signals": signals.to_dict(),
             "liveness": call.scores[-1]},
        )

        if call.planned:  # more Challenges planned: keep going, decide at the end
            return self._issue_next(s, call, "Thank you.")

        call.verdict = decision.verdict.value
        call.liveness = None if decision.liveness is None else round(decision.liveness, 3)
        call.reasons = decision.reasons
        self._audit(
            s, call, "verdict",
            {"verdict": decision.verdict.value, "liveness": call.liveness, "reasons": decision.reasons},
        )
        if decision.verdict is Verdict.PASS:
            if call.agent_review:
                call.review_status = "pending"
                return self._close(
                    s, call, Outcome.PASSED_PENDING_REVIEW,
                    "Thank you, you're verified. Because this is a high-value request, "
                    "a bank officer will confirm it shortly. Goodbye.",
                )
            return self._close(s, call, Outcome.PASSED, "Thank you, you're verified and your request is done. Goodbye.")
        if decision.verdict is Verdict.BLOCK:
            return self._block(s, call, decision)
        if decision.next_challenge is not None:
            call.step_ups += 1
            call.planned = [decision.next_challenge.value]
            return self._issue_next(s, call, "Thank you. I need one more check.")
        return self._start_app_approval(s, call, "I need one more confirmation.")

    def _off_script(self, call: CallRow, challenge: Challenge, signals: Signals):
        """The Caller said something other than an answer (a question, "repeat", "hold on",
        "use the app", "a person please"). Returns the Understanding, or None to score it as the Response."""
        if not signals.transcript:
            return None
        context = Context(challenge.kind, RequestKind(call.request) if call.request else None, self._pending(call).say)
        heard = self._interpreter.understand(signals.transcript, context)
        if heard.kind in (TurnKind.APP_APPROVAL, TurnKind.HUMAN):
            return heard  # explicit asks win
        if heard.kind is TurnKind.UNCLEAR:
            return None
        attempted = (
            (signals.task_match or 0) >= 0.5
            if challenge.kind is ChallengeKind.WHISPER_PHRASE
            else len(signals.spoken_digits or "") >= 4
        )
        return None if attempted else heard  # a QUESTION or REPEAT, unless they tried to answer

    def _block(self, s: Session, call: CallRow, decision) -> Step:
        if call.verdict != Verdict.BLOCK.value:  # record the Verdict if it was not recorded yet
            call.verdict = Verdict.BLOCK.value
            call.liveness = None if decision.liveness is None else round(decision.liveness, 3)
            call.reasons = decision.reasons
            self._audit(s, call, "verdict", {"verdict": "BLOCK", "liveness": call.liveness, "reasons": decision.reasons})
        return self._close(
            s, call, Outcome.BLOCKED,
            "We could not verify this call, so for your safety the request has been stopped. "
            "Please use the bank app or visit your branch. Goodbye.",
        )

    def _issue_next(self, s: Session, call: CallRow, lead_in: str) -> Step:
        planned = list(call.planned)
        kind = ChallengeKind(planned.pop(0))
        call.planned = planned
        now = self._now()
        if kind is ChallengeKind.WHISPER_PHRASE:
            phrase = random_phrase(self._rng)
            prompt = f"Please whisper these words: {speakable(phrase)}."
            record = {"kind": kind.value, "prompt": prompt, "phrase": phrase, "issued_at": now.isoformat()}
        else:
            code = f"{self._rng.randrange(10**6):06d}"
            s.add(PossessionCodeRow(
                call_id=call.id, customer_id=call.customer_id, code_hash=_hash_code(call.id, code),
                expires_at=now + self._code_ttl,
            ))
            s.add(DeviceMessageRow(
                customer_id=call.customer_id, call_id=call.id, kind="possession_code",
                body={"code": code, "request": call.request}, created_at=now, expires_at=now + self._code_ttl,
            ))
            prompt = "I've sent a six-digit code to the bank app on your registered phone. Please read it out."
            record = {"kind": kind.value, "prompt": prompt, "phrase": "", "issued_at": now.isoformat()}
        call.challenges = list(call.challenges) + [record]
        self._audit(s, call, "challenge_issued", {k: v for k, v in record.items() if k != "issued_at"})
        return self._set_step(call, Step(
            call.id, f"{lead_in} {prompt}", listen=True, long_reply=kind is ChallengeKind.POSSESSION_CODE,
            state=CallState.CHALLENGING,
        ))

    def _start_app_approval(self, s: Session, call: CallRow, lead_in: str) -> Step:
        now = self._now()
        for msg in self._open_messages(s, call):
            msg.resolved_at = now
        call.state = CallState.AWAITING_APP_APPROVAL
        call.planned = []
        s.add(DeviceMessageRow(
            customer_id=call.customer_id, call_id=call.id, kind="app_approval",
            body={"request": call.request, "request_text": _REQUEST_NAMES.get(RequestKind(call.request), "")},
            created_at=now, expires_at=now + self._approval_ttl,
        ))
        self._audit(s, call, "app_approval_requested", {"expires_in_s": int(self._approval_ttl.total_seconds())})
        say = f"{lead_in} I've sent an approval request to the bank app on your registered phone. Please approve it there."
        return self._set_step(call, Step(call.id, say, wait=True, state=CallState.AWAITING_APP_APPROVAL))

    def _check_code(self, s: Session, call: CallRow, spoken: str | None, final: bool) -> bool | None:
        """Compare the spoken digits with the issued Possession Code.

        The code is consumed on a match, or on the final attempt; a first miss keeps it valid.
        """
        row = s.scalars(
            select(PossessionCodeRow)
            .where(PossessionCodeRow.call_id == call.id, PossessionCodeRow.used_at.is_(None))
            .order_by(PossessionCodeRow.id.desc())
        ).first()
        if row is None:
            return False
        now = self._now()
        if not spoken:
            match: bool | None = None
        elif len(spoken) > self._policy.max_code_digits:
            match = False  # reading out a long run of digits would try dozens of codes at once
        else:
            # Accept the code anywhere in what was said ("my code is 4 8 1 9 2 7").
            candidates = {spoken[i : i + 6] for i in range(max(1, len(spoken) - 5))}
            match = row.expires_at > now and any(_hash_code(call.id, c) == row.code_hash for c in candidates)
        if match or final:
            row.used_at = now
            for msg in self._open_messages(s, call, kind="possession_code"):
                msg.resolved_at = now
        return match

    def _close(self, s: Session, call: CallRow, outcome: Outcome, say: str) -> Step:
        call.state = CallState.CLOSED
        call.outcome = outcome.value
        call.planned = []
        self._audit(s, call, "call_closed", {"outcome": outcome.value})
        return self._set_step(call, Step(call.id, say, end=True, state=CallState.CLOSED, outcome=outcome))

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _check_device(s: Session, customer_id: str, device_token: str) -> CustomerRow:
        customer = s.get(CustomerRow, customer_id)
        if customer is None:
            raise UnknownCustomer(customer_id)
        if not device_token or not hmac.compare_digest(customer.device_token, device_token):
            raise DeviceNotPaired(customer_id)
        return customer

    def _lock(self, s: Session, call_id: str) -> CallRow:
        call = s.get(CallRow, call_id, with_for_update=True)
        if call is None:
            raise CallNotFound(call_id)
        return call

    def _set_step(self, call: CallRow, step: Step) -> Step:
        call.pending_step = step.to_dict()
        call.updated_at = self._now()
        return step

    @staticmethod
    def _pending(call: CallRow) -> Step:
        return Step.from_dict(call.pending_step)

    def _open_messages(self, s: Session, call: CallRow, kind: str | None = None) -> list[DeviceMessageRow]:
        q = select(DeviceMessageRow).where(DeviceMessageRow.call_id == call.id, DeviceMessageRow.resolved_at.is_(None))
        if kind:
            q = q.where(DeviceMessageRow.kind == kind)
        return list(s.scalars(q).all())

    def _open_approval(self, s: Session, call: CallRow) -> DeviceMessageRow | None:
        msgs = self._open_messages(s, call, kind="app_approval")
        return msgs[-1] if msgs else None

    def _audit(self, s: Session, call: CallRow, kind: str, data: dict) -> None:
        seq = (s.scalar(select(func.max(AuditEventRow.seq)).where(AuditEventRow.call_id == call.id)) or 0) + 1
        s.add(AuditEventRow(call_id=call.id, seq=seq, kind=kind, data=_jsonable(data), created_at=self._now()))
        s.flush()

    def _publish_after(self, call_id: str) -> None:
        """Push the Call's latest state to live Consoles. Call only after the session commits."""
        try:
            view = self.call(call_id, with_events=True)
        except CallNotFound:
            return
        self._events.publish({"type": "call", "call": view})

    def _view(self, s: Session, call: CallRow, with_events: bool) -> dict:
        customer = s.get(CustomerRow, call.customer_id)
        view = {
            "id": call.id,
            "customer": {"id": call.customer_id, "name": customer.name if customer else call.customer_id},
            "room": call.room,
            "state": call.state,
            "request": call.request,
            "agent_review": call.agent_review,
            "review_status": call.review_status,
            "challenges": [
                {"kind": c["kind"], "prompt": c["prompt"], "phrase": c.get("phrase", "")} for c in call.challenges
            ],
            "evidence": call.evidence,
            "scores": call.scores,
            "step_ups": call.step_ups,
            "verdict": call.verdict,
            "liveness": call.liveness,
            "reasons": call.reasons,
            "outcome": call.outcome,
            "created_at": call.created_at.isoformat(),
            "updated_at": call.updated_at.isoformat(),
        }
        if with_events:
            rows = s.scalars(
                select(AuditEventRow).where(AuditEventRow.call_id == call.id).order_by(AuditEventRow.seq)
            ).all()
            view["events"] = [
                {"seq": e.seq, "kind": e.kind, "data": e.data, "at": e.created_at.isoformat()} for e in rows
            ]
        return view


def _evidence(rows: list[dict]) -> list[Evidence]:
    return [Evidence(ChallengeKind(r["kind"]), Signals.from_dict(r["signals"])) for r in rows]


def _with_code_match(signals: Signals, match: bool | None) -> Signals:
    d = signals.to_dict()
    d["code_match"] = match
    return Signals.from_dict(d)


def _jsonable(data: dict) -> dict:
    out = {}
    for k, v in data.items():
        if isinstance(v, (RequestKind, ChallengeKind, Verdict, Outcome, CallState)):
            v = v.value
        out[k] = v
    return out


def _said_in(heard, text: str) -> str:
    return _IN_LANGUAGE.get(heard.language, {}).get(text, text)


def _strip_lead(say: str) -> str:
    """Drop apology prefixes so repeated prompts don't stack ("Sorry… Sorry…")."""
    for lead in ("Sorry, I had trouble hearing that. ", "Sorry, I didn't hear you. ", "Of course. "):
        while say.startswith(lead):
            say = say[len(lead):]
    return say
