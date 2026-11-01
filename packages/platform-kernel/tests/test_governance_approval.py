"""Approval policy (0.4): auto, single and maker_checker, require_test, returned versions and discarded drafts.

Scenarios are written as steps (action, actor, expectation) so each rule reads like the lifecycle it describes."""
from __future__ import annotations

import pytest
from platform_kernel.governance import (
    ApprovalRule,
    GovernanceEngine,
    GovernedKind,
    MemoryGovernedStore,
    PostgresGovernedStore,
    StaticApprovalPolicy,
)
from platform_kernel.persistence import MemoryOutboxReader, MemoryUnitOfWorkFactory
from platform_plugin_sdk import Check
from platform_testing import requires_postgres
from pydantic import BaseModel

from .test_governance import as_user


class Item(BaseModel):
    value: int


def positive(spec: Item) -> list[Check]:
    return [Check(name="positive", ok=spec.value > 0, detail="The value must be positive.")]


def kind(maker_checker: str = "policy") -> GovernedKind:
    return GovernedKind(kind="item", plural="items", spec=Item, tests=(positive,), read="i:read", write="i:write",
                        approve="i:approve", maker_checker=maker_checker)  # type: ignore[arg-type]


def run(engine: GovernanceEngine, steps: list[tuple]) -> None:
    """Each step: (action, actor, argument or None, expected). Expected is an error code, or a tuple of
    (record status, active version, current version status)."""
    rid: str | None = None
    for i, (action, actor, arg, expected) in enumerate(steps):
        with as_user(actor):
            rev = engine.get("item", rid).value.record.revision if rid else 0
            if action == "create":
                result = engine.create("item", {"value": arg})
            elif action == "edit":
                result = engine.update_draft("item", rid, {"value": arg}, rev)
            elif action in ("reject", "pause", "retire"):
                result = getattr(engine, action)("item", rid, rev, arg)
            else:
                result = getattr(engine, {"test": "test"}.get(action, action))("item", rid, rev)
        if result.ok:
            rid = result.value.record.id
            got = (result.value.record.status, result.value.record.active_version, result.value.current.status)
        else:
            got = result.error.code
        assert got == expected, f"step {i} ({action} by {actor}): {got} != {expected}"


