"""GovernedStore port with memory and PostgreSQL providers. Both run inside the caller's unit of work."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Protocol

from ..core import ConcurrencyConflict
from .model import Record, Version


class GovernedStore(Protocol):
    def get(self, uow: Any, kind: str, id: str) -> Record | None: ...
    def list(self, uow: Any, kind: str, tenant: str | None, platform: bool) -> list[Record]: ...
    def versions(self, uow: Any, kind: str, id: str) -> list[Version]: ...
    def version(self, uow: Any, kind: str, id: str, number: int) -> Version | None: ...
    def insert(self, uow: Any, record: Record, version: Version) -> None: ...
    def save_record(self, uow: Any, record: Record, expected_revision: int) -> None: ...
    def save_version(self, uow: Any, version: Version) -> None: ...


class MemoryGovernedStore:
    simulated = True

    def get(self, uow: Any, kind: str, id: str) -> Record | None:
        return uow.table("governed_record").get((kind, id))

    def list(self, uow: Any, kind: str, tenant: str | None, platform: bool) -> list[Record]:
        rows = [r for (k, _), r in uow.table("governed_record").items() if k == kind]
        if not platform:
            rows = [r for r in rows if r.tenant == tenant]
        return sorted(rows, key=lambda r: r.created_at)

    def versions(self, uow: Any, kind: str, id: str) -> list[Version]:
        return sorted((v for (k, i, _), v in uow.table("governed_version").items() if k == kind and i == id),
                      key=lambda v: v.version)

    def version(self, uow: Any, kind: str, id: str, number: int) -> Version | None:
        return uow.table("governed_version").get((kind, id, number))

    def insert(self, uow: Any, record: Record, version: Version) -> None:
        records = uow.table("governed_record")
        if (record.kind, record.id) in records:
            raise ConcurrencyConflict(f"{record.kind} {record.id}", 0, records[(record.kind, record.id)].revision)
        records[(record.kind, record.id)] = record
        self.save_version(uow, version)

    def save_record(self, uow: Any, record: Record, expected_revision: int) -> None:
        records = uow.table("governed_record")
        current = records[(record.kind, record.id)]
        if current.revision != expected_revision:
            raise ConcurrencyConflict(f"{record.kind} {record.id}", expected_revision, current.revision)
        records[(record.kind, record.id)] = record

    def save_version(self, uow: Any, version: Version) -> None:
        # Mirror of the database constraint maker_checker_second_person (P14: enforced twice).
        if version.maker_checker and version.approved_by and version.approved_by in version.authors:
            raise PermissionError("maker-checker: the approver must not have authored, edited or submitted it")
        uow.table("governed_version")[(version.kind, version.id, version.version)] = version


def _record(row: Any) -> Record:
    return Record(kind=row.kind, id=row.id, tenant=row.tenant_id, status=row.status,
                  current_version=row.current_version, active_version=row.active_version, revision=row.revision,
                  created_at=row.created_at, updated_at=row.updated_at)


def _version(row: Any) -> Version:
    return Version(kind=row.kind, id=row.id, version=row.version, tenant=row.tenant_id, status=row.status,
                   spec=row.spec, maker_checker=row.maker_checker, created_by=row.created_by,
                   created_at=row.created_at, submitted_by=row.submitted_by, approved_by=row.approved_by,
                   test_result=row.test_result, edited_by=tuple(row.edited_by or ()))


class PostgresGovernedStore:
    """Row-level security on both tables applies the tenant scope a second time (P22)."""

    simulated = False

    def get(self, uow: Any, kind: str, id: str) -> Record | None:
        from sqlalchemy import text

        row = uow.connection.execute(text("select * from governed_record where kind = :k and id = :i"),
                                     {"k": kind, "i": id}).first()
        return _record(row) if row else None

    def list(self, uow: Any, kind: str, tenant: str | None, platform: bool) -> list[Record]:
        from sqlalchemy import text

        sql = "select * from governed_record where kind = :k"
        params: dict[str, Any] = {"k": kind}
        if not platform:
            sql += " and tenant_id = :t"
            params["t"] = tenant
        return [_record(r) for r in uow.connection.execute(text(sql + " order by created_at"), params)]

    def versions(self, uow: Any, kind: str, id: str) -> list[Version]:
        from sqlalchemy import text

        rows = uow.connection.execute(text("select * from governed_version where kind = :k and id = :i "
                                           "order by version"), {"k": kind, "i": id})
        return [_version(r) for r in rows]

    def version(self, uow: Any, kind: str, id: str, number: int) -> Version | None:
        from sqlalchemy import text

        row = uow.connection.execute(text("select * from governed_version where kind = :k and id = :i "
                                          "and version = :v"), {"k": kind, "i": id, "v": number}).first()
        return _version(row) if row else None

    def insert(self, uow: Any, record: Record, version: Version) -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        try:
            uow.connection.execute(text(
                "insert into governed_record (kind, id, tenant_id, status, current_version, active_version, "
                "revision, created_at, updated_at) values (:kind, :id, :tenant, :status, :cv, :av, :rev, :ca, :ua)"),
                self._record_params(record))
        except IntegrityError as exc:
            # The same answer whether the clashing record is visible to this tenant or not: no id oracle.
            raise ConcurrencyConflict(f"{record.kind} {record.id}", 0, 1) from exc
        self.save_version(uow, version)

    @staticmethod
    def _record_params(r: Record) -> dict[str, Any]:
        return {"kind": r.kind, "id": r.id, "tenant": r.tenant, "status": r.status, "cv": r.current_version,
                "av": r.active_version, "rev": r.revision, "ca": r.created_at, "ua": r.updated_at}

    def save_record(self, uow: Any, record: Record, expected_revision: int) -> None:
        from sqlalchemy import text

        params = self._record_params(record) | {"expected": expected_revision}
        result = uow.connection.execute(text(
            "update governed_record set status = :status, current_version = :cv, active_version = :av, "
            "revision = :rev, updated_at = :ua where kind = :kind and id = :id and revision = :expected"), params)
        if result.rowcount != 1:
            raise ConcurrencyConflict(f"{record.kind} {record.id}", expected_revision, -1)

    def save_version(self, uow: Any, version: Version) -> None:
        from sqlalchemy import text

        uow.connection.execute(text(
            "insert into governed_version (kind, id, version, tenant_id, status, spec, maker_checker, created_by, "
            "submitted_by, approved_by, test_result, edited_by, created_at) values (:kind, :id, :v, :tenant, "
            ":status, cast(:spec as jsonb), :mc, :cb, :sb, :ab, cast(:tr as jsonb), :eb, :ca) "
            "on conflict (kind, id, version) do update set status = excluded.status, spec = excluded.spec, "
            "submitted_by = excluded.submitted_by, approved_by = excluded.approved_by, "
            "test_result = excluded.test_result, edited_by = excluded.edited_by"),
            {"kind": version.kind, "id": version.id, "v": version.version, "tenant": version.tenant,
             "status": version.status, "spec": json.dumps(version.spec, default=str), "mc": version.maker_checker,
             "cb": version.created_by, "sb": version.submitted_by, "ab": version.approved_by,
             "tr": json.dumps(version.test_result) if version.test_result is not None else None,
             "eb": list(version.edited_by),
             "ca": version.created_at if isinstance(version.created_at, datetime) else version.created_at})
