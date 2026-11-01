"""The portal API (web-kit): who the caller is, what they may do, and what the service offers.

Every portal built on `@platform/web-kit` reads these endpoints to build its menus, its governed-record screens and
its plugin pickers, so no product writes that code (F11, F12). Capabilities only drive what the portal shows; the
API still checks every call (P21).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from .. import context as ctxmod
from ..core import DomainError
from ..http import DomainException

if TYPE_CHECKING:
    from .builder import Platform

LIFECYCLE = {
    "versionStates": ["draft", "tested", "submitted", "active", "superseded", "retired"],
    "recordStates": ["draft", "active", "paused", "retired"],
    "transitions": [
        {"name": "test", "from": ["draft", "tested"], "to": "tested", "capability": "write"},
        {"name": "submit", "from": ["tested"], "to": "submitted", "capability": "write"},
        {"name": "approve", "from": ["submitted"], "to": "active", "capability": "approve"},
        {"name": "reject", "from": ["submitted"], "to": "draft", "capability": "approve", "reason": True},
        {"name": "pause", "record": ["active"], "to": "paused", "capability": "write"},
        {"name": "resume", "record": ["paused"], "to": "active", "capability": "write"},
        {"name": "retire", "record": ["draft", "active", "paused"], "to": "retired", "capability": "write"},
    ],
}


def _signed_in() -> None:
    if ctxmod.current().principal.kind == "anonymous":
        raise DomainException(DomainError("UNAUTHENTICATED", "Sign in to use the portal API."))


def portal_router(platform: Platform, prefix: str = "/api/v1") -> APIRouter:
    r = APIRouter(prefix=f"{prefix}/portal", tags=["portal"])

    @r.get("/me", summary="The caller, their tenant and the capabilities the portal may offer them")
    def me() -> dict[str, Any]:
        _signed_in()
        ctx = ctxmod.current()
        p = ctx.principal
        allowed = platform.policy.capabilities(p)
        caps = [{"name": c.name, "display": c.display} for c in platform.capabilities.all() if c.name in allowed]
        return {"subject": p.subject, "kind": p.kind, "tenant": ctx.tenant.tenant, "platformScope": ctx.tenant.platform,
                "roles": sorted(p.roles), "onBehalfOf": p.on_behalf_of, "capabilities": caps,
                "service": platform.settings.service, "simulated": platform.simulated}

    @r.get("/kinds", summary="Governed kinds with their schema, lifecycle and capabilities")
    def kinds() -> dict[str, Any]:
        _signed_in()
        items = []
        for k in platform.governance.kinds():
            items.append({"kind": k.kind, "plural": k.plural, "display": k.display,
                          "makerChecker": k.maker_checker, "schema": k.spec.model_json_schema(),
                          "capabilities": {"read": k.read, "write": k.write, "approve": k.approve},
                          "tests": [getattr(t, "__name__", "check") for t in k.tests]})
        return {"items": items, "lifecycle": LIFECYCLE}

    @r.get("/plugins", summary="Installed plugins by kind, with their configuration schemas")
    def plugins() -> dict[str, Any]:
        _signed_in()
        items = []
        for kind, host in sorted(platform._plugin_hosts.items()):
            for d in host.descriptors():
                items.append({"kind": kind, "id": d.id, "version": d.version, "spi": d.spi,
                              "capabilities": sorted(d.capabilities), "display": d.display,
                              "publisher": d.publisher, "configSchema": d.config_schema,
                              "secrets": list(d.secrets)})
        return {"items": items, "total": len(items)}

    return r
