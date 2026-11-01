"""`pk scaffold`: new services and plugins that pass `pk check` and their own tests on the first run (F14)."""
from __future__ import annotations

import importlib
import importlib.util
import keyword
import re
import shutil
import sys
import tempfile
from pathlib import Path

import tomlkit

from . import templates

NAME = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


class ScaffoldError(Exception):
    pass


def _check_name(name: str, what: str) -> str:
    """The name becomes a Python package: refuse keywords, the standard library and anything already importable,
    so the new package can never shadow existing code."""
    if not NAME.match(name):
        raise ScaffoldError(f"a {what} name is lowercase letters, digits and hyphens, 2 to 63 characters")
    pkg = name.replace("-", "_")
    if keyword.iskeyword(pkg) or keyword.issoftkeyword(pkg):
        raise ScaffoldError(f"{name!r} is a Python keyword; choose another {what} name")
    if pkg in sys.stdlib_module_names:
        raise ScaffoldError(f"{name!r} is a standard library module; choose another {what} name")
    if importlib.util.find_spec(pkg) is not None:
        raise ScaffoldError(f"a package named {pkg!r} is already installed; choose another {what} name")
    return pkg


def _check_dir(root: Path, directory: str) -> Path:
    rel = Path(directory)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ScaffoldError("--dir is a relative folder inside the repository, for example 'services'")
    if not (root / rel).resolve().is_relative_to(root.resolve()):
        raise ScaffoldError("--dir must stay inside the repository")
    return rel


def _render(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def _write(base: Path, files: dict[str, str], values: dict[str, str]) -> list[Path]:
    written = []
    for rel, content in files.items():
        path = base / _render(rel, values)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_render(content, values), encoding="utf-8")
        written.append(path)
    return written


def _commit(root: Path, staged: Path, target: Path, edits: dict[Path, str]) -> None:
    """Move the generated folder into place and write the configuration edits; undo everything on failure."""
    originals = {path: path.read_text(encoding="utf-8") if path.exists() else None for path in edits}
    target.parent.mkdir(parents=True, exist_ok=True)
    staged.rename(target)
    try:
        for path, text in edits.items():
            path.write_text(text, encoding="utf-8")
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        for path, text in originals.items():
            if text is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(text, encoding="utf-8")
        raise


def _layers_text(root: Path, pkg: str) -> str:
    """The import-linter configuration with the new package added: inward layers and a pure domain (P3)."""
    path = root / ".importlinter"
    text = path.read_text(encoding="utf-8") if path.exists() else "[importlinter]\nroot_packages =\n"
    if f"[importlinter:contract:{pkg}-layers]" in text:
        return text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("root_packages"):
            j = i + 1
            while j < len(lines) and lines[j].startswith((" ", "\t")):
                j += 1
            lines.insert(j, f"    {pkg}")
            break
    else:
        raise ScaffoldError(".importlinter has no root_packages entry; add the package by hand")
    text = "\n".join(lines).rstrip() + f"""


[importlinter:contract:{pkg}-layers]
name = {pkg}: dependencies point inward (P3)
type = layers
containers = {pkg}
layers =
    main
    wiring
    adapters
    application
    domain

[importlinter:contract:{pkg}-domain-pure]
name = {pkg}: domain imports no web or database frameworks (P3)
type = forbidden
source_modules = {pkg}.domain
forbidden_modules =
    fastapi
    sqlalchemy
    psycopg
    httpx
"""
    return text


