"""The governed-record engine. Every transition: checks state and revision, writes the version and record, appends
an audit record and publishes `<kind>.<transition>.v1`, all in one unit of work (F9, F11)."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from platform_plugin_sdk import Check, FieldError
from pydantic import BaseModel, ValidationError

from .. import context as ctxmod
from ..audit import AuditEntry
from ..core import Clock, ConcurrencyConflict, DomainError, Err, Ok, Result, SystemClock, new_id
from ..messaging import make_event
from ..persistence import UnitOfWorkFactory
from .model import GovernedKind, GovernedView, Record, Version
from .store import GovernedStore

GovResult = Result[GovernedView, DomainError]


class GovernanceEngine:
    def __init__(self, *, uow: UnitOfWorkFactory, store: GovernedStore, source: str,
                 maker_checker_policy: bool = True, clock: Clock | None = None) -> None:
        self._uow, self._store, self._source = uow, store, source
        self._policy = maker_checker_policy
        self._clock = clock or SystemClock()
        self._kinds: dict[str, GovernedKind] = {}

    # Registration -----------------------------------------------------------------------------------------------

    def register(self, kind: GovernedKind) -> None:
        if kind.kind in self._kinds:
            raise ValueError(f"governed kind {kind.kind!r} is already registered")
        self._kinds[kind.kind] = kind

    def kinds(self) -> list[GovernedKind]:
        return list(self._kinds.values())

    def kind(self, name: str) -> GovernedKind:
        return self._kinds[name]

    def _maker_checker(self, k: GovernedKind) -> bool:
        return {"always": True, "never": False, "policy": self._policy}[k.maker_checker]

    # Helpers ----------------------------------------------------------------------------------------------------

    @staticmethod
    def _actor() -> str:
        return ctxmod.current().principal.subject

    def _validate(self, k: GovernedKind, spec: dict[str, Any]) -> Result[dict[str, Any], DomainError]:
        try:
            return Ok(k.spec.model_validate(spec).model_dump(mode="json"))
        except ValidationError as exc:
            fields = tuple(FieldError(pointer="/spec/" + "/".join(str(p) for p in e["loc"]), code=e["type"],
                                      message=e["msg"]) for e in exc.errors())
            return Err(DomainError("VALIDATION_FAILED", f"The {k.kind} specification is not valid.", fields))

    def _load(self, uow: Any, k: GovernedKind, id: str) -> Result[tuple[Record, Version], DomainError]:
        record = self._store.get(uow, k.kind, id)
        scope = ctxmod.current().tenant
        # Tenant scope applied in the domain as well as by row-level security (P22).
        if record is None or (not scope.platform and record.tenant != scope.tenant):
            return Err(DomainError("NOT_FOUND", f"{k.kind} {id} was not found."))
        current = self._store.version(uow, k.kind, id, record.current_version)
        assert current is not None
        return Ok((record, current))

    def _view(self, uow: Any, record: Record) -> GovernedView:
        current = self._store.version(uow, record.kind, record.id, record.current_version)
        active = (self._store.version(uow, record.kind, record.id, record.active_version)
                  if record.active_version else None)
        assert current is not None
        return GovernedView(record, current, active)

    def _record_change(self, uow: Any, k: GovernedKind, transition: str, record: Record,
                       before: dict | None, after: dict | None, reason: str | None = None) -> None:
        ctx = ctxmod.current()
        uow.audit.append(AuditEntry(
            stream=f"governed:{k.kind}", action=transition, subject=record.id, actor=ctx.principal.subject,
            on_behalf_of=ctx.principal.on_behalf_of, tenant=record.tenant, reason=reason,
            correlation_id=ctx.correlation_id, at=self._clock.now(), before=before, after=after))
        uow.events.publish([make_event(f"{self._source}.{k.kind}.{transition}.v1",
                                       {"id": record.id, "kind": k.kind, "version": record.current_version,
                                        "activeVersion": record.active_version, "status": record.status},
                                       source=self._source, subject=record.id, now=self._clock.now())])

    def _transition(self, kind: str, id: str, expected_revision: int, name: str,
                    change: Callable[[Any, GovernedKind, Record, Version, datetime],
                                     Result[tuple[Record, list[Version]], DomainError]],
                    reason: str | None = None) -> GovResult:
        k = self._kinds[kind]
        try:
            with self._uow() as uow:
                loaded = self._load(uow, k, id)
                if not loaded.ok:
                    return loaded
                record, current = loaded.value
                if record.status == "retired":
                    return Err(DomainError("INVALID_TRANSITION", f"{kind} {id} is retired; it cannot change."))
                if record.revision != expected_revision:
                    return Err(DomainError("REVISION_CONFLICT", f"{kind} {id} is at revision {record.revision}, "
                                                                f"not {expected_revision}. Reload and try again."))
                now = self._clock.now()
                changed = change(uow, k, record, current, now)
                if not changed.ok:
                    return changed
                new_record, versions = changed.value
                new_record = new_record.with_(revision=record.revision + 1, updated_at=now)
                for v in versions:
                    self._store.save_version(uow, v)
                self._store.save_record(uow, new_record, expected_revision)
                self._record_change(uow, k, name, new_record, {"status": record.status,
                                    "version": record.current_version}, {"status": new_record.status,
                                    "version": new_record.current_version}, reason)
                return Ok(self._view(uow, new_record))
        except ConcurrencyConflict as exc:
            return Err(DomainError("REVISION_CONFLICT", str(exc)))

    # Queries ----------------------------------------------------------------------------------------------------

    def get(self, kind: str, id: str) -> GovResult:
        k = self._kinds[kind]
        with self._uow() as uow:
            loaded = self._load(uow, k, id)
            return Ok(self._view(uow, loaded.value[0])) if loaded.ok else loaded

    def list(self, kind: str) -> list[GovernedView]:
        scope = ctxmod.current().tenant
        with self._uow() as uow:
            return [self._view(uow, r) for r in self._store.list(uow, kind, scope.tenant, scope.platform)]

    def versions(self, kind: str, id: str) -> Result[list[Version], DomainError]:
        k = self._kinds[kind]
        with self._uow() as uow:
            loaded = self._load(uow, k, id)
            return Ok(self._store.versions(uow, kind, id)) if loaded.ok else loaded

    # Commands ---------------------------------------------------------------------------------------------------

    def create(self, kind: str, spec: dict[str, Any], id: str | None = None) -> GovResult:
        k = self._kinds[kind]
        valid = self._validate(k, spec)
        if not valid.ok:
            return valid
        ctx = ctxmod.current()
        now = self._clock.now()
        rid = id or new_id()
        record = Record(kind=kind, id=rid, tenant=ctx.tenant.tenant, status="draft", current_version=1,
                        active_version=None, revision=1, created_at=now, updated_at=now)
        version = Version(kind=kind, id=rid, version=1, tenant=ctx.tenant.tenant, status="draft",
                          spec=valid.value, maker_checker=self._maker_checker(k), created_by=self._actor(),
                          created_at=now, edited_by=(self._actor(),))
        try:
            with self._uow() as uow:
                self._store.insert(uow, record, version)
                self._record_change(uow, k, "created", record, None, {"status": "draft", "version": 1})
                return Ok(GovernedView(record, version, None))
        except ConcurrencyConflict:
            return Err(DomainError("CONFLICT", f"{kind} {rid} already exists."))

    def update_draft(self, kind: str, id: str, spec: dict[str, Any], expected_revision: int) -> GovResult:
        k = self._kinds[kind]
        valid = self._validate(k, spec)
        if not valid.ok:
            return valid

        def change(uow: Any, k: GovernedKind, r: Record, cur: Version, now: datetime):
            if r.status == "retired":
                return Err(DomainError("INVALID_TRANSITION", f"{kind} {id} is retired."))
            if cur.status == "submitted":
                return Err(DomainError("INVALID_TRANSITION", "The version is waiting for approval. Reject it first."))
            if cur.status in ("draft", "tested"):
                # Any edit sends the draft back, clears the test result and records the editor (P14).
                editors = cur.edited_by if self._actor() in cur.edited_by else (*cur.edited_by, self._actor())
                return Ok((r, [cur.with_(spec=valid.value, status="draft", test_result=None, edited_by=editors)]))
            # Current version is active: start a new draft; the active version keeps running.
            new = Version(kind=kind, id=id, version=r.current_version + 1, tenant=r.tenant, status="draft",
                          spec=valid.value, maker_checker=self._maker_checker(k), created_by=self._actor(),
                          created_at=now, edited_by=(self._actor(),))
            return Ok((r.with_(current_version=new.version), [new]))

        return self._transition(kind, id, expected_revision, "draft_updated", change)

    def test(self, kind: str, id: str, expected_revision: int) -> GovResult:
        k = self._kinds[kind]
        # Read, then run the checks outside any transaction: tests may call remote systems (P39).
        with self._uow() as uow:
            loaded = self._load(uow, k, id)
            if not loaded.ok:
                return loaded
            record, cur = loaded.value
        if record.status == "retired":
            return Err(DomainError("INVALID_TRANSITION", f"{kind} {id} is retired; it cannot change."))
        if record.revision != expected_revision:
            return Err(DomainError("REVISION_CONFLICT", f"{kind} {id} is at revision {record.revision}, "
                                                        f"not {expected_revision}. Reload and try again."))
        if cur.status not in ("draft", "tested"):
            return Err(DomainError("INVALID_TRANSITION", f"Only a draft can be tested; this one is {cur.status}."))
        spec = k.spec.model_validate(cur.spec)
        checks: list[Check] = []
        for t in k.tests:
            try:
                checks.extend(t(spec))
            except Exception as exc:  # noqa: BLE001 - a crashing test is a failed check, not a 500
                checks.append(Check(name=getattr(t, "__name__", "test"), ok=False, detail=f"Test failed: {exc}"))
        passed = all(c.ok for c in checks)
        result = [c.model_dump() for c in checks]
        tested_version = cur.version

        def change(uow: Any, k: GovernedKind, r: Record, now_cur: Version, now: datetime):
            if now_cur.version != tested_version or now_cur.status not in ("draft", "tested"):
                return Err(DomainError("REVISION_CONFLICT", "The draft changed while it was being tested."))
            return Ok((r, [now_cur.with_(status="tested" if passed else "draft", test_result=result)]))

        return self._transition(kind, id, expected_revision, "tested", change)

    def submit(self, kind: str, id: str, expected_revision: int) -> GovResult:
        def change(uow: Any, k: GovernedKind, r: Record, cur: Version, now: datetime):
            if cur.status != "tested":
                return Err(DomainError("NOT_TESTED", "Run the test and fix any failed checks before submitting."))
            return Ok((r, [cur.with_(status="submitted", submitted_by=self._actor())]))

        return self._transition(kind, id, expected_revision, "submitted", change)

    def approve(self, kind: str, id: str, expected_revision: int) -> GovResult:
        def change(uow: Any, k: GovernedKind, r: Record, cur: Version, now: datetime):
            if cur.status != "submitted":
                return Err(DomainError("INVALID_TRANSITION", f"Only a submitted version can be approved; this one "
                                                             f"is {cur.status}."))
            actor = self._actor()
            if cur.maker_checker and actor in cur.authors:
                return Err(DomainError("MAKER_CHECKER", "Someone who did not create, edit or submit this version "
                                                        "must approve it."))
            versions = [cur.with_(status="active", approved_by=actor)]
            if r.active_version and r.active_version != cur.version:
                previous = self._store.version(uow, k.kind, r.id, r.active_version)
                if previous is not None:
                    versions.insert(0, previous.with_(status="superseded"))
            status = "paused" if r.status == "paused" else "active"
            return Ok((r.with_(active_version=cur.version, status=status), versions))

        return self._transition(kind, id, expected_revision, "approved", change)

    def reject(self, kind: str, id: str, expected_revision: int, reason: str) -> GovResult:
        def change(uow: Any, k: GovernedKind, r: Record, cur: Version, now: datetime):
            if cur.status != "submitted":
                return Err(DomainError("INVALID_TRANSITION", "Only a submitted version can be rejected."))
            return Ok((r, [cur.with_(status="draft", submitted_by=None, test_result=None)]))

        return self._transition(kind, id, expected_revision, "rejected", change, reason=reason)

    def pause(self, kind: str, id: str, expected_revision: int, reason: str | None = None) -> GovResult:
        def change(uow: Any, k: GovernedKind, r: Record, cur: Version, now: datetime):
            if r.status != "active":
                return Err(DomainError("INVALID_TRANSITION", f"Only an active record can be paused; it is {r.status}."))
            return Ok((r.with_(status="paused"), []))

        return self._transition(kind, id, expected_revision, "paused", change, reason=reason)

    def resume(self, kind: str, id: str, expected_revision: int) -> GovResult:
        def change(uow: Any, k: GovernedKind, r: Record, cur: Version, now: datetime):
            if r.status != "paused":
                return Err(DomainError("INVALID_TRANSITION", f"Only a paused record can be resumed; it is {r.status}."))
            return Ok((r.with_(status="active"), []))

        return self._transition(kind, id, expected_revision, "resumed", change)

    def retire(self, kind: str, id: str, expected_revision: int, reason: str | None = None) -> GovResult:
        def change(uow: Any, k: GovernedKind, r: Record, cur: Version, now: datetime):
            if r.status == "retired":
                return Err(DomainError("INVALID_TRANSITION", f"{kind} {id} is already retired."))
            versions = []
            if r.active_version:
                active = self._store.version(uow, k.kind, r.id, r.active_version)
                if active is not None:
                    versions.append(active.with_(status="retired"))
            if cur.version != r.active_version and cur.status in ("draft", "tested", "submitted"):
                # Withdraw any pending version so it can never be approved after retirement.
                versions.append(cur.with_(status="retired"))
            return Ok((r.with_(status="retired"), versions))

        return self._transition(kind, id, expected_revision, "retired", change, reason=reason)

    def active_spec(self, kind: str, id: str) -> BaseModel | None:
        """The spec products run on: the active version only, never a draft."""
        k = self._kinds[kind]
        with self._uow() as uow:
            loaded = self._load(uow, k, id)
            if not loaded.ok:
                return None
            record = loaded.value[0]
            if record.status != "active" or record.active_version is None:
                return None
            v = self._store.version(uow, kind, id, record.active_version)
            return k.spec.model_validate(v.spec) if v else None
