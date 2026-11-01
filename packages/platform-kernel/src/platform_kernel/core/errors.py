"""Domain errors carry a stable catalog code (P51) and a plain-language detail."""
from __future__ import annotations

from dataclasses import dataclass, field

from platform_plugin_sdk import FieldError


@dataclass(frozen=True)
class DomainError:
    code: str
    detail: str
    fields: tuple[FieldError, ...] = field(default=())


class ConcurrencyConflict(Exception):
    """Raised by repositories when the expected revision is stale."""

    def __init__(self, subject: str, expected: int, actual: int) -> None:
        super().__init__(f"{subject}: expected revision {expected}, found {actual}")
        self.subject, self.expected, self.actual = subject, expected, actual


class NotFound(Exception):
    def __init__(self, subject: str) -> None:
        super().__init__(f"{subject} not found")
        self.subject = subject


__all__ = ["ConcurrencyConflict", "DomainError", "FieldError", "NotFound"]
