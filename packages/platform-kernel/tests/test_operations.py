from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from platform_kernel import context as ctxmod
from platform_kernel.config import PlatformSettings
from platform_kernel.context import Principal, RequestContext, TenantScope
from platform_kernel.operations import (
    MemoryOperationStore,
    OperationFailed,
    OperationRunner,
    PostgresOperationStore,
    Saga,
    SagaStep,
    SqliteOperationStore,
    accepted,
)
from platform_kernel.persistence import MemoryOutboxReader, MemoryUnitOfWorkFactory
from platform_kernel.platform import Platform
from platform_testing import requires_postgres


def as_user(subject: str, tenant: str | None = "t1"):
    p = Principal(subject, tenant=tenant)
    return ctxmod.use(RequestContext(principal=p, tenant=TenantScope.resolve(p), correlation_id="corr-1",
                                     deadline=datetime.now(UTC) + timedelta(seconds=30)))


class _Operations:
    def test_runs_in_background_with_callers_identity_and_records_result(self, runner, events):
        seen = {}

        def handler(input, handle):
            ctx = ctxmod.current()
            seen.update(sub=ctx.principal.subject, tenant=ctx.tenant.tenant, corr=ctx.correlation_id)
            handle.progress(50)
            return {"doubled": input["n"] * 2}

        runner.register("double", handler)
        with as_user("ada"):
            op = runner.start("double", {"n": 21}).value
            assert op.status == "pending"
        runner.wait(op.id)
        with as_user("ada"):
            done = runner.get(op.id).value
        assert (done.status, done.result, done.progress) == ("succeeded", {"doubled": 42}, 100)
        assert seen == {"sub": "ada", "tenant": "t1", "corr": "corr-1"}
        assert [e.split(".")[-2] for e in events()] == ["accepted", "succeeded"]

    def test_failure_is_recorded_with_its_code(self, runner):
        def handler(input, handle):
            raise OperationFailed("PARTNER_REJECTED", "The partner refused the file.")

        runner.register("send", handler)
        with as_user("ada"):
            op = runner.start("send", {}).value
        runner.wait(op.id)
        with as_user("ada"):
            error = runner.get(op.id).value.error
            assert error == {"code": "PARTNER_REJECTED", "detail": "The partner refused the file."}

    def test_cancel_stops_cooperative_work(self, runner):
        started, release = threading.Event(), threading.Event()

        def handler(input, handle):
            started.set()
            release.wait(5)
            handle.check_cancelled()
            return {"never": True}

        runner.register("slow", handler)
        with as_user("ada"):
            op = runner.start("slow", {}).value
        started.wait(5)
        with as_user("bob"):
            assert runner.cancel(op.id).error.code == "NOT_FOUND"  # others in the tenant cannot even see it
        with as_user("ada"):
            assert runner.cancel(op.id).ok
        release.set()
        runner.wait(op.id)
        with as_user("ada"):
            assert runner.get(op.id).value.status == "cancelled"
            assert runner.cancel(op.id).error.code == "INVALID_TRANSITION"

    def test_other_tenants_cannot_see_an_operation(self, runner):
        runner.register("noop", lambda i, h: {})
        with as_user("ada", "t1"):
            op = runner.start("noop", {}).value
        runner.wait(op.id)
        with as_user("oli", "t2"):
            assert runner.get(op.id).error.code == "NOT_FOUND"

    def test_saga_compensates_in_reverse_order(self, runner):
        log: list[str] = []

        def step(name, fail=False):
            def action(data):
                log.append(f"do {name}")
                if fail:
                    raise OperationFailed("STEP_FAILED", f"{name} broke")
                return {name: True}
            return SagaStep(name, action, lambda data: log.append(f"undo {name}"))

        runner.register_saga(Saga("onboard", (step("reserve"), step("charge"), step("ship", fail=True))))
        with as_user("ada"):
            op = runner.start("onboard", {}).value
        runner.wait(op.id)
        with as_user("ada"):
            done = runner.get(op.id).value
        assert log == ["do reserve", "do charge", "do ship", "undo charge", "undo reserve"]
        assert done.status == "failed" and done.error["code"] == "STEP_FAILED"
        assert "Compensated: charge, reserve" in done.error["detail"]

    def test_saga_resumes_after_restart_without_repeating_done_steps(self, runner_factory):
        log: list[str] = []
        def recorder(name):
            def action(data):
                log.append(name)
                return {name: 1}
            return action

        steps = tuple(SagaStep(n, recorder(n)) for n in ("a", "b", "c"))
        first = runner_factory()
        first.register_saga(Saga("pipeline", steps))
        with as_user("ada"):
            op = first.start("pipeline", {}).value
        first.wait(op.id)
        # Simulate a crash after step "a": put the operation back to running with only "a" done.
        with as_user("ada"):
            first._update(op.id, lambda o: o.with_(status="running", result=None, state={
                "phase": "forward", "done": ["a"], "compensated": [], "data": {"a": 1}}))
        log.clear()
        second = runner_factory()
        second.register_saga(Saga("pipeline", steps))
        assert second.resume_unfinished() == 1
        second.wait(op.id)
        with as_user("ada"):
            done = second.get(op.id).value
        assert log == ["b", "c"] and done.status == "succeeded" and done.result["steps"] == ["a", "b", "c"]


