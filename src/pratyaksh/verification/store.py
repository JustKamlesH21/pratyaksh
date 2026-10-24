"""Database tables. MySQL in production, SQLite in tests (same models; see ADR-0004).

The Audit Trail table is insert-only: nothing in the code updates or deletes it, and
create_schema() adds database triggers that reject UPDATE and DELETE on it. Each event also
carries a SHA-256 hash chained to the previous event of its Call (chain_hash), so an edit or a
deleted event is detectable even by someone who drops the triggers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

import secrets

from sqlalchemy import (
    JSON, Boolean, DateTime as _DateTime, Double, ForeignKey, Integer, String, Text, create_engine, inspect, select,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


log = logging.getLogger(__name__)

# Microsecond timestamps on MySQL (its DATETIME default drops fractions of a second).
DateTime = _DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")

_AUDIT_TRIGGERS = {
    "mysql": {
        "audit_events_no_update": "CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
        "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_events is insert-only'",
        "audit_events_no_delete": "CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events "
        "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_events is insert-only'",
    },
    "sqlite": {
        "audit_events_no_update": "CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit_events is insert-only'); END",
        "audit_events_no_delete": "CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit_events is insert-only'); END",
    },
}


class Base(DeclarativeBase):
    pass


class CustomerRow(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone_masked: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8), default="kn")
    # Secret the Bank App on the Registered Device must present (pairing). Never sent to Callers.
    device_token: Mapped[str] = mapped_column(String(64), default=lambda: secrets.token_urlsafe(18))


class CallRow(Base):
    __tablename__ = "calls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    room: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(32))
    request: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_attempts: Mapped[int] = mapped_column(Integer, default=0)  # unclear turns before a Request
    side_turns: Mapped[int] = mapped_column(Integer, default=0)  # questions and repeats answered
    agent_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # pending|approved|rejected
    planned: Mapped[list] = mapped_column(JSON, default=list)  # ChallengeKind values still to ask, in order
    challenges: Mapped[list] = mapped_column(JSON, default=list)  # issued: {kind, prompt, phrase, issued_at}
    evidence: Mapped[list] = mapped_column(JSON, default=list)  # answered: {kind, signals}
    scores: Mapped[list] = mapped_column(JSON, default=list)  # Liveness Score per answered Challenge
    step_ups: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    liveness: Mapped[float | None] = mapped_column(Double, nullable=True)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pending_step: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(36), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="")


GENESIS = "0" * 64  # prev_hash of a Call's first event


def chain_hash(prev_hash: str, call_id: str, seq: int, kind: str, data: dict, created_at: datetime) -> str:
    """SHA-256 of one Audit Trail event and the hash before it. Stable across MySQL and SQLite."""
    body = json.dumps(_canonical(data), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    line = f"{prev_hash}|{call_id}|{seq}|{kind}|{body}|{created_at.isoformat(timespec='microseconds')}"
    return hashlib.sha256(line.encode()).hexdigest()


def _canonical(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)  # a database may hand 1.0 back as 1
    if isinstance(v, dict):
        return {str(k): _canonical(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_canonical(x) for x in v]
    return v


class PossessionCodeRow(Base):
    __tablename__ = "possession_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(36), index=True)
    customer_id: Mapped[str] = mapped_column(String(32))
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeviceMessageRow(Base):
    """A simulated push message to a Customer's Registered Device (shown in the Bank App)."""

    __tablename__ = "device_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(String(32), index=True)
    call_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(32))  # possession_code | app_approval
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EvalRunRow(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    label: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    rows: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


DEMO_CUSTOMERS = [
    ("cust-ananya", "Ananya Rao", "+91 98xxxx4410", "kn"),
    ("cust-rahul", "Rahul Verma", "+91 99xxxx2087", "hi"),
    ("cust-meera", "Meera Iyer", "+91 97xxxx7731", "en"),
]


class SchemaOutOfDate(RuntimeError):
    """The database was created by an older version: create_all() never adds columns."""


class Database:
    def __init__(self, url: str):
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs = {"connect_args": {"check_same_thread": False}}
            if url in ("sqlite://", "sqlite:///:memory:"):
                kwargs["poolclass"] = StaticPool
        self.engine = create_engine(url, **kwargs)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> list[str]:
        """Create the tables and the Audit Trail triggers. Returns the triggers that could not be added."""
        Base.metadata.create_all(self.engine)
        self._check_columns()
        return self._protect_audit_trail()

    def reset(self) -> None:
        """Drop every table (and with it the Audit Trail and its triggers). Demo data only."""
        Base.metadata.drop_all(self.engine)

    def _check_columns(self) -> None:
        tables = inspect(self.engine)
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in tables.get_columns(table.name)}
            missing = [c.name for c in table.columns if c.name not in have]
            if missing:
                raise SchemaOutOfDate(
                    f"table {table.name} has no {', '.join(missing)}: the database is older than this code. "
                    "Run pratyaksh-seed --reset (deletes all Calls and the Audit Trail) to recreate it."
                )

    def _protect_audit_trail(self) -> list[str]:
        dialect = self.engine.dialect.name
        existing: set[str] = set()
        if dialect == "mysql":
            with self.engine.connect() as conn:
                existing = set(conn.execute(text(
                    "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()"
                )).scalars())
        missing, cause = [], None
        for name, ddl in _AUDIT_TRIGGERS.get(dialect, {}).items():
            if name in existing:
                continue
            try:
                with self.engine.begin() as conn:
                    conn.execute(text(ddl))
            except Exception as e:  # e.g. the MySQL user lacks the TRIGGER privilege
                missing.append(name)
                cause = getattr(e, "orig", e)
        if missing:
            db = self.engine.url.database
            log.error(
                "Audit Trail is NOT protected in the database: could not add %s: %s. "
                "Fix as MySQL root: GRANT TRIGGER ON %s.* TO the app user; SET PERSIST "
                "log_bin_trust_function_creators = 1; then run pratyaksh-seed again. "
                "Until then the Audit Trail is insert-only in code only.",
                ", ".join(missing), cause, db,
            )
        return missing

    def seed_demo_customers(self) -> None:
        with self.session() as s:
            for cid, name, phone, lang in DEMO_CUSTOMERS:
                if s.get(CustomerRow, cid) is None:
                    s.add(CustomerRow(id=cid, name=name, phone_masked=phone, language=lang,
                                      device_token=secrets.token_urlsafe(18)))

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self._sessions()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def latest_eval_run(self) -> dict | None:
        with self.session() as s:
            row = s.scalars(select(EvalRunRow).order_by(EvalRunRow.id.desc()).limit(1)).first()
            if row is None:
                return None
            return {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "label": row.label,
                "summary": row.summary,
                "rows": row.rows,
                "notes": row.notes,
            }

    def save_eval_run(self, label: str, summary: dict, rows: list, notes: str, at: datetime) -> int:
        with self.session() as s:
            row = EvalRunRow(created_at=at, label=label, summary=summary, rows=rows, notes=notes)
            s.add(row)
            s.flush()
            return row.id


def seed_main() -> None:
    """Create tables and demo Customers. Usage: pratyaksh-seed [--database-url URL] [--reset]"""
    from ..config import Settings

    parser = argparse.ArgumentParser(description=seed_main.__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--reset", action="store_true", help="drop all tables first (deletes Calls and the Audit Trail)")
    args = parser.parse_args()
    db = Database(args.database_url or Settings().database_url)
    if args.reset:
        db.reset()
        print("dropped all tables")
    missing = db.create_schema()
    db.seed_demo_customers()
    print("tables ready, demo customers seeded" if missing else "schema ready, demo customers seeded")
    print("\nBank App pairing links (open each on that Customer's phone; keep them private):")
    with db.session() as s:
        for c in s.scalars(select(CustomerRow).order_by(CustomerRow.id)).all():
            print(f"  {c.name:14s} /bank?customer={c.id}&device={c.device_token}")
    if missing:
        sys.exit("\nAudit Trail triggers are missing (see the error above); fix it and run pratyaksh-seed again.")
