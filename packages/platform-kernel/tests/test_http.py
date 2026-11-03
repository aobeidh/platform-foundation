from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from platform_kernel import context as ctxmod
from platform_kernel.context import Principal, RequestContext, TenantScope
from platform_kernel.core import new_id
from platform_kernel.errors import kernel_catalog
from platform_kernel.http import (
    CircuitBreaker,
    EgressPolicy,
    HttpSettings,
    OutboundError,
    ResilientClient,
    Retry,
    create_app,
)
from platform_kernel.identity import DemoTokenVerifier
from platform_kernel.persistence import MemoryIdempotencyStore, MemoryUnitOfWorkFactory
from pydantic import BaseModel

AUTH = {"Authorization": "Bearer demo:alice:admin"}


class Thing(BaseModel):
    name: str
    size: int


def make_client(timeout: float = 5.0) -> tuple[TestClient, dict]:
    calls = {"n": 0}
    r = APIRouter()

    @r.post("/things", status_code=201)
    def create(thing: Thing) -> dict:
        calls["n"] += 1
        ctx = ctxmod.current()
        return {"id": new_id(), "name": thing.name, "actor": ctx.principal.subject, "tenant": ctx.tenant.tenant,
                "correlation": ctx.correlation_id}

    @r.get("/slow")
    async def slow() -> dict:
        import anyio

        await anyio.sleep(2)
        return {"ok": True}

    @r.get("/boom")
    def boom() -> dict:
        raise RuntimeError("secret internals")

    db = MemoryUnitOfWorkFactory().db
    app = create_app(settings=HttpSettings(service="test", request_timeout=timedelta(seconds=timeout),
                                           max_body_bytes=200, simulated=["identity"]),
                     verifier=DemoTokenVerifier(), catalog=kernel_catalog(), idempotency=MemoryIdempotencyStore(db),
                     routers=[r])
    return TestClient(app), calls


def test_missing_token_is_a_401_problem():
    client, _ = make_client()
    r = client.post("/things", json={"name": "a", "size": 1})
    assert r.status_code == 401
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "UNAUTHENTICATED" and r.json()["correlationId"]


def test_context_carries_principal_tenant_and_correlation():
    client, _ = make_client()
    r = client.post("/things", json={"name": "a", "size": 1},
                    headers={"Authorization": "Bearer demo:bob:user:t1", "X-Correlation-Id": "c-123",
                             "X-Tenant-Id": "t2"})
    body = r.json()
    assert r.status_code == 201
    assert (body["actor"], body["tenant"], body["correlation"]) == ("bob", "t1", "c-123")  # own tenant wins
    assert r.headers["x-correlation-id"] == "c-123"
    assert r.headers["x-platform-simulated"] == "identity"


def test_validation_errors_use_json_pointers():
    client, _ = make_client()
    r = client.post("/things", json={"name": "a", "size": "big"}, headers=AUTH)
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_FAILED"
    assert r.json()["errors"][0]["pointer"] == "/size"


def test_unhandled_errors_become_500_problems_without_internals():
    client, _ = make_client()
    r = client.get("/boom", headers=AUTH)
    assert r.status_code == 500 and r.json()["code"] == "INTERNAL_ERROR"
    assert "secret internals" not in r.text


def test_body_limit():
    client, _ = make_client()
    r = client.post("/things", json={"name": "x" * 500, "size": 1}, headers=AUTH)
    assert r.status_code == 413 and r.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_deadline_exceeded_returns_504():
    client, _ = make_client(timeout=0.3)
    r = client.get("/slow", headers=AUTH)
    assert r.status_code == 504 and r.json()["code"] == "DEADLINE_EXCEEDED"


