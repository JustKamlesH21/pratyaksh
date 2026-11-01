"""Voice Consent: the owner of a voice decides who may use it, for what, for how long, and how many times.

Interface:
    ask(customer_id, requester, purpose, minutes, max_uses)   -> dict   (the request, shown on the owner's phone)
    give(consent_id, customer_id, device_token, audio, raw)   -> dict   (the spoken statement; signs a Consent Pass)
    decline / revoke (consent_id, customer_id, device_token)  -> dict
    use(customer_id, requester, purpose, clip, consent_pass)  -> dict   (one Voice Use: allowed or refused, logged)
    authorize(consent_pass, requester, purpose, clip)         -> dict   (the same, for a tool holding only a pass)
    mine(customer_id, device_token), overview(), public_key()

Consent needs the same two proofs as a risky Request: the Registered Device, and a live person reading a statement
with a fresh random number. Only a hash of that recording is kept (ADR-0003). Every step goes on the owner's Voice
Ledger, an Audit Trail chain of its own. A Consent Pass has its own signing key: under the Verification Receipt key
it would verify as a receipt, because it names no Call to check (ADR-0007).
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import Audio
from ..phrases import speakable
from ..signals import SignalExtractor
from .errors import ConsentNotFound, DeviceNotPaired, NotAllowed, UnknownCustomer
from .receipts import InvalidReceipt, ReceiptSigner
from .store import AuditEventRow, CustomerRow, Database, VoiceConsentRow, append_event, walk_chain

log = logging.getLogger(__name__)

# What a voice may be asked for. A closed list: a purpose is only worth signing if everyone reads it the same way.
PURPOSES = {
    "security_test": "security testing",
    "speech_help": "speech assistance",
    "phone_greetings": "phone greetings",
    "advertising": "advertising",
}
MIN_STATEMENT_MATCH = 0.6  # as for a Whisper Phrase; a wrong number scores at most 0.5 (signals.phrase_match)
_ASK_TTL = timedelta(minutes=5)
_LEDGER_PREFIX = "v:"  # a Voice Ledger shares the Audit Trail table; Call ids are UUIDs, so they never collide
_LEDGER_SHOWN = 30
_REFUSED_SHOWN = 5
_DIGITS = 2
# English for every Customer: in Hindi the sentence was heard and the number was not (Nov 1, real readouts; in hall
# chatter English was accepted 12 of 12, Hindi about half). No full stop at the end: speakable() turns a digit into a
# word only when it stands alone.
_STATEMENT = "I am {name}. I allow {requester} to use my voice for {purpose}. Number {digits}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _same(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


class VoiceConsents:
    def __init__(
        self,
        db: Database,
        signals: SignalExtractor,
        signer: ReceiptSigner,
        rng: random.Random | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ):
        self._db = db
        self._signals = signals
        self._signer = signer
        self._rng = rng or random.SystemRandom()
        self._now = clock

    # ------------------------------------------------------------------ the requester

    def ask(self, customer_id: str, requester: str, purpose: str, minutes: int, max_uses: int) -> dict:
        requester = " ".join(requester.split())
        if purpose not in PURPOSES:
            raise NotAllowed(f"unknown purpose: {purpose}")
        if not 2 <= len(requester) <= 60:
            raise NotAllowed("the requester's name must be 2 to 60 characters")
        if not 5 <= minutes <= 1440:
            raise NotAllowed("consent can last 5 minutes to one day")
        if not 1 <= max_uses <= 100:
            raise NotAllowed("consent can cover 1 to 100 uses")
        at = self._now()
        with self._db.session() as s:
            customer = s.get(CustomerRow, customer_id)
            if customer is None:
                raise UnknownCustomer(customer_id)
            digits = " ".join(str(self._rng.randrange(10)) for _ in range(_DIGITS))
            row = VoiceConsentRow(
                id=str(uuid.uuid4()), customer_id=customer_id, requester=requester, purpose=purpose,
                statement=_STATEMENT.format(name=customer.name, requester=requester, purpose=PURPOSES[purpose], digits=digits),
                status="pending", minutes=minutes, max_uses=max_uses, uses=0,
                created_at=at, ask_expires_at=at + _ASK_TTL,
            )
            s.add(row)
            s.flush()
            self._log(s, row.customer_id, "consent_requested", self._about(row))
            return self._view(row, customer, at)

    def use(self, customer_id: str, requester: str, purpose: str, clip: str, consent_pass: str | None = None) -> dict:
        """One Voice Use. Refused or allowed, it goes on the owner's Voice Ledger."""
        claims, reason = self._read_pass(consent_pass)
        at = self._now()
        with self._db.session() as s:
            if s.get(CustomerRow, customer_id) is None:
                raise UnknownCustomer(customer_id)
            row = None
            if reason is None:
                row = s.get(VoiceConsentRow, str(claims.get("jti")), with_for_update=True)
                reason = self._refusal(row, claims, customer_id, requester, purpose, at)
            data = {"requester": requester, "purpose": purpose, "clip": clip}
            if reason is not None:
                self._log(s, customer_id, "voice_use_refused", {**data, "reason": reason, "consent_id": row.id if row else None})
                return {"allowed": False, "reason": reason}
            row.uses += 1
            self._log(s, customer_id, "voice_use_allowed", {**data, "consent_id": row.id, "use": row.uses})
            return {"allowed": True, "reason": "", "consent_id": row.id, "uses_left": row.max_uses - row.uses}

    def authorize(self, consent_pass: str, requester: str, purpose: str, clip: str) -> dict:
        """use() for a tool that holds only a pass. A forged pass names no real owner, so it logs nothing."""
        claims, reason = self._read_pass(consent_pass)
        if reason is not None:
            return {"allowed": False, "reason": reason}
        return self.use(str(claims.get("sub")), requester, purpose, clip, consent_pass)

    # ------------------------------------------------------------------ the owner, on the Registered Device

    def give(self, consent_id: str, customer_id: str, device_token: str, audio: Audio, raw: bytes) -> dict:
        """Consent by voice: the owner reads the statement aloud. Speech-to-text runs outside the transaction."""
        with self._db.session() as s:
            self._check_device(s, customer_id, device_token)
            row = self._owned(s, consent_id, customer_id)
            self._must_be_open(row)
            statement = row.statement
        heard, match = self._signals.statement_match(audio, statement)
        at = self._now()
        with self._db.session() as s:
            customer = self._check_device(s, customer_id, device_token)
            row = self._owned(s, consent_id, customer_id, lock=True)
            self._must_be_open(row)
            if match < MIN_STATEMENT_MATCH:
                self._log(s, customer_id, "consent_statement_failed", {
                    "consent_id": row.id, "heard": heard, "match": match, "seconds": round(audio.seconds, 1),
                    "peak": round(float(abs(audio.samples).max()), 3) if audio.samples.size else 0.0,
                })
                return {"granted": False, "heard": heard, "match": match,
                        "reason": "That was not clear, most often the number. Read it again, slowly."}
            row.status, row.approved_at = "active", at
            row.expires_at = at + timedelta(minutes=row.minutes)
            row.statement_match, row.statement_sha256 = match, hashlib.sha256(raw).hexdigest()
            row.consent_pass = self._signer.sign(self._claims(row, customer, at))
            self._log(s, customer_id, "consent_granted", {**self._about(row), "match": match, "statement_sha256": row.statement_sha256})
            return {"granted": True, "heard": heard, "match": match, "consent_pass": row.consent_pass}

    def decline(self, consent_id: str, customer_id: str, device_token: str) -> dict:
        with self._db.session() as s:
            customer = self._check_device(s, customer_id, device_token)
            row = self._owned(s, consent_id, customer_id, lock=True)
            self._must_be_open(row)
            row.status = "declined"
            self._log(s, customer_id, "consent_declined", self._about(row))
            return self._view(row, customer, self._now())

    def revoke(self, consent_id: str, customer_id: str, device_token: str) -> dict:
        """Withdrawn at once: use() reads this row every time, so a pass that still looks valid stops working."""
        with self._db.session() as s:
            customer = self._check_device(s, customer_id, device_token)
            row = self._owned(s, consent_id, customer_id, lock=True)
            if row.status != "active":
                raise NotAllowed("only a consent in force can be revoked")
            row.status, row.revoked_at = "revoked", self._now()
            row.consent_pass = None
            self._log(s, customer_id, "consent_revoked", self._about(row))
            return self._view(row, customer, self._now())

    def mine(self, customer_id: str, device_token: str) -> dict:
        """What the Bank App shows under My voice."""
        at = self._now()
        with self._db.session() as s:
            customer = self._check_device(s, customer_id, device_token)
            rows = s.scalars(select(VoiceConsentRow).where(VoiceConsentRow.customer_id == customer_id)
                             .order_by(VoiceConsentRow.created_at.desc()).limit(20)).all()
            refused = s.scalars(select(AuditEventRow).where(
                AuditEventRow.call_id == _LEDGER_PREFIX + customer_id, AuditEventRow.kind == "voice_use_refused",
            ).order_by(AuditEventRow.seq.desc()).limit(_REFUSED_SHOWN)).all()
            return {"consents": [self._view(r, customer, at) for r in rows], "refused": [_event(e) for e in refused]}

    # ------------------------------------------------------------------ reads

    def overview(self) -> dict:
        """The Consent page: every consent, the latest ledger events, and whether every ledger is intact."""
        at = self._now()
        with self._db.session() as s:
            customers = {c.id: c for c in s.scalars(select(CustomerRow)).all()}
            rows = s.scalars(select(VoiceConsentRow).order_by(VoiceConsentRow.created_at.desc()).limit(20)).all()
            events = s.scalars(select(AuditEventRow).where(AuditEventRow.call_id.like(f"{_LEDGER_PREFIX}%"))
                               .order_by(AuditEventRow.created_at.desc(), AuditEventRow.seq.desc()).limit(_LEDGER_SHOWN)).all()
            intact = all(walk_chain(s, _LEDGER_PREFIX + cid)[2] is None for cid in customers)
            return {
                "consents": [{**self._view(r, customers[r.customer_id], at), "consent_pass": r.consent_pass} for r in rows],
                "ledger": [{**_event(e), "customer_name": customers[e.call_id.removeprefix(_LEDGER_PREFIX)].name} for e in events],
                "ledger_intact": intact,
                "purposes": [{"id": k, "label": v} for k, v in PURPOSES.items()],
            }

    def public_key(self) -> dict:
        return self._signer.public_jwk()

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _check_device(s: Session, customer_id: str, device_token: str) -> CustomerRow:
        customer = s.get(CustomerRow, customer_id)
        if customer is None:
            raise UnknownCustomer(customer_id)
        if not device_token or not hmac.compare_digest(customer.device_token.encode(), device_token.encode()):
            raise DeviceNotPaired(customer_id)
        return customer

    @staticmethod
    def _owned(s: Session, consent_id: str, customer_id: str, lock: bool = False) -> VoiceConsentRow:
        row = s.get(VoiceConsentRow, consent_id, with_for_update=lock)
        if row is None or row.customer_id != customer_id:
            raise ConsentNotFound(consent_id)  # another Customer's consent looks the same as none at all
        return row

    def _must_be_open(self, row: VoiceConsentRow) -> None:
        if row.status != "pending":
            raise NotAllowed(f"this request is already {row.status}")
        if self._now() >= row.ask_expires_at:
            raise NotAllowed("this request has lapsed; ask again")

    def _read_pass(self, consent_pass: str | None) -> tuple[dict, str | None]:
        if not consent_pass:
            return {}, "no Consent Pass was given"
        try:
            claims = self._signer.verify(consent_pass)
        except InvalidReceipt:
            return {}, "this Consent Pass is not genuine"
        if claims.get("kind") != "voice_consent":
            return {}, "this is not a Consent Pass"
        return claims, None

    @staticmethod
    def _refusal(row: VoiceConsentRow | None, claims: dict, customer_id: str, requester: str, purpose: str,
                 at: datetime) -> str | None:
        if row is None or claims.get("sub") != customer_id or row.customer_id != customer_id:
            return "this Consent Pass is for someone else's voice"
        if row.status == "revoked":
            return "the owner revoked this consent"
        if row.status != "active" or row.expires_at is None or at >= row.expires_at:
            return "this consent has expired"
        if not _same(row.requester, requester):
            return f"this consent was given to {row.requester}"
        if row.purpose != purpose:
            return f"the owner agreed to {PURPOSES[row.purpose]} only: this purpose was not agreed"
        if row.uses >= row.max_uses:
            return "every agreed use has been used up"
        return None

    def _claims(self, row: VoiceConsentRow, customer: CustomerRow, at: datetime) -> dict:
        issued = int(at.replace(tzinfo=timezone.utc).timestamp())
        return {
            "iss": "pratyaksh", "kind": "voice_consent", "jti": row.id, "sub": row.customer_id, "name": customer.name,
            "requester": row.requester, "purpose": row.purpose, "max_uses": row.max_uses,
            "statement_sha256": row.statement_sha256, "iat": issued, "exp": issued + row.minutes * 60,
        }

    def _log(self, s: Session, customer_id: str, kind: str, data: dict) -> None:
        append_event(s, _LEDGER_PREFIX + customer_id, kind, data, self._now())

    @staticmethod
    def _about(row: VoiceConsentRow) -> dict:
        return {"consent_id": row.id, "requester": row.requester, "purpose": row.purpose, "minutes": row.minutes,
                "max_uses": row.max_uses}

    @staticmethod
    def _status(row: VoiceConsentRow, at: datetime) -> str:
        if row.status == "pending" and at >= row.ask_expires_at:
            return "lapsed"
        if row.status == "active" and row.expires_at is not None and at >= row.expires_at:
            return "expired"
        if row.status == "active" and row.uses >= row.max_uses:
            return "used_up"
        return row.status

    def _view(self, row: VoiceConsentRow, customer: CustomerRow, at: datetime) -> dict:
        ends = row.expires_at if row.status == "active" else row.ask_expires_at if row.status == "pending" else None
        return {
            "id": row.id, "customer_id": row.customer_id, "customer_name": customer.name, "requester": row.requester,
            "purpose": row.purpose, "purpose_label": PURPOSES[row.purpose],
            "statement": speakable(row.statement, "en"), "status": self._status(row, at),
            "minutes": row.minutes, "max_uses": row.max_uses, "uses": row.uses,
            "seconds_left": max(0, int((ends - at).total_seconds())) if ends else 0,
            "created_at": row.created_at.isoformat(),
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "statement_match": row.statement_match,
        }


