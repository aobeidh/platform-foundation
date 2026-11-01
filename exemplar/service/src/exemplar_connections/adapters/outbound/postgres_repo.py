from __future__ import annotations

from typing import Any

from ...domain import Activation


class PostgresActivationRepository:
    """Row-level security on the activations table applies tenant scope a second time (P22)."""

    simulated = False

    def add(self, uow: Any, activation: Activation) -> None:
        from sqlalchemy import text

        uow.connection.execute(text(
            "insert into activations (event_id, connection_id, version, tenant_id, activated_at) "
            "values (:e, :c, :v, :t, :at) on conflict do nothing"),
            {"e": activation.event_id, "c": activation.connection_id, "v": activation.version,
             "t": activation.tenant, "at": activation.activated_at})

    def list(self, uow: Any) -> list[Activation]:
        from sqlalchemy import text

        rows = uow.connection.execute(text("select * from activations order by activated_at"))
        return [Activation(r.connection_id, r.version, r.tenant_id, r.activated_at, r.event_id) for r in rows]
