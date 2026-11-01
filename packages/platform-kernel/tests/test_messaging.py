from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from platform_kernel import context as ctxmod
from platform_kernel.messaging import ConsumerRuntime, InvalidMessage, LocalTransport, PollingRelay, RetryPolicy
from platform_kernel.persistence import MemoryOutboxReader, MemoryUnitOfWorkFactory
from platform_testing import requires_postgres, sample_event


class _Wiring:
    def dead_letters(self, uow_factory):
        raise NotImplementedError

    def test_event_is_handled_once_with_its_tenant_context(self, uow_factory, reader):
        seen = []
        rt = ConsumerRuntime(uow_factory)
        rt.subscribe("test.thing.created.v1", "c1",
                     lambda env, uow: seen.append((env.id, ctxmod.current().tenant.tenant, env.correlationid)))
        relay = PollingRelay(reader, LocalTransport([rt]))
        e = sample_event(tenant="t9")
        with uow_factory(platform_scope=True) as uow:
            uow.events.publish([e])
        assert relay.run_once() == 1
        assert relay.run_once() == 0
        rt.deliver(e)  # a duplicate delivery is skipped by the inbox
        assert seen == [(e.id, "t9", e.correlationid)]

    def test_invalid_message_is_dead_lettered_without_retry(self, uow_factory, reader):
        calls = []

        def handler(env, uow):
            calls.append(1)
            raise InvalidMessage("missing name")

        rt = ConsumerRuntime(uow_factory)
        rt.subscribe("test.thing.created.v1", "c1", handler)
        e = sample_event()
        with uow_factory(platform_scope=True) as uow:
            uow.events.publish([e])
        PollingRelay(reader, LocalTransport([rt])).run_once()
        assert calls == [1]
        assert [(d["kind"], d["reason"]) for d in self.dead_letters(uow_factory)] == [("invalid", "missing name")]

    def test_failures_retry_then_dead_letter(self, uow_factory, reader):
        calls = []

        def handler(env, uow):
            calls.append(1)
            raise RuntimeError("target down")

        rt = ConsumerRuntime(uow_factory)
        rt.subscribe("test.thing.created.v1", "c1", handler, RetryPolicy(max_attempts=3))
        relay = PollingRelay(reader, LocalTransport([rt]))
        with uow_factory(platform_scope=True) as uow:
            uow.events.publish([sample_event()])
        sent = [relay.run_once() for _ in range(3)]
        assert sent == [0, 0, 1] and len(calls) == 3
        kinds = [d["kind"] for d in self.dead_letters(uow_factory)]
        assert kinds == ["dead"]

    def test_expired_message_is_dead_lettered(self, uow_factory, reader):
        rt = ConsumerRuntime(uow_factory)
        rt.subscribe("test.thing.created.v1", "c1", lambda env, uow: pytest.fail("must not run"))
        e = sample_event().model_copy(update={"expiresat": datetime.now(UTC) - timedelta(seconds=1)})
        rt.deliver(e)
        assert [d["reason"] for d in self.dead_letters(uow_factory)] == ["EXPIRED"]


class TestMemoryMessaging(_Wiring):
    @pytest.fixture
    def uow_factory(self):
        return MemoryUnitOfWorkFactory()

    @pytest.fixture
    def reader(self, uow_factory):
        return MemoryOutboxReader(uow_factory.db)

    def dead_letters(self, uow_factory):
        return uow_factory.db.state["dead_letter"]


@requires_postgres
class TestPostgresMessaging(_Wiring):
    @pytest.fixture
    def uow_factory(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresUnitOfWorkFactory

        return PostgresUnitOfWorkFactory(pg_engine, pg_schema)

    @pytest.fixture
    def reader(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresOutboxReader

        return PostgresOutboxReader(pg_engine, pg_schema)

    def dead_letters(self, uow_factory):
        from sqlalchemy import text

        with uow_factory.engine.begin() as c:
            c.execute(text(f"set local search_path to {uow_factory.schema}"))
            return [dict(r._mapping) for r in c.execute(text("select kind, reason from dead_letter order by at"))]
