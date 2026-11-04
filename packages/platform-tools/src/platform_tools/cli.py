"""`pk`: the one command that runs every architecture and contract check, locally and in CI (F13).

    pk check                 run all checks
    pk check layers          import layer contracts (lint-imports)
    pk check manifests       manifest schema, unique names, acyclic service graph, events have a publisher
    pk check contracts       each service's OpenAPI matches its committed contract (drift check)
    pk check spec            spec/ schemas match the reference models
    pk check migrations      destructive SQL needs an explicit, reasoned marker (P32); sqlite/ versions match
    pk check guides          every kernel module has its one-page guide (F20)
    pk update contracts|spec regenerate committed files after a reviewed change
    pk scaffold service NAME [--dir services]
    pk scaffold plugin NAME --kind KIND --group ENTRY_POINT_GROUP [--dir plugins]
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import jsonschema
import yaml

SKIP_DIRS = {".venv", "node_modules", ".git", "__pycache__", "dist", "build"}
DESTRUCTIVE = re.compile(r"\b(drop\s+table|drop\s+column|drop\s+schema|truncate|alter\s+column\s+\w+\s+type)\b", re.I)
ALLOW_MARKER = re.compile(r"--\s*pk:\s*allow-destructive\s+\S+", re.I)


def find_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".importlinter").exists() and (p / "pyproject.toml").exists():
            return p
    raise SystemExit("pk: run inside a repository with .importlinter and pyproject.toml")


def manifests(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("service.yaml"):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts):
            found.append(path)
    return sorted(found)


# Checks ------------------------------------------------------------------------------------------------------------

def check_layers(root: Path, update: bool = False) -> list[str]:
    proc = subprocess.run([sys.executable, "-m", "importlinter.cli", "--config", str(root / ".importlinter")],
                          cwd=root, capture_output=True, text=True)
    if proc.returncode != 0:
        out = proc.stdout + proc.stderr
        broken = [line.strip() for line in out.splitlines() if "BROKEN" in line]
        return broken or [out.strip()[-2000:]]
    return []


def check_manifests(root: Path, update: bool = False) -> list[str]:
    problems: list[str] = []
    schema = json.loads((root / "spec" / "manifest.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    loaded: dict[str, dict] = {}
    for path in manifests(root):
        rel = path.relative_to(root)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for err in validator.iter_errors(data):
            loc = "/".join(str(p) for p in err.absolute_path)
            problems.append(f"{rel}: {loc or '(root)'}: {err.message}")
        name = data.get("name")
        if name in loaded:
            problems.append(f"{rel}: service name {name!r} is used twice")
        for port, spec in (data.get("interfaces") or {}).items():
            if spec.get("default") not in spec.get("providers", []):
                problems.append(f"{rel}: interface {port}: default {spec.get('default')!r} is not a listed provider")
        data["_path"] = path
        loaded[name] = data
    for name, data in loaded.items():
        for callee in data.get("calls", []):
            if callee not in loaded:
                problems.append(f"{name}: calls unknown service {callee!r}")
    # P4: the service graph must be acyclic.
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(n: str) -> None:
        state[n] = 1
        stack.append(n)
        for m in loaded.get(n, {}).get("calls", []):
            if m not in loaded:
                continue
            if state.get(m) == 1:
                problems.append("service call cycle: " + " -> ".join(stack[stack.index(m):] + [m]))
            elif m not in state:
                visit(m)
        stack.pop()
        state[n] = 2

    for n in loaded:
        if n not in state:
            visit(n)
    published = {e for d in loaded.values() for e in d.get("publishes", [])}
    for name, data in loaded.items():
        for e in data.get("consumes", []):
            if e not in published:
                problems.append(f"{name}: consumes {e!r}, which no service publishes")
    return problems


def _load_app(target: str):
    os.environ.setdefault("ALLOW_DEMO", "true")
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.pop("DATABASE_URL", None)
    module, attr = target.split(":")
    factory: Callable = getattr(importlib.import_module(module), attr)
    built = factory()
    platform, app = built if isinstance(built, tuple) else (None, built)
    return platform, app


def _canonical(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def check_contracts(root: Path, update: bool = False) -> list[str]:
    problems: list[str] = []
    for path in manifests(root):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not data.get("app"):
            continue
        platform, app = _load_app(data["app"])
        try:
            current = _canonical(app.openapi())
        finally:
            if platform is not None:
                platform.close()
        committed = path.parent / data["contracts"]["http"]
        if update:
            committed.parent.mkdir(parents=True, exist_ok=True)
            committed.write_text(current, encoding="utf-8")
            print(f"pk: wrote {committed.relative_to(root)}")
        elif not committed.exists():
            problems.append(f"{data['name']}: {committed.relative_to(root)} is missing; run `pk update contracts`")
        elif committed.read_text(encoding="utf-8") != current:
            problems.append(f"{data['name']}: the API differs from {committed.relative_to(root)}. Review the change, "
                            f"then run `pk update contracts`")
    return problems


def _spec_models() -> dict[str, object]:
    from platform_kernel.contracts import Envelope, Problem
    from platform_plugin_sdk import Descriptor

    return {"envelope.schema.json": Envelope, "problem.schema.json": Problem,
            "plugin-descriptor.schema.json": Descriptor}


def check_spec(root: Path, update: bool = False) -> list[str]:
    problems: list[str] = []
    for name, model in _spec_models().items():
        target = root / "spec" / name
        current = _canonical(model.model_json_schema(by_alias=True))  # type: ignore[attr-defined]
        if update:
            target.write_text(current, encoding="utf-8")
            print(f"pk: wrote spec/{name}")
        elif not target.exists() or target.read_text(encoding="utf-8") != current:
            problems.append(f"spec/{name} is out of date with its reference model; run `pk update spec`")
    return problems


def check_migrations(root: Path, update: bool = False) -> list[str]:
    problems: list[str] = []
    dirs = [root / "packages/platform-kernel/src/platform_kernel/persistence/sql"]
    for path in manifests(root):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("migrations"):
            dirs.append(path.parent / data["migrations"])
    for d in dirs:
        sqlite = d / "sqlite"
        if sqlite.is_dir():
            # A SQLite version of every migration, with the same file name, and nothing else (ADR 0008).
            names, sqlite_names = {p.name for p in d.glob("*.sql")}, {p.name for p in sqlite.glob("*.sql")}
            for name in sorted(names - sqlite_names):
                problems.append(f"{(sqlite / name).relative_to(root)}: missing; every migration needs a SQLite "
                                f"version with the same file name")
            for name in sorted(sqlite_names - names):
                problems.append(f"{(sqlite / name).relative_to(root)}: has no PostgreSQL migration of the same name")
        for sql in sorted([*d.glob("*.sql"), *sqlite.glob("*.sql")]):
            for i, line in enumerate(sql.read_text(encoding="utf-8").splitlines(), 1):
                if DESTRUCTIVE.search(line) and not ALLOW_MARKER.search(line):
                    problems.append(f"{sql.relative_to(root)}:{i}: destructive statement; follow expand and "
                                    f"contract, or mark it '-- pk: allow-destructive <reason>'")
    return problems


def check_guides(root: Path, update: bool = False) -> list[str]:
    kernel = root / "packages/platform-kernel/src/platform_kernel"
    guides = root / "docs/modules"
    problems = []
    for module in sorted(p.name for p in kernel.iterdir() if p.is_dir() and (p / "__init__.py").exists()):
        if not (guides / f"{module}.md").exists():
            problems.append(f"kernel module {module!r} has no guide at docs/modules/{module}.md")
    return problems


CHECKS: dict[str, Callable[[Path, bool], list[str]]] = {
    "layers": check_layers,
    "manifests": check_manifests,
    "contracts": check_contracts,
    "spec": check_spec,
    "migrations": check_migrations,
    "guides": check_guides,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pk", description="Platform foundation checks (F13)")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="run checks")
    c.add_argument("names", nargs="*", metavar="check", help=", ".join(CHECKS))
    u = sub.add_parser("update", help="regenerate committed contracts or spec after review")
    u.add_argument("what", choices=["contracts", "spec"])
    sc = sub.add_parser("scaffold", help="create a service or plugin that passes every check (F14)")
    sc_sub = sc.add_subparsers(dest="what", required=True)
    svc = sc_sub.add_parser("service")
    svc.add_argument("name")
    svc.add_argument("--dir", default="services")
    plg = sc_sub.add_parser("plugin")
    plg.add_argument("name")
    plg.add_argument("--kind", required=True)
    plg.add_argument("--group", required=True)
    plg.add_argument("--dir", default="plugins")
    args = parser.parse_args(argv)
    root = find_root(Path.cwd())
    if args.command == "scaffold":
        from .scaffold import ScaffoldError, scaffold_plugin, scaffold_service

        try:
            if args.what == "service":
                target = scaffold_service(root, args.name, args.dir)
            else:
                target = scaffold_plugin(root, args.name, args.kind, args.group, args.dir)
        except ScaffoldError as exc:
            print(f"pk: {exc}")
            return 1
        print(f"pk: created {target.relative_to(root)}. Next: uv sync, then pk check and pytest.")
        return 0
    if args.command == "update":
        CHECKS[args.what](root, True)
        return 0
    failed = False
    for name in args.names or list(CHECKS):
        problems = CHECKS[name](root, False)
        status = "OK" if not problems else "FAILED"
        print(f"{name:<11} {status}")
        for p in problems:
            print(f"  - {p}")
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