def _event(e: AuditEventRow) -> dict:
    return {"seq": e.seq, "kind": e.kind, "at": e.created_at.isoformat(), "hash": e.hash[:12], **e.data}


class ConsentedClips:
    """The consented recordings the Consent page may release: the owner's real voice and the spoken Clone lines.
    A caller names a clip by id, never by path. The whispered lines are left out: they only exist for the attack."""

    def __init__(self, manifest: str, reference: str):
        self._files: dict[str, Path] = {}
        self._catalogue: list[dict] = []
        if reference and Path(reference).is_file():
            self._add("real", "real", "Real voice: the consented recording", Path(reference))
        if not manifest or not Path(manifest).is_file():
            return
        with open(manifest, newline="", encoding="utf-8") as f:
            spoken = [r for r in csv.DictReader(f) if r.get("variant") == "normal" and Path(r.get("file", "")).is_file()]
        for n, row in enumerate(reversed(spoken), start=1):  # the showcase sentence was voiced last
            self._add(f"clone-{n}", "clone", row["phrase"], Path(row["file"]))

    def _add(self, clip_id: str, kind: str, label: str, path: Path) -> None:
        self._files[clip_id] = path
        self._catalogue.append({"id": clip_id, "kind": kind, "label": label})

    def catalogue(self) -> list[dict]:
        return self._catalogue

    def has(self, clip_id: str) -> bool:
        return clip_id in self._files

    def read(self, clip_id: str) -> bytes:
        return self._files[clip_id].read_bytes()
