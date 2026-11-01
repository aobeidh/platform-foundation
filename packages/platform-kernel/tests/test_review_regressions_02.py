"""One regression test per finding of the milestone 0.2 review. Scaffold findings (#9, #10) are in tests/."""
from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from platform_kernel import context as ctxmod
from platform_kernel.context import Principal, RequestContext, TenantScope
from platform_kernel.expressions import JsonataEngine, Limits
from platform_kernel.identity import CachedJwksSource, OidcTokenVerifier, StaticJwksSource
from platform_kernel.operations import (
    MemoryOperationStore,
    OperationRunner,
    PostgresOperationStore,
    Saga,
    SagaStep,
)
from platform_kernel.persistence import MemoryUnitOfWorkFactory
from platform_testing import requires_postgres

from .test_identity import AUD, ISS, JWK1, _token_service, token


def as_user(subject: str, tenant: str | None = "t1", roles: frozenset[str] = frozenset()):
    p = Principal(subject, roles=roles, tenant=tenant)
    return ctxmod.use(RequestContext(principal=p, tenant=TenantScope.resolve(p), correlation_id="corr-1",
                                     deadline=datetime.now(UTC) + timedelta(seconds=30)))


# Expressions ------------------------------------------------------------------------------------------------------

CLOSED = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}


def _refused(text: str, schema=None, limits: Limits | None = None) -> bool:
    e = JsonataEngine()
    compiled = e.compile(text, schema, limits=limits) if limits else e.compile(text, schema)
    if not compiled.ok:
        return True
    out = e.evaluate(compiled.value, {"a": "x", "secret": "s"}, limits=limits) if limits else \
        e.evaluate(compiled.value, {"a": "x", "secret": "s"})
    return not out.ok


def test_1_eval_cannot_smuggle_a_regular_expression_past_the_switch():
    assert _refused('$match("aaaa!", $eval("/(a+)+$/"))')
    assert _refused('$eval("1+1")')
    assert _refused('$eval("1+1")', limits=Limits(allow_eval=True))  # eval without regex: still refused
    assert not _refused('$eval("1+1")', limits=Limits(allow_eval=True, allow_regex=True))


@pytest.mark.parametrize("text", ["$.secret", "$$.secret", '$lookup($, "secret")', "$keys($)", "$.*", "**.secret",
                                  '$each($, function($v){$v})', "$sift($, function($v){true})", "$spread($)"])
def test_11_a_closed_schema_cannot_be_bypassed_with_roots_wildcards_or_dynamic_access(text):
    assert _refused(text, CLOSED)


@pytest.mark.parametrize("text", ['$pad("x", 100000000)', '($s := "xxxxxxxxxx"; $s & $s & $s & $s & $s & $s & '
                                  '$s & $s & $s & $s & $s & $s & $s & $s & $s & $s & $s & $s & $s & $s)',
                                  '[1..10000000]'])
def test_12_memory_is_bounded_during_evaluation(text):
    small = Limits(max_output_bytes=100)
    assert _refused(text, limits=small)


# Identity ---------------------------------------------------------------------------------------------------------

def test_2_a_token_without_a_tenant_claim_is_refused_unless_it_has_a_platform_role():
    keys = StaticJwksSource({"keys": [JWK1]})
    plain = OidcTokenVerifier(keys, issuer=ISS, audience=AUD)
    assert plain.verify(token(tenant=None)).error.code == "TOKEN_INVALID"
    assert plain.verify(token(tenant="")).error.code == "TOKEN_INVALID"
    staff = OidcTokenVerifier(keys, issuer=ISS, audience=AUD, platform_roles=frozenset({"platform-operator"}))
    assert staff.verify(token(tenant=None)).error.code == "TOKEN_INVALID"  # admin is not a platform role
    p = staff.verify(token(tenant=None, roles=["platform-operator"])).value
    assert p.tenant is None and p.platform_scoped


def test_8_jwks_outage_keeps_last_good_keys_backs_off_and_answers_dependency_unavailable():
    now, calls, mode = [0.0], [], ["ok"]

    def fetch():
        calls.append(mode[0])
        if mode[0] == "down":
            raise httpx.ConnectError("idp down")
        if mode[0] == "garbage":
            return {"error": "maintenance"}
        return {"keys": [JWK1]}

    source = CachedJwksSource(fetch, ttl_seconds=60, min_refresh_seconds=30, clock=lambda: now[0])
    v = OidcTokenVerifier(source, issuer=ISS, audience=AUD)
    assert v.verify(token()).ok
    for m in ("down", "garbage"):
        mode[0] = m
        now[0] += 61  # cache is stale: a refresh is tried, fails, and the last good keys stay in use
        assert v.verify(token()).ok
        n = len(calls)
        assert v.verify(token()).ok and len(calls) == n  # backed off: no new fetch inside the minimum interval

    empty = OidcTokenVerifier(CachedJwksSource(lambda: (_ for _ in ()).throw(httpx.ConnectError("down")),
                                               clock=lambda: 0.0), issuer=ISS, audience=AUD)
    assert empty.verify(token()).error.code == "DEPENDENCY_UNAVAILABLE"


def test_13a_the_token_cache_has_a_hard_bound():
    svc = _token_service(lambda r: httpx.Response(200, json={"access_token": "t", "expires_in": 300}))
    svc.MAX_ENTRIES = 5
    for i in range(20):
        svc.token(f"aud-{i}")
    assert len(svc._cache) == 5 and "aud-19" in str(list(svc._cache))


# Operations -------------------------------------------------------------------------------------------------------

