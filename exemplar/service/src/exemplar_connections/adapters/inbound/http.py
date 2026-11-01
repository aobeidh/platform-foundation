from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from platform_kernel.http import Authorizer, DomainException

from ...application.use_cases import ListActivations, SendThroughConnection


def router(send: SendThroughConnection, activations: ListActivations, authz: Authorizer) -> APIRouter:
    r = APIRouter(prefix="/api/v1", tags=["connections"])

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
