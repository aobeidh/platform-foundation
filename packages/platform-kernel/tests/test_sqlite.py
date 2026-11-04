"""The SQLite provider (ADR 0008): timestamps as text, the migration runner, the engine's settings, one writer at a
time, maker-checker and tenant scope in code, deadlines, and the builder. The shared contract suites run against
SQLite in test_persistence, test_messaging, test_governance, test_governance_approval and test_operations."""
from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import APIRouter
from platform_kernel import context as ctxmod
from platform_kernel.audit import verify_chain
from platform_kernel.config import PlatformSettings
from platform_kernel.context import Principal, RequestContext, TenantScope
from platform_kernel.governance import GovernanceEngine, SqliteGovernedStore
from platform_kernel.operations import Operation, SqliteOperationStore
from platform_kernel.persistence.migrations import migrate_sqlite, sqlite_statements
from platform_kernel.persistence.sqlite import (
    TIMESTAMP_FORMAT,
    SqliteAuditReader,
    SqliteUnitOfWorkFactory,
    create_engine,
    from_text,
    to_text,
)
from platform_kernel.platform import ConfigurationError, Platform, default_persistence
from platform_testing import audit_entry
from sqlalchemy import text

from .test_governance import KIND, as_user
from .test_review_regressions import app_with

# Timestamps as text ---------------------------------------------------------------------------------------------

SAMPLES = [
    datetime(1, 1, 1, tzinfo=UTC),
    datetime(999, 12, 31, 23, 59, 59, tzinfo=UTC),
    datetime(2026, 11, 4, 9, 5, 7, 0, tzinfo=UTC),
    datetime(2026, 11, 4, 9, 5, 7, 1, tzinfo=UTC),
    datetime(2026, 11, 4, 9, 5, 7, 999_999, tzinfo=UTC),
    datetime(9999, 12, 31, 23, 59, 59, 999_999, tzinfo=UTC),
]


def test_to_text_is_fixed_width_utc_in_the_documented_format():
    assert TIMESTAMP_FORMAT == "%Y-%m-%dT%H:%M:%S.%fZ"
    assert to_text(datetime(2026, 11, 4, 9, 5, 7, 42, tzinfo=UTC)) == "2026-11-04T09:05:07.000042Z"
    assert to_text(datetime(1, 1, 1, tzinfo=UTC)) == "0001-01-01T00:00:00.000000Z"
    assert {len(to_text(d)) for d in SAMPLES} == {27}
    riyadh = timezone(timedelta(hours=3))
    assert to_text(datetime(2026, 11, 4, 12, 0, tzinfo=riyadh)) == "2026-11-04T09:00:00.000000Z"


def test_from_text_round_trips_as_timezone_aware_utc():
    for d in SAMPLES:
        back = from_text(to_text(d))
        assert back == d and back.tzinfo is UTC
    assert from_text(to_text(datetime(2026, 1, 1, 3, tzinfo=timezone(timedelta(hours=3))))) == datetime(
        2026, 1, 1, tzinfo=UTC)


def test_text_order_is_time_order():
    riyadh = timezone(timedelta(hours=3))
    times = [*SAMPLES, datetime(2026, 11, 4, 12, 5, 7, tzinfo=riyadh), datetime(2026, 11, 4, 9, 5, 6, tzinfo=UTC)]
    assert sorted(times) == sorted(times, key=to_text)
    assert [to_text(t) for t in sorted(times)] == sorted(to_text(t) for t in times)


def test_naive_datetimes_and_other_formats_are_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        to_text(datetime(2026, 1, 1))
    for bad in ["2026-01-01T00:00:00Z", "2026-01-01 00:00:00.000000Z", "2026-01-01T00:00:00.000000+00:00", ""]:
        with pytest.raises(ValueError):
            from_text(bad)


# Migration runner -----------------------------------------------------------------------------------------------

