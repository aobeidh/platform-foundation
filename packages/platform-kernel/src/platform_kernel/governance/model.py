"""Governed records: one lifecycle for every configurable artifact (P13, P14, F11).

Version states: draft -> tested -> submitted -> active; active versions are immutable. Editing an active record
creates a new draft version while the active one keeps running. Record states: draft (never activated), active,
paused, retired.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal

from platform_plugin_sdk import Check
from pydantic import BaseModel

VersionStatus = Literal["draft", "tested", "submitted", "active", "superseded", "retired"]
RecordStatus = Literal["draft", "active", "paused", "retired"]
MakerChecker = Literal["always", "never", "policy"]

KindTest = Callable[[BaseModel], list[Check]]


@dataclass(frozen=True)
class GovernedKind:
    """What a product registers. The engine provides everything else."""

    kind: str
    plural: str
    spec: type[BaseModel]
    tests: tuple[KindTest, ...] = ()
    maker_checker: MakerChecker = "policy"
    read: str = ""
    write: str = ""
    approve: str = ""
    display: dict[str, str] = field(default_factory=lambda: {"en": ""})

    def __post_init__(self) -> None:
        if not self.read or not self.write or not self.approve:
            raise ValueError(f"governed kind {self.kind!r} must name read, write and approve capabilities")


@dataclass(frozen=True)
class Version:
    kind: str
    id: str
    version: int
    tenant: str | None
    status: VersionStatus
    spec: dict[str, Any]
    maker_checker: bool
    created_by: str
    created_at: datetime
    submitted_by: str | None = None
    approved_by: str | None = None
    test_result: list[dict[str, Any]] | None = None
    edited_by: tuple[str, ...] = ()

    @property
    def authors(self) -> frozenset[str]:
        """Everyone who shaped this version. None of them may approve it under maker-checker (P14)."""
        return frozenset({self.created_by, *self.edited_by} | ({self.submitted_by} if self.submitted_by else set()))

    def with_(self, **changes: Any) -> Version:
        return replace(self, **changes)


@dataclass(frozen=True)
class Record:
    kind: str
    id: str
    tenant: str | None
    status: RecordStatus
    current_version: int
    active_version: int | None
    revision: int
    created_at: datetime
    updated_at: datetime

    def with_(self, **changes: Any) -> Record:
        return replace(self, **changes)


@dataclass(frozen=True)
class GovernedView:
    record: Record
    current: Version
    active: Version | None

    def to_json(self) -> dict[str, Any]:
        def v(x: Version | None) -> dict[str, Any] | None:
            if x is None:
                return None
            return {"version": x.version, "status": x.status, "spec": x.spec, "createdBy": x.created_by,
                    "submittedBy": x.submitted_by, "approvedBy": x.approved_by, "testResult": x.test_result,
                    "editedBy": list(x.edited_by),
                    "makerChecker": x.maker_checker, "createdAt": x.created_at.isoformat()}

        r = self.record
        return {"id": r.id, "kind": r.kind, "tenant": r.tenant, "status": r.status, "revision": r.revision,
                "currentVersion": r.current_version, "activeVersion": r.active_version,
                "createdAt": r.created_at.isoformat(), "updatedAt": r.updated_at.isoformat(),
                "current": v(self.current), "active": v(self.active)}
