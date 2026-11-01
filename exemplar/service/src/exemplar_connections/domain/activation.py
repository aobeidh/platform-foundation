from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class ConnectionNotActive(Exception):
    def __init__(self, connection_id: str) -> None:
        super().__init__(f"connection {connection_id} is not active")
        self.connection_id = connection_id


@dataclass(frozen=True)
class Activation:
    """A record that a connection version went live. Created once per approval event."""

    connection_id: str
    version: int
    tenant: str | None
    activated_at: datetime
    event_id: str

    @classmethod
    def from_event(cls, data: dict, tenant: str | None, at: datetime, event_id: str) -> Activation:
        if "id" not in data or "activeVersion" not in data:
            raise ValueError("approval event must carry id and activeVersion")
        return cls(str(data["id"]), int(data["activeVersion"]), tenant, at, event_id)