def _product(tmp_path: Path, files: dict[str, str], name: str = "product") -> Path:
    d = tmp_path / name
    (d / "sqlite").mkdir(parents=True)
    (d / "0001_things.sql").write_text("-- the PostgreSQL version, ignored on SQLite\ncreate table x (y jsonb);\n")
    for file, sql in files.items():
        (d / "sqlite" / file).write_text(sql)
    return d


def test_migrations_apply_each_sqlite_file_once_in_name_order(tmp_path):
    product = _product(tmp_path, {
        "0002_more.sql": "alter table thing add column note text;",
        "0001_things.sql": "-- things; a comment with a semicolon\ncreate table thing (id text primary key);\n"
                           "create trigger thing_guard before delete on thing begin select raise(abort, 'no; never');"
                           " end;\n",
    })
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    try:
        applied = migrate_sqlite(engine, [product])
        assert applied == ["kernel/0001_kernel.sql", "kernel/0002_operations.sql", "kernel/0003_operation_recent.sql",
                           "kernel/0004_governance_approval.sql", "product/0001_things.sql", "product/0002_more.sql"]
        assert migrate_sqlite(engine, [product]) == []
        with engine.begin() as c:
            assert [r[0] for r in c.execute(text("select name from schema_migration order by name"))] == sorted(applied)
            c.execute(text("insert into thing (id, note) values ('a', 'b')"))
        (product / "sqlite" / "0003_later.sql").write_text("create index thing_note on thing (note);")
        assert migrate_sqlite(engine, [product]) == ["product/0003_later.sql"]
    finally:
        engine.dispose()


def test_a_directory_without_a_sqlite_folder_is_refused_by_name_and_nothing_is_applied(tmp_path):
    good = _product(tmp_path, {"0001_things.sql": "create table thing (id text);"})
    bad = tmp_path / "postgres_only"
    bad.mkdir()
    (bad / "0001.sql").write_text("create table y (id text);")
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    try:
        with pytest.raises(ValueError, match="postgres_only"):
            migrate_sqlite(engine, [good, bad])
        with engine.connect() as c:
            assert c.execute(text("select count(*) from sqlite_master where name = 'thing'")).scalar() == 0
    finally:
        engine.dispose()


def test_a_failing_migration_applies_nothing(tmp_path):
    product = _product(tmp_path, {"0001_things.sql": "create table thing (id text);\nthis is not sql;"})
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    try:
        with pytest.raises(Exception, match="syntax"):
            migrate_sqlite(engine, [product])
        with engine.connect() as c:
            assert c.execute(text("select count(*) from sqlite_master where type = 'table'")).scalar() == 0
    finally:
        engine.dispose()


def test_statement_splitter_keeps_strings_comments_and_triggers_whole():
    script = "create table a (x text default ';');\n-- only a comment; with a semicolon\n" \
             "create trigger t after insert on a begin insert into a values ('x;'); end;\n/* c; */"
    assert sqlite_statements(script) == [
        "create table a (x text default ';');",
        "-- only a comment; with a semicolon\n"
        "create trigger t after insert on a begin insert into a values ('x;'); end;",
        "/* c; */"]
    assert sqlite_statements("create table a (x text);\ncreate table b (y text)") == [
        "create table a (x text);", "create table b (y text)"]


# Engine ---------------------------------------------------------------------------------------------------------

def test_engine_uses_wal_foreign_keys_a_busy_timeout_and_explicit_transactions(sqlite_engine):
    with sqlite_engine.connect() as c:
        raw = c.connection.dbapi_connection
        assert raw.isolation_level is None  # sqlite3 opens no transactions of its own
        assert raw.execute("pragma journal_mode").fetchone()[0] == "wal"
        assert raw.execute("pragma foreign_keys").fetchone()[0] == 1
        assert raw.execute("pragma busy_timeout").fetchone()[0] == 30_000
        assert not raw.in_transaction
    with SqliteUnitOfWorkFactory(sqlite_engine)() as u:
        assert u.connection.connection.dbapi_connection.in_transaction


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:", "postgresql://u@h/db"])
def test_engine_needs_a_database_file(url):
    with pytest.raises(ValueError):
        create_engine(url)


