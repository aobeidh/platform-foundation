"""SecretStore port (P23). References look like 'env://NAME' or 'mem://name'. Values are never logged."""
from __future__ import annotations

import os
from typing import Protocol


class SecretNotFound(LookupError):
    def __init__(self, ref: str) -> None:
        super().__init__(f"secret {ref!r} was not found")


class SecretStore(Protocol):
    simulated: bool

    def resolve(self, ref: str) -> str: ...


class EnvSecretStore:
    """Reads 'env://NAME' from the process environment, for containers that receive secrets as variables."""

    simulated = False

    def resolve(self, ref: str) -> str:
        if not ref.startswith("env://"):
            raise SecretNotFound(ref)
        value = os.environ.get(ref[len("env://"):])
        if value is None:
            raise SecretNotFound(ref)
        return value


class MemorySecretStore:
    """Development and tests. Labeled simulated."""

    simulated = True

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets = dict(secrets or {})

    def put(self, name: str, value: str) -> str:
        self._secrets[name] = value
        return f"mem://{name}"

    def resolve(self, ref: str) -> str:
        if not ref.startswith("mem://") or ref[len("mem://"):] not in self._secrets:
            raise SecretNotFound(ref)
        return self._secrets[ref[len("mem://"):]]
