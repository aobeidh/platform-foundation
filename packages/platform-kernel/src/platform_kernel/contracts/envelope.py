"""CloudEvents 1.0 envelope plus the integration headers of I2. Every event and message uses it."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HistoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    flow: str | None = None
    step: str
    version: int | None = None
    at: datetime


class Envelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    specversion: Literal["1.0"] = "1.0"
    id: str
    source: str
    type: str
    time: datetime
    subject: str | None = None
    datacontenttype: str = "application/json"
    dataschema: str | None = None
    kind: Literal["event", "command", "document"] = "event"
    tenantid: str | None = None
    correlationid: str
    causationid: str | None = None
    replyto: str | None = None
    expiresat: datetime | None = None
    traceparent: str | None = None
    history: tuple[HistoryEntry, ...] = ()
    test: bool = False
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _versioned(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) < 3 or not parts[-1].startswith("v") or not parts[-1][1:].isdigit():
            raise ValueError("type must be dotted and end with a version, for example 'hub.connection.activated.v1'")
        return v

    @field_validator("time", "expiresat")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("timestamps must be timezone aware")
        return v
