"""Generated admin API per governed kind (F11). Mutations need If-Match with the record revision (P6)."""
# No "from __future__ import annotations": FastAPI must see the real spec types at runtime.

from typing import Any

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from ..core import DomainError
from ..http import Authorizer, DomainException
from .engine import GovernanceEngine, GovResult


def _revision(if_match: str | None) -> int:
    if not if_match:
        raise DomainException(DomainError("VALIDATION_FAILED", "Send If-Match with the record revision."))
    value = if_match.strip().removeprefix("W/").strip('"')
    if not value.isdigit():
        raise DomainException(DomainError("VALIDATION_FAILED", "If-Match must be the record revision, like \"3\"."))
    return int(value)


def _respond(result: GovResult, status: int = 200) -> JSONResponse:
    if not result.ok:
        raise DomainException(result.error)
    view = result.value
    return JSONResponse(view.to_json(), status_code=status, headers={"ETag": f'"{view.record.revision}"'})


def governed_router(engine: GovernanceEngine, kind: str, authz: Authorizer, prefix: str = "/api/v1") -> APIRouter:
    k = engine.kind(kind)
    r = APIRouter(prefix=f"{prefix}/{k.plural}", tags=[k.plural])
    read, write, approve = authz.require(k.read), authz.require(k.write), authz.require(k.approve)
    from fastapi import Depends

    @r.get("", dependencies=[Depends(read)], summary=f"List {k.plural}")
    def list_items() -> dict[str, Any]:
        items = [v.to_json() for v in engine.list(kind)]
        return {"items": items, "total": len(items)}

    @r.post("", dependencies=[Depends(write)], status_code=201, summary=f"Create a draft {kind}")
    def create(spec: k.spec = Body(..., embed=True)) -> JSONResponse:  # type: ignore[valid-type]
        return _respond(engine.create(kind, spec.model_dump(mode="json")), 201)

    @r.get("/{id}", dependencies=[Depends(read)], summary=f"Get a {kind}")
    def get(id: str) -> JSONResponse:
        return _respond(engine.get(kind, id))

    @r.get("/{id}/versions", dependencies=[Depends(read)], summary=f"List versions of a {kind}")
    def versions(id: str) -> dict[str, Any]:
        result = engine.versions(kind, id)
        if not result.ok:
            raise DomainException(result.error)
        return {"items": [{"version": v.version, "status": v.status, "spec": v.spec, "createdBy": v.created_by,
                           "submittedBy": v.submitted_by, "approvedBy": v.approved_by} for v in result.value]}

    @r.put("/{id}/draft", dependencies=[Depends(write)], summary=f"Edit the draft of a {kind}")
    def update(id: str, spec: k.spec = Body(..., embed=True),  # type: ignore[valid-type]
               if_match: str | None = Header(default=None)) -> JSONResponse:
        return _respond(engine.update_draft(kind, id, spec.model_dump(mode="json"), _revision(if_match)))

    def action(name: str, dep: Any, fn: Any, needs_reason: bool = False) -> None:
        if needs_reason:
            @r.post(f"/{{id}}/{name}", dependencies=[Depends(dep)], summary=f"{name.capitalize()} a {kind}")
            def with_reason(id: str, reason: str = Body(..., embed=True, min_length=1, max_length=500),
                            if_match: str | None = Header(default=None)) -> JSONResponse:
                return _respond(fn(kind, id, _revision(if_match), reason))
        else:
            @r.post(f"/{{id}}/{name}", dependencies=[Depends(dep)], summary=f"{name.capitalize()} a {kind}")
            def plain(id: str, if_match: str | None = Header(default=None)) -> JSONResponse:
                return _respond(fn(kind, id, _revision(if_match)))

    action("test", write, engine.test)
    action("submit", write, engine.submit)
    action("approve", approve, engine.approve)
    action("reject", approve, engine.reject, needs_reason=True)
    action("pause", write, engine.pause)
    action("resume", write, engine.resume)
    action("retire", write, engine.retire)
    return r