class _Approval:
    def engine(self, uow, store, rule: ApprovalRule, maker_checker: str = "policy") -> GovernanceEngine:
        e = GovernanceEngine(uow=uow, store=store, source="svc", policy=StaticApprovalPolicy(rule))
        e.register(kind(maker_checker))
        return e

    def test_auto_activates_on_submit_and_a_new_version_starts_from_the_active_one(self, uow, store, events):
        run(self.engine(uow, store, ApprovalRule("auto", True)), [
            ("create", "alice", 1, ("draft", None, "draft")),
            ("submit", "alice", None, "NOT_TESTED"),
            ("test", "alice", None, ("draft", None, "tested")),
            ("submit", "alice", None, ("active", 1, "active")),
            ("edit", "alice", 2, ("active", 1, "draft")),
            ("test", "alice", None, ("active", 1, "tested")),
            ("edit", "alice", 3, ("active", 1, "draft")),
            ("submit", "alice", None, "NOT_TESTED"),
            ("test", "alice", None, ("active", 1, "tested")),
            ("submit", "alice", None, ("active", 2, "active")),
        ])
        # Consumers of approved events still see auto approvals.
        assert [e.split(".")[-2] for e in events()].count("approved") == 2

    def test_maker_checker_refuses_every_maker_and_accepts_a_second_person(self, uow, store):
        run(self.engine(uow, store, ApprovalRule("maker_checker", True)), [
            ("create", "alice", 1, ("draft", None, "draft")),
            ("edit", "carol", 2, ("draft", None, "draft")),
            ("test", "alice", None, ("draft", None, "tested")),
            ("submit", "dave", None, ("draft", None, "submitted")),
            ("edit", "alice", 3, "DRAFT_SUBMITTED"),
            ("approve", "alice", None, "MAKER_CHECKER"),
            ("approve", "carol", None, "MAKER_CHECKER"),
            ("approve", "dave", None, "MAKER_CHECKER"),
            ("approve", "bob", None, ("active", 1, "active")),
            ("approve", "bob", None, "NOT_SUBMITTED"),
        ])

    def test_single_allows_the_maker_and_require_test_can_be_off(self, uow, store):
        run(self.engine(uow, store, ApprovalRule("single", False)), [
            ("create", "alice", -1, ("draft", None, "draft")),
            ("submit", "alice", None, ("draft", None, "submitted")),
            ("approve", "alice", None, ("active", 1, "active")),
        ])

    def test_return_pause_resume_and_discard(self, uow, store):
        run(self.engine(uow, store, ApprovalRule("maker_checker", True)), [
            ("create", "alice", 1, ("draft", None, "draft")),
            ("pause", "alice", "maintenance", "NOT_ACTIVE"),
            ("test", "alice", None, ("draft", None, "tested")),
            ("submit", "alice", None, ("draft", None, "submitted")),
            ("discard", "alice", None, "DRAFT_SUBMITTED"),
            ("reject", "bob", "wrong endpoint", ("draft", None, "returned")),
            ("submit", "alice", None, "NOT_TESTED"),
            ("test", "alice", None, ("draft", None, "tested")),
            ("submit", "alice", None, ("draft", None, "submitted")),
            ("approve", "bob", None, ("active", 1, "active")),
            ("resume", "bob", None, "NOT_PAUSED"),
            ("pause", "bob", "vendor outage", ("paused", 1, "active")),
            ("discard", "bob", None, "NO_DRAFT"),
            ("resume", "bob", None, ("active", 1, "active")),
            ("edit", "alice", 5, ("active", 1, "draft")),
            ("discard", "alice", None, ("active", 1, "active")),
        ])

    def test_discarding_the_only_draft_retires_the_record(self, uow, store):
        run(self.engine(uow, store, ApprovalRule("auto", True)), [
            ("create", "alice", 1, ("draft", None, "draft")),
            ("discard", "alice", None, ("retired", None, "discarded")),
            ("edit", "alice", 2, "RECORD_RETIRED"),
            ("test", "alice", None, "RECORD_RETIRED"),
        ])

    def test_a_kind_that_insists_on_maker_checker_overrides_a_lax_policy(self, uow, store):
        e = self.engine(uow, store, ApprovalRule("auto", False), maker_checker="always")
        assert e.rule_for("item") == ApprovalRule("maker_checker", True)
        run(e, [
            ("create", "alice", 1, ("draft", None, "draft")),
            ("submit", "alice", None, "NOT_TESTED"),
        ])

    def test_returned_versions_keep_the_reason_and_tests_record_who_and_when(self, uow, store):
        e = self.engine(uow, store, ApprovalRule("maker_checker", True))
        with as_user("alice"):
            v = e.create("item", {"value": 1}).value
            v = e.test("item", v.record.id, v.record.revision).value
            assert v.current.tested_by == "alice" and v.current.tested_at is not None
            v = e.submit("item", v.record.id, v.record.revision).value
        with as_user("bob"):
            v = e.reject("item", v.record.id, v.record.revision, "wrong endpoint").value
        assert (v.current.status, v.current.reason, v.current.test_result, v.current.tested_by) == (
            "returned", "wrong endpoint", None, None)
        with as_user("alice"):
            assert e.get("item", v.record.id).value.current.reason == "wrong endpoint"


class TestMemoryApproval(_Approval):
    @pytest.fixture
    def uow(self):
        return MemoryUnitOfWorkFactory()

    @pytest.fixture
    def store(self):
        return MemoryGovernedStore()

    @pytest.fixture
    def events(self, uow):
        return lambda: [r.envelope.type for r in MemoryOutboxReader(uow.db).claim(100)]