def test_idempotency_replays_and_detects_reuse():
    client, calls = make_client()
    h = AUTH | {"Idempotency-Key": "k1"}
    first = client.post("/things", json={"name": "a", "size": 1}, headers=h)
    again = client.post("/things", json={"name": "a", "size": 1}, headers=h)
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"] and again.headers["idempotent-replay"] == "true"
    assert calls["n"] == 1
    other = client.post("/things", json={"name": "b", "size": 1}, headers=h)
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_health_is_public():
    client, _ = make_client()
    assert client.get("/health/live").json() == {"status": "ok"}


# Outbound client -------------------------------------------------------------------------------------------------

def public(host: str) -> list[str]:
    return ["93.184.216.34"]


def test_egress_blocks_unlisted_plain_http_and_private_addresses():
    policy = EgressPolicy(allowlist=("api.example.com", "*.partner.com"), resolver=public)
    policy.check("https://api.example.com/x")
    policy.check("https://a.partner.com/x")
    for url in ("https://evil.com/", "http://api.example.com/", "ftp://api.example.com/", "https://partner.com/"):
        with pytest.raises(OutboundError) as e:
            policy.check(url)
        assert e.value.error.code == "EGRESS_BLOCKED"
    private = EgressPolicy(allowlist=("api.example.com",), resolver=lambda h: ["10.0.0.5"])
    with pytest.raises(OutboundError):
        private.check("https://api.example.com/")


def _client(handler, **kw) -> ResilientClient:
    return ResilientClient("dep", "https://api.example.com", egress=EgressPolicy(allowlist=("api.example.com",),
                           resolver=public), transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def test_retries_idempotent_calls_only():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return httpx.Response(503)

    c = _client(handler, retry=Retry(max_attempts=3), breaker=CircuitBreaker(failures=100))
    assert c.request("GET", "/x").status_code == 503
    assert seen == ["GET"] * 3
    seen.clear()
    c.request("POST", "/x")
    assert seen == ["POST"]
    seen.clear()
    c.request("POST", "/x", headers={"Idempotency-Key": "k"})
    assert seen == ["POST"] * 3


def test_breaker_opens_after_failures():
    c = _client(lambda r: httpx.Response(503), retry=Retry(max_attempts=1),
                breaker=CircuitBreaker(failures=2, open_seconds=60))
    c.request("GET", "/x")
    c.request("GET", "/x")
    with pytest.raises(OutboundError) as e:
        c.request("GET", "/x")
    assert e.value.error.code == "DEPENDENCY_UNAVAILABLE"


def test_propagates_correlation_and_deadline():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.headers)
        return httpx.Response(200, json={})

    ctx = RequestContext(principal=Principal("svc"), tenant=TenantScope(None), correlation_id="corr-9",
                         deadline=datetime.now(UTC) + timedelta(seconds=5))
    with ctxmod.use(ctx):
        _client(handler).request("GET", "/x")
    assert captured["x-correlation-id"] == "corr-9" and "request-deadline" in captured


def test_no_call_after_deadline():
    ctx = RequestContext(principal=Principal("svc"), tenant=TenantScope(None), correlation_id="c",
                         deadline=datetime.now(UTC) - timedelta(seconds=1))
    with ctxmod.use(ctx), pytest.raises(OutboundError) as e:
        _client(lambda r: httpx.Response(200)).request("GET", "/x")
    assert e.value.error.code == "DEADLINE_EXCEEDED"


def test_response_size_limit():
    c = ResilientClient("dep", "https://api.example.com",
                        egress=EgressPolicy(allowlist=("api.example.com",), resolver=public, max_response_bytes=10),
                        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 100)))
    with pytest.raises(OutboundError) as e:
        c.request("GET", "/x")
    assert e.value.error.code == "PAYLOAD_TOO_LARGE"


def _public_app(*, routers=(), public=(), max_body=200, idempotency=True, verifier=None):
    db = MemoryUnitOfWorkFactory().db
    return create_app(settings=HttpSettings(service="test", max_body_bytes=max_body),
                      verifier=verifier or DemoTokenVerifier(), catalog=kernel_catalog(),
                      idempotency=MemoryIdempotencyStore(db) if idempotency else None, routers=list(routers),
                      public_routers=list(public))


