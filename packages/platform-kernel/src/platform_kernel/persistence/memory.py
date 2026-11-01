"""In-memory providers. Transactions are snapshot based: a unit of work copies state on enter and swaps it in
on commit, so a failed use case leaves nothing behind. One writer at a time (a lock), like a serializable store."""
from __future__ import annotations

import copy
import threading
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from ..audit import GENESIS, AuditEntry, AuditRecord, link
from ..contracts import Envelope
from .ports import IdempotencyBegin, OutboxRow


class MemoryDatabase:
    """Shared state for all in-memory providers of one platform instance."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.state: dict[str, Any] = {
            "outbox": {},           # id -> {"envelope", "sent_at", "attempts", "last_error"}
            "inbox": set(),         # (consumer, event_id)
            "dead_letter": [],
            "audit": {},            # stream -> list[AuditRecord]
            "idempotency": {},      # (tenant, key) -> dict
            "tables": {},           # product and engine tables: name -> dict
        }


class _Events:
    def __init__(self, state: dict[str, Any]) -> None:
        self._s = state

    def publish(self, events: list[Envelope]) -> None:
        for e in events:
            if e.id in self._s["outbox"]:
                raise ValueError(f"event {e.id} already published")
            self._s["outbox"][e.id] = {"envelope": e, "sent_at": None, "attempts": 0, "last_error": None}


class _Audit:
    def __init__(self, state: dict[str, Any]) -> None:
        self._s = state

    def append(self, entry: AuditEntry) -> AuditRecord:
        stream = self._s["audit"].setdefault(entry.stream, [])
        rec = link(len(stream) + 1, entry, stream[-1].hash if stream else GENESIS)
        stream.append(rec)
        return rec


class _Inbox:
    def __init__(self, state: dict[str, Any]) -> None:
        self._s = state

    def first_time(self, consumer: str, event_id: str) -> bool:
        key = (consumer, event_id)
        if key in self._s["inbox"]:
            return False
        self._s["inbox"].add(key)
        return True


class _DeadLetters:
    def __init__(self, state: dict[str, Any]) -> None:
        self._s = state

    def add(self, consumer: str, kind: Literal["invalid", "dead"], reason: str, envelope: Envelope) -> None:
        self._s["dead_letter"].append({"consumer": consumer, "kind": kind, "reason": reason, "envelope": envelope})


class MemoryUnitOfWork:
    def __init__(self, db: MemoryDatabase, platform_scope: bool = False) -> None:
        self._db = db
        self.platform_scope = platform_scope
        self._work: dict[str, Any] | None = None

    def __enter__(self) -> MemoryUnitOfWork:
        from .. import context as ctxmod

        ctxmod.check_deadline("opening a unit of work")
        self._db.lock.acquire()
        self._work = copy.deepcopy(self._db.state)
        self.events = _Events(self._work)
        self.audit = _Audit(self._work)
        self.inbox = _Inbox(self._work)
        self.dead_letters = _DeadLetters(self._work)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            if exc_type is None and self._work is not None:
                self._db.state = self._work
        finally:
            self._work = None
            self._db.lock.release()

    def table(self, name: str) -> dict[str, Any]:
        """Transactional dict for a product or engine table."""
        assert self._work is not None, "use the unit of work inside a with block"
        return self._work["tables"].setdefault(name, {})


class MemoryUnitOfWorkFactory:
    simulated = True

    def __init__(self, db: MemoryDatabase | None = None) -> None:
        self.db = db or MemoryDatabase()

    def __call__(self, *, platform_scope: bool = False) -> MemoryUnitOfWork:
        return MemoryUnitOfWork(self.db, platform_scope)

    def audit_records(self, stream: str) -> list[AuditRecord]:
        with self.db.lock:
            return list(self.db.state["audit"].get(stream, []))


class MemoryOutboxReader:
    def __init__(self, db: MemoryDatabase) -> None:
        self._db = db

    def claim(self, limit: int) -> list[OutboxRow]:
        with self._db.lock:
            rows = [(k, v) for k, v in self._db.state["outbox"].items() if v["sent_at"] is None]
            rows.sort(key=lambda kv: (kv[1]["envelope"].time, kv[0]))
            return [OutboxRow(k, v["envelope"], v["attempts"]) for k, v in rows[:limit]]

    def mark_sent(self, ids: list[str]) -> None:
        with self._db.lock:
            for i in ids:
                self._db.state["outbox"][i]["sent_at"] = datetime.now(UTC)

    def mark_failed(self, id: str, error: str) -> None:
        with self._db.lock:
            row = self._db.state["outbox"][id]
            row["attempts"] += 1
            row["last_error"] = error


class MemoryIdempotencyStore:
    def __init__(self, db: MemoryDatabase, retention: timedelta = timedelta(hours=24),
                 lease: timedelta = timedelta(minutes=5)) -> None:
        self._db, self._retention, self._lease = db, retention, lease

    def begin(self, tenant: str | None, key: str, request_hash: str) -> IdempotencyBegin:
        with self._db.lock:
            store = self._db.state["idempotency"]
            k = (tenant or "", key)
            row = store.get(k)
            age = datetime.now(UTC) - row["created_at"] if row else None
            if row and (age > self._retention or (row["status"] == "in_progress" and age > self._lease)):
                row = None
            if row is None:
                store[k] = {"hash": request_hash, "status": "in_progress", "code": None, "response": None,
                            "created_at": datetime.now(UTC)}
                return IdempotencyBegin("started")
            if row["hash"] != request_hash:
                return IdempotencyBegin("reused")
            if row["status"] == "in_progress":
                return IdempotencyBegin("in_progress")
            return IdempotencyBegin("replay", row["code"], row["response"])

    def complete(self, tenant: str | None, key: str, status_code: int, response: Any) -> None:
        with self._db.lock:
            row = self._db.state["idempotency"][(tenant or "", key)]
            row.update(status="completed", code=status_code, response=response)

    def abandon(self, tenant: str | None, key: str) -> None:
        with self._db.lock:
            self._db.state["idempotency"].pop((tenant or "", key), None)
