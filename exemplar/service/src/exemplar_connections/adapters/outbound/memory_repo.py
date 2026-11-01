from __future__ import annotations

from typing import Any

from platform_kernel import context as ctxmod

from ...domain import Activation


class MemoryActivationRepository:
    simulated = True

    def add(self, uow: Any, activation: Activation) -> None:
        uow.table("activations")[activation.event_id] = activation

    def list(self, uow: Any) -> list[Activation]:
        scope = ctxmod.current().tenant
        rows = [a for a in uow.table("activations").values() if scope.platform or a.tenant == scope.tenant]
        return sorted(rows, key=lambda a: a.activated_at)
