"""SQLite providers: a single-node durable mode without PostgreSQL (ADR 0008). The tenant scope is applied in code,
as the memory provider does; SQLite has no row-level security, so there is no second line of defense (P22).

Every unit of work begins with `BEGIN IMMEDIATE`, so there is one writer at a time, like the memory provider. Python's
sqlite3 module opens no transactions of its own: the engine issues them explicitly. Timestamps are stored as text in
one fixed-width UTC format (`to_text`, `from_text`), so text order is time order; JSON is stored as text.
SQLAlchemy is imported here only, never at kernel import time (F5)."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from ..audit import GENESIS, AuditEntry, AuditRecord, link
from ..contracts import Envelope
from .ports import IdempotencyBegin, OutboxRow

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
DEFAULT_BUSY_TIMEOUT = timedelta(seconds=30)
_MIN_SQLITE = (3, 24, 0)  # upsert (on conflict do nothing / do update)
_BEGIN_MODES = frozenset({"DEFERRED", "IMMEDIATE", "EXCLUSIVE"})


# Timestamps as text ---------------------------------------------------------------------------------------------

def to_text(dt: datetime) -> str:
    """Write a timezone-aware datetime as UTC text, exactly `%Y-%m-%dT%H:%M:%S.%fZ` and always 27 characters wide,
    so text order is time order. Naive datetimes are refused, because their time zone is unknown."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("to_text needs a timezone-aware datetime; a naive one has no known time zone")
    u = dt.astimezone(UTC)
    # Formatted field by field: strftime does not pad years below 1000 on every platform.
    return (f"{u.year:04d}-{u.month:02d}-{u.day:02d}T{u.hour:02d}:{u.minute:02d}:{u.second:02d}."
            f"{u.microsecond:06d}Z")


