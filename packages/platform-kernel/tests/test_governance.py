from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from platform_kernel import context as ctxmod
from platform_kernel.audit import verify_chain
from platform_kernel.context import Principal, RequestContext, TenantScope
from platform_kernel.governance import GovernanceEngine, GovernedKind, MemoryGovernedStore, PostgresGovernedStore
from platform_kernel.persistence import MemoryOutboxReader, MemoryUnitOfWorkFactory
from platform_plugin_sdk import Check
from platform_testing import requires_postgres
from pydantic import BaseModel


class Rate(BaseModel):
    name: str
    amount: float


def reach(spec: Rate) -> list[Check]:
    return [Check(name="positive", ok=spec.amount > 0, detail="Amount must be positive.")]


KIND = GovernedKind(kind="rate", plural="rates", spec=Rate, tests=(reach,), read="rates:read", write="rates:write",
                    approve="rates:approve")


def as_user(subject: str, tenant: str | None = "t1"):
    p = Principal(subject=subject, tenant=tenant)
    return ctxmod.use(RequestContext(principal=p, tenant=TenantScope.resolve(p), correlation_id="c",
                                     deadline=datetime.now(UTC) + timedelta(seconds=30)))


class _Lifecycle:
    def test_full_lifecycle_with_maker_checker(self, engine, events, audit):
        with as_user("maker"):
            v = engine.create("rate", {"name": "vm", "amount": 10}).value
            v = engine.test("rate", v.record.id, v.record.revision).value
            assert v.current.status == "tested"
            v = engine.submit("rate", v.record.id, v.record.revision).value
            denied = engine.approve("rate", v.record.id, v.record.revision)
            assert not denied.ok and denied.error.code == "MAKER_CHECKER"
        with as_user("checker"):
            v = engine.approve("rate", v.record.id, v.record.revision).value
        assert (v.record.status, v.record.active_version, v.current.approved_by) == ("active", 1, "checker")
        assert [e.split(".")[-2] for e in events()] == ["created", "tested", "submitted", "approved"]
        records = audit("governed:rate")
        assert [r.entry.action for r in records] == ["created", "tested", "submitted", "approved"]
        assert verify_chain(records) == (True, None)

    def test_editing_active_creates_new_draft_while_active_keeps_running(self, engine):
        with as_user("maker"):
            v = engine.create("rate", {"name": "vm", "amount": 10}).value
            v = engine.test("rate", v.record.id, v.record.revision).value
            v = engine.submit("rate", v.record.id, v.record.revision).value
        with as_user("checker"):
            v = engine.approve("rate", v.record.id, v.record.revision).value
        with as_user("maker"):
            v = engine.update_draft("rate", v.record.id, {"name": "vm", "amount": 12}, v.record.revision).value
            assert (v.record.current_version, v.record.active_version, v.current.status) == (2, 1, "draft")
            assert engine.active_spec("rate", v.record.id).amount == 10
            v = engine.test("rate", v.record.id, v.record.revision).value
            v = engine.submit("rate", v.record.id, v.record.revision).value
        with as_user("checker"):
            v = engine.approve("rate", v.record.id, v.record.revision).value
            assert engine.active_spec("rate", v.record.id).amount == 12
            statuses = [x.status for x in engine.versions("rate", v.record.id).value]
            assert statuses == ["superseded", "active"]

    def test_failed_check_keeps_draft_and_blocks_submit(self, engine):
        with as_user("maker"):
            v = engine.create("rate", {"name": "vm", "amount": -1}).value
            v = engine.test("rate", v.record.id, v.record.revision).value
            assert v.current.status == "draft" and v.current.test_result[0]["ok"] is False
            r = engine.submit("rate", v.record.id, v.record.revision)
            assert r.error.code == "NOT_TESTED"

    def test_stale_revision_is_refused(self, engine):
        with as_user("maker"):
            v = engine.create("rate", {"name": "vm", "amount": 1}).value
            engine.test("rate", v.record.id, v.record.revision)
            stale = engine.test("rate", v.record.id, v.record.revision)
            assert stale.error.code == "REVISION_CONFLICT"

    def test_tenants_cannot_see_each_other(self, engine):
        with as_user("maker", "t1"):
            v = engine.create("rate", {"name": "vm", "amount": 1}).value
        with as_user("other", "t2"):
            assert engine.get("rate", v.record.id).error.code == "NOT_FOUND"
            assert engine.list("rate") == []
        with as_user("staff", None):
            assert len(engine.list("rate")) == 1

    def test_invalid_spec_reports_pointers(self, engine):
        with as_user("maker"):
            r = engine.create("rate", {"name": "vm", "amount": "lots"})
            assert r.error.code == "VALIDATION_FAILED" and r.error.fields[0].pointer == "/spec/amount"

    def test_pause_resume_retire(self, engine):
        with as_user("maker"):
            v = engine.create("rate", {"name": "vm", "amount": 1}).value
            assert engine.pause("rate", v.record.id, v.record.revision).error.code == "NOT_ACTIVE"
            v = engine.test("rate", v.record.id, v.record.revision).value
            v = engine.submit("rate", v.record.id, v.record.revision).value
        with as_user("checker"):
            v = engine.approve("rate", v.record.id, v.record.revision).value
            v = engine.pause("rate", v.record.id, v.record.revision).value
            assert engine.active_spec("rate", v.record.id) is None
            v = engine.resume("rate", v.record.id, v.record.revision).value
            v = engine.retire("rate", v.record.id, v.record.revision).value
            assert v.record.status == "retired" and v.active.status == "retired"


class TestMemoryGovernance(_Lifecycle):
    @pytest.fixture
    def uow(self):
        return MemoryUnitOfWorkFactory()

    @pytest.fixture
    def engine(self, uow):
        e = GovernanceEngine(uow=uow, store=MemoryGovernedStore(), source="svc")
        e.register(KIND)
        return e

    @pytest.fixture
    def events(self, uow):
        return lambda: [r.envelope.type for r in MemoryOutboxReader(uow.db).claim(100)]

    @pytest.fixture
    def audit(self, uow):
        return uow.audit_records


@requires_postgres
class TestPostgresGovernance(_Lifecycle):
    @pytest.fixture
    def uow(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresUnitOfWorkFactory

        return PostgresUnitOfWorkFactory(pg_engine, pg_schema)

    @pytest.fixture
    def engine(self, uow):
        e = GovernanceEngine(uow=uow, store=PostgresGovernedStore(), source="svc")
        e.register(KIND)
        return e

    @pytest.fixture
    def events(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresOutboxReader

        return lambda: [r.envelope.type for r in PostgresOutboxReader(pg_engine, pg_schema).claim(100)]

    @pytest.fixture
    def audit(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresAuditReader

        return PostgresAuditReader(pg_engine, pg_schema).records

    def test_row_level_security_hides_other_tenants_in_sql(self, engine, uow):
        from sqlalchemy import text

        with as_user("maker", "t1"):
            engine.create("rate", {"name": "vm", "amount": 1})
        with as_user("other", "t2"), uow() as u:
            assert u.connection.execute(text("select count(*) from governed_record")).scalar() == 0
        with as_user("maker", "t1"), uow() as u:
            assert u.connection.execute(text("select count(*) from governed_record")).scalar() == 1

    def test_database_enforces_maker_checker(self, engine, uow):
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        with as_user("maker"):
            v = engine.create("rate", {"name": "vm", "amount": 1}).value
        with as_user("maker"), pytest.raises(IntegrityError), uow() as u:
            u.connection.execute(text("update governed_version set submitted_by = 'maker', approved_by = 'maker' "
                                      "where id = :i"), {"i": v.record.id})
