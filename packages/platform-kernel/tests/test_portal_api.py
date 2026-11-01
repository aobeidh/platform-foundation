"""The portal API that @platform/web-kit reads: caller, capabilities, governed kinds, plugins, operations."""
from __future__ import annotations

from fastapi.testclient import TestClient
from platform_kernel.config import PlatformSettings
from platform_kernel.governance import GovernedKind
from platform_kernel.platform import Platform
from platform_kernel.policy import Role
from pydantic import BaseModel


class NoteSpec(BaseModel):
    title: str


def _app():
    settings = PlatformSettings(service="notes", allow_demo=True)

    def caps(c):
        c.declare("notes:read", "Read notes", ar="عرض الملاحظات")
        c.declare("notes:write", "Change notes")
        c.declare("notes:approve", "Approve notes")

    p = (Platform.builder("notes", settings).with_capabilities(caps)
         .with_roles([Role("writer", frozenset({"notes:read", "notes:write"}), "tenant")], [])
         .with_governed_kinds([GovernedKind("note", "notes", NoteSpec, read="notes:read", write="notes:write",
                                            approve="notes:approve", display={"en": "Note"})])
         .build())
    return p, TestClient(p.create_app())


def test_me_lists_only_the_capabilities_the_caller_holds():
    p, c = _app()
    me = c.get("/api/v1/portal/me", headers={"Authorization": "Bearer demo:ada:writer:t1"}).json()
    assert me["subject"] == "ada" and me["tenant"] == "t1" and not me["platformScope"]
    assert [x["name"] for x in me["capabilities"]] == ["notes:read", "notes:write"]
    assert me["capabilities"][0]["display"]["ar"] == "عرض الملاحظات"
    assert "identity" in me["simulated"]
    p.close()


def test_kinds_carry_schema_lifecycle_and_capabilities():
    p, c = _app()
    body = c.get("/api/v1/portal/kinds", headers={"Authorization": "Bearer demo:ada:writer:t1"}).json()
    note = body["items"][0]
    assert note["plural"] == "notes" and note["schema"]["required"] == ["title"]
    assert note["capabilities"]["approve"] == "notes:approve"
    assert {t["name"] for t in body["lifecycle"]["transitions"]} >= {"test", "submit", "approve", "reject"}
    p.close()


def test_portal_api_needs_a_signed_in_caller():
    p, c = _app()
    for path in ("me", "kinds", "plugins"):
        assert c.get(f"/api/v1/portal/{path}").status_code == 401
    p.close()


def test_operations_list_shows_only_what_the_caller_may_see():
    p, c = _app()
    p.operations.register("noop", lambda i, h: {})
    from datetime import UTC, datetime, timedelta

    from platform_kernel import context as ctxmod
    from platform_kernel.context import Principal, RequestContext, TenantScope

    def start(subject, tenant):
        pr = Principal(subject, tenant=tenant)
        with ctxmod.use(RequestContext(principal=pr, tenant=TenantScope.resolve(pr), correlation_id="c",
                                       deadline=datetime.now(UTC) + timedelta(seconds=30))):
            op = p.operations.start("noop", {}).value
        p.operations.wait(op.id)
        return op.id

    mine, other, elsewhere = start("ada", "t1"), start("bob", "t1"), start("cy", "t2")
    items = c.get("/api/v1/operations", headers={"Authorization": "Bearer demo:ada:writer:t1"}).json()["items"]
    assert [i["id"] for i in items] == [mine]
    assert other and elsewhere
    p.close()
