"""OperationStore port with memory and PostgreSQL providers, used inside the caller's unit of work."""
from __future__ import annotations

import json
from typing import Any, Protocol

from .model import RESUMABLE, Operation


class OperationStore(Protocol):
    def get(self, uow: Any, id: str) -> Operation | None: ...
    def get_for_update(self, uow: Any, id: str) -> Operation | None:
        """Read and lock the row until the unit of work ends, so read-modify-write never loses an update."""
        ...
    def save(self, uow: Any, op: Operation) -> None: ...
    def unfinished(self, uow: Any) -> list[Operation]: ...
    def recent(self, uow: Any, limit: int) -> list[Operation]:
        """Newest first, within the unit of work's tenant scope (row-level security in PostgreSQL)."""
        ...


class MemoryOperationStore:
    simulated = True

    def get(self, uow: Any, id: str) -> Operation | None:
        return uow.table("operation").get(id)

    def get_for_update(self, uow: Any, id: str) -> Operation | None:
        return self.get(uow, id)  # the memory unit of work already holds the single writer lock

    def save(self, uow: Any, op: Operation) -> None:
        uow.table("operation")[op.id] = op

    def recent(self, uow: Any, limit: int) -> list[Operation]:
        ops = sorted(uow.table("operation").values(), key=lambda o: o.created_at, reverse=True)
        scope = getattr(uow, "platform_scope", False)
        from .. import context as ctxmod

        ctx = ctxmod.maybe_current()
        if not scope and ctx is not None and not ctx.tenant.platform:
            ops = [o for o in ops if o.tenant == ctx.tenant.tenant]
        return ops[:limit]

    def unfinished(self, uow: Any) -> list[Operation]:
        return sorted((o for o in uow.table("operation").values() if o.status in RESUMABLE),
                      key=lambda o: o.created_at)


def _row(r: Any) -> Operation:
    return Operation(id=r.id, kind=r.kind, tenant=r.tenant_id, status=r.status, input=r.input,
                     created_by=r.created_by, created_at=r.created_at, updated_at=r.updated_at, progress=r.progress,
                     state=r.state or {}, result=r.result, error=r.error, cancel_requested=r.cancel_requested,
                     correlation_id=r.correlation_id, created_roles=frozenset(r.created_roles or []),
                     lease_owner=r.lease_owner, lease_until=r.lease_until)


class PostgresOperationStore:
    simulated = False

    def get(self, uow: Any, id: str) -> Operation | None:
        from sqlalchemy import text

        row = uow.connection.execute(text("select * from operation where id = :i"), {"i": id}).first()
        return _row(row) if row else None

    def get_for_update(self, uow: Any, id: str) -> Operation | None:
        from sqlalchemy import text

        row = uow.connection.execute(text("select * from operation where id = :i for update"), {"i": id}).first()
        return _row(row) if row else None

    def save(self, uow: Any, op: Operation) -> None:
        from sqlalchemy import text

        uow.connection.execute(text(
            "insert into operation (id, kind, tenant_id, status, progress, input, state, result, error, "
            "cancel_requested, created_by, created_roles, correlation_id, lease_owner, lease_until, created_at, "
            "updated_at) values (:id, :kind, :tenant, :status, :progress, cast(:input as jsonb), "
            "cast(:state as jsonb), cast(:result as jsonb), cast(:error as jsonb), :cancel, :by, "
            "cast(:roles as jsonb), :corr, :lo, :lu, :ca, :ua) on conflict (id) do update set "
            "status = excluded.status, progress = excluded.progress, state = excluded.state, "
            "result = excluded.result, error = excluded.error, "
            "cancel_requested = operation.cancel_requested or excluded.cancel_requested, "
            "lease_owner = excluded.lease_owner, lease_until = excluded.lease_until, "
            "updated_at = excluded.updated_at"),
            {"id": op.id, "kind": op.kind, "tenant": op.tenant, "status": op.status, "progress": op.progress,
             "input": json.dumps(op.input, default=str), "state": json.dumps(op.state, default=str),
             "result": json.dumps(op.result, default=str) if op.result is not None else None,
             "error": json.dumps(op.error, default=str) if op.error is not None else None,
             "cancel": op.cancel_requested, "by": op.created_by, "roles": json.dumps(sorted(op.created_roles)),
             "corr": op.correlation_id, "lo": op.lease_owner, "lu": op.lease_until,
             "ca": op.created_at, "ua": op.updated_at})

    def unfinished(self, uow: Any) -> list[Operation]:
        from sqlalchemy import text

        rows = uow.connection.execute(text("select * from operation where status in ('pending', 'running', 'stalled') "
                                           "order by created_at"))
        return [_row(r) for r in rows]

    def recent(self, uow: Any, limit: int) -> list[Operation]:
        from sqlalchemy import text

        rows = uow.connection.execute(text("select * from operation order by created_at desc limit :n"), {"n": limit})
        return [_row(r) for r in rows]
