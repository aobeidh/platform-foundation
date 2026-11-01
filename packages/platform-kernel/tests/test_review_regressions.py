"""Regression tests for the findings of the independent review of milestone 0.1. One test per finding."""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import APIRouter, Response
from fastapi.testclient import TestClient
from platform_kernel import context as ctxmod
from platform_kernel.config import PlatformSettings
from platform_kernel.context import Principal, RequestContext, TenantScope
from platform_kernel.errors import kernel_catalog
from platform_kernel.governance import GovernanceEngine, GovernedKind, MemoryGovernedStore, PostgresGovernedStore
from platform_kernel.http import CircuitBreaker, EgressPolicy, HttpSettings, OutboundError, ResilientClient, create_app
from platform_kernel.identity import DemoTokenVerifier
from platform_kernel.persistence import MemoryIdempotencyStore, MemoryUnitOfWorkFactory
from platform_kernel.platform import Platform
from platform_kernel.plugins import AllowUnsignedVerifier, PluginHost
from platform_plugin_sdk import Check, Descriptor
from platform_testing import requires_postgres
from pydantic import BaseModel


def app_with(router: APIRouter, uow: MemoryUnitOfWorkFactory | None = None, timeout: float = 5.0) -> TestClient:
    db = (uow or MemoryUnitOfWorkFactory()).db
    return TestClient(create_app(settings=HttpSettings(service="t", request_timeout=timedelta(seconds=timeout)),
                                 verifier=DemoTokenVerifier(), catalog=kernel_catalog(),
                                 idempotency=MemoryIdempotencyStore(db), routers=[router]))


# 1. Public paths match exactly; anonymous callers never get platform scope -----------------------------------------

def test_public_path_prefix_does_not_skip_authentication():
    r = APIRouter()

    @r.get("/docs-admin/tenants")
    def leak() -> dict:
        return {"platform": ctxmod.current().tenant.platform}

    client = app_with(r)
    assert client.get("/docs-admin/tenants").status_code == 401
    assert client.get("/health/live-debug").status_code == 401
    assert client.get("/health/live").status_code == 200


def test_anonymous_scope_is_never_platform():
    scope = TenantScope.resolve(Principal("anonymous", kind="anonymous"))
    assert not scope.platform and scope.tenant == ctxmod.ANONYMOUS_TENANT


# 2 and 10. Idempotency is scoped per caller, hashes the query string, and replays headers --------------------------

def _orders() -> tuple[TestClient, list[str]]:
    calls: list[str] = []
    r = APIRouter()

    @r.post("/orders", status_code=201)
    def create(response: Response, dryRun: bool = False) -> dict:
        who = ctxmod.current().principal.subject
        calls.append(who)
        response.headers["ETag"] = '"7"'
        response.headers["Location"] = "/orders/1"
        return {"owner": who, "dryRun": dryRun}

    return app_with(r), calls


def test_idempotency_keys_are_scoped_per_caller():
    client, calls = _orders()
    a = client.post("/orders", json={}, headers={"Authorization": "Bearer demo:alice:r:t1", "Idempotency-Key": "k"})
    b = client.post("/orders", json={}, headers={"Authorization": "Bearer demo:bob:r:t1", "Idempotency-Key": "k"})
    assert a.json()["owner"] == "alice" and b.json()["owner"] == "bob" and calls == ["alice", "bob"]


def test_idempotency_replay_keeps_headers_and_hashes_the_query():
    client, calls = _orders()
    h = {"Authorization": "Bearer demo:alice:r:t1", "Idempotency-Key": "k"}
    first = client.post("/orders?dryRun=true", json={}, headers=h)
    again = client.post("/orders?dryRun=true", json={}, headers=h)
    assert again.headers["idempotent-replay"] == "true"
    assert (again.headers["etag"], again.headers["location"]) == (first.headers["etag"], first.headers["location"])
    other = client.post("/orders?dryRun=false", json={}, headers=h)
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert calls == ["alice"]


def test_stale_in_progress_key_can_start_again_after_its_lease():
    store = MemoryIdempotencyStore(MemoryUnitOfWorkFactory().db, lease=timedelta(milliseconds=50))
    assert store.begin("t1", "k", "h").outcome == "started"
    assert store.begin("t1", "k", "h").outcome == "in_progress"
    time.sleep(0.06)
    assert store.begin("t1", "k", "h").outcome == "started"


