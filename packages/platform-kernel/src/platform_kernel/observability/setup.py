"""Stable telemetry names live in docs/modules/observability.md (F21)."""
from __future__ import annotations

import logging
from typing import Any

import structlog
from opentelemetry import metrics, trace

from .. import context as ctxmod

SENSITIVE = ("password", "secret", "token", "authorization", "api_key", "apikey", "cookie", "private_key")
REDACTED = "[redacted]"


def redact(value: Any) -> Any:
    """Remove secrets from nested structures by key name."""
    if isinstance(value, dict):
        return {k: (REDACTED if any(s in str(k).lower() for s in SENSITIVE) else redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(redact(v) for v in value)
    return value


def _context_fields(_: Any, __: str, event: dict[str, Any]) -> dict[str, Any]:
    ctx = ctxmod.maybe_current()
    if ctx is not None:
        event.setdefault("correlation_id", ctx.correlation_id)
        event.setdefault("tenant", ctx.tenant.tenant)
        event.setdefault("actor", ctx.principal.subject)
    span = trace.get_current_span().get_span_context()
    if span.is_valid:
        event.setdefault("trace_id", format(span.trace_id, "032x"))
        event.setdefault("span_id", format(span.span_id, "016x"))
    return event


def _redact(_: Any, __: str, event: dict[str, Any]) -> dict[str, Any]:
    return redact(event)


def configure_logging(service: str, version: str, environment: str, level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _context_fields,
            _redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=False,
    )
    structlog.contextvars.bind_contextvars(service=service, version=version, environment=environment)


def get_logger(name: str = "platform") -> Any:
    return structlog.get_logger(name)


tracer = trace.get_tracer("platform_kernel")
meter = metrics.get_meter("platform_kernel")
