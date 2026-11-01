from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from platform_kernel.http import Authorizer, DomainException
from platform_kernel.operations import OperationFailed, OperationRunner, accepted

from ...application.use_cases import ListActivations, SendThroughConnection


def router(send: SendThroughConnection, activations: ListActivations, authz: Authorizer,
           operations: OperationRunner | None = None) -> APIRouter:
    r = APIRouter(prefix="/api/v1", tags=["connections"])

    if operations is not None:
        def send_batch(input: dict[str, Any], handle: Any) -> dict[str, Any]:
            payloads = input["payloads"]
            done = handle.state.get("done", 0)
            for i in range(done, len(payloads)):
                handle.check_cancelled()
                result = send(input["id"], payloads[i])
                if not result.ok:
                    raise OperationFailed(result.error.code, result.error.detail)
                handle.save_state({"done": i + 1})
                handle.progress(int(100 * (i + 1) / len(payloads)))
            return {"sent": len(payloads)}

        operations.register("connections.send-batch", send_batch)

        @r.post("/connections/{id}/send-batch", status_code=202,
                dependencies=[Depends(authz.require("connections:use"))],
                summary="Send many payloads through a connection as a long-running operation")
        def send_many(id: str, payloads: list[dict[str, Any]] = Body(..., embed=True, max_length=1000)) -> Any:
            return accepted(operations.start("connections.send-batch", {"id": id, "payloads": payloads}))

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
