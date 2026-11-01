"""The connector SPI this product publishes for plugin authors (P11). Extends the SDK's Plugin protocol."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from platform_plugin_sdk import Check, Descriptor, FieldError, PluginContext

SPI_VERSION = "0.1.0"


@runtime_checkable
class ConnectorSpi(Protocol):
    descriptor: Descriptor

    def validate(self, config: dict[str, Any]) -> list[FieldError]: ...
    def test(self, config: dict[str, Any], ctx: PluginContext) -> list[Check]: ...
    def migrate_config(self, config: dict[str, Any], from_version: str) -> dict[str, Any]: ...
    def send(self, config: dict[str, Any], payload: dict[str, Any], ctx: PluginContext) -> dict[str, Any]: ...