def from_text(s: str) -> datetime:
    """Read text written by `to_text` back as a timezone-aware UTC datetime. Any other format is refused."""
    if len(s) != 27:
        raise ValueError(f"{s!r} is not a timestamp in the format {TIMESTAMP_FORMAT}")
    return datetime.strptime(s, TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def _opt_text(dt: datetime | None) -> str | None:
    return to_text(dt) if dt is not None else None


def _opt_dt(s: str | None) -> datetime | None:
    return from_text(s) if s is not None else None


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _opt_json(value: Any) -> str | None:
    return _json(value) if value is not None else None


def _load(s: str | None) -> Any:
    return json.loads(s) if s is not None else None


# Engine ---------------------------------------------------------------------------------------------------------

def create_engine(url: str, *, busy_timeout: timedelta = DEFAULT_BUSY_TIMEOUT) -> Any:
    """An engine for a SQLAlchemy `sqlite:///path` URL. Each connection uses WAL journal mode, enforces foreign
    keys and waits up to `busy_timeout` for the write lock. Transactions are explicit: `BEGIN IMMEDIATE` unless the
    connection's execution option `sqlite_begin` says `DEFERRED` (read-only work) or `EXCLUSIVE`."""
    from sqlalchemy import create_engine as _create
    from sqlalchemy import event
    from sqlalchemy.engine import make_url

    if sqlite3.sqlite_version_info < _MIN_SQLITE:
        raise RuntimeError(f"the SQLite provider needs SQLite {'.'.join(map(str, _MIN_SQLITE))} or later; this "
                           f"Python has {sqlite3.sqlite_version}")
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or parsed.get_driver_name() != "pysqlite":
        raise ValueError(f"{parsed.render_as_string(hide_password=True)!r} is not a sqlite:/// URL for Python's "
                         f"sqlite3 driver")
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("select value from json_each('[1]')")  # the maker-checker triggers need JSON functions
    except sqlite3.OperationalError as exc:
        raise RuntimeError("the SQLite provider needs SQLite's JSON functions, which this Python's SQLite "
                           "lacks") from exc
    finally:
        probe.close()
    if parsed.database in (None, "", ":memory:") or str(parsed.database).startswith("file::memory:"):
        raise ValueError("the SQLite provider needs a database file (sqlite:///path/to/file.db); use the memory "
                         "provider for a database that lives in memory")
    busy_ms = max(0, int(busy_timeout.total_seconds() * 1000))
    engine = _create(url, future=True, connect_args={"check_same_thread": False,
                                                     "timeout": busy_timeout.total_seconds()})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None  # sqlite3 must not open transactions of its own
        dbapi_connection.execute("pragma journal_mode = wal")
        dbapi_connection.execute("pragma foreign_keys = on")
        dbapi_connection.execute(f"pragma busy_timeout = {busy_ms}")

    @event.listens_for(engine, "begin")
    def _on_begin(conn: Any) -> None:
        mode = str(conn.get_execution_options().get("sqlite_begin", "IMMEDIATE")).upper()
        if mode not in _BEGIN_MODES:
            raise ValueError(f"sqlite_begin must be one of {sorted(_BEGIN_MODES)}, not {mode!r}")
        conn.exec_driver_sql(f"begin {mode.lower()}")

    _guard(engine)
    return engine


def _read(engine: Any) -> Any:
    """A short read-only transaction. It does not wait for the write lock."""
    return engine.execution_options(sqlite_begin="DEFERRED").begin()


def scope_clause(column: str = "tenant_id") -> str:
    """The tenant scope applied in code, with the rule of PostgreSQL's row-level security policy: platform scope
    sees every row, otherwise only the unit of work's tenant (no tenant sees no tenant rows). Bind `scope_params`."""
    return f"(:scope_platform = 1 or {column} = :scope_tenant)"


def scope_params(uow: Any) -> dict[str, Any]:
    """Parameters for `scope_clause`, from a SQLite unit of work."""
    return {"scope_platform": 1 if uow.platform_scope else 0, "scope_tenant": uow.tenant}


# Unit of work ---------------------------------------------------------------------------------------------------

class _Events:
    def __init__(self, conn: Any) -> None:
        self._c = conn

    def publish(self, events: list[Envelope]) -> None:
        from sqlalchemy import text

        for e in events:
            self._c.execute(text(
                "insert into outbox (id, type, subject, tenant_id, occurred_at, envelope) "
                "values (:id, :type, :subject, :tenant, :at, :env)"),
                {"id": e.id, "type": e.type, "subject": e.subject, "tenant": e.tenantid, "at": to_text(e.time),
                 "env": e.model_dump_json()})


class _Audit:
    def __init__(self, conn: Any) -> None:
        self._c = conn

    def append(self, entry: AuditEntry) -> AuditRecord:
        from sqlalchemy import text

        # The unit of work holds the database's only write lock, so appends to a stream are already serialized.
        last = self._c.execute(text("select seq, hash from audit_record where stream = :s order by seq desc limit 1"),
                               {"s": entry.stream}).first()
        rec = link((last.seq + 1) if last else 1, entry, last.hash if last else GENESIS)
        body = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in entry.__dict__.items()}
        self._c.execute(text(
            "insert into audit_record (stream, seq, at, tenant_id, entry, prev_hash, hash) "
            "values (:s, :seq, :at, :tenant, :entry, :prev, :hash)"),
            {"s": entry.stream, "seq": rec.seq, "at": to_text(entry.at), "tenant": entry.tenant, "entry": _json(body),
             "prev": rec.prev_hash, "hash": rec.hash})
        return rec


class _Inbox:
    def __init__(self, conn: Any) -> None:
        self._c = conn

    def first_time(self, consumer: str, event_id: str) -> bool:
        from sqlalchemy import text

        result = self._c.execute(text("insert into inbox (consumer, event_id, processed_at) values (:c, :e, :at) "
                                      "on conflict do nothing"),
                                 {"c": consumer, "e": event_id, "at": to_text(datetime.now(UTC))})
        return result.rowcount == 1


class _DeadLetters:
    def __init__(self, conn: Any) -> None:
        self._c = conn

    def add(self, consumer: str, kind: Literal["invalid", "dead"], reason: str, envelope: Envelope) -> None:
        from sqlalchemy import text

        from ..core import new_id

        self._c.execute(text("insert into dead_letter (id, consumer, kind, reason, envelope, at) "
                             "values (:id, :c, :k, :r, :env, :at)"),
                        {"id": new_id(), "c": consumer, "k": kind, "r": reason, "env": envelope.model_dump_json(),
                         "at": to_text(datetime.now(UTC))})


