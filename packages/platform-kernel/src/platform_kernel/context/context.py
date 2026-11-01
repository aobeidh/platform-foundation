"""RequestContext lives in one context variable. Product code reads it; only the kernel sets it (F8, F22)."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class Principal:
    """Who is acting. `on_behalf_of` is set when a service or agent acts for a user (P36, P50)."""

    subject: str
    roles: frozenset[str] = frozenset()
    tenant: str | None = None
    kind: str = "user"
    on_behalf_of: str | None = None
    claims: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def platform_scoped(self) -> bool:
        return self.tenant is None


ANONYMOUS_TENANT = "\u2205anonymous"  # matches no real tenant


@dataclass(frozen=True)
class TenantScope:
    """Either the whole platform (staff) or exactly one tenant (P22)."""

    tenant: str | None

    @property
    def platform(self) -> bool:
        return self.tenant is None

    @classmethod
    def resolve(cls, principal: Principal, requested: str | None = None) -> TenantScope:
        # Anonymous callers (public endpoints) get a scope that matches no tenant and is never platform scope.
        if principal.kind == "anonymous":
            return cls(ANONYMOUS_TENANT)
        # Tenant-bound principals always get their own tenant, whatever they ask for.
        if principal.tenant is not None:
            return cls(principal.tenant)
        return cls(requested)


@dataclass(frozen=True)
class RequestContext:
    principal: Principal
    tenant: TenantScope
    correlation_id: str
    deadline: datetime
    causation_id: str | None = None
    traceparent: str | None = None
    idempotency_key: str | None = None
    test: bool = False

    def with_tenant(self, scope: TenantScope) -> RequestContext:
        return replace(self, tenant=scope)


class DeadlineExceeded(RuntimeError):
    """Raised at kernel boundaries (unit of work, outbound calls) when the request deadline has passed (F10)."""

    def __init__(self, where: str) -> None:
        super().__init__(f"the request deadline passed before {where}")
        self.where = where


def check_deadline(where: str) -> None:
    ctx = _current.get()
    if ctx is not None and ctx.deadline <= datetime.now(UTC):
        raise DeadlineExceeded(where)


class NoRequestContext(RuntimeError):
    def __init__(self) -> None:
        super().__init__("no request context is active; run inside a request, consumer or context.use(...)")


_current: ContextVar[RequestContext | None] = ContextVar("platform_request_context", default=None)


def current() -> RequestContext:
    ctx = _current.get()
    if ctx is None:
        raise NoRequestContext()
    return ctx


def maybe_current() -> RequestContext | None:
    return _current.get()


def remaining(now: datetime | None = None) -> timedelta:
    now = now or datetime.now(UTC)
    return current().deadline - now


def deadline_exceeded(now: datetime | None = None) -> bool:
    ctx = _current.get()
    return ctx is not None and remaining(now) <= timedelta(0)


@contextmanager
def use(ctx: RequestContext) -> Iterator[RequestContext]:
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)