class _Regressions:
    def test_3_cancel_is_never_lost_to_a_concurrent_update_and_does_nothing_once_finished(self, runner):
        started, stop = threading.Event(), threading.Event()

        def handler(input, handle):
            started.set()
            i = 0
            while not stop.is_set():  # a busy handler racing the cancel with progress updates
                handle.progress(i % 100)
                i += 1
            handle.check_cancelled()
            return {}

        runner.register("busy", handler)
        with as_user("ada"):
            op = runner.start("busy", {}).value
        started.wait(5)
        with as_user("ada"):
            assert runner.cancel(op.id).ok
        time.sleep(0.05)
        stop.set()
        runner.wait(op.id)
        with as_user("ada"):
            assert runner.get(op.id).value.status == "cancelled"
            assert runner.cancel(op.id).error.code == "INVALID_TRANSITION"

    def test_4_resumed_work_runs_with_the_creators_roles(self, runner_factory, monkeypatch):
        crashed = runner_factory()
        crashed.register("job", lambda i, h: {})
        monkeypatch.setattr(crashed, "_submit", lambda op: None)  # the instance dies before the work starts
        with as_user("ada", roles=frozenset({"editor"})):
            op = crashed.start("job", {}).value
        seen = []
        restarted = runner_factory()
        restarted.register("job", lambda i, h: seen.append(ctxmod.current().principal) or {})
        assert restarted.resume_unfinished() == 1
        restarted.wait(op.id)
        assert [(p.subject, p.roles, p.tenant) for p in seen] == [("ada", frozenset({"editor"}), "t1")]

    def test_5_an_operation_past_its_deadline_fails_instead_of_staying_running(self, runner_factory, uow, store):
        runner = OperationRunner(uow=uow, store=store, source="svc", operation_timeout=timedelta(milliseconds=300))

        def slow(input, handle):
            time.sleep(0.5)
            handle.check_cancelled()  # the next step notices the deadline
            return {}

        runner.register("slow", slow)
        runner.register("late", lambda i, h: time.sleep(0.5) or {"done": True})
        try:
            with as_user("ada"):
                a = runner.start("slow", {}).value
                b = runner.start("late", {}).value
            runner.wait(a.id)
            runner.wait(b.id)
            with as_user("ada"):
                failed = runner.get(a.id).value
                assert failed.status == "failed" and failed.error["code"] == "DEADLINE_EXCEEDED"
                assert runner.get(b.id).value.status == "succeeded"  # bookkeeping lands after the deadline
        finally:
            runner.close()

    def test_6_a_failing_compensation_stalls_and_resumes(self, runner):
        attempts = []

        def undo(data):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("ledger unavailable")

        def boom(data):
            raise RuntimeError("partner said no: secret-host-10.0.0.7")

        runner.register_saga(Saga("pay", (SagaStep("reserve", lambda d: {"r": 1}, undo), SagaStep("charge", boom))))
        with as_user("ada"):
            op = runner.start("pay", {}).value
        runner.wait(op.id)
        with as_user("ada"):
            stalled = runner.get(op.id).value
        assert stalled.status == "stalled" and stalled.error["code"] == "COMPENSATION_FAILED"
        assert runner.resume_unfinished() == 1
        runner.wait(op.id)
        with as_user("ada"):
            done = runner.get(op.id).value
        assert done.status == "failed" and len(attempts) == 2
        assert "Compensated: reserve" in done.error["detail"]
        assert "secret-host" not in str(done.error)  # #13b: unexpected errors never reach the operation

    def test_7_resume_never_runs_an_operation_twice(self, runner_factory):
        first = runner_factory()
        calls, gate = [], threading.Event()
        first.register("job", lambda i, h: calls.append(1) or gate.wait(5) and {})
        with as_user("ada"):
            op = first.start("job", {}).value
        time.sleep(0.1)
        assert first.resume_unfinished() == 0  # running here: skipped
        other = runner_factory()
        other.register("job", lambda i, h: calls.append(2) or {})
        assert other.resume_unfinished() == 0  # another instance holds the lease
        gate.set()
        first.wait(op.id)
        assert calls == [1]

    def test_13b_internal_errors_are_generic_and_only_the_creator_or_a_reader_sees_an_operation(self, runner):
        def broken(input, handle):
            raise RuntimeError("password=hunter2 at db-7.internal")

        runner.register("broken", broken)
        with as_user("ada"):
            op = runner.start("broken", {}).value
        runner.wait(op.id)
        with as_user("ada"):
            assert runner.get(op.id).value.error == {"code": "INTERNAL_ERROR",
                                                     "detail": "The operation failed unexpectedly."}
        with as_user("bob"):
            assert runner.get(op.id).error.code == "NOT_FOUND"
        with as_user("carol", roles=frozenset({"operations.read"})):
            assert runner.get(op.id).ok
        with as_user("carol", tenant="t2", roles=frozenset({"operations.read"})):
            assert runner.get(op.id).error.code == "NOT_FOUND"


def _factory(uow, store):
    made = []

    def make():
        r = OperationRunner(uow=uow, store=store, source="svc")
        made.append(r)
        return r
    return make, made


class TestMemoryRegressions(_Regressions):
    @pytest.fixture
    def uow(self):
        return MemoryUnitOfWorkFactory()

    @pytest.fixture
    def store(self):
        return MemoryOperationStore()

    @pytest.fixture
    def runner_factory(self, uow, store):
        make, made = _factory(uow, store)
        yield make
        for r in made:
            r.close()

    @pytest.fixture
    def runner(self, runner_factory):
        return runner_factory()


@requires_postgres
class TestPostgresRegressions(TestMemoryRegressions):
    @pytest.fixture
    def uow(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresUnitOfWorkFactory

        return PostgresUnitOfWorkFactory(pg_engine, pg_schema)

    @pytest.fixture
    def store(self):
        return PostgresOperationStore()
