"""ExpressionEngine port. Expressions are compiled at design time (syntax and field references checked against the
input schema) and evaluated at run time inside limits on time, depth, steps and output size (P15, ADR 0001)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..core import DomainError, Err, Ok, Result


@dataclass(frozen=True)
class Limits:
    timeout_ms: int = 100
    max_depth: int = 100
    max_steps: int = 100_000
    max_output_bytes: int = 1_048_576
    allow_regex: bool = False  # regex runs in Python's `re` and cannot be interrupted, so it is opt-in
    allow_eval: bool = False  # `$eval` runs code built at run time, beyond the compile-time checks


@dataclass(frozen=True)
class Compiled:
    language: str
    text: str
    handle: Any = field(compare=False, repr=False)
    references: frozenset[str] = frozenset()
    warnings: tuple[str, ...] = ()
    uses_regex: bool = False


class ExpressionEngine(Protocol):
    language: str

    def compile(self, text: str, input_schema: dict[str, Any] | None = None,
                limits: Limits | None = None) -> Result[Compiled, DomainError]: ...

    def evaluate(self, compiled: Compiled, data: Any, bindings: dict[str, Any] | None = None,
                 limits: Limits | None = None) -> Result[Any, DomainError]: ...


class ExpressionRegistry:
    """Several languages can run side by side; a stored expression names its language (ADR 0001)."""

    def __init__(self, engines: list[ExpressionEngine], default: str) -> None:
        self._engines = {e.language: e for e in engines}
        if default not in self._engines:
            raise ValueError(f"default expression language {default!r} has no engine; have {sorted(self._engines)}")
        self.default = default

    def languages(self) -> list[str]:
        return sorted(self._engines)

    def get(self, language: str | None = None) -> Result[ExpressionEngine, DomainError]:
        name = language or self.default
        engine = self._engines.get(name)
        if engine is None:
            return Err(DomainError("EXPRESSION_LANGUAGE_UNKNOWN", f"No engine for expression language {name!r}."))
        return Ok(engine)

    def compile(self, text: str, language: str | None = None, input_schema: dict[str, Any] | None = None,
                limits: Limits | None = None) -> Result[Compiled, DomainError]:
        engine = self.get(language)
        return engine.value.compile(text, input_schema, limits) if engine.ok else engine

    def evaluate(self, compiled: Compiled, data: Any, bindings: dict[str, Any] | None = None,
                 limits: Limits | None = None) -> Result[Any, DomainError]:
        engine = self.get(compiled.language)
        return engine.value.evaluate(compiled, data, bindings, limits) if engine.ok else engine
