"""Layer 3. Units of work, outbox, inbox, idempotency and audit storage, with memory and PostgreSQL providers.

The PostgreSQL providers live in `platform_kernel.persistence.postgres` and import SQLAlchemy lazily (F5)."""
from .memory import (
    MemoryDatabase,
    MemoryIdempotencyStore,
    MemoryOutboxReader,
    MemoryUnitOfWork,
    MemoryUnitOfWorkFactory,
)
from .ports import (
    DeadLetters,
    EventPublisher,
    IdempotencyBegin,
    IdempotencyStore,
    Inbox,
    OutboxReader,
    OutboxRow,
    TransactionalAudit,
    UnitOfWork,
    UnitOfWorkFactory,
)

__all__ = [
    "DeadLetters", "EventPublisher", "IdempotencyBegin", "IdempotencyStore", "Inbox", "MemoryDatabase",
    "MemoryIdempotencyStore", "MemoryOutboxReader", "MemoryUnitOfWork", "MemoryUnitOfWorkFactory", "OutboxReader",
    "OutboxRow", "TransactionalAudit", "UnitOfWork", "UnitOfWorkFactory",
]