# One writer at a time -------------------------------------------------------------------------------------------

def test_a_second_writer_waits_for_the_first_to_commit(sqlite_engine):
    factory = SqliteUnitOfWorkFactory(sqlite_engine)
    order: list[str] = []
    first_in = threading.Event()

    def first() -> None:
        with factory(platform_scope=True) as u:
            u.audit.append(audit_entry(subject="first"))
            first_in.set()
            time.sleep(0.3)
            order.append("first commits")

    def second() -> None:
        first_in.wait(5)
        with factory(platform_scope=True) as u:
            order.append("second begins")
            u.audit.append(audit_entry(subject="second"))

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert order == ["first commits", "second begins"]
    records = SqliteAuditReader(sqlite_engine).records("things")
    assert [r.entry.subject for r in records] == ["first", "second"] and verify_chain(records) == (True, None)


def test_concurrent_writers_never_lose_or_fork_the_audit_chain(sqlite_engine):
    factory = SqliteUnitOfWorkFactory(sqlite_engine)
    errors: list[BaseException] = []

    def work(n: int) -> None:
        try:
            for i in range(10):
                with factory(platform_scope=True) as u:
                    u.audit.append(audit_entry(subject=f"{n}-{i}"))
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert errors == []
    records = SqliteAuditReader(sqlite_engine).records("things")
    assert [r.seq for r in records] == list(range(1, 41)) and verify_chain(records) == (True, None)


def test_a_failed_unit_of_work_releases_the_write_lock(sqlite_engine):
    factory = SqliteUnitOfWorkFactory(sqlite_engine)
    with pytest.raises(RuntimeError), factory(platform_scope=True):
        raise RuntimeError("boom")
    done = threading.Event()

    def other() -> None:
        with factory(platform_scope=True) as u:
            u.audit.append(audit_entry())
        done.set()

    threading.Thread(target=other).start()
    assert done.wait(5)


def test_a_nested_unit_of_work_keeps_its_own_scope_and_other_engines_stay_independent(sqlite_engine, tmp_path):
    from platform_testing import fresh_sqlite

    factory = SqliteUnitOfWorkFactory(sqlite_engine)
    with factory(platform_scope=True) as outer:
        with as_user("ada", "t1"), factory() as inner:
            assert inner.connection is outer.connection
            assert (inner.tenant, inner.platform_scope) == ("t1", False)
        assert (outer.tenant, outer.platform_scope) == (None, True)
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        for other in fresh_sqlite(other_dir):
            with SqliteUnitOfWorkFactory(other)(platform_scope=True) as separate:
                assert separate.connection is not outer.connection
                separate.audit.append(audit_entry())
            assert len(SqliteAuditReader(other).records("things")) == 1
    with factory(platform_scope=True) as again:  # the outer ended: a new transaction, not a joined one
        assert again.connection is not outer.connection and again.connection is not None


def test_an_approval_policy_that_reads_through_a_unit_of_work_does_not_deadlock(sqlite_engine):
    from platform_kernel.governance import ApprovalRule

    factory = SqliteUnitOfWorkFactory(sqlite_engine)

    class SettingsPolicy:
        def rule_for(self, kind: str) -> ApprovalRule:
            with factory() as u:  # the engine calls this inside its own unit of work
                u.connection.execute(text("select count(*) from governed_record")).scalar()
            return ApprovalRule("single", False)

    e = GovernanceEngine(uow=factory, store=SqliteGovernedStore(), source="svc", policy=SettingsPolicy())
    e.register(KIND)
    started = time.monotonic()
    with as_user("ada"):
        v = e.create("rate", {"name": "vm", "amount": 1}).value
        v = e.submit("rate", v.record.id, v.record.revision).value
        assert e.approve("rate", v.record.id, v.record.revision).value.record.status == "active"
    assert time.monotonic() - started < 5