@requires_postgres
class TestPostgresApproval(_Approval):
    @pytest.fixture
    def uow(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresUnitOfWorkFactory

        return PostgresUnitOfWorkFactory(pg_engine, pg_schema)

    @pytest.fixture
    def store(self):
        return PostgresGovernedStore()

    @pytest.fixture
    def events(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresOutboxReader

        return lambda: [r.envelope.type for r in PostgresOutboxReader(pg_engine, pg_schema).claim(100)]


class _Review04:
    def test_r1_a_draft_after_a_discarded_one_gets_a_new_number(self, uow, store):
        e = GovernanceEngine(uow=uow, store=store, source="svc",
                             policy=StaticApprovalPolicy(ApprovalRule("single", False)))
        e.register(kind())
        with as_user("bob"):
            v = e.create("item", {"value": 1}).value
            v = e.submit("item", v.record.id, v.record.revision).value
            v = e.approve("item", v.record.id, v.record.revision).value
            v = e.update_draft("item", v.record.id, {"value": 2}, v.record.revision).value
            v = e.discard("item", v.record.id, v.record.revision).value
        with as_user("carol"):
            v = e.update_draft("item", v.record.id, {"value": 3}, v.record.revision).value
            assert v.current.version == 3 and v.current.created_by == "carol"
            versions = e.versions("item", v.record.id).value
        assert [(x.version, x.status, x.created_by) for x in versions] == [
            (1, "active", "bob"), (2, "discarded", "bob"), (3, "draft", "carol")]

    def test_r2_auto_approval_is_recorded_atomically(self, uow, store, monkeypatch):
        e = GovernanceEngine(uow=uow, store=store, source="svc",
                             policy=StaticApprovalPolicy(ApprovalRule("auto", False)))
        e.register(kind())
        original = e._record_change

        def failing(uow_, k, transition, *a, **kw):
            if transition == "approved":
                raise RuntimeError("audit store down")
            return original(uow_, k, transition, *a, **kw)

        with as_user("alice"):
            v = e.create("item", {"value": 1}).value
            monkeypatch.setattr(e, "_record_change", failing)
            with pytest.raises(RuntimeError):
                e.submit("item", v.record.id, v.record.revision)
            monkeypatch.setattr(e, "_record_change", original)
            after = e.get("item", v.record.id).value
        assert (after.record.status, after.record.active_version, after.current.status) == ("draft", None, "draft")

    def test_r3_r4_failed_or_missing_tests_block_submit_and_approval(self, uow, store):
        policy = StaticApprovalPolicy(ApprovalRule("single", False))
        e = GovernanceEngine(uow=uow, store=store, source="svc", policy=policy)
        e.register(kind())
        with as_user("alice"):
            v = e.create("item", {"value": -1}).value
            v = e.test("item", v.record.id, v.record.revision).value
            assert e.submit("item", v.record.id, v.record.revision).error.code == "NOT_TESTED"
            w = e.create("item", {"value": -2}, id="w").value
            w = e.submit("item", "w", w.record.revision).value
        policy.kinds["item"] = ApprovalRule("maker_checker", True)
        with as_user("bob"):
            assert e.approve("item", "w", w.record.revision).error.code == "NOT_TESTED"

    def test_r5_retiring_withdraws_a_returned_version(self, uow, store):
        e = GovernanceEngine(uow=uow, store=store, source="svc",
                             policy=StaticApprovalPolicy(ApprovalRule("maker_checker", True)))
        e.register(kind())
        run(e, [
            ("create", "alice", 1, ("draft", None, "draft")),
            ("test", "alice", None, ("draft", None, "tested")),
            ("submit", "alice", None, ("draft", None, "submitted")),
            ("reject", "bob", "wrong value", ("draft", None, "returned")),
            ("retire", "alice", "not needed", ("retired", None, "retired")),
        ])


class TestMemoryReview04(_Review04):
    uow = TestMemoryApproval.uow
    store = TestMemoryApproval.store


@requires_postgres
class TestPostgresReview04(_Review04):
    uow = TestPostgresApproval.uow
    store = TestPostgresApproval.store