class TestMemoryOperations(_Operations):
    @pytest.fixture
    def uow(self):
        return MemoryUnitOfWorkFactory()

    @pytest.fixture
    def runner_factory(self, uow):
        made = []

        def make():
            r = OperationRunner(uow=uow, store=MemoryOperationStore(), source="svc")
            made.append(r)
            return r
        yield make
        for r in made:
            r.close()

    @pytest.fixture
    def runner(self, runner_factory):
        return runner_factory()

    @pytest.fixture
    def events(self, uow):
        return lambda: [r.envelope.type for r in MemoryOutboxReader(uow.db).claim(100)]


class TestSqliteOperations(_Operations):
    @pytest.fixture
    def uow(self, sqlite_engine):
        from platform_kernel.persistence.sqlite import SqliteUnitOfWorkFactory

        return SqliteUnitOfWorkFactory(sqlite_engine)

    @pytest.fixture
    def runner_factory(self, uow):
        made = []

        def make():
            r = OperationRunner(uow=uow, store=SqliteOperationStore(), source="svc")
            made.append(r)
            return r
        yield make
        for r in made:
            r.close()

    @pytest.fixture
    def runner(self, runner_factory):
        return runner_factory()

    @pytest.fixture
    def events(self, sqlite_engine):
        from platform_kernel.persistence.sqlite import SqliteOutboxReader

        return lambda: [r.envelope.type for r in SqliteOutboxReader(sqlite_engine).claim(100)]


@requires_postgres
class TestPostgresOperations(_Operations):
    @pytest.fixture
    def uow(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresUnitOfWorkFactory

        return PostgresUnitOfWorkFactory(pg_engine, pg_schema)

    @pytest.fixture
    def runner_factory(self, uow):
        made = []

        def make():
            r = OperationRunner(uow=uow, store=PostgresOperationStore(), source="svc")
            made.append(r)
            return r
        yield make
        for r in made:
            r.close()

    @pytest.fixture
    def runner(self, runner_factory):
        return runner_factory()

    @pytest.fixture
    def events(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresOutboxReader

        return lambda: [r.envelope.type for r in PostgresOutboxReader(pg_engine, pg_schema).claim(100)]


def test_http_answers_202_with_a_location_that_reports_status():
    p = Platform.builder("svc", PlatformSettings(service="svc", allow_demo=True)).build()
    p.operations.register("report", lambda i, h: {"rows": i["rows"]})
    r = APIRouter()

    @r.post("/api/v1/reports")
    def start(body: dict):
        return accepted(p.operations.start("report", body))

    client = TestClient(p.create_app([r]))
    h = {"Authorization": "Bearer demo:ada:r:t1"}
    res = client.post("/api/v1/reports", json={"rows": 3}, headers=h)
    assert res.status_code == 202 and res.headers["location"].startswith("/api/v1/operations/")
    p.operations.wait(res.json()["id"])
    status = client.get(res.headers["location"], headers=h).json()
    assert status["status"] == "succeeded" and status["result"] == {"rows": 3}
    p.close()
