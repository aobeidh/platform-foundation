from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal

Status = Literal["pending", "running", "stalled", "succeeded", "failed", "cancelled"]
FINISHED = frozenset({"succeeded", "failed", "cancelled"})
# "stalled": a saga compensation failed. Not finished: it is resumed (at startup or by an operator) until it ends.
RESUMABLE = frozenset({"pending", "running", "stalled"})


@dataclass(frozen=True)
class Operation:
    id: str
    kind: str
    tenant: str | None
    status: Status
    input: dict[str, Any]
    created_by: str
    created_at: datetime
    updated_at: datetime
    progress: int = 0
    state: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    cancel_requested: bool = False
    correlation_id: str | None = None
    created_roles: frozenset[str] = frozenset()  # resumed work runs with the creator's roles, not more and not less
    lease_owner: str | None = None  # the runner instance executing it; others may take over once the lease ends
    lease_until: datetime | None = None

    def with_(self, **changes: Any) -> Operation:
        return replace(self, **changes)

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "status": self.status, "progress": self.progress,
                "result": self.result, "error": self.error, "cancelRequested": self.cancel_requested,
                "createdBy": self.created_by, "createdAt": self.created_at.isoformat(),
                "updatedAt": self.updated_at.isoformat()}
