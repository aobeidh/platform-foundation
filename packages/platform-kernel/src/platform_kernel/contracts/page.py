"""Pages are cursor based with an optional total (P6)."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next: str | None = None
    total: int | None = None