def test_a_consumer_that_handles_a_conflict_keeps_its_work_and_its_inbox_mark(sqlite_engine):
    from platform_kernel.messaging import ConsumerRuntime
    from platform_testing import sample_event

    factory = SqliteUnitOfWorkFactory(sqlite_engine)
    governance = GovernanceEngine(uow=factory, store=SqliteGovernedStore(), source="svc")
    governance.register(KIND)
    with as_user("alice", "t1"):
        assert governance.create("rate", {"name": "vm", "amount": 1}, id="fixed").ok
    calls: list[str] = []

    def handler(env, uow) -> None:
        calls.append(env.id)
        uow.audit.append(audit_entry(subject="handled"))
        assert governance.create("rate", {"name": "vm", "amount": 1}, id="fixed").error.code == "CONFLICT"

    rt = ConsumerRuntime(factory)
    rt.subscribe("test.thing.created.v1", "c1", handler)
    e = sample_event(tenant="t1")
    assert rt.deliver(e) is True
    assert rt.deliver(e) is True and calls == [e.id]  # the inbox mark committed: no second run
    assert [r.entry.subject for r in SqliteAuditReader(sqlite_engine).records("things")] == ["handled"]


def test_after_sqlite_rolls_back_on_its_own_no_statement_runs_and_the_exit_raises(sqlite_engine):
    from platform_kernel.persistence.sqlite import TransactionAborted
    from sqlalchemy.exc import OperationalError

    factory = SqliteUnitOfWorkFactory(sqlite_engine)
    p = Principal("a", tenant="t1")
    ctx = RequestContext(principal=p, tenant=TenantScope.resolve(p), correlation_id="c",
                         deadline=datetime.now(UTC) + timedelta(milliseconds=200))
    slow_write = ("insert into inbox (consumer, event_id, processed_at) with recursive c(x) as (select 1 union all "
                  "select x + 1 from c where x < 500000000) select 'slow', x, 'x' from c")
    with ctxmod.use(ctx), pytest.raises(TransactionAborted), factory() as u:
        u.inbox.first_time("c1", "before")
        with pytest.raises(OperationalError):
            u.connection.execute(text(slow_write))  # interrupted: SQLite rolls the whole transaction back
        with pytest.raises(TransactionAborted):
            u.connection.execute(text("insert into inbox values ('c1', 'after', 'x')"))
    with factory(platform_scope=True) as u:
        assert u.connection.execute(text("select count(*) from inbox")).scalar() == 0


# Deadlines (F10) ------------------------------------------------------------------------------------------------

SLOW = "with recursive c(x) as (select 1 union all select x + 1 from c where x < 500000000) select count(*) from c"


def test_statements_stop_at_the_request_deadline(sqlite_engine):
    factory = SqliteUnitOfWorkFactory(sqlite_engine)
    r = APIRouter()

    @r.get("/slow")
    def slow() -> dict:
        with factory() as u:
            u.connection.execute(text(SLOW))
        return {"ok": True}

    client = app_with(r, timeout=0.5)
    started = time.monotonic()
    res = client.get("/slow", headers={"Authorization": "Bearer demo:a:r"})
    assert res.status_code == 504 and time.monotonic() - started < 1.5


def test_an_interrupted_statement_raises_deadline_exceeded_and_the_connection_is_reset(sqlite_engine):
    factory = SqliteUnitOfWorkFactory(sqlite_engine)
    p = Principal("a", tenant="t1")
    ctx = RequestContext(principal=p, tenant=TenantScope.resolve(p), correlation_id="c",
                         deadline=datetime.now(UTC) + timedelta(milliseconds=200))
    with ctxmod.use(ctx), pytest.raises(ctxmod.DeadlineExceeded), factory() as u:
        u.connection.execute(text(SLOW))
    with factory() as u:  # outside the request: no progress handler, the full busy timeout again
        raw = u.connection.connection.dbapi_connection
        assert raw.execute("pragma busy_timeout").fetchone()[0] == 30_000
        assert u.connection.execute(text("select 1")).scalar() == 1


