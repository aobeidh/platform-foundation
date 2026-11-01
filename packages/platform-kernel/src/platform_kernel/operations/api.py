"""Operation status API and the 202 helper (P39)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..core import DomainError, Result
from ..http import DomainException
from .model import Operation
from .runner import OperationRunner


def accepted(result: Result[Operation, DomainError], prefix: str = "/api/v1") -> JSONResponse:
    """Answer a request that started an operation: 202 Accepted with Location pointing at its status."""
    if not result.ok:
        raise DomainException(result.error)
    op = result.value
    return JSONResponse(op.to_json(), status_code=202, headers={"Location": f"{prefix}/operations/{op.id}"})


def operations_router(runner: OperationRunner, prefix: str = "/api/v1") -> APIRouter:
    r = APIRouter(prefix=f"{prefix}/operations", tags=["operations"])

    def unwrap(result: Result[Operation, DomainError]) -> dict:
        if not result.ok:
            raise DomainException(result.error)
        return result.value.to_json()

    @r.get("", summary="Long-running operations the caller may see, newest first")
    def list_operations(limit: int = Query(50, ge=1, le=200)) -> dict:
        items = [op.to_json() for op in runner.recent(limit)]
        return {"items": items, "total": len(items)}

    @r.get("/{id}", summary="Status, progress, result or error of a long-running operation")
    def get(id: str) -> dict:
        return unwrap(runner.get(id))

    @r.post("/{id}/cancel", status_code=202, summary="Ask a running operation to stop")
    def cancel(id: str) -> dict:
        return unwrap(runner.cancel(id))

    return r
