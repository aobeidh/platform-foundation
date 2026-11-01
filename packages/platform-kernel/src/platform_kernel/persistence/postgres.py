"""PostgreSQL providers (extra: [postgres]). One schema per service (P7); tenant scope set per transaction so
row-level security applies (P22). SQLAlchemy is imported here only, never at kernel import time (F5)."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from ..audit import GENESIS, AuditEntry, AuditRecord, link
from ..contracts import Envelope
from .ports import IdempotencyBegin, OutboxRow

_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def check_identifier(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"{name!r} is not a safe SQL identifier")
    return name


def create_engine(url: str) -> Any:
    from sqlalchemy import create_engine as _create

    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return _create(url, pool_pre_ping=True, future=True)


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


class _Events:
    def __init__(self, conn: Any) -> None:
        self._c = conn

    def publish(self, events: list[Envelope]) -> None:
        from sqlalchemy import text

        for e in events:
            self._c.execute(text(
                "insert into outbox (id, type, subject, tenant_id, occurred_at, envelope) "
                "values (:id, :type, :subject, :tenant, :at, cast(:env as jsonb))"),
                {"id": e.id, "type": e.type, "subject": e.subject, "tenant": e.tenantid, "at": e.time,
                 "env": e.model_dump_json()})


class _Audit:
    def __init__(self, conn: Any) -> None:
        self._c = conn

    def append(self, entry: AuditEntry) -> AuditRecord:
        from sqlalchemy import text

        # Serialize appends per stream for the rest of this transaction.
        self._c.execute(text("select pg_advisory_xact_lock(hashtext(:s))"), {"s": "audit:" + entry.stream})
        last = self._c.execute(text("select seq, hash from audit_record where stream = :s order by seq desc limit 1"),
                               {"s": entry.stream}).first()
        rec = link((last.seq + 1) if last else 1, entry, last.hash if last else GENESIS)
        body = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in entry.__dict__.items()}
        self._c.execute(text(
            "insert into audit_record (stream, seq, at, tenant_id, entry, prev_hash, hash) "
            "values (:s, :seq, :at, :tenant, cast(:entry as jsonb), :prev, :hash)"),
            {"s": entry.stream, "seq": rec.seq, "at": entry.at, "tenant": entry.tenant, "entry": _json(body),
             "prev": rec.prev_hash, "hash": rec.hash})
        return rec


class _Inbox:
    def __init__(self, conn: Any) -> None:
        self._c = conn

    def first_time(self, consumer: str, event_id: str) -> bool:
        from sqlalchemy import text

        row = self._c.execute(text("insert into inbox (consumer, event_id) values (:c, :e) "
                                   "on conflict do nothing returning event_id"), {"c": consumer, "e": event_id}).first()
        return row is not None


class _DeadLetters:
    def __init__(self, conn: Any) -> None:
        self._c = conn

    def add(self, consumer: str, kind: Literal["invalid", "dead"], reason: str, envelope: Envelope) -> None:
        from sqlalchemy import text

        from ..core import new_id

        self._c.execute(text("insert into dead_letter (id, consumer, kind, reason, envelope) "
                             "values (:id, :c, :k, :r, cast(:env as jsonb))"),
                        {"id": new_id(), "c": consumer, "k": kind, "r": reason, "env": envelope.model_dump_json()})


class PostgresUnitOfWork:
    def __init__(self, engine: Any, schema: str, tenant: str | None, platform_scope: bool) -> None:
        self._engine, self._schema = engine, check_identifier(schema)
        self._tenant, self._platform = tenant, platform_scope
        self.connection: Any = None
        self._tx: Any = None

    def __enter__(self) -> PostgresUnitOfWork:
        from sqlalchemy import text

        from .. import context as ctxmod

        ctxmod.check_deadline("opening a unit of work")
        ctx = ctxmod.maybe_current()
        self.connection = self._engine.connect()
        self._tx = self.connection.begin()
        self.connection.execute(text(f"set local search_path to {self._schema}"))
        self.connection.execute(
            text("select set_config('app.scope', :scope, true), set_config('app.tenant', :t, true)"),
            {"scope": "platform" if self._platform else "tenant", "t": self._tenant or ""})
        if ctx is not None:
            # No statement may outlive the request deadline (F10), even in synchronous code.
            budget_ms = max(1, int((ctx.deadline - datetime.now(UTC)).total_seconds() * 1000))
            budget_ms = min(budget_ms, 2_147_483_647)  # PostgreSQL's integer limit for statement_timeout
            self.connection.execute(text(f"set local statement_timeout = {budget_ms}"))
        self.events = _Events(self.connection)
        self.audit = _Audit(self.connection)
        self.inbox = _Inbox(self.connection)
        self.dead_letters = _DeadLetters(self.connection)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            if exc_type is None:
                self._tx.commit()
            else:
                self._tx.rollback()
        finally:
            self.connection.close()
            self.connection = None


class PostgresUnitOfWorkFactory:
    """Takes the tenant scope from the current request context when a unit of work opens."""

    simulated = False

    def __init__(self, engine: Any, schema: str) -> None:
        self.engine, self.schema = engine, check_identifier(schema)

    def __call__(self, *, platform_scope: bool = False) -> PostgresUnitOfWork:
        from .. import context as ctxmod

        ctx = ctxmod.maybe_current()
        tenant = ctx.tenant.tenant if ctx else None
        platform = platform_scope or (ctx is not None and ctx.tenant.platform)
        return PostgresUnitOfWork(self.engine, self.schema, tenant, platform)


class PostgresOutboxReader:
    def __init__(self, engine: Any, schema: str) -> None:
        self._engine, self._schema = engine, check_identifier(schema)

    def claim(self, limit: int) -> list[OutboxRow]:
        from sqlalchemy import text

        with self._engine.begin() as c:
            c.execute(text(f"set local search_path to {self._schema}"))
            # One relay per schema in 0.1 (docs/modules/messaging.md); competing relays need a lease, planned later.
            rows = c.execute(text("select id, envelope, attempts from outbox where sent_at is null "
                                  "order by occurred_at, id limit :n"), {"n": limit}).all()
        return [OutboxRow(r.id, Envelope.model_validate(r.envelope), r.attempts) for r in rows]

    def mark_sent(self, ids: list[str]) -> None:
        from sqlalchemy import bindparam, text

        if not ids:
            return
        with self._engine.begin() as c:
            c.execute(text(f"set local search_path to {self._schema}"))
            c.execute(text("update outbox set sent_at = now() where id in :ids").bindparams(
                bindparam("ids", expanding=True)), {"ids": ids})

    def mark_failed(self, id: str, error: str) -> None:
        from sqlalchemy import text

        with self._engine.begin() as c:
            c.execute(text(f"set local search_path to {self._schema}"))
            c.execute(text("update outbox set attempts = attempts + 1, last_error = :e where id = :id"),
                      {"id": id, "e": error[:2000]})


class PostgresIdempotencyStore:
    def __init__(self, engine: Any, schema: str, retention: timedelta = timedelta(hours=24),
                 lease: timedelta = timedelta(minutes=5)) -> None:
        self._engine, self._schema, self._retention = engine, check_identifier(schema), retention
        self._lease = lease

    def _tx(self) -> Any:
        return self._engine.begin()

    def begin(self, tenant: str | None, key: str, request_hash: str) -> IdempotencyBegin:
        from sqlalchemy import text

        with self._tx() as c:
            c.execute(text(f"set local search_path to {self._schema}"))
            now = datetime.now(UTC)
            # Expired keys, and in-progress keys whose lease ran out (the process died), may start again.
            c.execute(text("delete from idempotency_key where tenant_id = :t and key = :k and (created_at < :cut "
                           "or (status = 'in_progress' and created_at < :lease))"),
                      {"t": tenant or "", "k": key, "cut": now - self._retention, "lease": now - self._lease})
            inserted = c.execute(text(
                "insert into idempotency_key (tenant_id, key, request_hash, status) values (:t, :k, :h, 'in_progress') "
                "on conflict do nothing returning key"), {"t": tenant or "", "k": key, "h": request_hash}).first()
            if inserted:
                return IdempotencyBegin("started")
            row = c.execute(text("select request_hash, status, status_code, response from idempotency_key "
                                 "where tenant_id = :t and key = :k"), {"t": tenant or "", "k": key}).first()
        if row is None:
            return IdempotencyBegin("in_progress")
        if row.request_hash != request_hash:
            return IdempotencyBegin("reused")
        if row.status == "in_progress":
            return IdempotencyBegin("in_progress")
        return IdempotencyBegin("replay", row.status_code, row.response)

    def complete(self, tenant: str | None, key: str, status_code: int, response: Any) -> None:
        from sqlalchemy import text

        with self._tx() as c:
            c.execute(text(f"set local search_path to {self._schema}"))
            c.execute(text("update idempotency_key set status = 'completed', status_code = :sc, "
                           "response = cast(:r as jsonb) where tenant_id = :t and key = :k"),
                      {"sc": status_code, "r": _json(response), "t": tenant or "", "k": key})

    def abandon(self, tenant: str | None, key: str) -> None:
        from sqlalchemy import text

        with self._tx() as c:
            c.execute(text(f"set local search_path to {self._schema}"))
            c.execute(text("delete from idempotency_key where tenant_id = :t and key = :k"),
                      {"t": tenant or "", "k": key})


class PostgresAuditReader:
    """Reads a stream back for verification and audit queries."""

    def __init__(self, engine: Any, schema: str) -> None:
        self._engine, self._schema = engine, check_identifier(schema)

    def records(self, stream: str) -> list[AuditRecord]:
        from sqlalchemy import text

        with self._engine.begin() as c:
            c.execute(text(f"set local search_path to {self._schema}"))
            rows = c.execute(text("select seq, entry, prev_hash, hash from audit_record where stream = :s "
                                  "order by seq"), {"s": stream}).all()
        out = []
        for r in rows:
            e = dict(r.entry)
            e["at"] = datetime.fromisoformat(e["at"])
            out.append(AuditRecord(r.seq, AuditEntry(**e), r.prev_hash, r.hash))
        return out
