# persistence

**Purpose:** Units of work that commit a state change with its outbox events, audit records and inbox marks (F9); the migration runner; the idempotency store.

**Use it when:** Any use case that changes state.

**Do not use it when:** You need to publish an event outside a transaction; there is deliberately no API for that.

**Ports and API:** `UnitOfWorkFactory`, `UnitOfWork` (events, audit, inbox, dead_letters), `OutboxReader`, `IdempotencyStore`.

**Providers:** Memory (simulated, snapshot transactions) and PostgreSQL (`[postgres]` extra; one schema per service; `app.scope` and `app.tenant` set per transaction for row-level security). Opening a unit of work after the request deadline raises `DeadlineExceeded`; PostgreSQL units of work set `statement_timeout` to the remaining budget. The idempotency store runs each call in its own short transaction; completion is recorded after the response, and an in-progress key left by a crashed process can start again after its lease (default 5 minutes).

**Example:**

```python
with platform.uow() as uow:
    repo.save(uow, thing)
    uow.events.publish([make_event("svc.thing.created.v1", {...}, source="svc")])
```

**Failure modes:** Run one relay per schema in 0.1. Destructive migrations fail `pk check migrations` unless marked with a reason.

**Telemetry:** None yet.
