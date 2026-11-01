"""Long-running operations (P39) and sagas (I12).

`OperationRunner.start` records the operation and returns at once; the caller answers 202 with a Location. Work
runs in a background pool with the caller's identity and tenant, its own deadline, and the same correlation id.
Every status change commits with its event in one unit of work (F9), under a row lock so concurrent changes (a
cancel, a progress update, the finish) never overwrite each other. Unfinished operations resume after a restart,
so handlers and saga steps must be idempotent. A runner claims an operation with a lease before running it; another
instance takes it over only once the lease has ended, so one operation never runs twice at the same time.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .. import context as ctxmod
from ..context import DeadlineExceeded, Principal, RequestContext, TenantScope
from ..core import Clock, DomainError, Err, Ok, Result, SystemClock, new_id
from ..messaging import make_event
from ..observability import get_logger
from ..persistence import UnitOfWorkFactory
from .model import FINISHED, RESUMABLE, Operation
from .store import OperationStore

log = get_logger("platform.operations")


class OperationCancelled(Exception):
    """Raised by `handle.check_cancelled()` when someone asked to cancel the operation."""


class SagaStalled(Exception):
    """A compensation failed. The operation becomes "stalled" and resumes later from the failed compensation."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(detail)
        self.step, self.detail = step, detail


class OperationFailed(Exception):
    """Raise from a handler to fail with a catalogued code and a plain detail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code, self.detail = code, detail


class Handle:
    """What a handler sees: progress, cancellation and saved state."""

    def __init__(self, runner: OperationRunner, op_id: str) -> None:
        self._runner, self.id = runner, op_id

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._runner._load(self.id).state)

    def save_state(self, state: dict[str, Any]) -> None:
        self._runner._update(self.id, lambda op: op.with_(state=dict(state)))

    def progress(self, percent: int) -> None:
        self._runner._update(self.id, lambda op: op.with_(progress=max(0, min(100, int(percent)))))

    def step(self, state: dict[str, Any], percent: int) -> None:
        """Save state and progress together, in one write: the cheap way to record each step of a long loop."""
        self._runner._update(self.id, lambda op: op.with_(state=dict(state), progress=max(0, min(100, int(percent)))))

    def check_cancelled(self) -> None:
        """Call between units of work: stops on a cancel request or once the operation's deadline has passed."""
        ctxmod.check_deadline("the next step of the operation")
        if self._runner._load(self.id).cancel_requested:
            raise OperationCancelled()


OperationHandler = Callable[[dict[str, Any], Handle], dict[str, Any] | None]


class Orchestrator(Protocol):
    """Port for durable workflows. In-process provider below; Temporal is a later provider (base P39)."""

    def start(self, kind: str, input: dict[str, Any]) -> Result[Operation, DomainError]: ...
    def cancel(self, id: str) -> Result[Operation, DomainError]: ...


