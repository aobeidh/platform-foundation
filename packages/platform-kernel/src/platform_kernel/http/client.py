"""Outbound HTTP. Every call passes the egress policy (P23) and the shared resilience policy (P26), and never waits
longer than the request's remaining deadline (F10). Plugins receive only an egress-bound client (P12)."""
from __future__ import annotations

import ipaddress
import random
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from .. import context as ctxmod
from ..core import DomainError
from ..observability import meter

_client_duration = meter.create_histogram("http.client.duration", unit="ms", description="Outbound HTTP duration")

IDEMPOTENT = {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}


class OutboundError(Exception):
    def __init__(self, error: DomainError) -> None:
        super().__init__(error.detail)
        self.error = error


Resolver = Callable[[str], list[str]]


def system_resolver(host: str) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


@dataclass(frozen=True)
class EgressPolicy:
    """Allowlist of hosts (exact, or '*.example.com'), TLS only, private and reserved addresses refused after DNS
    resolution, no redirects, size and time limits. `allow_private` lists hosts allowed to resolve privately (for
    internal services); `allow_plain_http` lists hosts allowed without TLS (local development only)."""

    allowlist: tuple[str, ...] = ()
    allow_private: tuple[str, ...] = ()
    allow_plain_http: tuple[str, ...] = ()
    max_response_bytes: int = 10 * 1024 * 1024
    resolver: Resolver = field(default=system_resolver, compare=False)

    @staticmethod
    def _match(host: str, patterns: tuple[str, ...]) -> bool:
        host = host.lower().rstrip(".")
        for p in patterns:
            p = p.lower()
            if p.startswith("*.") and (host.endswith(p[1:]) and host != p[2:]):
                return True
            if host == p:
                return True
        return False

    def check(self, url: str) -> list[str]:
        """Validate the URL and return the addresses the call may use (empty when DNS is not checked)."""
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.scheme not in ("https", "http"):
            raise OutboundError(DomainError("EGRESS_BLOCKED", f"Scheme {parts.scheme!r} is not allowed."))
        if parts.scheme == "http" and not self._match(host, self.allow_plain_http):
            raise OutboundError(DomainError("EGRESS_BLOCKED", f"Plain HTTP to {host} is not allowed; use HTTPS."))
        if not self._match(host, self.allowlist):
            raise OutboundError(DomainError("EGRESS_BLOCKED", f"Host {host} is not on the egress allowlist."))
        if self._match(host, self.allow_private):
            return []
        try:
            addresses = self.resolver(host)
        except OSError as exc:
            raise OutboundError(DomainError("DEPENDENCY_UNAVAILABLE", f"Could not resolve {host}: {exc}.")) from exc
        if not addresses:
            raise OutboundError(DomainError("DEPENDENCY_UNAVAILABLE", f"{host} resolved to no address."))
        for a in addresses:
            ip = ipaddress.ip_address(a)
            # `is_global` also rejects carrier-grade NAT (100.64.0.0/10) and other non-public ranges.
            if not ip.is_global or ip.is_multicast:
                raise OutboundError(DomainError("EGRESS_BLOCKED", f"Host {host} resolves to a non-public address."))
        return addresses


@dataclass(frozen=True)
class Retry:
    max_attempts: int = 3
    on_status: tuple[int, ...] = (502, 503, 504)
    base_delay: float = 0.1
    max_delay: float = 2.0


class CircuitBreaker:
    """Opens after `failures` consecutive failures, stays open for `open_seconds`, then lets one trial through."""

    def __init__(self, failures: int = 5, open_seconds: float = 20.0, clock: Callable[[], float] = time.monotonic):
        self._limit, self._open_for, self._clock = failures, open_seconds, clock
        self._count, self._opened_at, self._lock = 0, None, threading.Lock()
        self._trial_in_flight = False

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if self._clock() - self._opened_at < self._open_for:
                return False
            # Half-open: exactly one trial call at a time; everyone else is refused until it reports back.
            if self._trial_in_flight:
                return False
            self._trial_in_flight = True
            return True

    def success(self) -> None:
        with self._lock:
            self._count, self._opened_at, self._trial_in_flight = 0, None, False

    def failure(self) -> None:
        with self._lock:
            self._count += 1
            if self._trial_in_flight or self._count >= self._limit:
                self._opened_at = self._clock()
            self._trial_in_flight = False

    @property
    def open(self) -> bool:
        return self._opened_at is not None


