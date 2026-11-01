from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .. import context as ctxmod
from ..context import Principal, RequestContext, TenantScope
from ..contracts import Envelope
from ..core import new_id
from ..observability import get_logger
from ..persistence import OutboxReader, UnitOfWork, UnitOfWorkFactory

log = get_logger("platform.messaging")

Handler = Callable[[Envelope, UnitOfWork], None]


class InvalidMessage(Exception):
    """Raised by a handler when the message itself is wrong. Goes to the invalid channel, never retried (I7)."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5


def make_event(type: str, data: dict[str, Any], *, source: str, subject: str | None = None,
               now: datetime | None = None) -> Envelope:
    """Build an envelope that carries the current request context (F8)."""
    ctx = ctxmod.maybe_current()
    return Envelope(
        id=new_id(), source=source, type=type, time=now or datetime.now(UTC), subject=subject,
        tenantid=ctx.tenant.tenant if ctx else None,
        correlationid=ctx.correlation_id if ctx else new_id(),
        causationid=ctx.causation_id if ctx else None,
        traceparent=ctx.traceparent if ctx else None,
        test=ctx.test if ctx else False,
        data=data,
    )


class Transport(Protocol):
    def send(self, envelope: Envelope) -> None: ...


@dataclass
class _Subscription:
    consumer: str
    type: str
    handler: Handler
    retry: RetryPolicy


class ConsumerRuntime:
    """Runs handlers with the envelope's context rebuilt, inside a unit of work, exactly once per consumer."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow
        self._subs: list[_Subscription] = []
        self._attempts: dict[tuple[str, str], int] = {}

    def subscribe(self, type: str, consumer: str, handler: Handler, retry: RetryPolicy | None = None) -> None:
        self._subs.append(_Subscription(consumer, type, handler, retry or RetryPolicy()))

    def consumer(self, type: str, consumer: str, retry: RetryPolicy | None = None) -> Callable[[Handler], Handler]:
        def register(fn: Handler) -> Handler:
            self.subscribe(type, consumer, fn, retry)
            return fn
        return register

    def types(self) -> set[str]:
        return {s.type for s in self._subs}

    def _context(self, env: Envelope) -> RequestContext:
        return RequestContext(
            principal=Principal(subject=f"consumer:{env.source}", kind="service", tenant=env.tenantid),
            tenant=TenantScope(env.tenantid), correlation_id=env.correlationid, causation_id=env.id,
            traceparent=env.traceparent, deadline=datetime.now(UTC) + timedelta(seconds=60), test=env.test)

    def deliver(self, env: Envelope) -> bool:
        """Returns True when every subscriber has finished with the message (processed or dead-lettered)."""
        done = True
        for sub in [s for s in self._subs if s.type == env.type]:
            if env.expiresat is not None and env.expiresat <= datetime.now(UTC):
                with ctxmod.use(self._context(env)), self._uow() as uow:
                    if uow.inbox.first_time(sub.consumer, env.id):
                        uow.dead_letters.add(sub.consumer, "dead", "EXPIRED", env)
                continue
            key = (sub.consumer, env.id)
            try:
                with ctxmod.use(self._context(env)), self._uow() as uow:
                    if not uow.inbox.first_time(sub.consumer, env.id):
                        continue
                    sub.handler(env, uow)
                self._attempts.pop(key, None)
            except InvalidMessage as exc:
                with ctxmod.use(self._context(env)), self._uow() as uow:
                    if uow.inbox.first_time(sub.consumer, env.id):
                        uow.dead_letters.add(sub.consumer, "invalid", str(exc) or "INVALID", env)
                log.warning("message.invalid", consumer=sub.consumer, event_id=env.id, reason=str(exc))
            except Exception as exc:  # noqa: BLE001 - classified as retryable
                attempts = self._attempts.get(key, 0) + 1
                self._attempts[key] = attempts
                if attempts >= sub.retry.max_attempts:
                    with ctxmod.use(self._context(env)), self._uow() as uow:
                        if uow.inbox.first_time(sub.consumer, env.id):
                            uow.dead_letters.add(sub.consumer, "dead", f"RETRIES_EXHAUSTED: {exc}", env)
                    self._attempts.pop(key, None)
                    log.warning("message.dead", consumer=sub.consumer, event_id=env.id, error=str(exc))
                else:
                    done = False
                    log.info("message.retry", consumer=sub.consumer, event_id=env.id, attempt=attempts)
        return done


class LocalTransport:
    """In-process transport: hands each envelope to the consumer runtimes registered with it."""

    simulated = False

    def __init__(self, runtimes: list[ConsumerRuntime] | None = None) -> None:
        self.runtimes = list(runtimes or [])

    def send(self, envelope: Envelope) -> None:
        if not all(rt.deliver(envelope) for rt in self.runtimes):
            raise RuntimeError("at least one consumer will retry this message")


class PollingRelay:
    """Delivers unsent outbox rows in order. Run one relay per service schema in 0.1."""

    def __init__(self, reader: OutboxReader, transport: Transport) -> None:
        self._reader, self._transport = reader, transport

    def run_once(self, batch: int = 100) -> int:
        sent: list[str] = []
        for row in self._reader.claim(batch):
            try:
                self._transport.send(row.envelope)
                sent.append(row.id)
            except Exception as exc:  # noqa: BLE001
                self._reader.mark_failed(row.id, str(exc))
                break  # keep per-relay order: stop at the first failure and retry next run
        self._reader.mark_sent(sent)
        return len(sent)