def _hooks() -> APIRouter:
    r = APIRouter()

    @r.post("/hooks/{name}")
    def hook(name: str, body: dict) -> dict:
        ctx = ctxmod.current()
        return {"name": name, "subject": ctx.principal.subject, "kind": ctx.principal.kind,
                "tenant": ctx.tenant.tenant, "platform": ctx.tenant.platform, "correlation": ctx.correlation_id,
                "key": ctx.idempotency_key}

    @r.post("/hooks/{name}/slow")
    def slow(name: str) -> dict:
        import time

        time.sleep(0.5)
        return {}

    return r


def test_public_routes_skip_tokens_but_keep_the_stack():
    """A public route authenticates its caller itself; the deadline, body limit and problem details still apply."""
    client = TestClient(_public_app(public=[_hooks()]))
    ok = client.post("/hooks/orders", json={"a": 1}, headers={"X-Correlation-Id": "c-1", "X-Tenant-Id": "retail"})
    body = ok.json()
    assert ok.status_code == 200 and body["kind"] == "anonymous" and body["correlation"] == "c-1"
    assert body["subject"].startswith(ctxmod.RESERVED) and body["tenant"] == ctxmod.ANONYMOUS_TENANT
    assert not body["platform"]  # the tenant header is ignored, and the scope is never platform scope
    too_big = client.post("/hooks/orders", content=b"x" * 500, headers={"content-type": "application/json"})
    assert too_big.status_code == 413 and too_big.headers["content-type"] == "application/problem+json"
    soon = (datetime.now(UTC) + timedelta(milliseconds=50)).isoformat()
    late = client.post("/hooks/orders/slow", headers={"Request-Deadline": soon})
    assert late.status_code == 504
    assert client.post("/hooks/", json={}).status_code == 401  # no public route matches it


def test_public_routes_ignore_idempotency_keys():
    """Every anonymous caller would share one key space, so a public route sees each request afresh."""
    client = TestClient(_public_app(public=[_hooks()]))
    first = client.post("/hooks/a", json={"n": 1}, headers={"Idempotency-Key": "k"})
    second = client.post("/hooks/a", json={"n": 2}, headers={"Idempotency-Key": "k"})
    assert first.status_code == second.status_code == 200
    assert "idempotent-replay" not in second.headers


def test_a_protected_route_that_matches_first_keeps_its_authentication():
    """Public is decided by the route the router runs, not by the path's text."""
    protected = APIRouter()

    @protected.post("/{region}/{name}")
    def anything(region: str, name: str) -> dict:
        return {"who": ctxmod.current().principal.subject}

    @protected.get("/hooks-admin")
    def admin() -> dict:
        return {"secret": True}

    client = TestClient(_public_app(routers=[protected], public=[_hooks()]))
    assert client.post("/hooks/orders", json={}).status_code == 401  # the protected catch-all wins the match
    assert client.get("/hooks-admin").status_code == 401


def test_a_mount_or_root_path_cannot_make_other_routes_public():
    from fastapi import FastAPI

    protected = APIRouter()

    @protected.get("/api/v1/secret")
    def secret() -> dict:
        return {"secret": True}

    inner = _public_app(routers=[protected], public=[_hooks()])
    outer = FastAPI()
    outer.mount("/hooks", inner)
    client = TestClient(outer)
    assert client.get("/hooks/api/v1/secret").status_code == 401
    assert client.get("/hooks/health/live").status_code == 200  # the kernel's paths are matched without the mount
    rooted = TestClient(_public_app(routers=[protected], public=[_hooks()]), root_path="/svc")
    assert rooted.post("/svc/hooks/orders", json={}).status_code == 200
    assert rooted.get("/svc/health/live").status_code == 200
    assert rooted.get("/svc/api/v1/secret").status_code == 401