# 3 and 4. Maker-checker covers every author; retired records stay retired -------------------------------------------

class Spec(BaseModel):
    url: str


KIND = GovernedKind(kind="conn", plural="conns", spec=Spec, tests=(lambda s: [Check(name="x", ok=True, detail="ok")],),
                    read="c:read", write="c:write", approve="c:approve")


def as_user(subject: str):
    p = Principal(subject, tenant="t1")
    return ctxmod.use(RequestContext(principal=p, tenant=TenantScope.resolve(p), correlation_id="c",
                                     deadline=datetime.now(UTC) + timedelta(seconds=30)))


class _Governance:
    def test_an_editor_cannot_approve_the_version_they_edited(self, engine):
        with as_user("alice"):
            v = engine.create("conn", {"url": "https://good"}).value
        with as_user("mallory"):
            v = engine.update_draft("conn", v.record.id, {"url": "https://evil"}, v.record.revision).value
        with as_user("alice"):
            v = engine.test("conn", v.record.id, v.record.revision).value
            v = engine.submit("conn", v.record.id, v.record.revision).value
        with as_user("mallory"):
            r = engine.approve("conn", v.record.id, v.record.revision)
        assert r.error.code == "MAKER_CHECKER"
        with as_user("checker"):
            assert engine.approve("conn", v.record.id, v.record.revision).ok

    def test_a_retired_record_cannot_be_revived(self, engine):
        with as_user("alice"):
            v = engine.create("conn", {"url": "https://x"}).value
            v = engine.test("conn", v.record.id, v.record.revision).value
            v = engine.submit("conn", v.record.id, v.record.revision).value
            v = engine.retire("conn", v.record.id, v.record.revision).value
            assert v.current.status == "retired"
        with as_user("checker"):
            r = engine.approve("conn", v.record.id, v.record.revision)
            assert r.error.code == "INVALID_TRANSITION"
            assert engine.active_spec("conn", v.record.id) is None
            assert engine.test("conn", v.record.id, v.record.revision).error.code == "INVALID_TRANSITION"

    def test_duplicate_id_is_a_conflict_not_a_crash(self, engine):
        with as_user("alice"):
            assert engine.create("conn", {"url": "https://x"}, id="fixed").ok
            assert engine.create("conn", {"url": "https://x"}, id="fixed").error.code == "CONFLICT"


class TestMemoryGovernanceRegressions(_Governance):
    @pytest.fixture
    def engine(self):
        e = GovernanceEngine(uow=MemoryUnitOfWorkFactory(), store=MemoryGovernedStore(), source="svc")
        e.register(KIND)
        return e


