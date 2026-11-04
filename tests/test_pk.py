"""Tests for the pk checks, run against throwaway repositories."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from platform_tools import cli

ROOT = Path(__file__).resolve().parent.parent


def repo(tmp_path: Path, services: dict[str, dict]) -> Path:
    (tmp_path / "spec").mkdir()
    shutil.copy(ROOT / "spec" / "manifest.schema.json", tmp_path / "spec")
    for name, extra in services.items():
        d = tmp_path / name
        d.mkdir()
        m = {"name": name, "tier": "S", "owner": "team", "package": name.replace("-", "_"),
             "schema": name.replace("-", "_"), "contracts": {"http": "contract/openapi.json"}, "calls": [],
             "publishes": [], "consumes": [], "residency": {"runs_in": ["r1"], "data": []}} | extra
        import yaml

        (d / "service.yaml").write_text(yaml.safe_dump(m), encoding="utf-8")
    return tmp_path


def test_valid_manifests_pass(tmp_path):
    root = repo(tmp_path, {"alpha": {"calls": ["beta"], "publishes": ["alpha.thing.created.v1"]},
                           "beta": {"consumes": ["alpha.thing.created.v1"]}})
    assert cli.check_manifests(root) == []


def test_cycles_are_reported(tmp_path):
    root = repo(tmp_path, {"alpha": {"calls": ["beta"]}, "beta": {"calls": ["gamma"]}, "gamma": {"calls": ["alpha"]}})
    problems = cli.check_manifests(root)
    assert any("cycle: alpha -> beta -> gamma -> alpha" in p for p in problems)


def test_unknown_calls_orphan_events_and_bad_defaults(tmp_path):
    root = repo(tmp_path, {"alpha": {"calls": ["ghost"], "consumes": ["x.y.z.v1"],
                                 "interfaces": {"Repo": {"providers": ["memory", "postgres"], "default": "mongo"}}}})
    problems = "\n".join(cli.check_manifests(root))
    assert "unknown service 'ghost'" in problems
    assert "no service publishes" in problems
    assert "default 'mongo'" in problems


def test_schema_violations_are_reported(tmp_path):
    root = repo(tmp_path, {"alpha": {"tier": "X"}})
    assert any("tier" in p for p in cli.check_manifests(root))


def test_destructive_migrations_need_a_reason(tmp_path):
    root = repo(tmp_path, {"alpha": {"migrations": "migrations"}})
    (root / "packages/platform-kernel/src/platform_kernel/persistence/sql").mkdir(parents=True)
    mig = root / "alpha" / "migrations"
    mig.mkdir()
    (mig / "0002_x.sql").write_text("alter table t drop column c;\n", encoding="utf-8")
    assert len(cli.check_migrations(root)) == 1
    (mig / "0002_x.sql").write_text("alter table t drop column c; -- pk: allow-destructive column unused since 0.3\n",
                                    encoding="utf-8")
    assert cli.check_migrations(root) == []


def test_sqlite_migrations_match_by_name_and_are_checked_for_destructive_sql(tmp_path):
    root = repo(tmp_path, {"alpha": {"migrations": "migrations"}})
    (root / "packages/platform-kernel/src/platform_kernel/persistence/sql").mkdir(parents=True)
    mig = root / "alpha" / "migrations"
    (mig / "sqlite").mkdir(parents=True)
    (mig / "0001_a.sql").write_text("create table a (x jsonb);\n", encoding="utf-8")
    (mig / "0002_b.sql").write_text("create table b (x jsonb);\n", encoding="utf-8")
    (mig / "sqlite" / "0001_a.sql").write_text("create table a (x text);\n", encoding="utf-8")
    (mig / "sqlite" / "0003_c.sql").write_text("drop table a;\n", encoding="utf-8")
    problems = cli.check_migrations(root)
    assert len(problems) == 3
    assert any("sqlite/0002_b.sql: missing" in p for p in problems)
    assert any("sqlite/0003_c.sql: has no PostgreSQL" in p for p in problems)
    assert any("sqlite/0003_c.sql:1: destructive" in p for p in problems)


def test_contract_drift_is_detected():
    problems = cli.check_contracts(ROOT)
    assert problems == []
    contract = ROOT / "exemplar/service/contract/openapi.json"
    original = contract.read_text(encoding="utf-8")
    try:
        data = json.loads(original)
        data["info"]["title"] = "changed"
        contract.write_text(json.dumps(data), encoding="utf-8")
        assert any("differs" in p for p in cli.check_contracts(ROOT))
    finally:
        contract.write_text(original, encoding="utf-8")