class ResilientClient:
    """One client per named dependency. Propagates correlation, trace and deadline headers (F8, F10)."""

    def __init__(self, name: str, base_url: str, *, egress: EgressPolicy, timeout: float = 5.0,
                 retry: Retry | None = None, breaker: CircuitBreaker | None = None, max_concurrent: int = 50,
                 auth: Callable[[], str | None] | None = None, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.name, self.base_url = name, base_url.rstrip("/")
        self.egress, self.timeout = egress, timeout
        self.retry, self.breaker = retry or Retry(), breaker or CircuitBreaker()
        self._bulkhead = threading.BoundedSemaphore(max_concurrent)
        self._auth, self._sleep = auth, sleep
        self._http = httpx.Client(follow_redirects=False, transport=transport)

    def _budget(self) -> float:
        ctx = ctxmod.maybe_current()
        if ctx is None:
            return self.timeout
        left = (ctx.deadline - datetime.now(UTC)).total_seconds()
        if left <= 0:
            raise OutboundError(DomainError("DEADLINE_EXCEEDED", f"No time left to call {self.name}."))
        return min(self.timeout, left)

    def _headers(self, extra: dict[str, str] | None) -> dict[str, str]:
        h = dict(extra or {})
        ctx = ctxmod.maybe_current()
        if ctx is not None:
            h.setdefault("X-Correlation-Id", ctx.correlation_id)
            h.setdefault("Request-Deadline", ctx.deadline.isoformat())
            if ctx.traceparent:
                h.setdefault("traceparent", ctx.traceparent)
        if self._auth is not None:
            token = self._auth()
            if token:
                h.setdefault("Authorization", f"Bearer {token}")
        return h

    def request(self, method: str, path_or_url: str, **kwargs: Any) -> httpx.Response:
        method = method.upper()
        url = path_or_url if "://" in path_or_url else f"{self.base_url}/{path_or_url.lstrip('/')}"
        addresses = self.egress.check(url)
        headers = self._headers(kwargs.pop("headers", None))
        retryable = method in IDEMPOTENT or "Idempotency-Key" in headers
        if not self._bulkhead.acquire(timeout=0.05):
            raise OutboundError(DomainError("DEPENDENCY_UNAVAILABLE", f"Too many concurrent calls to {self.name}."))
        try:
            attempt = 0
            while True:
                attempt += 1
                if not self.breaker.allow():
                    raise OutboundError(DomainError("DEPENDENCY_UNAVAILABLE", f"{self.name} is failing; circuit open."))
                started = time.perf_counter()
                try:
                    response = self._send(method, url, headers, self._budget(), dict(kwargs), addresses)
                except httpx.TransportError as exc:
                    self.breaker.failure()
                    if retryable and attempt < self.retry.max_attempts and self._backoff(attempt):
                        continue
                    raise OutboundError(DomainError("DEPENDENCY_UNAVAILABLE", f"{self.name} unreachable: {exc}.")) \
                        from exc
                finally:
                    _client_duration.record((time.perf_counter() - started) * 1000, {"dependency": self.name})
                if response.status_code in self.retry.on_status:
                    self.breaker.failure()
                    if retryable and attempt < self.retry.max_attempts and self._backoff(attempt):
                        continue
                    return response
                self.breaker.success()
                return response
        finally:
            self._bulkhead.release()

    def _send(self, method: str, url: str, headers: dict[str, str], budget: float, kwargs: dict,
              addresses: list[str]) -> httpx.Response:
        extensions = dict(kwargs.pop("extensions", None) or {})
        target = httpx.URL(url)
        if addresses:
            # Connect to the address that passed the egress check, so DNS cannot change between check and connect.
            # TLS still verifies the certificate against the original host name (SNI).
            ip = ipaddress.ip_address(addresses[0])
            host = target.host
            target = target.copy_with(host=str(ip))
            headers = {**headers, "Host": host if target.port is None else f"{host}:{target.port}"}
            extensions.setdefault("sni_hostname", host)
        deadline = time.monotonic() + budget
        with self._http.stream(method, target, headers=headers, timeout=budget, extensions=extensions,
                               **kwargs) as r:
            chunks, size = [], 0
            for chunk in r.iter_bytes():
                size += len(chunk)
                if size > self.egress.max_response_bytes:
                    raise OutboundError(DomainError("PAYLOAD_TOO_LARGE", f"Response from {self.name} is too large."))
                if time.monotonic() > deadline:
                    # httpx timeouts apply per phase; this bounds the whole call (F10).
                    raise OutboundError(DomainError("DEADLINE_EXCEEDED", f"{self.name} did not finish in time."))
                chunks.append(chunk)
            return httpx.Response(r.status_code, headers=r.headers, content=b"".join(chunks), request=r.request)

    def _backoff(self, attempt: int) -> bool:
        delay = random.uniform(0, min(self.retry.max_delay, self.retry.base_delay * 2 ** (attempt - 1)))
        ctx = ctxmod.maybe_current()
        if ctx is not None and (ctx.deadline - datetime.now(UTC)).total_seconds() <= delay:
            return False
        self._sleep(delay)
        return True

    def close(self) -> None:
        self._http.close()