@pytest.mark.parametrize("path", ["/api/v1/hooks/{name}", "/health/hook", "/docs/hook", "/openapi.json", "/{name}",
                                  "/{a}/b"])
def test_a_public_route_cannot_stand_in_for_kernel_paths(path):
    r = APIRouter()

    @r.post(path)
    def hook() -> dict:
        return {}

    with pytest.raises(ValueError):
        _public_app(public=[r])


def test_tokens_cannot_name_reserved_principals():
    from platform_kernel.core import Ok

    class Claims:
        def __init__(self, principal: Principal) -> None:
            self.principal = principal

        def verify(self, token: str):
            return Ok(self.principal)

    r = APIRouter()

    @r.get("/me")
    def me() -> dict:
        return {"subject": ctxmod.current().principal.subject}

    for p in (Principal(subject="x", kind="anonymous", tenant="t1"),
              Principal(subject="x", kind="partner", tenant="t1"),
              Principal(subject=ctxmod.RESERVED + "partner:orders", tenant="t1"),
              Principal(subject="x", tenant=ctxmod.ANONYMOUS_TENANT)):
        client = TestClient(_public_app(routers=[r], verifier=Claims(p)))
        refused = client.get("/me", headers={"Authorization": "Bearer t"})
        assert refused.status_code == 401 and refused.json()["code"] == "TOKEN_INVALID"
    fine = TestClient(_public_app(routers=[r], verifier=Claims(Principal(subject="anonymous", tenant="t1"))))
    assert fine.get("/me", headers={"Authorization": "Bearer t"}).json()["subject"] == "anonymous"


def test_a_public_route_acts_as_a_partner_in_one_tenant():
    r = APIRouter()

    @r.post("/hooks/{name}")
    def hook(name: str) -> dict:
        with ctxmod.as_partner(f"webhook:{name}", "t1") as ctx:
            return {"subject": ctx.principal.subject, "kind": ctx.principal.kind, "tenant": ctx.tenant.tenant,
                    "after": None}

    @r.post("/other/{name}")
    def other(name: str) -> dict:
        try:
            with ctxmod.as_partner("x", ""):
                pass
        except ValueError:
            return {"refused": True}
        return {"refused": False}

    client = TestClient(_public_app(public=[r]))
    body = client.post("/hooks/orders").json()
    assert body == {"subject": ctxmod.RESERVED + "partner:webhook:orders", "kind": "partner", "tenant": "t1",
                    "after": None}
    assert client.post("/other/x").json() == {"refused": True}


def test_only_the_anonymous_caller_can_become_a_partner():
    user = RequestContext(principal=Principal(subject="u", tenant="t1"), tenant=TenantScope("t1"), correlation_id="c",
                          deadline=datetime.now(UTC) + timedelta(seconds=5))
    with ctxmod.use(user), pytest.raises(PermissionError), ctxmod.as_partner("orders", "t2"):
        pass
    anon = RequestContext(principal=ctxmod.ANONYMOUS, tenant=TenantScope(ctxmod.ANONYMOUS_TENANT), correlation_id="c",
                          deadline=datetime.now(UTC) + timedelta(seconds=5))
    with ctxmod.use(anon):
        for name, tenant in (("bad name", "t1"), ("", "t1"), ("ok", ctxmod.ANONYMOUS_TENANT)):
            with pytest.raises(ValueError), ctxmod.as_partner(name, tenant):
                pass
        with ctxmod.as_partner("orders", "t1") as ctx:
            assert ctxmod.current() is ctx
        assert ctxmod.current() is anon


def test_the_platform_passes_public_routers_through():
    from platform_kernel.config import PlatformSettings
    from platform_kernel.platform import Platform

    platform = Platform.builder("svc", PlatformSettings(service="svc", allow_demo=True)).build()
    client = TestClient(platform.create_app(public_routers=[_hooks()]))
    assert client.post("/hooks/orders", json={}).json()["kind"] == "anonymous"
    assert client.get("/api/v1/operations").status_code == 401
