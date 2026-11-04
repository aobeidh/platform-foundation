"""End-to-end proof that the kernel works as one system (F15), in memory, on SQLite and on PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from exemplar_connections.adapters.outbound.memory_repo import MemoryActivationRepository
from exemplar_connections.adapters.outbound.postgres_repo import PostgresActivationRepository
from exemplar_connections.adapters.outbound.sqlite_repo import SqliteActivationRepository
from exemplar_connections.domain import Activation
from exemplar_connections.wiring import build
from fastapi.testclient import TestClient
from platform_kernel import context as ctxmod
from platform_kernel.config import PlatformSettings
from platform_kernel.context import Principal, RequestContext, TenantScope
from platform_testing import database_url, requires_postgres

ADMIN = {"Authorization": "Bearer demo:ada:integration-admin:t1"}
APPROVER = {"Authorization": "Bearer demo:sam:integration-approver:t1"}
OTHER_TENANT = {"Authorization": "Bearer demo:oli:integration-admin,integration-approver:t2"}
BOTH_ROLES = {"Authorization": "Bearer demo:max:integration-admin,integration-approver:t1"}


@pytest.fixture(params=["memory", "sqlite", pytest.param("postgres", marks=requires_postgres)])
def system(request, tmp_path):
    if request.param in ("memory", "sqlite"):
        url = f"sqlite:///{tmp_path / 'connections.db'}" if request.param == "sqlite" else None
        settings = PlatformSettings(service="connections", allow_demo=True, database_url=url)
        platform, app = build(settings)
        platform.migrate()
        yield platform, TestClient(app)
        platform.close()
        return
    schema = "ex_" + uuid.uuid4().hex[:10]
    settings = PlatformSettings(service="connections", allow_demo=True, database_url=database_url(),
                                schema_name=schema)
    platform, app = build(settings)
    platform.migrate()
    yield platform, TestClient(app)
    from sqlalchemy import text

    with platform._engine.begin() as c:
        c.execute(text(f"drop schema {schema} cascade"))
    platform.close()


def etag(r) -> dict:
    return {"If-Match": r.headers["etag"]}


def make_active(client, prefix: str = "hi:") -> str:
    r = client.post("/api/v1/connections", headers=ADMIN, json={"spec": {
        "name": "Echo", "connector": "echo", "connector_version": "1.0.0", "config": {"prefix": prefix}}})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = client.post(f"/api/v1/connections/{cid}/test", headers=ADMIN | etag(r))
    assert r.json()["current"]["status"] == "tested", r.json()
    r = client.post(f"/api/v1/connections/{cid}/submit", headers=ADMIN | etag(r))
    r = client.post(f"/api/v1/connections/{cid}/approve", headers=APPROVER | etag(r))
    assert r.status_code == 200 and r.json()["status"] == "active", r.text
    return cid


def test_governed_connection_goes_live_and_records_its_activation(system):
    platform, client = system
    cid = make_active(client)
    assert client.get("/api/v1/activations", headers=ADMIN).json()["total"] == 0
    assert platform.relay.run_once() == 4  # created, tested, submitted, approved
    items = client.get("/api/v1/activations", headers=ADMIN).json()["items"]
    assert [(i["connectionId"], i["version"], i["tenant"]) for i in items] == [(cid, 1, "t1")]
    assert platform.relay.run_once() == 0


def test_send_runs_only_the_active_version(system):
    _, client = system
    cid = make_active(client, prefix="v1:")
    r = client.post(f"/api/v1/connections/{cid}/send", headers=ADMIN, json={"payload": {"text": "x"}})
    assert r.json()["result"]["echo"] == "v1:x"
    cur = client.get(f"/api/v1/connections/{cid}", headers=ADMIN)
    client.put(f"/api/v1/connections/{cid}/draft", headers=ADMIN | etag(cur), json={"spec": {
        "name": "Echo", "connector": "echo", "connector_version": "1.0.0", "config": {"prefix": "v2:"}}})
    r = client.post(f"/api/v1/connections/{cid}/send", headers=ADMIN, json={"payload": {"text": "x"}})
    assert r.json()["result"]["echo"] == "v1:x"  # the draft never runs


def test_bad_config_fails_the_test_with_a_plain_message(system):
    _, client = system
    r = client.post("/api/v1/connections", headers=ADMIN, json={"spec": {
        "name": "Echo", "connector": "echo", "connector_version": "1.0.0", "config": {"prefix": ""}}})
    r = client.post(f"/api/v1/connections/{r.json()['id']}/test", headers=ADMIN | etag(r))
    checks = r.json()["current"]["testResult"]
    assert r.json()["current"]["status"] == "draft"
    assert checks[0]["name"] == "config" and not checks[0]["ok"] and "/prefix" in checks[0]["detail"]


def test_unknown_plugin_fails_the_test(system):
    _, client = system
    r = client.post("/api/v1/connections", headers=ADMIN, json={"spec": {
        "name": "X", "connector": "nope", "connector_version": "9.9.9", "config": {}}})
    r = client.post(f"/api/v1/connections/{r.json()['id']}/test", headers=ADMIN | etag(r))
    assert "No connector plugin nope" in r.json()["current"]["testResult"][0]["detail"]


def test_separation_of_duties_and_maker_checker(system):
    _, client = system
    r = client.post("/api/v1/connections", headers=BOTH_ROLES, json={"spec": {
        "name": "Echo", "connector": "echo", "connector_version": "1.0.0", "config": {"prefix": "a"}}})
    # Holding both write and approve through roles grants neither (P21).
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"


def test_tenant_isolation_over_http(system):
    platform, client = system
    cid = make_active(client)
    platform.relay.run_once()
    assert client.get(f"/api/v1/connections/{cid}", headers=OTHER_TENANT).status_code == 404
    assert client.get("/api/v1/activations", headers=OTHER_TENANT).json()["total"] == 0
    r = client.post(f"/api/v1/connections/{cid}/send", headers=OTHER_TENANT, json={"payload": {}})
    assert r.json()["code"] == "CONNECTION_NOT_ACTIVE"


def test_idempotent_send(system):
    _, client = system
    cid = make_active(client)
    h = ADMIN | {"Idempotency-Key": "send-1"}
    a = client.post(f"/api/v1/connections/{cid}/send", headers=h, json={"payload": {"text": "x"}})
    b = client.post(f"/api/v1/connections/{cid}/send", headers=h, json={"payload": {"text": "x"}})
    assert a.json() == b.json() and b.headers["idempotent-replay"] == "true"


def test_simulated_providers_are_labeled(system):
    platform, client = system
    r = client.get("/api/v1/activations", headers=ADMIN)
    assert "identity" in r.headers["x-platform-simulated"]


# Product port contract: every ActivationRepository provider behaves the same (P9) -------------------------------

def _activation(tenant: str) -> Activation:
    return Activation(uuid.uuid4().hex, 1, tenant, datetime.now(UTC), uuid.uuid4().hex)


def test_activation_repository_contract(system):
    platform, _ = system
    # Runs once per persistence provider through the `system` fixture.
    repo = (MemoryActivationRepository() if platform._engine is None else SqliteActivationRepository()
            if platform._engine.dialect.name == "sqlite" else PostgresActivationRepository())
    a1, a2 = _activation("t1"), _activation("t2")

    def as_tenant(t):
        p = Principal("x", tenant=t)
        return ctxmod.use(RequestContext(principal=p, tenant=TenantScope.resolve(p), correlation_id="c",
                                         deadline=datetime.now(UTC).replace(year=2100)))

    with as_tenant("t1"), platform.uow() as uow:
        repo.add(uow, a1)
        repo.add(uow, a1)  # adding the same event twice is harmless
    with as_tenant("t2"), platform.uow() as uow:
        repo.add(uow, a2)
    with as_tenant("t1"), platform.uow() as uow:
        assert [a.event_id for a in repo.list(uow)] == [a1.event_id]


def test_sqlite_repository_refuses_another_tenants_activation(tmp_path):
    from exemplar_connections.wiring import MIGRATIONS
    from platform_kernel.persistence.sqlite import SqliteUnitOfWorkFactory
    from platform_testing import fresh_sqlite

    for engine in fresh_sqlite(tmp_path, [MIGRATIONS]):
        p = Principal("x", tenant="t1")
        ctx = RequestContext(principal=p, tenant=TenantScope.resolve(p), correlation_id="c",
                             deadline=datetime.now(UTC).replace(year=2100))
        with ctxmod.use(ctx), SqliteUnitOfWorkFactory(engine)() as uow, pytest.raises(PermissionError):
            SqliteActivationRepository().add(uow, _activation("t2"))


def test_send_batch_runs_as_an_operation_with_progress(system):
    platform, client = system
    cid = make_active(client, prefix="b:")
    r = client.post(f"/api/v1/connections/{cid}/send-batch", headers=ADMIN,
                    json={"payloads": [{"n": i} for i in range(3)]})
    assert r.status_code == 202 and r.headers["location"].startswith("/api/v1/operations/")
    op_id = r.json()["id"]
    platform.operations.wait(op_id)
    done = client.get(r.headers["location"], headers=ADMIN).json()
    assert done["status"] == "succeeded" and done["progress"] == 100 and done["result"] == {"sent": 3}
    assert [i["id"] for i in client.get("/api/v1/operations", headers=ADMIN).json()["items"]] == [op_id]
    assert client.get(r.headers["location"], headers=APPROVER).status_code == 404  # not theirs


def test_portal_api_reflects_roles_kinds_and_plugins(system):
    _, client = system
    me = client.get("/api/v1/portal/me", headers=APPROVER).json()
    assert {c["name"] for c in me["capabilities"]} == {"connections:read", "connections:approve"}
    kinds = client.get("/api/v1/portal/kinds", headers=ADMIN).json()["items"]
    assert [k["plural"] for k in kinds] == ["connections"]
    plugins = client.get("/api/v1/portal/plugins", headers=ADMIN).json()["items"]
    assert [(p["kind"], p["id"]) for p in plugins] == [("connector", "echo")]


def test_api_shapes_match_the_web_kit_conformance_fixture():
    """The web-kit's simulated provider is tested against this fixture; the live service must match it too."""
    import importlib.util
    import json
    from pathlib import Path

    loaded = importlib.util.spec_from_file_location("journey", Path(__file__).with_name("journey.py"))
    journey = importlib.util.module_from_spec(loaded)
    loaded.loader.exec_module(journey)
    FIXTURE, run, shape = journey.FIXTURE, journey.run, journey.shape

    settings = PlatformSettings(service="connections", allow_demo=True)
    platform, app = build(settings)
    try:
        live = run(platform, TestClient(app))
    finally:
        platform.close()
    recorded = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert {k: v["status"] for k, v in live.items()} == {k: v["status"] for k, v in recorded.items()}
    for key in recorded:
        assert shape(live[key]["body"]) == shape(recorded[key]["body"]), key


