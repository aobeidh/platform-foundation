from __future__ import annotations

from typing import Any

from ...domain import Activation


class SqliteActivationRepository:
    """SQLite has no row-level security, so the tenant scope is applied here, in code (P22)."""

    simulated = False

    def add(self, uow: Any, activation: Activation) -> None:
        from platform_kernel.persistence.sqlite import to_text
        from sqlalchemy import text

        uow.connection.execute(text(
            "insert into activations (event_id, connection_id, version, tenant_id, activated_at) "
            "values (:e, :c, :v, :t, :at) on conflict do nothing"),
            {"e": activation.event_id, "c": activation.connection_id, "v": activation.version,
             "t": activation.tenant, "at": to_text(activation.activated_at)})

    def list(self, uow: Any) -> list[Activation]:
        from platform_kernel.persistence.sqlite import from_text, scope_clause, scope_params
        from sqlalchemy import text

        rows = uow.connection.execute(text(f"select * from activations where {scope_clause()} "
                                           "order by activated_at"), scope_params(uow))
        return [Activation(r.connection_id, r.version, r.tenant_id, from_text(r.activated_at), r.event_id)
                for r in rows]