def test_a_lock_wait_cut_short_by_the_deadline_is_deadline_exceeded_without_a_clock_check(sqlite_engine, monkeypatch):
    factory = SqliteUnitOfWorkFactory(sqlite_engine)
    holding, release = threading.Event(), threading.Event()

    def hold() -> None:
        with factory(platform_scope=True):
            holding.set()
            release.wait(10)

    t = threading.Thread(target=hold)
    t.start()
    try:
        assert holding.wait(5)
        p = Principal("a", tenant="t1")
        ctx = RequestContext(principal=p, tenant=TenantScope.resolve(p), correlation_id="c",
                             deadline=datetime.now(UTC) + timedelta(milliseconds=200))
        # The busy timeout is rounded down to whole milliseconds, so the wait may end just before the deadline.
        monkeypatch.setattr(ctxmod, "deadline_exceeded", lambda now=None: False)
        with ctxmod.use(ctx), pytest.raises(ctxmod.DeadlineExceeded), factory():
            pass
    finally:
        release.set()
        t.join(10)


def test_waiting_for_the_write_lock_stops_at_the_deadline(sqlite_engine):
    factory = SqliteUnitOfWorkFactory(sqlite_engine)
    holding, release = threading.Event(), threading.Event()

    def hold() -> None:
        with factory(platform_scope=True):
            holding.set()
            release.wait(10)

    t = threading.Thread(target=hold)
    t.start()
    try:
        assert holding.wait(5)
        p = Principal("a", tenant="t1")
        ctx = RequestContext(principal=p, tenant=TenantScope.resolve(p), correlation_id="c",
                             deadline=datetime.now(UTC) + timedelta(milliseconds=300))
        started = time.monotonic()
        with ctxmod.use(ctx), pytest.raises(ctxmod.DeadlineExceeded), factory():
            pass
        assert time.monotonic() - started < 2
    finally:
        release.set()
        t.join(10)


# Maker-checker, tenant scope and the id oracle -------------------------------------------------------------------

@pytest.fixture
def governance(sqlite_engine):
    e = GovernanceEngine(uow=SqliteUnitOfWorkFactory(sqlite_engine), store=SqliteGovernedStore(), source="svc")
    e.register(KIND)
    return e


def test_maker_checker_refuses_an_editor_as_approver_in_the_engine_and_in_the_store(governance, sqlite_engine):
    with as_user("maker"):
        v = governance.create("rate", {"name": "vm", "amount": 1}).value
    with as_user("editor"):
        v = governance.update_draft("rate", v.record.id, {"name": "vm", "amount": 2}, v.record.revision).value
        v = governance.test("rate", v.record.id, v.record.revision).value
    with as_user("maker"):
        v = governance.submit("rate", v.record.id, v.record.revision).value
    with as_user("editor"):
        assert governance.approve("rate", v.record.id, v.record.revision).error.code == "MAKER_CHECKER"
    store = SqliteGovernedStore()
    current = v.current
    assert "editor" in current.edited_by
    with as_user("editor"), SqliteUnitOfWorkFactory(sqlite_engine)() as u, pytest.raises(PermissionError):
        store.save_version(u, current.with_(approved_by="editor"))
    with as_user("checker"):
        assert governance.approve("rate", v.record.id, v.record.revision).value.record.status == "active"


