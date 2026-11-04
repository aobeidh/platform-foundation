# ADR 0008: SQLite persistence provider

## Status

Accepted (milestone 0.4).

## Context

The persistence ports had two providers: memory, which is simulated and loses everything when the process stops, and
PostgreSQL, which needs a database server. The Integration Hub, a product on the foundation, needs a single-node
durable mode: one process that keeps its state on local disk, for a developer machine, an embedded deployment or a
small site, without running PostgreSQL. Building that in the hub would give the platform a second set of outbox,
inbox, audit, idempotency, governed-record and operation stores (F2), so it belongs in the foundation.

## Decision

- `platform_kernel.persistence.sqlite` provides `create_engine(url)`, `SqliteUnitOfWorkFactory`,
  `SqliteUnitOfWork`, `SqliteOutboxReader`, `SqliteIdempotencyStore` and `SqliteAuditReader`. `SqliteGovernedStore`
  and `SqliteOperationStore` are ports of the PostgreSQL stores. All of them pass the same contract suites.
- The engine needs a database file (`sqlite:///path`). Every connection uses WAL journal mode, enforces foreign keys
  and has a busy timeout (30 seconds by default). Python's sqlite3 module opens no transactions of its own; the engine
  begins each transaction explicitly, with `BEGIN IMMEDIATE` unless a connection asks for `DEFERRED`.
- A unit of work begins with `BEGIN IMMEDIATE`, so there is one writer at a time, like the memory provider. The audit
  chain needs no advisory lock as a result. A unit of work honors the request deadline (F10): it refuses to open
  after the deadline, waits for the write lock no longer than the remaining budget, and interrupts a statement that
  runs past the deadline, which raises `DeadlineExceeded`.
- One writer per file means a nested unit of work in one thread joins the outer transaction, as a savepoint. It
  shares the outer's connection. When it exits cleanly its savepoint is released, and its writes commit or roll back
  with the outer unit of work. When an exception leaves it, only its own writes are rolled back to the savepoint; the
  outer carries on and commits what it wrote before and after. (A consumer that handles a `CONFLICT` from
  `governance.create` therefore keeps its own writes and its inbox mark.) Without joining, a unit of work opened
  inside another one in the same thread, such as an approval policy that reads a setting while the governed-record
  engine holds a unit of work, would wait for itself until the deadline. A joined unit of work keeps its own tenant
  scope but runs under the outer's request deadline, which was set when the outer opened. Units of work on different
  engines stay independent.
- SQLite ends a transaction on its own after some errors: an interrupted write, a full disk, an I/O error, or out of
  memory. Because sqlite3 opens no transactions of its own, later statements would then run in autocommit mode and a
  clean exit would "commit" nothing. The unit of work is poisoned instead: further statements raise
  `TransactionAborted`, and so does a clean exit.
- Timestamps are stored as text, written by `to_text` in exactly `%Y-%m-%dT%H:%M:%S.%fZ` (UTC, fixed width), so
  text order is time order, and read by `from_text` as timezone-aware UTC. JSON is stored as text. Products store
  their own timestamps with the same two functions.
- SQLite has no row-level security and no schemas. The SQLite stores apply the tenant scope in code, with the rule
  of the PostgreSQL policy (`scope_clause` and `scope_params` let products do the same). On PostgreSQL, row-level
  security is a second line of defense (P22); SQLite does not have it, so a query that forgets the scope is not
  caught by the database.
- Maker-checker (P14) is enforced twice, as on PostgreSQL. `edited_by` is a JSON array. The store enforces the
  whole rule in code before every write. In the database, the check `maker_checker_second_person` refuses the creator
  or the submitter as approver, and two triggers on `governed_version` (before insert and before update) refuse an
  editor by testing membership with `json_each`, because a check constraint cannot hold a subquery. The provider
  needs SQLite's JSON functions and checks for them when it creates an engine.
- Writes that would touch another tenant's row are refused with `PermissionError`, including an upsert whose key
  exists in another tenant, where PostgreSQL's row-level security raises a violation.
- Migrations: each migration directory keeps SQLite versions of its files in a `sqlite/` subfolder, with the same
  file names. `migrate_sqlite(engine, product_dirs)` applies the kernel's, then each product's, in name order, once
  each, in one transaction, and records them in `schema_migration`. A directory without a `sqlite/` subfolder is an
  error that names it. `pk check migrations` reports a `sqlite/` subfolder whose file names differ from its
  directory's, and checks its files for destructive statements too.
- The builder uses SQLite when `PROVIDER_PERSISTENCE=sqlite`, or when no provider is named and `DATABASE_URL`
  names the `sqlite` backend (`sqlite:///x.db` or `sqlite+pysqlite:///x.db`). It decides by the URL's SQLAlchemy
  backend, and the PostgreSQL provider refuses any backend other than `postgresql`. `platform.migrate()` runs the SQLite runner, and `platform.uow` is the
  `SqliteUnitOfWorkFactory`, with an `engine` attribute as on PostgreSQL. SQLite is not a simulated provider, so it
  is allowed when `ENVIRONMENT=production`.

## Consequences

- A product can run durably on one node without a database server, and its tests can run against a real database
  without PostgreSQL.
- A product that supports SQLite writes every migration twice and keeps both in step; `pk check migrations` reports
  a missing or extra SQLite file. Its SQLite adapters must apply the tenant scope in code.
- Writes are serialized across the whole database, and a busy writer makes other writers wait. SQLite suits one
  process on one node; it is not a replacement for PostgreSQL under load or across several instances.
- `DATABASE_SCHEMA` does not apply: one database file holds one service.