@requires_postgres
class TestPostgresGovernanceRegressions(_Governance):
    @pytest.fixture
    def engine(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresUnitOfWorkFactory

        e = GovernanceEngine(uow=PostgresUnitOfWorkFactory(pg_engine, pg_schema), store=PostgresGovernedStore(),
                             source="svc")
        e.register(KIND)
        return e

    def test_database_rejects_an_editor_as_approver(self, engine, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresUnitOfWorkFactory
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        with as_user("alice"):
            v = engine.create("conn", {"url": "https://x"}).value
        with as_user("alice"), pytest.raises(IntegrityError), PostgresUnitOfWorkFactory(pg_engine, pg_schema)() as u:
            u.connection.execute(text("update governed_version set edited_by = array['mallory'], "
                                      "submitted_by = 'alice', approved_by = 'mallory' where id = :i"),
                                 {"i": v.record.id})


# 5. The deadline is enforced at kernel boundaries, also for synchronous code ----------------------------------------

def test_unit_of_work_refuses_to_open_after_the_deadline():
    uow = MemoryUnitOfWorkFactory()
    r = APIRouter()

    @r.post("/work")
    def work() -> dict:
        time.sleep(0.4)
        with uow():
            return {"ok": True}

    client = app_with(r, uow, timeout=0.2)
    res = client.post("/work", headers={"Authorization": "Bearer demo:a:r"})
    assert res.status_code == 504 and res.json()["code"] == "DEADLINE_EXCEEDED"


@requires_postgres
def test_postgres_statements_stop_at_the_deadline(pg_engine, pg_schema):
    from platform_kernel.persistence.postgres import PostgresUnitOfWorkFactory
    from sqlalchemy import text

    factory = PostgresUnitOfWorkFactory(pg_engine, pg_schema)
    r = APIRouter()

    @r.get("/slow")
    def slow() -> dict:
        with factory() as u:
            u.connection.execute(text("select pg_sleep(2)"))
        return {"ok": True}

    client = app_with(r, timeout=0.5)
    started = time.monotonic()
    res = client.get("/slow", headers={"Authorization": "Bearer demo:a:r"})
    assert res.status_code == 504 and time.monotonic() - started < 1.5


# 6 and 11. Egress pins the checked address, rejects non-global ranges, and bounds the whole call --------------------

def test_carrier_grade_nat_is_blocked():
    policy = EgressPolicy(allowlist=("api.example.com",), resolver=lambda h: ["100.64.1.1"])
    with pytest.raises(OutboundError):
        policy.check("https://api.example.com/")


def test_call_connects_to_the_checked_address_with_original_host_and_sni():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(host=request.url.host, header=request.headers["host"],
                    sni=request.extensions.get("sni_hostname"))
        return httpx.Response(200)

    c = ResilientClient("dep", "https://api.example.com", transport=httpx.MockTransport(handler),
                        egress=EgressPolicy(allowlist=("api.example.com",), resolver=lambda h: ["93.184.216.34"]))
    c.request("GET", "/x")
    assert seen == {"host": "93.184.216.34", "header": "api.example.com", "sni": "api.example.com"}


def test_slow_streaming_response_is_bounded_by_the_budget():
    class Drip(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(5):
                time.sleep(0.15)
                yield b"x"

    c = ResilientClient("dep", "https://api.example.com", timeout=0.3,
                        transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=Drip())),
                        egress=EgressPolicy(allowlist=("api.example.com",), resolver=lambda h: ["93.184.216.34"]))
    with pytest.raises(OutboundError) as e:
        c.request("GET", "/x")
    assert e.value.error.code == "DEADLINE_EXCEEDED"


# 7. One plugin context per platform ---------------------------------------------------------------------------------

def test_plugin_context_is_built_once():
    p = Platform.builder("svc", PlatformSettings(service="svc", allow_demo=True)).build()
    assert p.plugin_context() is p.plugin_context()
    p.close()


# 8. Plugin calls carry the request context --------------------------------------------------------------------------

class CtxPlugin:
    descriptor = Descriptor(id="ctx", version="1.0.0", spi=">=0.1", kind="probe", display={"en": "Ctx"},
                            publisher="test")

    def validate(self, config):
        return []

    def test(self, config, ctx):
        return []

    def migrate_config(self, config, from_version):
        return config

    def whoami(self) -> str:
        return ctxmod.current().correlation_id


def test_plugin_calls_carry_the_request_context():
    from platform_plugin_sdk import Plugin

    host = PluginHost("probe", "0.1.0", Plugin, AllowUnsignedVerifier())
    assert host.register(CtxPlugin()).ok
    ctx = RequestContext(principal=Principal("a"), tenant=TenantScope(None), correlation_id="corr-42",
                         deadline=datetime.now(UTC) + timedelta(seconds=5))
    with ctxmod.use(ctx):
        assert host.call("ctx", "1.0.0", "whoami").value == "corr-42"
    host.close()


# 9. Half-open breaker lets exactly one trial through ----------------------------------------------------------------

def test_half_open_breaker_allows_one_trial():
    now = [0.0]
    b = CircuitBreaker(failures=1, open_seconds=10, clock=lambda: now[0])
    b.failure()
    assert not b.allow()
    now[0] = 11
    assert [b.allow() for _ in range(4)] == [True, False, False, False]
    b.failure()
    assert not b.allow()  # the failed trial re-opens the breaker
    now[0] = 22
    assert b.allow()
    b.success()
    assert all(b.allow() for _ in range(3))


def test_a_504_keeps_the_idempotency_key_reserved():
    uow = MemoryUnitOfWorkFactory()
    r = APIRouter()

    @r.post("/work")
    def work() -> dict:
        time.sleep(0.4)
        return {"ok": True}

    client = app_with(r, uow, timeout=0.2)
    h = {"Authorization": "Bearer demo:a:r", "Idempotency-Key": "k"}
    assert client.post("/work", headers=h).status_code == 504
    retry = client.post("/work", headers=h)
    assert retry.status_code == 409 and retry.json()["code"] == "IDEMPOTENCY_IN_PROGRESS"
