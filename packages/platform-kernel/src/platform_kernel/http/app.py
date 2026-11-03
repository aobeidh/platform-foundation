"""App factory. One pure ASGI middleware applies the platform stack in a fixed order (F7):

1 correlation id, 2 tracing span, 3 deadline, 4 body size limit, 5 authentication and context, 6 tenant scope,
7 idempotency for unsafe methods, 8 problem details for every error, 9 metrics.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

from .. import context as ctxmod
from ..context import ANONYMOUS, RequestContext, TenantScope, reserved
from ..contracts import Problem
from ..core import ConcurrencyConflict, DomainError, FieldError, NotFound, new_id
from ..errors import ErrorCatalog
from ..identity import TokenVerifier
from ..observability import get_logger, meter, tracer
from ..persistence import IdempotencyStore

log = get_logger("platform.http")
_requests = meter.create_counter("http.server.requests", description="HTTP requests by route and status")
_duration = meter.create_histogram("http.server.duration", unit="ms", description="HTTP request duration")

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
PUBLIC_PATHS = frozenset({"/health/live", "/health/ready", "/openapi.json", "/docs", "/docs/oauth2-redirect",
                          "/redoc"})
REPLAY_HEADERS = ("etag", "location", "content-type")


KERNEL_PREFIXES = ("/api/", "/health/", "/docs", "/redoc", "/openapi.json")


def route_path(scope: dict) -> str:
    """The path the router matches: the request path without the app's root path (a mount, or a proxy prefix)."""
    path, root = scope["path"], scope.get("root_path", "")
    if not root or not path.startswith(root):
        return path
    if path == root:
        return "/"
    return path[len(root):] if path[len(root)] == "/" else path


def is_public(path: str) -> bool:
    """The kernel's public paths match exactly: a prefix match would let '/docs-admin' skip authentication."""
    return path in PUBLIC_PATHS


class DomainException(Exception):
    """Raise from routers to return a catalogued problem."""

    def __init__(self, error: DomainError) -> None:
        super().__init__(error.detail)
        self.error = error


@dataclass
class HttpSettings:
    service: str
    request_timeout: timedelta = timedelta(seconds=10)
    max_body_bytes: int = 1_048_576
    simulated: list[str] = field(default_factory=list)
    production: bool = False


def problem_response(catalog: ErrorCatalog, error: DomainError, *, instance: str | None = None,
                     headers: dict[str, str] | None = None) -> JSONResponse:
    ctx = ctxmod.maybe_current()
    p = catalog.problem(error, correlation_id=ctx.correlation_id if ctx else None, instance=instance)
    return JSONResponse(p.body(), status_code=p.status, media_type="application/problem+json", headers=headers)


def _parse_deadline(value: str | None, default: timedelta, now: datetime) -> datetime:
    limit = now + default
    if not value:
        return limit
    try:
        requested = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if requested.tzinfo is None:
            return limit
    except ValueError:
        return limit
    return min(requested, limit)


