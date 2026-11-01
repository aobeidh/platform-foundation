from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..contracts import Problem, ProblemFieldError
from ..core import DomainError


@dataclass(frozen=True)
class CatalogEntry:
    code: str
    status: int
    retryable: bool
    title: str
    remedy: str


class ErrorCatalog:
    def __init__(self, entries: list[CatalogEntry] | None = None) -> None:
        self._entries: dict[str, CatalogEntry] = {}
        for e in entries or []:
            self.add(e)

    def add(self, entry: CatalogEntry) -> None:
        if entry.code in self._entries and self._entries[entry.code] != entry:
            raise ValueError(f"error code {entry.code} defined twice with different content")
        self._entries[entry.code] = entry

    def merge(self, other: ErrorCatalog) -> ErrorCatalog:
        for e in other._entries.values():
            self.add(e)
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> ErrorCatalog:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls([CatalogEntry(code=k, status=int(v["status"]), retryable=bool(v["retryable"]),
                                 title=v["title"], remedy=v["remedy"]) for k, v in data.items()])

    def get(self, code: str) -> CatalogEntry:
        return self._entries.get(code) or self._entries["INTERNAL_ERROR"]

    def __contains__(self, code: str) -> bool:
        return code in self._entries

    def codes(self) -> list[str]:
        return sorted(self._entries)

    def problem(self, error: DomainError, *, correlation_id: str | None = None,
                instance: str | None = None) -> Problem:
        entry = self.get(error.code)
        return Problem(
            title=entry.title, status=entry.status, code=error.code if error.code in self else entry.code,
            detail=error.detail, instance=instance, correlationId=correlation_id,
            errors=[ProblemFieldError(pointer=f.pointer, code=f.code, message=f.message) for f in error.fields],
        )


def kernel_catalog() -> ErrorCatalog:
    return ErrorCatalog.from_yaml(Path(__file__).with_name("kernel_errors.yaml"))