class OperationRunner:
    simulated = False

    def __init__(self, *, uow: UnitOfWorkFactory, store: OperationStore, source: str, clock: Clock | None = None,
                 max_workers: int = 4, operation_timeout: timedelta = timedelta(hours=1),
                 reader_roles: frozenset[str] = frozenset({"operations.read"})) -> None:
        """`operation_timeout` is both the deadline of one run and the lease: an operation claimed by an instance
        that died is taken over once that time has passed. `reader_roles` may read operations others started in
        their tenant; anyone else sees only their own (P22)."""
        self._uow, self._store, self._source = uow, store, source
        self._clock = clock or SystemClock()
        self._timeout = operation_timeout
        self._readers = frozenset(reader_roles)
        self._instance = new_id()
        self._handlers: dict[str, OperationHandler] = {}
        self._sagas: set[str] = set()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="operation")
        self._futures: dict[str, Future[None]] = {}
        self._lock = threading.RLock()

    # Registration -----------------------------------------------------------------------------------------------

    def register(self, kind: str, handler: OperationHandler) -> None:
        if kind in self._handlers:
            raise ValueError(f"operation kind {kind!r} is already registered")
        self._handlers[kind] = handler

    def register_saga(self, saga: Saga) -> None:
        self.register(saga.name, saga.run)
        self._sagas.add(saga.name)  # a cancelled saga still runs to compensate

    # Commands ---------------------------------------------------------------------------------------------------

    def start(self, kind: str, input: dict[str, Any]) -> Result[Operation, DomainError]:
        if kind not in self._handlers:
            return Err(DomainError("NOT_FOUND", f"No operation kind {kind!r} is registered."))
        ctx = ctxmod.current()
        now = self._clock.now()
        op = Operation(id=new_id(), kind=kind, tenant=ctx.tenant.tenant, status="pending", input=dict(input),
                       created_by=ctx.principal.subject, created_at=now, updated_at=now,
                       correlation_id=ctx.correlation_id, created_roles=frozenset(ctx.principal.roles))
        with self._uow() as uow:
            self._store.save(uow, op)
            self._event(uow, op, "accepted")
        self._submit(op)
        return Ok(op)

    def _visible(self, op: Operation | None) -> bool:
        ctx = ctxmod.current()
        if op is None:
            return False
        if ctx.tenant.platform:
            return True
        return op.tenant == ctx.tenant.tenant and (op.created_by == ctx.principal.subject
                                                    or bool(ctx.principal.roles & self._readers))

    def get(self, id: str) -> Result[Operation, DomainError]:
        with self._uow() as uow:
            op = self._store.get(uow, id)
        if not self._visible(op):
            return Err(DomainError("NOT_FOUND", f"Operation {id} was not found."))
        assert op is not None
        return Ok(op)

    def recent(self, limit: int = 50) -> list[Operation]:
        """Operations the caller may see, newest first. Without a reader role the store filters by creator, so
        other people's work can never crowd out the caller's own."""
        ctx = ctxmod.current()
        limit = max(1, min(int(limit), 200))
        reader = ctx.tenant.platform or bool(ctx.principal.roles & self._readers)
        with self._uow() as uow:
            ops = self._store.recent(uow, limit, None if reader else ctx.principal.subject)
        return [o for o in ops if self._visible(o)][:limit]

    def cancel(self, id: str) -> Result[Operation, DomainError]:
        ctx = ctxmod.current()
        with self._uow() as uow:
            op = self._store.get_for_update(uow, id)  # locked: the check and the change see the same row
            if not self._visible(op):
                return Err(DomainError("NOT_FOUND", f"Operation {id} was not found."))
            assert op is not None
            if not ctx.tenant.platform and op.created_by != ctx.principal.subject:
                return Err(DomainError("FORBIDDEN", "Only the person who started an operation may cancel it."))
            if op.status in FINISHED:
                return Err(DomainError("INVALID_TRANSITION", f"Operation {id} has already {op.status}."))
            op = op.with_(cancel_requested=True, updated_at=self._clock.now())
            self._store.update(uow, op)
            self._event(uow, op, "cancel_requested")
        return Ok(op)

    def resume_unfinished(self) -> int:
        """Call at startup (and from an operator job for stalled sagas): re-run pending, running and stalled
        operations that are not running here and whose lease has ended. Sagas continue from their saved state.
        Returns how many were submitted."""
        with self._bookkeeping(), self._uow(platform_scope=True) as uow:
            ops = self._store.unfinished(uow)
        now = self._clock.now()
        submitted = 0
        for op in ops:
            if op.kind not in self._handlers or self._live(op.id):
                continue
            if op.lease_until is not None and op.lease_until > now and op.lease_owner != self._instance:
                continue  # another instance holds it
            self._submit(op)
            submitted += 1
        return submitted

    def wait(self, id: str, timeout: float = 10.0) -> None:
        future = self._futures.get(id)
        if future is not None:
            future.result(timeout=timeout)

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # Execution --------------------------------------------------------------------------------------------------

    def _live(self, op_id: str) -> bool:
        with self._lock:
            future = self._futures.get(op_id)
            return future is not None and not future.done()

    def _submit(self, op: Operation) -> None:
        principal = Principal(subject=op.created_by, roles=op.created_roles, tenant=op.tenant)
        ctx = RequestContext(principal=principal, tenant=TenantScope(op.tenant),
                             correlation_id=op.correlation_id or new_id(), causation_id=op.id,
                             deadline=datetime.now(UTC) + self._timeout)
        with self._lock:
            if self._live(op.id):
                return
            self._futures[op.id] = self._pool.submit(self._run, op.id, ctx)

    @contextmanager
    def _bookkeeping(self) -> Iterator[None]:
        """Status changes must land even after the operation's own deadline passed, so they run with a short
        deadline of their own (the identity and tenant stay the same)."""
        ctx = ctxmod.maybe_current()
        if ctx is None:
            yield
            return
        with ctxmod.use(replace(ctx, deadline=datetime.now(UTC) + timedelta(seconds=30))):
            yield

    def _claim(self, op_id: str) -> Operation | None:
        """Take the operation if it is resumable and nobody else holds a live lease on it."""
        now = self._clock.now()
        with self._bookkeeping(), self._uow() as uow:
            op = self._store.get_for_update(uow, op_id)
            if op is None or op.status not in RESUMABLE:
                return None
            if op.lease_owner not in (None, self._instance) and op.lease_until is not None and op.lease_until > now:
                return None
            op = op.with_(status="running", lease_owner=self._instance, lease_until=now + self._timeout,
                          updated_at=now)
            self._store.update(uow, op)
            return op

    def _run(self, op_id: str, ctx: RequestContext) -> None:
        with ctxmod.use(ctx):
            op = self._claim(op_id)
            if op is None:
                return
            handler = self._handlers[op.kind]
            try:
                if op.cancel_requested and op.kind not in self._sagas:
                    raise OperationCancelled()
                result = handler(dict(op.input), Handle(self, op_id)) or {}
            except OperationCancelled:
                self._finish(op_id, "cancelled", error={"code": "CANCELLED", "detail": "The operation was cancelled."})
            except SagaStalled as exc:
                log.error("operation.stalled", operation=op_id, kind=op.kind, step=exc.step)
                self._finish(op_id, "stalled", error={"code": "COMPENSATION_FAILED", "detail": (
                    f"Undoing step {exc.step!r} failed; the operation will be retried.")})
            except OperationFailed as exc:
                self._finish(op_id, "failed", error={"code": exc.code, "detail": exc.detail})
            except DeadlineExceeded:
                self._finish(op_id, "failed", error={"code": "DEADLINE_EXCEEDED",
                                                     "detail": "The operation ran past its time limit."})
            except Exception:  # noqa: BLE001 - recorded on the operation, never lost; details go to the log only
                log.exception("operation.failed", operation=op_id, kind=op.kind)
                self._finish(op_id, "failed", error={"code": "INTERNAL_ERROR",
                                                     "detail": "The operation failed unexpectedly."})
            else:
                self._finish(op_id, "succeeded", result=result)

    def _finish(self, op_id: str, status: str, *, result: dict | None = None, error: dict | None = None) -> None:
        with self._bookkeeping(), self._uow() as uow:
            op = self._store.get_for_update(uow, op_id)
            assert op is not None
            op = op.with_(status=status, result=result, error=error,
                          progress=100 if status == "succeeded" else op.progress,
                          lease_owner=None, lease_until=None, updated_at=self._clock.now())
            self._store.update(uow, op)
            self._event(uow, op, status)

    def _load(self, op_id: str) -> Operation:
        with self._uow() as uow:
            op = self._store.get(uow, op_id)
        assert op is not None
        return op

    def _update(self, op_id: str, change: Callable[[Operation], Operation]) -> Operation:
        with self._uow() as uow:
            op = self._store.get_for_update(uow, op_id)
            if op is None:
                raise LookupError(op_id)
            op = change(op).with_(updated_at=self._clock.now())
            self._store.update(uow, op)
            return op

    def _event(self, uow: Any, op: Operation, what: str) -> None:
        uow.events.publish([make_event(f"{self._source}.operation.{what}.v1",
                                       {"id": op.id, "kind": op.kind, "status": op.status},
                                       source=self._source, subject=op.id, now=self._clock.now())])


