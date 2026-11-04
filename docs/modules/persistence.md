# persistence

**Purpose:** Units of work that commit a state change with its outbox events, audit records and inbox marks (F9); the migration runner; the idempotency store.

**Use it when:** Any use case that changes state.

**Do not use it when:** You need to publish an event outside a transaction; there is deliberately no API for that.

**Ports and API:** `UnitOfWorkFactory`, `UnitOfWork` (events, audit, inbox, dead_letters), `OutboxReader`, `IdempotencyStore`. Migration runners `migrations.migrate` (PostgreSQL) and `migrations.migrate_sqlite` (SQLite). For SQLite, `sqlite.to_text` and `sqlite.from_text` store timestamps as text, and `sqlite.scope_clause` and `sqlite.scope_params` apply the tenant scope in a query.

**Providers:** Memory (simulated, snapshot transactions), PostgreSQL (`[postgres]` extra; one schema per service; `app.scope` and `app.tenant` set per transaction for row-level security) and SQLite (ADR 0008; one database file per service, no extra needed).

SQLite: `create_engine("sqlite:///path/to/file.db")` uses WAL journal mode, foreign keys and a 30-second busy timeout, and begins every transaction explicitly. A unit of work begins with `BEGIN IMMEDIATE`, so there is one writer at a time. A unit of work opened in a thread that already holds one on the same engine joins it as a savepoint: it shares the connection and the outer's request deadline, and its writes commit or roll back with the outer unit of work. An exception that leaves it rolls back its own writes only; the outer carries on. If SQLite ends the transaction on its own (an interrupted write, a full disk, an I/O error), further statements and a clean exit raise `TransactionAborted`. Timestamps are UTC text in exactly `%Y-%m-%dT%H:%M:%S.%fZ`, so text order is time order; JSON is text. SQLite has no row-level security, so the SQLite stores apply the tenant scope in code, as the memory provider does. On PostgreSQL, row-level security is a second line of defense; SQLite does not have it, so a product's SQLite adapters must apply the scope in every query. SQLite suits one process on one node. Opening a unit of work after the request deadline raises `DeadlineExceeded`; PostgreSQL units of work set `statement_timeout` to the remaining budget. The idempotency store runs each call in its own short transaction; completion is recorded after the response, and an in-progress key left by a crashed process can start again after its lease (default 5 minutes).

**Example:**

```python
with platform.uow() as uow:
    repo.save(uow, thing)
    uow.events.publish([make_event("svc.thing.created.v1", {...}, source="svc")])
```

**Migrations:** Each migration directory holds the PostgreSQL files; a `sqlite/` subfolder holds the SQLite version of each, with the same file name. `platform.migrate()` applies the kernel's files and then each product's, in name order, once each, recording them in `schema_migration`. On SQLite a directory without a `sqlite/` subfolder is an error that names it.

**Failure modes:** Run one relay per schema (or SQLite file) in 0.1. Destructive migrations fail `pk check migrations` unless marked with a reason, and so does a `sqlite/` subfolder whose file names differ from its directory's. On SQLite, a writer that holds the lock makes other writers wait up to the busy timeout or the request deadline, whichever comes first.

**Telemetry:** None yet.