class PlatformMiddleware:
    def __init__(self, app: Any, *, settings: HttpSettings, verifier: TokenVerifier, catalog: ErrorCatalog,
                 idempotency: IdempotencyStore | None, routes: list[Any] | None = None,
                 public_routes: frozenset[int] = frozenset()) -> None:
        self.app, self.s, self.verifier, self.catalog, self.idem = app, settings, verifier, catalog, idempotency
        self._routes, self._public = routes if routes is not None else [], public_routes

    def _is_public(self, scope: dict) -> bool:
        """Public when the kernel's own public path is asked for exactly, or when the route the router will run is one
        the app declared public. Deciding by the route, not the path's text, means a protected route that matches the
        path first keeps its authentication, and a mount or a root path cannot make another route public."""
        if is_public(route_path(scope)):
            return True
        if not self._public:
            return False
        for route in self._routes:
            match, _ = route.matches(scope)
            if match is Match.FULL:
                return id(route) in self._public
        return False

    async def _send_problem(self, send: Any, error: DomainError, correlation_id: str,
                            extra: dict[str, str] | None = None) -> None:
        entry = self.catalog.get(error.code)
        body = Problem(title=entry.title, status=entry.status, code=error.code if error.code in self.catalog
                       else entry.code, detail=error.detail, correlationId=correlation_id).body()
        await self._send_json(send, entry.status, body, correlation_id, "application/problem+json", extra)

    async def _send_json(self, send: Any, status: int, body: Any, correlation_id: str,
                         media: str = "application/json", extra: dict[str, str] | None = None) -> None:
        raw = json.dumps(body, default=str).encode()
        headers = [(b"content-type", media.encode()), (b"content-length", str(len(raw)).encode())]
        headers += [(k.encode(), v.encode()) for k, v in (extra or {}).items()]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": raw})

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        method, path = scope["method"], scope["path"]
        # 1 correlation id
        correlation_id = headers.get("x-correlation-id") or new_id()
        status_holder = {"status": 500}
        sim = ",".join(self.s.simulated)

        async def send_wrapped(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                extra = [(b"x-correlation-id", correlation_id.encode())]
                if sim:
                    extra.append((b"x-platform-simulated", sim.encode()))
                message = {**message, "headers": list(message.get("headers", [])) + extra}
            await send(message)

        # 2 tracing span
        with tracer.start_as_current_span(f"{method} {path}") as span:
            span.set_attribute("http.method", method)
            try:
                await self._handle(scope, receive, send_wrapped, headers, method, path, correlation_id)
            finally:
                elapsed = (time.perf_counter() - started) * 1000
                attrs = {"service": self.s.service, "method": method, "status": status_holder["status"]}
                _requests.add(1, attrs)
                _duration.record(elapsed, attrs)

    async def _handle(self, scope: dict, receive: Any, send: Any, headers: dict[str, str], method: str, path: str,
                      correlation_id: str) -> None:
        now = datetime.now(UTC)
        # 3 deadline
        deadline = _parse_deadline(headers.get("request-deadline"), self.s.request_timeout, now)
        # 4 body size limit
        length = headers.get("content-length")
        if length and length.isdigit() and int(length) > self.s.max_body_bytes:
            await self._send_problem(send, DomainError("PAYLOAD_TOO_LARGE", "The request body is too large."),
                                     correlation_id)
            return
        body = b""
        more = True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if len(body) > self.s.max_body_bytes:
                await self._send_problem(send, DomainError("PAYLOAD_TOO_LARGE", "The request body is too large."),
                                         correlation_id)
                return

        replayed = {"done": False}

        async def replay_receive() -> dict:
            # Hand the buffered body to the app once, then pass through (for disconnect detection).
            if not replayed["done"]:
                replayed["done"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        public = self._is_public(scope)
        # 5 authentication and context
        if public:
            principal = ANONYMOUS
        else:
            auth = headers.get("authorization", "")
            if not auth.lower().startswith("bearer "):
                await self._send_problem(send, DomainError("UNAUTHENTICATED", "Send a bearer token."), correlation_id,
                                         {"www-authenticate": "Bearer"})
                return
            # Verification may fetch keys over the network; keep it off the event loop.
            verified = await anyio.to_thread.run_sync(self.verifier.verify, auth[7:].strip())
            if not verified.ok:
                await self._send_problem(send, verified.error, correlation_id, {"www-authenticate": "Bearer"})
                return
            principal = verified.value
            if reserved(principal):
                # The anonymous caller and the partners public routes act as exist only inside the kernel.
                await self._send_problem(send, DomainError("TOKEN_INVALID", "The token names a reserved principal."),
                                         correlation_id, {"www-authenticate": "Bearer"})
                return
        # 6 tenant scope
        scope_ = TenantScope.resolve(principal, headers.get("x-tenant-id"))
        ctx = RequestContext(principal=principal, tenant=scope_, correlation_id=correlation_id, deadline=deadline,
                             traceparent=headers.get("traceparent"), idempotency_key=headers.get("idempotency-key"),
                             test=headers.get("x-test-message", "").lower() == "true",
                             token=None if public else headers.get("authorization", "")[7:].strip())
        with ctxmod.use(ctx):
            # 7 idempotency for unsafe methods
            client_key = headers.get("idempotency-key")
            if client_key and method in UNSAFE and self.idem is not None and not public:
                # Keys are scoped to the caller, not only the tenant, so one caller never sees another's response.
                key = f"{principal.subject}\n{client_key}"
                query = scope.get("query_string", b"")
                request_hash = hashlib.sha256(method.encode() + b" " + path.encode() + b"?" + query + b"\n"
                                              + body).hexdigest()
                begin = self.idem.begin(scope_.tenant, key, request_hash)
                if begin.outcome == "replay":
                    stored = begin.response or {}
                    replay_headers = {k: v for k, v in (stored.get("headers") or {}).items() if k != "content-type"}
                    media = (stored.get("headers") or {}).get("content-type", "application/json")
                    await self._send_json(send, begin.status_code or 200, stored.get("body"), correlation_id, media,
                                          extra={"idempotent-replay": "true", **replay_headers})
                    return
                if begin.outcome == "reused":
                    await self._send_problem(send, DomainError("IDEMPOTENCY_KEY_REUSED",
                                             "This Idempotency-Key was used for a different request."), correlation_id)
                    return
                if begin.outcome == "in_progress":
                    await self._send_problem(send, DomainError("IDEMPOTENCY_IN_PROGRESS",
                                             "A request with this Idempotency-Key is still running."), correlation_id)
                    return
                captured: dict[str, Any] = {"status": 500, "body": b"", "headers": {}}

                async def capture(message: dict) -> None:
                    if message["type"] == "http.response.start":
                        captured["status"] = message["status"]
                        for k, v in message.get("headers", []):
                            name = k.decode().lower()
                            if name in REPLAY_HEADERS:
                                captured["headers"][name] = v.decode()
                    elif message["type"] == "http.response.body":
                        captured["body"] += message.get("body", b"")
                    await send(message)

                try:
                    await self._call(scope, replay_receive, capture, deadline, correlation_id)
                finally:
                    if captured["status"] < 500:
                        try:
                            payload = json.loads(captured["body"] or b"null")
                        except ValueError:
                            payload = None
                        self.idem.complete(scope_.tenant, key, captured["status"],
                                           {"body": payload, "headers": captured["headers"]})
                    elif captured["status"] == 504:
                        # Outcome unknown: the abandoned work may still commit. Keep the key reserved until its
                        # lease ends, so a retry gets IDEMPOTENCY_IN_PROGRESS instead of running twice.
                        pass
                    else:
                        self.idem.abandon(scope_.tenant, key)
                return
            await self._call(scope, replay_receive, send, deadline, correlation_id)

    async def _call(self, scope: dict, receive: Any, send: Any, deadline: datetime, correlation_id: str) -> None:
        """Run the app until its deadline. Threads cannot be cancelled in Python, so when the deadline passes before
        the response starts, the middleware answers 504 itself and drops whatever the abandoned work sends later.
        Kernel boundaries (unit of work, outbound calls, PostgreSQL statement_timeout) stop that work (F10)."""
        state = {"started": False, "abandoned": False}
        errors: list[BaseException] = []

        async def guarded(message: dict) -> None:
            if state["abandoned"]:
                return
            if message["type"] == "http.response.start":
                state["started"] = True
            await send(message)

        remaining = (deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            await self._send_problem(send, DomainError("DEADLINE_EXCEEDED", "The request deadline has passed."),
                                     correlation_id)
            return
        done = anyio.Event()

        async def run() -> None:
            try:
                await self.app(scope, receive, guarded)
            except Exception as exc:  # noqa: BLE001 - collected and turned into a problem below
                errors.append(exc)
            finally:
                done.set()

        async with anyio.create_task_group() as tg:
            tg.start_soon(run)
            with anyio.move_on_after(remaining):
                await done.wait()
            if not done.is_set():
                if not state["started"]:
                    state["abandoned"] = True
                    await self._send_problem(send, DomainError("DEADLINE_EXCEEDED",
                                             "The request did not finish before its deadline."), correlation_id)
                    tg.cancel_scope.cancel()  # cancels async work; thread work ends at its next kernel boundary
                else:
                    await done.wait()  # a response is already streaming; let it finish
        if state["abandoned"]:
            return
        for exc in errors:
            if state["started"]:
                log.exception("http.error_after_response_started", exc_info=exc)
                return
            if getattr(getattr(exc, "orig", None), "sqlstate", None) == "57014":
                # PostgreSQL cancelled a statement at the request's statement_timeout (F10).
                await self._send_problem(send, DomainError("DEADLINE_EXCEEDED",
                                         "The request did not finish before its deadline."), correlation_id)
                return
            log.error("http.unhandled_error", exc_info=exc)
            await self._send_problem(send, DomainError("INTERNAL_ERROR", "An unexpected error occurred."),
                                     correlation_id)
            return


def _install_handlers(app: FastAPI, catalog: ErrorCatalog) -> None:
    @app.exception_handler(DomainException)
    async def _domain(request: Request, exc: DomainException) -> JSONResponse:
        return problem_response(catalog, exc.error, instance=request.url.path)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p not in ("body",)]
            fields.append(FieldError(pointer="/" + "/".join(loc), code=err.get("type", "invalid"),
                                     message=err.get("msg", "invalid")))
        return problem_response(catalog, DomainError("VALIDATION_FAILED", "The request is not valid.",
                                                     tuple(fields)), instance=request.url.path)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT"}.get(
            exc.status_code, "INTERNAL_ERROR" if exc.status_code >= 500 else "VALIDATION_FAILED")
        return problem_response(catalog, DomainError(code, str(exc.detail)), instance=request.url.path)

    @app.exception_handler(ConcurrencyConflict)
    async def _conflict(request: Request, exc: ConcurrencyConflict) -> JSONResponse:
        return problem_response(catalog, DomainError("REVISION_CONFLICT", str(exc)), instance=request.url.path)

    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound) -> JSONResponse:
        return problem_response(catalog, DomainError("NOT_FOUND", str(exc)), instance=request.url.path)

    @app.exception_handler(ctxmod.DeadlineExceeded)
    async def _deadline(request: Request, exc: ctxmod.DeadlineExceeded) -> JSONResponse:
        return problem_response(catalog, DomainError("DEADLINE_EXCEEDED", str(exc)), instance=request.url.path)

    @app.exception_handler(PermissionError)
    async def _forbidden(request: Request, exc: PermissionError) -> JSONResponse:
        return problem_response(catalog, DomainError("FORBIDDEN", str(exc) or "Not allowed."),
                                instance=request.url.path)


