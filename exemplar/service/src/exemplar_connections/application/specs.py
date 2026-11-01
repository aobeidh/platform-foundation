from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConnectionSpec(BaseModel):
    """The governed spec of a connection: which connector plugin, which version, and its configuration."""

    name: str = Field(min_length=1, max_length=80)
    connector: str
    connector_version: str
    config: dict[str, Any] = Field(default_factory=dict)
