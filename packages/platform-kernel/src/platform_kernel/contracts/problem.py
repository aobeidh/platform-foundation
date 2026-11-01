"""RFC 9457 problem details with a stable code and JSON-pointer field errors (P6, P51)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProblemFieldError(BaseModel):
    pointer: str
    code: str
    message: str


class Problem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str | None = None
    instance: str | None = None
    correlation_id: str | None = Field(default=None, alias="correlationId")
    errors: list[ProblemFieldError] = Field(default_factory=list)

    def body(self) -> dict:
        return self.model_dump(by_alias=True, exclude_none=True)
