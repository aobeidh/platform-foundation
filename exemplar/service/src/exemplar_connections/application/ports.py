from __future__ import annotations

from typing import Any, Protocol

from ..domain import Activation


class ActivationRepository(Protocol):
    """Product port. Providers: memory and postgres, chosen by PROVIDER_ACTIVATIONS (P9)."""

    def add(self, uow: Any, activation: Activation) -> None: ...
    def list(self, uow: Any) -> list[Activation]: ...
