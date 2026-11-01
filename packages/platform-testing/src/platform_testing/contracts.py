"""Port contract suites (F4, P9). Subclass a suite and provide its fixtures; every provider must pass unchanged.

Example:
    class TestMemoryUnitOfWork(UnitOfWorkContract):
        @pytest.fixture
        def uow_factory(self): return MemoryUnitOfWorkFactory()
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from platform_kernel.audit import AuditEntry, verify_chain
from platform_kernel.contracts import Envelope
from platform_kernel.core import new_id


def sample_event(type: str = "test.thing.created.v1", tenant: str | None = "t1", **data: object) -> Envelope:
    return Envelope(id=new_id(), source="test", type=type, time=datetime.now(UTC), tenantid=tenant,
                    correlationid=new_id(), data=dict(data))


def audit_entry(stream: str = "things", action: str = "created", subject: str = "x") -> AuditEntry:
    return AuditEntry(stream=stream, action=action, subject=subject, actor="tester", at=datetime.now(UTC))


class UnitOfWorkContract:
    """Needs fixtures: uow_factory, outbox_reader, audit_records (callable stream -> list[AuditRecord])."""

    def test_commit_publishes_events_to_outbox(self, uow_factory, outbox_reader):
        e = sample_event()
        with uow_factory(platform_scope=True) as uow:
            uow.events.publish([e])
        assert [r.id for r in outbox_reader.claim(100)] == [e.id]

    def test_failure_rolls_back_events_audit_and_inbox(self, uow_factory, outbox_reader, audit_records):
        e = sample_event()
        with pytest.raises(RuntimeError), uow_factory(platform_scope=True) as uow:
            uow.events.publish([e])
            uow.audit.append(audit_entry())
            uow.inbox.first_time("c1", e.id)
            raise RuntimeError("boom")
        assert outbox_reader.claim(100) == []
        assert audit_records("things") == []
        with uow_factory(platform_scope=True) as uow:
            assert uow.inbox.first_time("c1", e.id) is True

    def test_inbox_detects_duplicates_per_consumer(self, uow_factory):
        with uow_factory(platform_scope=True) as uow:
            assert uow.inbox.first_time("c1", "e1") is True
            assert uow.inbox.first_time("c1", "e1") is False
            assert uow.inbox.first_time("c2", "e1") is True

    def test_audit_chain_links_and_verifies(self, uow_factory, audit_records):
        for i in range(3):
            with uow_factory(platform_scope=True) as uow:
                uow.audit.append(audit_entry(subject=f"x{i}"))
        records = audit_records("things")
        assert [r.seq for r in records] == [1, 2, 3]
        assert verify_chain(records) == (True, None)


class OutboxReaderContract:
    """Needs fixtures: uow_factory, outbox_reader."""

    def test_claims_in_order_and_marks_sent(self, uow_factory, outbox_reader):
        events = [sample_event(n=i) for i in range(3)]
        with uow_factory(platform_scope=True) as uow:
            uow.events.publish(events)
        claimed = outbox_reader.claim(2)
        assert [r.id for r in claimed] == [e.id for e in events[:2]]
        outbox_reader.mark_sent([r.id for r in claimed])
        assert [r.id for r in outbox_reader.claim(10)] == [events[2].id]

    def test_failed_delivery_counts_attempts(self, uow_factory, outbox_reader):
        e = sample_event()
        with uow_factory(platform_scope=True) as uow:
            uow.events.publish([e])
        outbox_reader.mark_failed(e.id, "down")
        assert outbox_reader.claim(10)[0].attempts == 1


class IdempotencyStoreContract:
    """Needs fixture: idempotency_store."""

    def test_first_call_starts_then_replays_after_completion(self, idempotency_store):
        assert idempotency_store.begin("t1", "k1", "h1").outcome == "started"
        assert idempotency_store.begin("t1", "k1", "h1").outcome == "in_progress"
        idempotency_store.complete("t1", "k1", 201, {"id": "x"})
        replay = idempotency_store.begin("t1", "k1", "h1")
        assert (replay.outcome, replay.status_code, replay.response) == ("replay", 201, {"id": "x"})

    def test_same_key_different_request_is_reused(self, idempotency_store):
        idempotency_store.begin("t1", "k2", "h1")
        assert idempotency_store.begin("t1", "k2", "other").outcome == "reused"

    def test_keys_are_scoped_by_tenant(self, idempotency_store):
        idempotency_store.begin("t1", "k3", "h1")
        assert idempotency_store.begin("t2", "k3", "h1").outcome == "started"

    def test_abandon_allows_retry(self, idempotency_store):
        idempotency_store.begin("t1", "k4", "h1")
        idempotency_store.abandon("t1", "k4")
        assert idempotency_store.begin("t1", "k4", "h1").outcome == "started"
