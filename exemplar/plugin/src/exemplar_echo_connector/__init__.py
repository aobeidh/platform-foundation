"""Exemplar connector plugin. Depends only on the plugin SDK, like any third-party plugin (P11, P12).

It implements the exemplar service's connector SPI structurally: descriptor, validate, test, migrate_config, send.
"""
from __future__ import annotations

from typing import Any

from platform_plugin_sdk import Check, Descriptor, FieldError, PluginContext


class EchoConnector:
    descriptor = Descriptor(
        id="echo",
        version="1.0.0",
        spi=">=0.1,<1",
        kind="connector",
        capabilities=frozenset({"sink", "request-reply"}),
        config_schema={
            "type": "object",
            "required": ["prefix"],
            "additionalProperties": False,
            "properties": {
                "prefix": {"type": "string", "minLength": 1, "maxLength": 20},
                "uppercase": {"type": "boolean", "default": False},
            },
        },
        display={"en": "Echo", "ar": "صدى"},
        publisher="platform-foundation",
    )

    def validate(self, config: dict[str, Any]) -> list[FieldError]:
        if config.get("prefix", "").strip() != config.get("prefix", ""):
            return [FieldError(pointer="/prefix", code="whitespace", message="The prefix must not start or end "
                                                                               "with spaces.")]
        return []

    def test(self, config: dict[str, Any], ctx: PluginContext) -> list[Check]:
        ctx.log.info("echo.test", prefix=config.get("prefix"))
        return [Check(name="reach", ok=True, detail="Echo needs no network; it is always reachable.")]

    def migrate_config(self, config: dict[str, Any], from_version: str) -> dict[str, Any]:
        return dict(config)

    def send(self, config: dict[str, Any], payload: dict[str, Any], ctx: PluginContext) -> dict[str, Any]:
        text = f"{config['prefix']}{payload.get('text', '')}"
        return {"echo": text.upper() if config.get("uppercase") else text, "at": ctx.clock.now().isoformat()}
