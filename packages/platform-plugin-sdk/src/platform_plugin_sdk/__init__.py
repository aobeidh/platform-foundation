"""Plugin SDK: the types every plugin and every plugin host share.

This package is the lowest layer of the foundation (ADR 0002). It depends only on pydantic, so a third-party
plugin never pulls in the kernel. Changes here follow the strictest compatibility rules (P57, F1).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

SDK_VERSION = "0.1.0"

_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class FieldError(BaseModel):
    """One problem with one field, addressed by a JSON pointer."""

    model_config = ConfigDict(frozen=True)
    pointer: str
    code: str
    message: str


class Check(BaseModel):
    """A named test result with a plain-language detail, shown to operators as is."""

    model_config = ConfigDict(frozen=True)
    name: str
    ok: bool
    detail: str


class Descriptor(BaseModel):
    """What a plugin declares about itself. Validated by the host before registration (P11)."""

    model_config = ConfigDict(frozen=True)
    id: str
    version: str
    spi: str = Field(description="PEP 440 specifier of compatible host SPI versions, for example '>=0.1,<1'")
    kind: str
    capabilities: frozenset[str] = frozenset()
    config_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    secrets: tuple[str, ...] = ()
    display: dict[str, str]
    publisher: str
    config_migrations_from: tuple[str, ...] = ()

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _ID.match(v):
            raise ValueError("id must be lowercase letters, digits and hyphens, 2 to 63 characters")
        return v

    @field_validator("version")
    @classmethod
    def _version(cls, v: str) -> str:
        if not _SEMVER.match(v):
            raise ValueError("version must be semantic, for example 1.2.3")
        return v

    @field_validator("display")
    @classmethod
    def _display(cls, v: dict[str, str]) -> dict[str, str]:
        if "en" not in v:
            raise ValueError("display needs at least an English name under 'en'")
        return v


class SecretResolver(Protocol):
    def resolve(self, ref: str) -> str: ...


class HttpClient(Protocol):
    """An HTTP client already bound to the host's egress policy (P12, P23)."""

    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class Logger(Protocol):
    def info(self, event: str, **fields: Any) -> None: ...
    def warning(self, event: str, **fields: Any) -> None: ...


class PluginContext(Protocol):
    """The narrow set of capabilities a host hands to a plugin. Plugins get nothing else (P12)."""

    secrets: SecretResolver
    http: HttpClient
    clock: Clock
    log: Logger


@runtime_checkable
class Plugin(Protocol):
    """Every plugin kind's SPI extends this."""

    descriptor: Descriptor

    def validate(self, config: dict[str, Any]) -> list[FieldError]: ...
    def test(self, config: dict[str, Any], ctx: PluginContext) -> list[Check]: ...
    def migrate_config(self, config: dict[str, Any], from_version: str) -> dict[str, Any]: ...


__all__ = [
    "SDK_VERSION",
    "Check",
    "Clock",
    "Descriptor",
    "FieldError",
    "HttpClient",
    "Logger",
    "Plugin",
    "PluginContext",
    "SecretResolver",
]
