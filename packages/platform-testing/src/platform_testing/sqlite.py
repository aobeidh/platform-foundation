"""SQLite test helpers. SQLite needs no server, so its suites always run, on a temporary database file."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any


def fresh_sqlite(directory: str | Path, product_dirs: list[Path] | None = None) -> Iterator[Any]:
    """Create a migrated SQLite database file in `directory` (pytest's `tmp_path`, for example) and yield its
    engine; dispose of the engine afterwards. Product directories need a `sqlite/` subfolder (ADR 0008)."""
    from platform_kernel.persistence.migrations import migrate_sqlite
    from platform_kernel.persistence.sqlite import create_engine

    engine = create_engine(f"sqlite:///{Path(directory) / 'platform.db'}")
    try:
        migrate_sqlite(engine, product_dirs)
        yield engine
    finally:
        engine.dispose()