def _interrupted(exc: BaseException | None) -> bool:
    orig = getattr(exc, "orig", exc)
    return isinstance(orig, sqlite3.OperationalError) and "interrupt" in str(orig).lower()


def _locked(exc: BaseException | None) -> bool:
    orig = getattr(exc, "orig", exc)
    return isinstance(orig, sqlite3.OperationalError) and "locked" in str(orig).lower()


_open = threading.local()  # per thread: id(engine) -> the outermost open unit of work on that engine
_UOW_KEY = "platform_kernel.sqlite.uow"  # connection.info: the unit of work that owns the connection


class TransactionAborted(RuntimeError):
    """SQLite ended the unit of work's transaction on its own (an interrupted write, a full disk, an I/O error or
    out of memory). Nothing the unit of work wrote is kept, so no further statement may run and it cannot commit."""

    def __init__(self) -> None:
        super().__init__("SQLite rolled the unit of work's transaction back after an error; nothing it wrote is "
                         "kept, and no further statement may run in it")


def _outermost(engine: Any) -> SqliteUnitOfWork | None:
    return getattr(_open, "by_engine", {}).get(id(engine))


def _owner(conn: Any) -> SqliteUnitOfWork | None:
    try:
        return conn.info.get(_UOW_KEY)
    except Exception:  # noqa: BLE001 - a closed or invalidated connection has no owner
        return None


def _guard(engine: Any) -> None:
    """Statements of a unit of work whose transaction SQLite ended on its own would run in autocommit mode
    (sqlite3 opens no transactions of its own), so they are refused; the unit of work is poisoned."""
    from sqlalchemy import event

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn: Any, _cursor: Any, _statement: Any, _params: Any, _context: Any, _many: Any) -> None:
        uow = _owner(conn)
        if uow is not None and (uow.poisoned or not uow._in_transaction()):
            uow.poisoned = True
            raise TransactionAborted()

    @event.listens_for(engine, "handle_error")
    def _on_error(context: Any) -> None:
        conn = context.connection
        uow = _owner(conn) if conn is not None else None
        if uow is not None and not uow._in_transaction():
            uow.poisoned = True


