"""Golden test (F14): scaffolded code passes every check and its own tests on the first run, without edits."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from platform_tools import cli
from platform_tools.scaffold import ScaffoldError, scaffold_plugin, scaffold_service

ROOT = Path(__file__).resolve().parent.parent

PYPROJECT = '''[project]
name = "workspace"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["packages/*"]

[dependency-groups]
dev = [
  "pytest>=8.3",
]

[tool.uv.sources]
platform-kernel = { workspace = true }
'''


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "spec").mkdir()
    shutil.copy(ROOT / "spec" / "manifest.schema.json", tmp_path / "spec")
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / ".importlinter").write_text("[importlinter]\nroot_packages =\n    platform_kernel\n", encoding="utf-8")
    return tmp_path


def run(args: list[str], cwd: Path, pythonpath: list[Path]) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(str(p) for p in pythonpath))
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)


def test_scaffolded_service_passes_every_check_and_its_tests(repo, monkeypatch):
    target = scaffold_service(repo, "notes-service")
    src = target / "src"
    monkeypatch.syspath_prepend(str(src))
    monkeypatch.setenv("PYTHONPATH", str(src))

    assert cli.check_manifests(repo) == []
    assert cli.check_layers(repo) == []
    assert cli.check_contracts(repo) == []
    assert cli.check_migrations(repo) == []

    lint = run([sys.executable, "-m", "ruff", "check", "--config", str(ROOT / "pyproject.toml"), str(target)],
               repo, [src])
    assert lint.returncode == 0, lint.stdout + lint.stderr

    tests = run([sys.executable, "-m", "pytest", str(target / "tests"), "-q", "-p", "no:cacheprovider",
                 "-o", "addopts=", "-W", "ignore"], repo, [src])
    assert tests.returncode == 0, tests.stdout[-3000:] + tests.stderr[-2000:]
    expected = 8 if os.environ.get("PF_TEST_DATABASE_URL") else 4
    assert f"{expected} passed" in tests.stdout, tests.stdout[-500:]

    text = (repo / "pyproject.toml").read_text()
    assert '"services/notes-service"' in text and '"notes-service",' in text
    assert "notes-service = { workspace = true }" in text
    assert "[importlinter:contract:notes_service-layers]" in (repo / ".importlinter").read_text()


def test_scaffolded_plugin_registers_and_passes_its_tests(repo):
    target = scaffold_plugin(repo, "acme-sftp", kind="connector", group="acme.connectors")
    src = target / "src"
    lint = run([sys.executable, "-m", "ruff", "check", "--config", str(ROOT / "pyproject.toml"), str(target)],
               repo, [src])
    assert lint.returncode == 0, lint.stdout
    tests = run([sys.executable, "-m", "pytest", str(target / "tests"), "-q", "-p", "no:cacheprovider",
                 "-o", "addopts=", "-W", "ignore"], repo, [src])
    assert tests.returncode == 0 and "1 passed" in tests.stdout, tests.stdout[-2000:]
    assert '[project.entry-points."acme.connectors"]' in (target / "pyproject.toml").read_text()


def test_scaffold_refuses_bad_names_and_existing_targets(repo):
    with pytest.raises(ScaffoldError):
        scaffold_service(repo, "Bad_Name")
    scaffold_plugin(repo, "acme-sftp", kind="connector", group="acme.connectors")
    with pytest.raises(ScaffoldError):
        scaffold_plugin(repo, "acme-sftp", kind="connector", group="acme.connectors")


# Review findings (0.2) ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["class", "match", "json", "email", "platform-kernel", "pytest"])
def test_scaffold_refuses_names_that_would_shadow_python_or_installed_packages(repo, name):
    with pytest.raises(ScaffoldError):
        scaffold_service(repo, name)
    assert not (repo / "services").exists()


@pytest.mark.parametrize("directory", ["../outside", "/tmp/abs", "a/../../b", ""])
def test_scaffold_refuses_a_directory_outside_the_repository(repo, directory):
    with pytest.raises(ScaffoldError):
        scaffold_plugin(repo, "acme-ftp", kind="connector", group="acme.connectors", directory=directory)


def test_scaffold_edits_pyproject_as_toml_and_keeps_comments(repo):
    (repo / "pyproject.toml").write_text(PYPROJECT.replace(
        'dev = [\n  "pytest>=8.3",\n]', '# tools for developers\ndev = ["pytest>=8.3"]  # keep me\n'
    ) + '\n[tool.other]\nmembers = ["not-this-one"]\n', encoding="utf-8")
    scaffold_plugin(repo, "acme-ftp", kind="connector", group="acme.connectors")
    import tomllib

    text = (repo / "pyproject.toml").read_text(encoding="utf-8")
    doc = tomllib.loads(text)
    assert "plugins/acme-ftp" in doc["tool"]["uv"]["workspace"]["members"]
    assert "acme-ftp" in doc["dependency-groups"]["dev"] and "pytest>=8.3" in doc["dependency-groups"]["dev"]
    assert doc["tool"]["uv"]["sources"]["acme-ftp"] == {"workspace": True}
    assert doc["tool"]["other"]["members"] == ["not-this-one"]
    assert "# tools for developers" in text and "# keep me" in text


def test_scaffold_leaves_nothing_behind_when_a_step_fails(repo, monkeypatch):
    from platform_tools import scaffold as sc

    before = {p: p.read_text() for p in (repo / "pyproject.toml", repo / ".importlinter")}

    def broken(*args, **kwargs):
        raise RuntimeError("contract generation failed")

    monkeypatch.setattr(sc, "write_contract", broken)
    with pytest.raises(RuntimeError):
        scaffold_service(repo, "billing")
    assert not (repo / "services" / "billing").exists()
    assert {p: p.read_text() for p in before} == before
    assert not list(repo.glob(".pk-scaffold-*"))