def test_the_database_refuses_an_editor_as_approver(governance, sqlite_engine):
    from sqlalchemy.exc import IntegrityError

    with as_user("alice"):
        rid = governance.create("rate", {"name": "vm", "amount": 1}).value.record.id
    with pytest.raises(IntegrityError, match="maker_checker"), sqlite_engine.begin() as c:
        c.execute(text("update governed_version set edited_by = '[\"bob\", \"mallory\"]', submitted_by = 'alice', "
                       "approved_by = 'mallory' where id = :i"), {"i": rid})
    with pytest.raises(IntegrityError, match="maker_checker"), sqlite_engine.begin() as c:
        c.execute(text("insert into governed_version (kind, id, version, tenant_id, status, spec, maker_checker, "
                       "created_by, approved_by, edited_by, created_at) values ('rate', :i, 9, 't1', 'active', '{}', "
                       "1, 'alice', 'mallory', '[\"mallory\"]', 'x')"), {"i": rid})
    with sqlite_engine.begin() as c:  # without maker-checker, an editor may approve
        c.execute(text("update governed_version set maker_checker = 0, edited_by = '[\"mallory\"]', "
                       "approved_by = 'mallory' where id = :i"), {"i": rid})


def test_upserts_never_touch_another_tenants_row(governance, sqlite_engine):
    with as_user("alice", "t1"):
        v = governance.create("rate", {"name": "vm", "amount": 1}, id="shared").value
    store, factory = SqliteGovernedStore(), SqliteUnitOfWorkFactory(sqlite_engine)
    with as_user("bob", "t2"), factory() as u, pytest.raises(PermissionError):
        store.save_version(u, v.current.with_(tenant="t2", spec={"name": "stolen", "amount": 9}))
    ops, now = SqliteOperationStore(), datetime.now(UTC)
    with as_user("alice", "t1"), factory() as u:
        ops.save(u, Operation(id="op", kind="k", tenant="t1", status="pending", input={}, created_by="alice",
                              created_at=now, updated_at=now))
    with as_user("bob", "t2"), factory() as u, pytest.raises(PermissionError):
        ops.save(u, Operation(id="op", kind="k", tenant="t2", status="failed", input={}, created_by="bob",
                              created_at=now, updated_at=now))
    with as_user("alice", "t1"), factory() as u:
        assert store.version(u, "rate", "shared", 1).spec == {"name": "vm", "amount": 1}
        assert ops.get(u, "op").status == "pending"


def test_the_database_check_refuses_the_creator_or_submitter_as_approver(governance, sqlite_engine):
    from sqlalchemy.exc import IntegrityError

    with as_user("alice"):
        rid = governance.create("rate", {"name": "vm", "amount": 1}).value.record.id
    for column in ("created_by", "submitted_by"):
        with pytest.raises(IntegrityError), sqlite_engine.begin() as c:
            c.execute(text(f"update governed_version set submitted_by = 'bob', {column} = 'mallory', "
                           "approved_by = 'mallory' where id = :i"), {"i": rid})


def test_a_duplicate_id_in_another_tenant_gets_the_same_conflict(governance):
    with as_user("alice", "t1"):
        assert governance.create("rate", {"name": "vm", "amount": 1}, id="fixed").ok
    with as_user("bob", "t2"):
        assert governance.create("rate", {"name": "vm", "amount": 1}, id="fixed").error.code == "CONFLICT"
        assert governance.get("rate", "fixed").error.code == "NOT_FOUND"
    with as_user("alice", "t1"):
        assert governance.create("rate", {"name": "vm", "amount": 1}, id="fixed").error.code == "CONFLICT"


