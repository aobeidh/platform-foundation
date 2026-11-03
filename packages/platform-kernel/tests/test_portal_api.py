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


# Review findings (0.3) ---------------------------------------------------------------------------------------------

def test_r1_others_operations_never_crowd_out_the_callers_own():
    from datetime import UTC, datetime, timedelta

    from platform_kernel import context as ctxmod
    from platform_kernel.context import Principal, RequestContext, TenantScope

    p, c = _app()
    p.operations.register("noop", lambda i, h: {})

    def start(subject):
        pr = Principal(subject, tenant="t1")
        with ctxmod.use(RequestContext(principal=pr, tenant=TenantScope.resolve(pr), correlation_id="c",
                                       deadline=datetime.now(UTC) + timedelta(seconds=30))):
            op = p.operations.start("noop", {}).value
        p.operations.wait(op.id)
        return op.id

    mine = start("ada")
    for _ in range(30):
        start("bob")
    items = c.get("/api/v1/operations?limit=5", headers={"Authorization": "Bearer demo:ada:writer:t1"}).json()["items"]
    assert [i["id"] for i in items] == [mine]
    ada = {"Authorization": "Bearer demo:ada:writer:t1"}
    for bad in ("0", "-1", "201"):
        assert c.get(f"/api/v1/operations?limit={bad}", headers=ada).status_code == 422
    p.close()


def test_r6_kinds_and_plugin_schemas_follow_capabilities():
    p, c = _app()
    stranger = {"Authorization": "Bearer demo:eve:nobody:t9"}
    assert c.get("/api/v1/portal/kinds", headers=stranger).json()["items"] == []
    assert c.get("/api/v1/portal/plugins", headers=stranger).status_code == 403
    p.close()


def test_sign_in_says_demo_and_needs_no_token():
    p, c = _app()
    r = c.get("/api/v1/portal/sign-in")
    assert r.status_code == 200 and r.json() == {"method": "demo"}
    p.close()


def _oidc_platform(**kw):
    settings = PlatformSettings(service="notes", egress_allowlist=("idp.example.com",), **kw.pop("settings", {}))
    return (Platform.builder("notes", settings)
            .with_oidc(issuer="https://idp.example.com/realms/notes", audience="notes",
                       jwks_url="https://idp.example.com/realms/notes/protocol/openid-connect/certs", **kw)
            .build())


def test_sign_in_gives_the_oidc_settings_of_the_portal_client():
    p = _oidc_platform(portal_client_id="notes-portal", portal_scopes=("profile", "openid", "email"))
    c = TestClient(p.create_app())
    assert c.get("/api/v1/portal/sign-in").json() == {
        "method": "oidc", "issuer": "https://idp.example.com/realms/notes", "clientId": "notes-portal",
        "scopes": ["openid", "profile", "email"]}
    assert c.get("/api/v1/portal/me").status_code == 401  # the rest of the portal API still needs a token
    p.close()


def test_sign_in_without_a_portal_client_is_none():
    p = _oidc_platform()
    assert TestClient(p.create_app()).get("/api/v1/portal/sign-in").json() == {"method": "none"}
    p.close()


def test_sign_in_is_public_only_at_its_exact_path():
    p, c = _app()
    assert c.get("/api/v1/portal/sign-in/x").status_code in (401, 404)
    assert c.get("/api/v1/portal/sign-inx").status_code in (401, 404)
    p.close()
