"""Migration runners. Apply the kernel's SQL, then the product's, in file-name order, and record each file once.
Destructive statements are flagged by `pk check migrations` (P32).

PostgreSQL (`migrate`) applies each directory's `*.sql` files inside the service schema. SQLite (`migrate_sqlite`)
applies the files in each directory's `sqlite/` subfolder instead: a product that supports SQLite keeps a SQLite
version of every migration there, with the same file name (ADR 0008)."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .postgres import check_identifier

KERNEL_SQL = Path(__file__).with_name("sql")
SQLITE_FOLDER = "sqlite"


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


def migrate_sqlite(engine: Any, product_dirs: list[Path] | None = None) -> list[str]:
    """Apply the `sqlite/` files of the kernel's migration directory, then of each product directory, in name order,
    once each, in one `BEGIN IMMEDIATE` transaction (so one migrator runs at a time). Each file is recorded in
    `schema_migration` as `kernel/<name>` or `product/<name>`, as the PostgreSQL runner records it. A directory
    without a `sqlite/` subfolder is an error that names it, and nothing is applied."""
    from sqlalchemy import text

    from .sqlite import to_text

    dirs = [("kernel", KERNEL_SQL)] + [("product", Path(d)) for d in (product_dirs or [])]
    missing = [str(d) for _, d in dirs if not (d / SQLITE_FOLDER).is_dir()]
    if missing:
        raise ValueError("these migration directories have no sqlite/ subfolder with SQLite versions of their "
                         "files: " + ", ".join(missing))
    applied: list[str] = []
    with engine.begin() as c:
        c.execute(text("create table if not exists schema_migration (name text primary key, applied_at text not null)"))
        done = {r[0] for r in c.execute(text("select name from schema_migration"))}
        for origin, directory in dirs:
            for path in sorted((directory / SQLITE_FOLDER).glob("*.sql")):
                name = f"{origin}/{path.name}"
                if name in done:
                    continue
                for statement in sqlite_statements(path.read_text(encoding="utf-8")):
                    c.exec_driver_sql(statement)
                c.execute(text("insert into schema_migration (name, applied_at) values (:n, :at)"),
                          {"n": name, "at": to_text(datetime.now(UTC))})
                applied.append(name)
    return applied


def sqlite_statements(script: str) -> list[str]:
    """Split a SQLite script into single statements, keeping semicolons inside strings, comments and trigger bodies.
    (sqlite3's `executescript` cannot be used: it commits the open transaction first.) Text after the last complete
    statement is kept as one more statement, so SQLite reports its error when it runs."""
    out: list[str] = []
    buffer = ""
    parts = script.split(";")
    for part in parts[:-1]:
        buffer += part + ";"
        if sqlite3.complete_statement(buffer):
            if _has_code(buffer):
                out.append(buffer.strip())
            buffer = ""
    buffer += parts[-1]
    if _has_code(buffer):
        out.append(buffer.strip())
    return out


def _has_code(sql: str) -> bool:
    """True when the text holds more than comments, blank lines and semicolons."""
    return any(line.split("--", 1)[0].strip().strip(";").strip() for line in sql.splitlines())