class SqliteUnitOfWork:
    """One transaction that holds the database's write lock from `BEGIN IMMEDIATE` until it commits or rolls back.

    `tenant` and `platform_scope` say which rows the unit of work may see; the SQLite stores apply them in code.

    Nesting: SQLite has one writer per database file, so a unit of work opened while the same thread already holds
    one on the same engine would wait for itself. Instead it joins the outer transaction as a savepoint: it shares
    the outer's `connection`, `events`, `audit`, `inbox` and `dead_letters`. When it exits cleanly its savepoint is
    released, and its writes commit or roll back with the outer unit of work. When an exception leaves it, only its
    own writes are rolled back (to the savepoint); the outer carries on and commits what it wrote before and after.
    `tenant` and `platform_scope` are the inner's own; the request deadline is the outer's, which was set when the
    outer opened. Units of work on different engines, and in different threads, stay independent.

    If SQLite ends the transaction on its own (an interrupted write, a full disk, an I/O error, out of memory), the
    unit of work is poisoned: further statements raise `TransactionAborted`, and so does a clean exit, because
    there is nothing left to commit."""

    def __init__(self, engine: Any, tenant: str | None, platform_scope: bool) -> None:
        self._engine = engine
        self._outer: SqliteUnitOfWork | None = None
        self._savepoint: str | None = None
        self._depth = 0  # savepoints opened by joined units of work, for unique names
        self.poisoned = False
        self.tenant, self.platform_scope = tenant, platform_scope
        self.connection: Any = None
        self._tx: Any = None
        self._raw: Any = None
        self._busy_ms: int | None = None
        self._deadline: datetime | None = None
        self._deadline_limits_wait = False

    def _in_transaction(self) -> bool:
        return self._raw is not None and bool(self._raw.in_transaction)

    def __enter__(self) -> SqliteUnitOfWork:
        from .. import context as ctxmod

        ctxmod.check_deadline("opening a unit of work")
        outer = _outermost(self._engine)
        if outer is not None:
            if outer.poisoned or not outer._in_transaction():
                outer.poisoned = True
                raise TransactionAborted()
            outer._depth += 1
            self._outer, self._savepoint = outer, f"pf_uow_{outer._depth}"
            self.connection = outer.connection
            self.connection.exec_driver_sql(f"savepoint {self._savepoint}")
            self.events, self.audit, self.inbox = outer.events, outer.audit, outer.inbox
            self.dead_letters = outer.dead_letters
            return self
        ctx = ctxmod.maybe_current()
        self._deadline = ctx.deadline if ctx is not None else None
        self.connection = self._engine.connect()
        try:
            self._raw = self.connection.connection.dbapi_connection
            if self._deadline is not None:
                # No wait for the write lock and no statement may outlive the request deadline (F10).
                budget_ms = max(1, int((self._deadline - datetime.now(UTC)).total_seconds() * 1000))
                self._busy_ms = int(self._raw.execute("pragma busy_timeout").fetchone()[0])
                self._deadline_limits_wait = budget_ms <= self._busy_ms
                self._raw.execute(f"pragma busy_timeout = {min(budget_ms, self._busy_ms)}")
                deadline = self._deadline
                self._raw.set_progress_handler(lambda: 1 if datetime.now(UTC) >= deadline else 0, 1000)
            self._tx = self.connection.begin()  # BEGIN IMMEDIATE: waits for the write lock
        except BaseException as exc:
            self._release()
            if self._deadline is not None and ((_locked(exc) and self._deadline_limits_wait)
                                               or (_interrupted(exc) and ctxmod.deadline_exceeded())):
                # The wait for the lock was cut to the request's budget, so giving up means the deadline passed.
                raise ctxmod.DeadlineExceeded("the database write lock was free") from exc
            raise
        self.connection.info[_UOW_KEY] = self
        self.events = _Events(self.connection)
        self.audit = _Audit(self.connection)
        self.inbox = _Inbox(self.connection)
        self.dead_letters = _DeadLetters(self.connection)
        if not hasattr(_open, "by_engine"):
            _open.by_engine = {}
        _open.by_engine[id(self._engine)] = self
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        from .. import context as ctxmod

        if self._outer is not None:
            self._exit_joined(exc_type)
            return
        _open.by_engine.pop(id(self._engine), None)
        aborted = self.poisoned or not self._in_transaction()
        try:
            if exc_type is None and not aborted:
                self._tx.commit()
            else:
                self._tx.rollback()
        finally:
            self._release()
        if exc is not None and self._deadline is not None and _interrupted(exc) and ctxmod.deadline_exceeded():
            raise ctxmod.DeadlineExceeded("a database statement finished") from exc
        if exc_type is None and aborted:
            raise TransactionAborted()

    def _exit_joined(self, exc_type: Any) -> None:
        outer, name = self._outer, self._savepoint
        self._outer, self._savepoint, self.connection = None, None, None
        assert outer is not None and name is not None
        outer._depth -= 1
        if outer.poisoned or not outer._in_transaction():
            outer.poisoned = True  # the savepoint went with the transaction
            if exc_type is None:
                raise TransactionAborted()
            return
        if exc_type is not None:
            outer.connection.exec_driver_sql(f"rollback to {name}")
        outer.connection.exec_driver_sql(f"release {name}")

    def _release(self) -> None:
        try:
            if self._raw is not None and self._busy_ms is not None:
                self._raw.set_progress_handler(None, 0)
                self._raw.execute(f"pragma busy_timeout = {self._busy_ms}")
        finally:
            self._raw, self._busy_ms = None, None
            if self.connection is not None:
                self.connection.info.pop(_UOW_KEY, None)
                self.connection.close()
                self.connection = None


class SqliteUnitOfWorkFactory:
    """Takes the tenant scope from the current request context when a unit of work opens."""

    simulated = False

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def __call__(self, *, platform_scope: bool = False) -> SqliteUnitOfWork:
        from .. import context as ctxmod

        ctx = ctxmod.maybe_current()
        tenant = ctx.tenant.tenant if ctx else None
        platform = platform_scope or (ctx is not None and ctx.tenant.platform)
        return SqliteUnitOfWork(self.engine, tenant, platform)


