"""Persistence ports. A unit of work commits a state change and its consequences together (F9)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from ..audit import AuditEntry, AuditRecord
from ..contracts import Envelope


class EventPublisher(Protocol):
    """Writes events to the outbox inside the current unit of work. There is no other way to publish (F9)."""

    def publish(self, events: list[Envelope]) -> None: ...


class TransactionalAudit(Protocol):
    def append(self, entry: AuditEntry) -> AuditRecord: ...


class Inbox(Protocol):
    def first_time(self, consumer: str, event_id: str) -> bool:
        """Record the event for this consumer. False means it was already processed (P19)."""
        ...


class DeadLetters(Protocol):
    def add(self, consumer: str, kind: Literal["invalid", "dead"], reason: str, envelope: Envelope) -> None: ...


class UnitOfWork(Protocol):
    events: EventPublisher
    audit: TransactionalAudit
    inbox: Inbox
    dead_letters: DeadLetters

    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None: ...


class UnitOfWorkFactory(Protocol):
    """Creates units of work. `platform_scope=True` is for kernel jobs (relay) that work across tenants."""

    simulated: bool

    def __call__(self, *, platform_scope: bool = False) -> UnitOfWork: ...


@dataclass(frozen=True)
class OutboxRow:
    id: str
    envelope: Envelope
    attempts: int


class OutboxReader(Protocol):
    """Used only by the relay."""

    def claim(self, limit: int) -> list[OutboxRow]: ...
    def mark_sent(self, ids: list[str]) -> None: ...
    def mark_failed(self, id: str, error: str) -> None: ...


@dataclass(frozen=True)
class IdempotencyBegin:
    outcome: Literal["started", "replay", "reused", "in_progress"]
    status_code: int | None = None
    response: Any = None


class IdempotencyStore(Protocol):
    """Each call runs in its own short transaction (see docs/modules/persistence.md)."""

    def begin(self, tenant: str | None, key: str, request_hash: str) -> IdempotencyBegin: ...
    def complete(self, tenant: str | None, key: str, status_code: int, response: Any) -> None: ...
    def abandon(self, tenant: str | None, key: str) -> None: ...
