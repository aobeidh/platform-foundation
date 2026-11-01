"""PostgreSQL test helpers. Set PF_TEST_DATABASE_URL to run PostgreSQL suites; they are skipped otherwise.

Use a non-superuser role so row-level security is enforced as in production."""
from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ENV = "PF_TEST_DATABASE_URL"


def database_url() -> str | None:
    return os.environ.get(ENV)


requires_postgres = pytest.mark.skipif(database_url() is None, reason=f"{ENV} is not set")


def fresh_schema(engine: Any, product_dirs: list[Path] | None = None) -> Iterator[str]:
    """Create a migrated, throwaway schema; drop it afterwards."""
    from platform_kernel.persistence.migrations import migrate
    from sqlalchemy import text

    schema = "t_" + uuid.uuid4().hex[:12]
    migrate(engine, schema, product_dirs)
    try:
        yield schema
    finally:
        with engine.begin() as c:
            c.execute(text(f"drop schema if exists {schema} cascade"))