# Relay, idempotency and audit readers ---------------------------------------------------------------------------

class SqliteOutboxReader:
    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def claim(self, limit: int) -> list[OutboxRow]:
        from sqlalchemy import text

        with _read(self._engine) as c:
            # One relay per database (docs/modules/messaging.md); competing relays need a lease, planned later.
            rows = c.execute(text("select id, envelope, attempts from outbox where sent_at is null "
                                  "order by occurred_at, id limit :n"), {"n": limit}).all()
        return [OutboxRow(r.id, Envelope.model_validate_json(r.envelope), r.attempts) for r in rows]

    def mark_sent(self, ids: list[str]) -> None:
        from sqlalchemy import bindparam, text

        if not ids:
            return
        with self._engine.begin() as c:
            c.execute(text("update outbox set sent_at = :at where id in :ids").bindparams(
                bindparam("ids", expanding=True)), {"ids": ids, "at": to_text(datetime.now(UTC))})

    def mark_failed(self, id: str, error: str) -> None:
        from sqlalchemy import text

        with self._engine.begin() as c:
            c.execute(text("update outbox set attempts = attempts + 1, last_error = :e where id = :id"),
                      {"id": id, "e": error[:2000]})


class SqliteIdempotencyStore:
    def __init__(self, engine: Any, retention: timedelta = timedelta(hours=24),
                 lease: timedelta = timedelta(minutes=5)) -> None:
        self._engine, self._retention, self._lease = engine, retention, lease

    def begin(self, tenant: str | None, key: str, request_hash: str) -> IdempotencyBegin:
        from sqlalchemy import text

        with self._engine.begin() as c:
            now = datetime.now(UTC)
            # Expired keys, and in-progress keys whose lease ran out (the process died), may start again.
            c.execute(text("delete from idempotency_key where tenant_id = :t and key = :k and (created_at < :cut "
                           "or (status = 'in_progress' and created_at < :lease))"),
                      {"t": tenant or "", "k": key, "cut": to_text(now - self._retention),
                       "lease": to_text(now - self._lease)})
            inserted = c.execute(text(
                "insert into idempotency_key (tenant_id, key, request_hash, status, created_at) "
                "values (:t, :k, :h, 'in_progress', :at) on conflict do nothing"),
                {"t": tenant or "", "k": key, "h": request_hash, "at": to_text(now)})
            if inserted.rowcount == 1:
                return IdempotencyBegin("started")
            row = c.execute(text("select request_hash, status, status_code, response from idempotency_key "
                                 "where tenant_id = :t and key = :k"), {"t": tenant or "", "k": key}).first()
        if row is None:
            return IdempotencyBegin("in_progress")
        if row.request_hash != request_hash:
            return IdempotencyBegin("reused")
        if row.status == "in_progress":
            return IdempotencyBegin("in_progress")
        return IdempotencyBegin("replay", row.status_code, _load(row.response))

    def complete(self, tenant: str | None, key: str, status_code: int, response: Any) -> None:
        from sqlalchemy import text

        with self._engine.begin() as c:
            c.execute(text("update idempotency_key set status = 'completed', status_code = :sc, response = :r "
                           "where tenant_id = :t and key = :k"),
                      {"sc": status_code, "r": _json(response), "t": tenant or "", "k": key})

    def abandon(self, tenant: str | None, key: str) -> None:
        from sqlalchemy import text

        with self._engine.begin() as c:
            c.execute(text("delete from idempotency_key where tenant_id = :t and key = :k"),
                      {"t": tenant or "", "k": key})


class SqliteAuditReader:
    """Reads a stream back for verification and audit queries."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def records(self, stream: str) -> list[AuditRecord]:
        from sqlalchemy import text

        with _read(self._engine) as c:
            rows = c.execute(text("select seq, entry, prev_hash, hash from audit_record where stream = :s "
                                  "order by seq"), {"s": stream}).all()
        out = []
        for r in rows:
            e = json.loads(r.entry)
            e["at"] = datetime.fromisoformat(e["at"])
            out.append(AuditRecord(r.seq, AuditEntry(**e), r.prev_hash, r.hash))
        return out