def test_operations_are_scoped_to_the_tenant_in_code(sqlite_engine):
    factory, store = SqliteUnitOfWorkFactory(sqlite_engine), SqliteOperationStore()
    now = datetime.now(UTC)

    def op(id: str, tenant: str) -> Operation:
        return Operation(id=id, kind="k", tenant=tenant, status="pending", input={"n": 1}, created_by="ada",
                         created_at=now, updated_at=now, created_roles=frozenset({"r"}))

    with as_user("ada", "t1"), factory() as u:
        store.save(u, op("a", "t1"))
        with pytest.raises(PermissionError):
            store.save(u, op("b", "t2"))
    with as_user("ada", "t2"), factory() as u:
        store.save(u, op("b", "t2"))
        assert store.get(u, "a") is None and [o.id for o in store.recent(u, 10, None)] == ["b"]
        assert [o.id for o in store.unfinished(u)] == ["b"]
    with factory(platform_scope=True) as u:
        got = store.get(u, "a")
        assert sorted(o.id for o in store.unfinished(u)) == ["a", "b"]
    assert (got.tenant, got.input, got.created_roles, got.created_at) == ("t1", {"n": 1}, frozenset({"r"}), now)


# Builder --------------------------------------------------------------------------------------------------------

def test_default_persistence_follows_the_database_url():
    assert default_persistence(None) == "memory"
    assert default_persistence("postgresql://u@h/db") == "postgres"
    assert default_persistence("postgresql+psycopg://u@h/db") == "postgres"
    assert default_persistence("sqlite:///x.db") == "sqlite"
    assert default_persistence("sqlite+pysqlite:///x.db") == "sqlite"


def test_builder_takes_a_driver_qualified_sqlite_url_and_refuses_other_backends_for_postgres(tmp_path):
    p = Platform.builder("svc", PlatformSettings.from_env("svc", {
        "DATABASE_URL": f"sqlite+pysqlite:///{tmp_path / 'svc.db'}", "ALLOW_DEMO": "1"})).build()
    try:
        assert isinstance(p.uow, SqliteUnitOfWorkFactory)
    finally:
        p.close()
    for url in ("mysql://u@h/db", "sqlite+pysqlite:///x.db"):
        with pytest.raises(ConfigurationError, match="PostgreSQL DATABASE_URL"):
            Platform.builder("svc", PlatformSettings.from_env("svc", {
                "PROVIDER_PERSISTENCE": "postgres", "DATABASE_URL": url, "ALLOW_DEMO": "1"})).build()


@pytest.mark.parametrize("env", [{"PROVIDER_PERSISTENCE": "sqlite"}, {}])
def test_builder_chooses_sqlite_and_migrates(tmp_path, env):
    settings = PlatformSettings.from_env("svc", {"DATABASE_URL": f"sqlite:///{tmp_path / 'svc.db'}",
                                                 "ALLOW_DEMO": "true", **env})
    p = Platform.builder("svc", settings).build()
    try:
        assert isinstance(p.uow, SqliteUnitOfWorkFactory) and hasattr(p.uow, "engine")
        assert p.uow.simulated is False and "persistence" not in p.simulated
        assert p.migrate()[0] == "kernel/0001_kernel.sql" and p.migrate() == []
        assert p._database_ready()
        p.operations.register("double", lambda i, h: {"n": i["n"] * 2})
        with as_user("ada"):
            started = p.operations.start("double", {"n": 2}).value
            p.operations.wait(started.id)
            assert p.operations.get(started.id).value.result == {"n": 4}
    finally:
        p.close()


def test_builder_refuses_mismatched_urls():
    with pytest.raises(ConfigurationError, match="sqlite:///path"):
        Platform.builder("svc", PlatformSettings.from_env("svc", {
            "PROVIDER_PERSISTENCE": "sqlite", "DATABASE_URL": "postgresql://u@h/db", "ALLOW_DEMO": "1"})).build()
    with pytest.raises(ConfigurationError, match="PostgreSQL DATABASE_URL"):
        Platform.builder("svc", PlatformSettings.from_env("svc", {
            "PROVIDER_PERSISTENCE": "postgres", "DATABASE_URL": "sqlite:///x.db", "ALLOW_DEMO": "1"})).build()
    with pytest.raises(ConfigurationError, match="database file"):
        Platform.builder("svc", PlatformSettings.from_env("svc", {
            "DATABASE_URL": "sqlite:///:memory:", "ALLOW_DEMO": "1"})).build()
