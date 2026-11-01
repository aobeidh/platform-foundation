from __future__ import annotations

from .. import context as ctxmod
from ..context import TenantScope


def current_scope() -> TenantScope:
    return ctxmod.current().tenant


def require_tenant() -> str:
    scope = current_scope()
    if scope.platform:
        raise PermissionError("this operation needs a tenant scope")
    return scope.tenant  # type: ignore[return-value]


def tenant_key(key: str, scope: TenantScope | None = None) -> str:
    """Prefix a cache or storage key with the tenant so tenants never share entries."""
    scope = scope or current_scope()
    return f"{scope.tenant or '_platform'}:{key}"
