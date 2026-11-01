from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from platform_kernel.core import DomainError
from platform_kernel.http import Authorizer, DomainException
from platform_kernel.operations import OperationFailed, OperationRunner, accepted

from ...application.use_cases import ActiveVersion, ListActivations, SendThroughConnection


def router(send: SendThroughConnection, activations: ListActivations, authz: Authorizer,
           operations: OperationRunner | None = None, active: ActiveVersion | None = None) -> APIRouter:
    r = APIRouter(prefix="/api/v1", tags=["connections"])

    if operations is not None:
        def send_batch(input: dict[str, Any], handle: Any) -> dict[str, Any]:
            """At-least-once: a crash between a send and its saved step re-sends that one payload after resume,
            so connectors behind batches must tolerate a repeat. The version is pinned at start: if the connection
            is paused, retired or approved at a new version, the batch stops and says how far it got."""
            payloads, version = input["payloads"], input["version"]
            done = handle.state.get("done", 0)
            for i in range(done, len(payloads)):
                handle.check_cancelled()
                result = send(input["id"], payloads[i], version)
                if not result.ok:
                    raise OperationFailed(result.error.code,
                                          f"{result.error.detail} {i} of {len(payloads)} payloads were sent.")
                handle.step({"done": i + 1}, int(100 * (i + 1) / len(payloads)))
            return {"sent": len(payloads)}

        operations.register("connections.send-batch", send_batch)

        @r.post("/connections/{id}/send-batch", status_code=202,
                dependencies=[Depends(authz.require("connections:use"))],
                summary="Send many payloads through a connection as a long-running operation")
        def send_many(id: str, payloads: list[dict[str, Any]] = Body(..., embed=True, min_length=1,
                                                                       max_length=1000)) -> Any:
            if active is None:
                raise DomainException(DomainError("CONNECTION_NOT_ACTIVE", "Batches need the active version."))
            version = active(id)  # answer now, not later in the background
            if not version.ok:
                raise DomainException(version.error)
            return accepted(operations.start("connections.send-batch",
                                             {"id": id, "version": version.value, "payloads": payloads}))

    @r.post("/connections/{id}/send", dependencies=[Depends(authz.require("connections:use"))],
            summary="Send a payload through the active version of a connection")
    def send_payload(id: str, payload: dict[str, Any] = Body(..., embed=True)) -> dict[str, Any]:
        result = send(id, payload)
        if not result.ok:
            raise DomainException(result.error)
        return {"result": result.value}

    @r.get("/activations", dependencies=[Depends(authz.require("connections:read"))],
           summary="List connection activations recorded from approval events")
    def list_activations() -> dict[str, Any]:
        items = [{"connectionId": a.connection_id, "version": a.version, "tenant": a.tenant,
                  "activatedAt": a.activated_at.isoformat(), "eventId": a.event_id} for a in activations()]
        return {"items": items, "total": len(items)}

    return r
