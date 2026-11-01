"""Authorization as a FastAPI dependency backed by the PolicyEngine port (P21). Services stay the authority."""
from __future__ import annotations

from collections.abc import Callable

from .. import context as ctxmod
from ..core import DomainError
from ..policy import PolicyEngine
from .app import DomainException


class Authorizer:
    def __init__(self, policy: PolicyEngine) -> None:
        self.policy = policy

    def check(self, capability: str) -> None:
        decision = self.policy.decide(ctxmod.current().principal, capability)
        if not decision.allowed:
            raise DomainException(DomainError("FORBIDDEN", f"{capability}: {decision.reason}."))

    def require(self, capability: str) -> Callable[[], None]:
        def dependency() -> None:
            self.check(capability)
        dependency.__name__ = f"require_{capability.replace(':', '_').replace('-', '_')}"
        return dependency
