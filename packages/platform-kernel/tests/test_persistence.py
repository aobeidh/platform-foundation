from __future__ import annotations

import pytest
from platform_kernel.persistence import MemoryIdempotencyStore, MemoryOutboxReader, MemoryUnitOfWorkFactory
from platform_testing import (
    IdempotencyStoreContract,
    OutboxReaderContract,
    UnitOfWorkContract,
    requires_postgres,
)


class _Memory:
    @pytest.fixture
    def uow_factory(self):
        return MemoryUnitOfWorkFactory()

    @pytest.fixture
    def outbox_reader(self, uow_factory):
        return MemoryOutboxReader(uow_factory.db)

    @pytest.fixture
    def audit_records(self, uow_factory):
        return uow_factory.audit_records

    @pytest.fixture
    def idempotency_store(self, uow_factory):
        return MemoryIdempotencyStore(uow_factory.db)


class TestMemoryUnitOfWork(_Memory, UnitOfWorkContract):
    pass


class TestMemoryOutbox(_Memory, OutboxReaderContract):
    pass


class TestMemoryIdempotency(_Memory, IdempotencyStoreContract):
    pass


@requires_postgres
class _Postgres:
    @pytest.fixture
    def uow_factory(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresUnitOfWorkFactory

        return PostgresUnitOfWorkFactory(pg_engine, pg_schema)

    @pytest.fixture
    def outbox_reader(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresOutboxReader

        return PostgresOutboxReader(pg_engine, pg_schema)

    @pytest.fixture
    def audit_records(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresAuditReader

        return PostgresAuditReader(pg_engine, pg_schema).records

    @pytest.fixture
    def idempotency_store(self, pg_engine, pg_schema):
        from platform_kernel.persistence.postgres import PostgresIdempotencyStore

        return PostgresIdempotencyStore(pg_engine, pg_schema)


class TestPostgresUnitOfWork(_Postgres, UnitOfWorkContract):
    pass


class TestPostgresOutbox(_Postgres, OutboxReaderContract):
    pass


class TestPostgresIdempotency(_Postgres, IdempotencyStoreContract):
    pass


@requires_postgres
def test_migrations_are_recorded_once(pg_engine, pg_schema):
    from platform_kernel.persistence.migrations import migrate

    assert migrate(pg_engine, pg_schema) == []


def test_unsafe_schema_name_is_refused():
    from platform_kernel.persistence.postgres import check_identifier

    with pytest.raises(ValueError):
        check_identifier("x; drop table y")
