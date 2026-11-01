from __future__ import annotations

import pytest
from platform_testing import database_url, fresh_schema


@pytest.fixture(scope="session")
def pg_engine():
    url = database_url()
    if url is None:
        pytest.skip("PF_TEST_DATABASE_URL is not set")
    from platform_kernel.persistence.postgres import create_engine

    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_schema(pg_engine):
    yield from fresh_schema(pg_engine)
