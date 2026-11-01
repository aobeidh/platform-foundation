"""Migration runner. Applies the kernel's SQL, then the product's, in file-name order inside the service schema,
and records each file once. Destructive statements are flagged by `pk check migrations` (P32)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .postgres import check_identifier

KERNEL_SQL = Path(__file__).with_name("sql")


def migrate(engine: Any, schema: str, product_dirs: list[Path] | None = None) -> list[str]:
    from sqlalchemy import text

    schema = check_identifier(schema)
    applied: list[str] = []
    dirs = [("kernel", KERNEL_SQL)] + [("product", Path(d)) for d in (product_dirs or [])]
    with engine.begin() as c:
        c.execute(text("select pg_advisory_xact_lock(hashtext(:s))"), {"s": "migrate:" + schema})
        c.execute(text(f"create schema if not exists {schema}"))
        c.execute(text(f"set local search_path to {schema}"))
        c.execute(text("create table if not exists schema_migration (name text primary key, "
                       "applied_at timestamptz not null default now())"))
        done = {r[0] for r in c.execute(text("select name from schema_migration"))}
        for origin, directory in dirs:
            for path in sorted(directory.glob("*.sql")):
                name = f"{origin}/{path.name}"
                if name in done:
                    continue
                c.exec_driver_sql(path.read_text(encoding="utf-8"))
                c.execute(text("insert into schema_migration (name) values (:n)"), {"n": name})
                applied.append(name)
    return applied
