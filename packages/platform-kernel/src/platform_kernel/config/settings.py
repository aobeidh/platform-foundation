"""Settings come from defaults, then environment variables. Providers are chosen by PROVIDER_<PORT> (P9)."""
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UnknownProvider(ValueError):
    def __init__(self, port: str, value: str, valid: list[str]) -> None:
        super().__init__(f"PROVIDER_{port.upper()}={value!r} is not valid; choose one of: {', '.join(sorted(valid))}")


class SecretRef(BaseModel):
    """A reference to a secret, never the secret itself (P23). Resolved through a SecretStore when used."""

    model_config = ConfigDict(frozen=True)
    ref: str

    def __repr__(self) -> str:
        return f"SecretRef({self.ref!r})"


class PlatformSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    service: str
    environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: str | None = None
    schema_name: str | None = None
    providers: dict[str, str] = Field(default_factory=dict)
    request_timeout_seconds: float = 10.0
    max_body_bytes: int = 1_048_576
    idempotency_retention_hours: int = 24
    allow_demo: bool = False
    egress_allowlist: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, service: str, env: dict[str, str] | None = None, **overrides: object) -> PlatformSettings:
        env = dict(os.environ if env is None else env)
        values: dict[str, object] = {"service": service}
        simple = {
            "ENVIRONMENT": "environment",
            "DATABASE_URL": "database_url",
            "DATABASE_SCHEMA": "schema_name",
            "REQUEST_TIMEOUT_SECONDS": "request_timeout_seconds",
            "MAX_BODY_BYTES": "max_body_bytes",
            "IDEMPOTENCY_RETENTION_HOURS": "idempotency_retention_hours",
        }
        for key, field in simple.items():
            if key in env:
                values[field] = env[key]
        if env.get("ALLOW_DEMO", "").lower() in {"1", "true", "yes"}:
            values["allow_demo"] = True
        if env.get("EGRESS_ALLOWLIST"):
            values["egress_allowlist"] = tuple(h.strip() for h in env["EGRESS_ALLOWLIST"].split(",") if h.strip())
        values["providers"] = {k[len("PROVIDER_"):].lower(): v for k, v in env.items() if k.startswith("PROVIDER_")}
        values.update(overrides)
        return cls(**values)

    def provider(self, port: str, default: str) -> str:
        return self.providers.get(port.lower(), default)

    @property
    def production(self) -> bool:
        return self.environment == "production"