def _check_public(path: str) -> None:
    """A public route has a literal first segment outside the kernel's paths, so it can never stand in for them."""
    first = path.split("/")[1] if path.count("/") >= 1 else ""
    kernel = any(path == k.rstrip("/") or path.startswith(k) for k in KERNEL_PREFIXES)
    if not path.startswith("/") or not first or "{" in first or kernel:
        raise ValueError("A public route starts with a fixed segment outside /api, /health and the docs, like "
                         f"'/hooks/{{name}}': {path!r}")


def create_app(*, settings: HttpSettings, verifier: TokenVerifier, catalog: ErrorCatalog,
               idempotency: IdempotencyStore | None, routers: Iterable[APIRouter] = (),
               readiness: dict[str, Callable[[], bool]] | None = None, version: str = "0.1.0",
               public_routers: Iterable[APIRouter] = ()) -> FastAPI:
    """`public_routers` hold routes that authenticate their callers themselves (a webhook signature, for example).
    They skip token authentication and run as the anonymous principal, whose tenant scope matches no tenant, until
    the route calls `context.as_partner`. The deadline, body limit, correlation id, tracing, problem details and
    metrics still apply; idempotency does not."""
    app = FastAPI(title=settings.service, version=version)
    _install_handlers(app, catalog)
    probes = readiness or {}

    @app.get("/health/live", include_in_schema=False)
    def live() -> dict:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    def ready() -> JSONResponse:
        results = {}
        for name, probe in probes.items():
            try:
                results[name] = bool(probe())
            except Exception:  # noqa: BLE001
                results[name] = False
        ok = all(results.values())
        return JSONResponse({"status": "ok" if ok else "unavailable", "checks": results},
                            status_code=200 if ok else 503)

    for r in routers:
        app.include_router(r)
    public: set[int] = set()
    for r in public_routers:
        for route in r.routes:
            if not isinstance(route, APIRoute):
                raise ValueError("A public router holds only its own API routes, not other routers, mounts or "
                                 "websockets.")
            _check_public(route.path)
        before = len(app.router.routes)
        app.include_router(r)
        # What the include added to the app's routes (the router itself, or copies of its routes): the middleware
        # treats a request as public only when one of these is the first full match.
        public.update(id(route) for route in app.router.routes[before:])
    app.add_middleware(PlatformMiddleware, settings=settings, verifier=verifier, catalog=catalog,
                       idempotency=idempotency, routes=app.router.routes, public_routes=frozenset(public))
    return app