# Sagas -------------------------------------------------------------------------------------------------------------

StepAction = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True)
class SagaStep:
    """`action` receives the saga data and returns new data to merge. `compensate` undoes the step. Both must be
    idempotent: after a restart a step may run again."""

    name: str
    action: StepAction
    compensate: StepAction | None = None


@dataclass(frozen=True)
class Saga:
    name: str
    steps: tuple[SagaStep, ...]

    def __post_init__(self) -> None:
        names = [s.name for s in self.steps]
        if len(names) != len(set(names)):
            raise ValueError(f"saga {self.name!r} has duplicate step names")

    def run(self, input: dict[str, Any], handle: Handle) -> dict[str, Any]:
        state = handle.state or {"phase": "forward", "done": [], "compensated": [], "data": dict(input)}
        data: dict[str, Any] = dict(state["data"])
        if state["phase"] == "forward":
            for i, step in enumerate(self.steps):
                if step.name in state["done"]:
                    continue
                try:
                    handle.check_cancelled()
                    data.update(step.action(dict(data)) or {})
                except Exception as exc:  # noqa: BLE001 - every failure, including cancellation, compensates
                    if isinstance(exc, OperationCancelled):
                        code, detail = "CANCELLED", "cancelled"
                    elif isinstance(exc, OperationFailed):
                        code, detail = exc.code, exc.detail
                    else:  # unexpected: the detail goes to the log, never onto the operation
                        log.exception("saga.step_failed", saga=self.name, step=step.name)
                        code, detail = "STEP_FAILED", "an unexpected error"
                    state = {**state, "phase": "compensating", "failed_step": step.name,
                             "failure": code, "failure_detail": detail, "data": data}
                    handle.save_state(state)
                    break
                state = {**state, "done": [*state["done"], step.name], "data": data}
                handle.save_state(state)
                handle.progress(int(100 * (i + 1) / max(1, len(self.steps))))
        if state["phase"] == "compensating":
            for step in reversed([s for s in self.steps if s.name in state["done"]]):
                if step.name in state["compensated"] or step.compensate is None:
                    continue
                try:
                    step.compensate(dict(state["data"]))
                except Exception as exc:  # noqa: BLE001 - stalls; resumes from this compensation later
                    raise SagaStalled(step.name, str(exc)) from exc
                state = {**state, "compensated": [*state["compensated"], step.name]}
                handle.save_state(state)
            if state.get("failure") == "CANCELLED":
                raise OperationCancelled()
            raise OperationFailed(str(state.get("failure") or "SAGA_FAILED"),
                                  f"Step {state.get('failed_step')!r} failed: {state.get('failure_detail')}. "
                                  f"Compensated: {', '.join(state['compensated']) or 'nothing'}.")
        return {"data": data, "steps": state["done"]}