def test_r3_r4_batch_checks_the_connection_up_front_and_stops_when_it_is_paused(system):
    platform, client = system
    gone = client.post("/api/v1/connections/missing/send-batch", headers=ADMIN, json={"payloads": [{}]})
    assert gone.status_code == 404
    draft = client.post("/api/v1/connections", headers=ADMIN, json={"spec": {
        "name": "D", "connector": "echo", "connector_version": "1.0.0", "config": {"prefix": "d"}}}).json()
    assert client.post(f"/api/v1/connections/{draft['id']}/send-batch", headers=ADMIN,
                       json={"payloads": [{}]}).json()["code"] == "CONNECTION_NOT_ACTIVE"
    cid = make_active(client, prefix="p:")
    rec = client.get(f"/api/v1/connections/{cid}", headers=ADMIN)
    client.post(f"/api/v1/connections/{cid}/pause", headers=ADMIN | etag(rec))
    # The batch was accepted before the pause in real life; here start it through the runner with the pinned version.
    from datetime import timedelta

    from platform_kernel import context as ctxmod
    from platform_kernel.context import Principal, RequestContext, TenantScope

    pr = Principal("ada", roles=frozenset({"integration-admin"}), tenant="t1")
    with ctxmod.use(RequestContext(principal=pr, tenant=TenantScope.resolve(pr), correlation_id="c",
                                   deadline=datetime.now(UTC) + timedelta(seconds=30))):
        op = platform.operations.start("connections.send-batch",
                                       {"id": cid, "version": 1, "payloads": [{}, {}]}).value
    platform.operations.wait(op.id)
    failed = client.get(f"/api/v1/operations/{op.id}", headers=ADMIN).json()
    assert failed["status"] == "failed" and failed["error"]["code"] == "CONNECTION_NOT_ACTIVE"
    assert "0 of 2 payloads were sent" in failed["error"]["detail"]


def test_r7_reject_needs_a_reason(system):
    _, client = system
    r = client.post("/api/v1/connections", headers=ADMIN, json={"spec": {
        "name": "R", "connector": "echo", "connector_version": "1.0.0", "config": {"prefix": "r"}}})
    cid = r.json()["id"]
    r = client.post(f"/api/v1/connections/{cid}/test", headers=ADMIN | etag(r))
    r = client.post(f"/api/v1/connections/{cid}/submit", headers=ADMIN | etag(r))
    empty = client.post(f"/api/v1/connections/{cid}/reject", headers=APPROVER | etag(r), json={"reason": ""})
    assert empty.status_code == 422
