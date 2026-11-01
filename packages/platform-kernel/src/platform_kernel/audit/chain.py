"""The audit chain format. hash = SHA-256 over canonical JSON of the record without its hash (spec/audit)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Protocol

GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    stream: str
    action: str
    subject: str
    actor: str
    at: datetime
    on_behalf_of: str | None = None
    tenant: str | None = None
    reason: str | None = None
    correlation_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


@dataclass(frozen=True)
class AuditRecord:
    seq: int
    entry: AuditEntry
    prev_hash: str
    hash: str


def _canonical(seq: int, entry: AuditEntry, prev_hash: str) -> bytes:
    body = asdict(entry)
    body["at"] = entry.at.isoformat()
    body.update({"seq": seq, "prev_hash": prev_hash})
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()


def link(seq: int, entry: AuditEntry, prev_hash: str) -> AuditRecord:
    return AuditRecord(seq, entry, prev_hash, hashlib.sha256(_canonical(seq, entry, prev_hash)).hexdigest())


def verify_chain(records: list[AuditRecord]) -> tuple[bool, int | None]:
    """Returns (ok, first_bad_seq)."""
    prev = GENESIS
    for i, rec in enumerate(records, start=1):
        if rec.seq != i or rec.prev_hash != prev or link(rec.seq, rec.entry, rec.prev_hash).hash != rec.hash:
            return False, rec.seq
        prev = rec.hash
    return True, None


class AuditTrail(Protocol):
    def append(self, entry: AuditEntry) -> AuditRecord: ...
    def records(self, stream: str) -> list[AuditRecord]: ...


class MemoryAuditTrail:
    def __init__(self) -> None:
        self._streams: dict[str, list[AuditRecord]] = {}

    def append(self, entry: AuditEntry) -> AuditRecord:
        stream = self._streams.setdefault(entry.stream, [])
        prev = stream[-1].hash if stream else GENESIS
        rec = link(len(stream) + 1, entry, prev)
        stream.append(rec)
        return rec

    def records(self, stream: str) -> list[AuditRecord]:
        return list(self._streams.get(stream, []))