def _workspace_text(root: Path, rel: Path, name: str) -> str | None:
    """The root pyproject.toml with the package added to the uv workspace, the dev group and the sources. Edited
    as TOML (comments and layout kept), never with text patterns. None when there is no root pyproject."""
    path = root / "pyproject.toml"
    if not path.exists():
        return None
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    uv = doc.setdefault("tool", tomlkit.table(True)).setdefault("uv", tomlkit.table())
    workspace = uv.setdefault("workspace", tomlkit.table())
    members = workspace.setdefault("members", tomlkit.array())
    if not any(rel.match(str(g)) or rel.as_posix() == str(g) for g in members):
        members.append(rel.as_posix())
    dev = doc.setdefault("dependency-groups", tomlkit.table()).setdefault("dev", tomlkit.array())
    if not any(re.split(r"[\[<>=!~ ;]", str(d), maxsplit=1)[0] == name for d in dev):
        dev.append(name)
        dev.multiline(True)
    sources = uv.setdefault("sources", tomlkit.table())
    if name not in sources:
        sources[name] = tomlkit.parse("x = { workspace = true }")["x"]  # same layout as hand-written entries
    return tomlkit.dumps(doc)


def scaffold_service(root: Path, name: str, directory: str = "services", register: bool = True) -> Path:
    """Generate in a temporary folder, render its contract, then move it into place and register it. A failure at
    any step leaves the repository as it was."""
    pkg = _check_name(name, "service")
    rel = _check_dir(root, directory) / name
    target = root / rel
    if target.exists():
        raise ScaffoldError(f"{target} already exists")
    values = {"__NAME__": name, "__PKG__": pkg, "__TITLE__": name.replace("-", " ").capitalize()}
    with tempfile.TemporaryDirectory(prefix=".pk-scaffold-", dir=root) as tmp:
        staged = Path(tmp) / name
        _write(staged, templates.SERVICE, values)
        write_contract(staged, pkg)
        edits: dict[Path, str] = {}
        if register:
            edits[root / ".importlinter"] = _layers_text(root, pkg)
            workspace = _workspace_text(root, rel, name)
            if workspace is not None:
                edits[root / "pyproject.toml"] = workspace
        _commit(root, staged, target, edits)
    return target


def write_contract(service_dir: Path, pkg: str) -> None:
    """Generate the first committed contract from the generated app, so `pk check contracts` passes at once."""
    import os

    from .cli import _canonical

    src = str(service_dir / "src")
    added = src not in sys.path
    if added:
        sys.path.insert(0, src)
    os.environ.setdefault("ALLOW_DEMO", "true")
    try:
        module = importlib.import_module(f"{pkg}.wiring")
        platform, app = module.build()
        try:
            (service_dir / "contract").mkdir(exist_ok=True)
            (service_dir / "contract" / "openapi.json").write_text(_canonical(app.openapi()), encoding="utf-8")
        finally:
            platform.close()
    finally:
        if added:
            sys.path.remove(src)
        for mod in [m for m in sys.modules if m == pkg or m.startswith(pkg + ".")]:
            del sys.modules[mod]


def scaffold_plugin(root: Path, name: str, kind: str, group: str, directory: str = "plugins",
                    register: bool = True) -> Path:
    pkg = _check_name(name, "plugin")
    if not NAME.match(kind):
        raise ScaffoldError("a kind is lowercase letters, digits and hyphens")
    if not re.match(r"^[a-z][a-z0-9_.-]*$", group):
        raise ScaffoldError("the entry point group is lowercase, for example 'hub.connectors'")
    rel = _check_dir(root, directory) / name
    target = root / rel
    if target.exists():
        raise ScaffoldError(f"{target} already exists")
    plugin_id = name.removesuffix("-plugin")
    values = {"__NAME__": name, "__PKG__": pkg, "__TITLE__": name.replace("-", " ").capitalize(),
              "__KIND__": kind, "__GROUP__": group, "__ID__": plugin_id}
    with tempfile.TemporaryDirectory(prefix=".pk-scaffold-", dir=root) as tmp:
        staged = Path(tmp) / name
        _write(staged, templates.PLUGIN, values)
        edits: dict[Path, str] = {}
        if register:
            workspace = _workspace_text(root, rel, name)
            if workspace is not None:
                edits[root / "pyproject.toml"] = workspace
        _commit(root, staged, target, edits)
    return target
