"""Scaffolder templates. Placeholders: __NAME__ (service or plugin name), __PKG__ (Python package), __TITLE__,
__KIND__ and __GROUP__ (plugins). Generated code must pass `pk check` and its own tests on the first run (F14)."""
from __future__ import annotations

SERVICE: dict[str, str] = {
    "pyproject.toml": '''[project]
name = "__NAME__"
version = "0.1.0"
description = "__TITLE__ service built on the platform foundation."
requires-python = ">=3.12"
dependencies = ["platform-kernel"]

[tool.uv.sources]
platform-kernel = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
''',
    "service.yaml": '''# Service manifest (spec/manifest.schema.json), checked by `pk check manifests`.
name: __NAME__
tier: S
owner: change-me
package: __PKG__
schema: __PKG__
app: __PKG__.wiring:build
contracts:
  http: contract/openapi.json
errors: src/__PKG__/errors.yaml
migrations: migrations
calls: []
publishes:
  - __NAME__.note.created.v1
consumes: []
interfaces:
  NoteRepository: {providers: [memory, postgres], default: memory}
residency: {runs_in: [primary-region], data: [records, audit]}
''',
    "src/__PKG__/__init__.py": '"""__TITLE__ service."""\n',
    "src/__PKG__/domain/__init__.py": '''"""Domain: pure Python, no frameworks (P3)."""
from .note import InvalidNote, Note

__all__ = ["InvalidNote", "Note"]
''',
    "src/__PKG__/domain/note.py": '''from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MAX_LENGTH = 500


class InvalidNote(ValueError):
    pass


@dataclass(frozen=True)
class Note:
    """Replace this example entity with the service's own domain."""

    id: str
    text: str
    tenant: str | None
    created_by: str
    created_at: datetime

    @classmethod
    def create(cls, *, id: str, text: str, tenant: str | None, author: str, at: datetime) -> Note:
        text = text.strip()
        if not text:
            raise InvalidNote("A note needs some text.")
        if len(text) > MAX_LENGTH:
            raise InvalidNote(f"A note can have at most {MAX_LENGTH} characters.")
        return cls(id=id, text=text, tenant=tenant, created_by=author, created_at=at)
''',
    "src/__PKG__/application/__init__.py": '"""Application: ports and use cases (P3)."""\n',
    "src/__PKG__/application/ports.py": '''from __future__ import annotations

from typing import Any, Protocol

from ..domain import Note


class NoteRepository(Protocol):
    """Product port. Providers: memory and postgres, chosen by PROVIDER_NOTES (P9)."""

    def add(self, uow: Any, note: Note) -> None: ...
    def list(self, uow: Any) -> list[Note]: ...
''',
    "src/__PKG__/application/use_cases.py": '''from __future__ import annotations

from collections.abc import Callable
from typing import Any

from platform_kernel import context
from platform_kernel.audit import AuditEntry
from platform_kernel.core import Clock, DomainError, Err, Ok, Result, new_id
from platform_kernel.messaging import make_event

from ..domain import InvalidNote, Note
from .ports import NoteRepository

SERVICE = "__NAME__"


class CreateNote:
    """Saves the note, its audit record and its event in one unit of work (F9)."""

    def __init__(self, repo: NoteRepository, uow: Callable[[], Any], clock: Clock) -> None:
        self._repo, self._uow, self._clock = repo, uow, clock

    def __call__(self, text: str) -> Result[Note, DomainError]:
        ctx = context.current()
        try:
            note = Note.create(id=new_id(), text=text, tenant=ctx.tenant.tenant, author=ctx.principal.subject,
                               at=self._clock.now())
        except InvalidNote as exc:
            return Err(DomainError("NOTE_INVALID", str(exc)))
        with self._uow() as uow:
            self._repo.add(uow, note)
            uow.audit.append(AuditEntry(stream="notes", action="created", subject=note.id, actor=note.created_by,
                                        tenant=note.tenant, correlation_id=ctx.correlation_id, at=note.created_at))
            uow.events.publish([make_event(f"{SERVICE}.note.created.v1", {"id": note.id}, source=SERVICE,
                                           subject=note.id, now=note.created_at)])
        return Ok(note)


class ListNotes:
    def __init__(self, repo: NoteRepository, uow: Callable[[], Any]) -> None:
        self._repo, self._uow = repo, uow

    def __call__(self) -> list[Note]:
        with self._uow() as uow:
            return self._repo.list(uow)
''',
    "src/__PKG__/adapters/__init__.py": '"""Adapters: HTTP in, persistence out. Only wiring.py names providers."""\n',
    "src/__PKG__/adapters/inbound/__init__.py": "",
    "src/__PKG__/adapters/outbound/__init__.py": "",
    "src/__PKG__/adapters/inbound/http.py": '''from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from platform_kernel.http import Authorizer, DomainException
from pydantic import BaseModel, Field

from ...application.use_cases import CreateNote, ListNotes


class NewNote(BaseModel):
    text: str = Field(min_length=1, max_length=500)


def router(create: CreateNote, list_notes: ListNotes, authz: Authorizer) -> APIRouter:
    r = APIRouter(prefix="/api/v1", tags=["notes"])

    @r.post("/notes", status_code=201, dependencies=[Depends(authz.require("__NAME__:write"))],
            summary="Create a note")
    def create_note(body: NewNote) -> dict[str, Any]:
        result = create(body.text)
        if not result.ok:
            raise DomainException(result.error)
        n = result.value
        return {"id": n.id, "text": n.text, "createdBy": n.created_by, "createdAt": n.created_at.isoformat()}

    @r.get("/notes", dependencies=[Depends(authz.require("__NAME__:read"))], summary="List notes")
    def list_all() -> dict[str, Any]:
        items = [{"id": n.id, "text": n.text, "createdBy": n.created_by, "createdAt": n.created_at.isoformat()}
                 for n in list_notes()]
        return {"items": items, "total": len(items)}

    return r
''',
    "src/__PKG__/adapters/outbound/memory_repo.py": '''from __future__ import annotations

from typing import Any

from platform_kernel import context

from ...domain import Note


class MemoryNoteRepository:
    simulated = True

    def add(self, uow: Any, note: Note) -> None:
        uow.table("notes")[note.id] = note

    def list(self, uow: Any) -> list[Note]:
        scope = context.current().tenant
        notes = [n for n in uow.table("notes").values() if scope.platform or n.tenant == scope.tenant]
        return sorted(notes, key=lambda n: n.created_at)
''',
    "src/__PKG__/adapters/outbound/postgres_repo.py": '''from __future__ import annotations

from typing import Any

from ...domain import Note


class PostgresNoteRepository:
    """Row-level security on the notes table applies tenant scope a second time (P22)."""

    simulated = False

    def add(self, uow: Any, note: Note) -> None:
        from sqlalchemy import text

        uow.connection.execute(text("insert into notes (id, text, tenant_id, created_by, created_at) "
                                    "values (:id, :text, :tenant, :by, :at)"),
                               {"id": note.id, "text": note.text, "tenant": note.tenant, "by": note.created_by,
                                "at": note.created_at})

    def list(self, uow: Any) -> list[Note]:
        from sqlalchemy import text

        rows = uow.connection.execute(text("select * from notes order by created_at"))
        return [Note(r.id, r.text, r.tenant_id, r.created_by, r.created_at) for r in rows]
''',
    "src/__PKG__/errors.yaml": (
        "NOTE_INVALID: {status: 422, retryable: false, title: Note not valid, remedy: Correct the note text.}\n"
    ),
    "src/__PKG__/wiring.py": '''"""Composition root: the only place providers are named (P3, F6)."""
from __future__ import annotations

from pathlib import Path

from platform_kernel.config import PlatformSettings
from platform_kernel.errors import ErrorCatalog
from platform_kernel.platform import Platform
from platform_kernel.policy import CapabilityCatalog, Role

from .adapters.inbound.http import router
from .adapters.outbound.memory_repo import MemoryNoteRepository
from .adapters.outbound.postgres_repo import PostgresNoteRepository
from .application.use_cases import SERVICE, CreateNote, ListNotes

HERE = Path(__file__).parent
MIGRATIONS = HERE.parent.parent / "migrations"


def declare(caps: CapabilityCatalog) -> None:
    caps.declare("__NAME__:read", "Read notes")
    caps.declare("__NAME__:write", "Write notes")


ROLES = [
    Role("__NAME__-reader", frozenset({"__NAME__:read"}), "tenant"),
    Role("__NAME__-writer", frozenset({"__NAME__:read", "__NAME__:write"}), "tenant"),
]


def build(settings: PlatformSettings | None = None):
    settings = settings or PlatformSettings.from_env(SERVICE)
    platform = (
        Platform.builder(SERVICE, settings)
        .with_errors(ErrorCatalog.from_yaml(HERE / "errors.yaml"))
        .with_capabilities(declare)
        .with_roles(ROLES)
        .with_provider("notes", {"memory": lambda p: MemoryNoteRepository(),
                                 "postgres": lambda p: PostgresNoteRepository()},
                       default="postgres" if settings.database_url else "memory")
        .with_migrations(MIGRATIONS)
        .build()
    )
    repo = platform.provider("notes")
    app = platform.create_app([router(CreateNote(repo, platform.uow, platform.clock),
                                      ListNotes(repo, platform.uow), platform.authz)])
    return platform, app
''',
    "src/__PKG__/main.py": '''"""Process entry: `uvicorn __PKG__.main:app`."""
from __future__ import annotations

from platform_kernel.observability import configure_logging

from .wiring import SERVICE, build

configure_logging(SERVICE, "0.1.0", "development")
platform, app = build()
''',
    "migrations/0001_notes.sql": '''create table if not exists notes (
  id text primary key,
  text text not null,
  tenant_id text,
  created_by text not null,
  created_at timestamptz not null
);
alter table notes enable row level security;
alter table notes force row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname = current_schema() and tablename = 'notes') then
    create policy tenant_scope on notes using (
      coalesce(current_setting('app.scope', true), '') = 'platform'
      or tenant_id = current_setting('app.tenant', true));
  end if;
end $$;
''',
    "tests/test___PKG__.py": '''"""Generated tests: they pass on the first run, on memory and on PostgreSQL (F14)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from platform_kernel.config import PlatformSettings
from platform_testing import database_url, requires_postgres

WRITER = {"Authorization": "Bearer demo:ada:__NAME__-writer:t1"}
READER = {"Authorization": "Bearer demo:rui:__NAME__-reader:t1"}
OTHER = {"Authorization": "Bearer demo:oli:__NAME__-writer:t2"}


@pytest.fixture(params=["memory", pytest.param("postgres", marks=requires_postgres)])
def system(request):
    from __PKG__.wiring import build  # imported here so the generated file is lint-clean for any package name

    if request.param == "memory":
        platform, app = build(PlatformSettings(service="__NAME__", allow_demo=True))
        yield platform, TestClient(app)
        platform.close()
        return
    schema = "t_" + uuid.uuid4().hex[:10]
    platform, app = build(PlatformSettings(service="__NAME__", allow_demo=True, database_url=database_url(),
                                           schema_name=schema))
    platform.migrate()
    yield platform, TestClient(app)
    from sqlalchemy import text

    with platform._engine.begin() as c:
        c.execute(text(f"drop schema {schema} cascade"))
    platform.close()


def test_create_and_list(system):
    platform, client = system
    r = client.post("/api/v1/notes", json={"text": "first"}, headers=WRITER)
    assert r.status_code == 201, r.text
    assert [n["text"] for n in client.get("/api/v1/notes", headers=READER).json()["items"]] == ["first"]
    assert platform.relay.run_once() == 1


def test_readers_cannot_write(system):
    _, client = system
    r = client.post("/api/v1/notes", json={"text": "x"}, headers=READER)
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"


def test_blank_note_is_refused(system):
    _, client = system
    r = client.post("/api/v1/notes", json={"text": "   "}, headers=WRITER)
    assert r.status_code == 422 and r.json()["code"] == "NOTE_INVALID"


def test_tenants_are_isolated(system):
    _, client = system
    client.post("/api/v1/notes", json={"text": "mine"}, headers=WRITER)
    assert client.get("/api/v1/notes", headers=OTHER).json()["total"] == 0
''',
}

PLUGIN: dict[str, str] = {
    "pyproject.toml": '''[project]
name = "__NAME__"
version = "0.1.0"
description = "__TITLE__ plugin (__KIND__). Depends only on the plugin SDK."
requires-python = ">=3.12"
dependencies = ["platform-plugin-sdk"]

[project.entry-points."__GROUP__"]
__ID__ = "__PKG__:Plugin"

[tool.uv.sources]
platform-plugin-sdk = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
''',
    "src/__PKG__/__init__.py": '''"""__TITLE__ plugin of kind __KIND__. Depends only on the plugin SDK (P11, P12)."""
from __future__ import annotations

from typing import Any

from platform_plugin_sdk import Check, Descriptor, FieldError, PluginContext


class Plugin:
    descriptor = Descriptor(
        id="__ID__",
        version="0.1.0",
        spi=">=0.1,<1",
        kind="__KIND__",
        config_schema={
            "type": "object",
            "required": ["endpoint"],
            "additionalProperties": False,
            "properties": {"endpoint": {"type": "string", "format": "uri", "pattern": "^https://"}},
        },
        secrets=(),
        display={"en": "__TITLE__"},
        publisher="change-me",
    )

    def validate(self, config: dict[str, Any]) -> list[FieldError]:
        return []

    def test(self, config: dict[str, Any], ctx: PluginContext) -> list[Check]:
        return [Check(name="config", ok=True, detail="The configuration is complete.")]

    def migrate_config(self, config: dict[str, Any], from_version: str) -> dict[str, Any]:
        return dict(config)
''',
    "tests/test___PKG__.py": '''from __future__ import annotations

from platform_kernel.plugins import AllowUnsignedVerifier, PluginHost
from platform_plugin_sdk import Plugin as PluginSpi


def test_registers_with_a_host_and_validates_config():
    from __PKG__ import Plugin  # imported here so the generated file is lint-clean for any package name

    host = PluginHost("__KIND__", "0.1.0", PluginSpi, AllowUnsignedVerifier())
    assert host.register(Plugin()).ok
    assert host.validate_config("__ID__", "0.1.0", {"endpoint": "https://example.com"}).ok
    assert not host.validate_config("__ID__", "0.1.0", {"endpoint": "http://example.com"}).ok
    host.close()
''',
}
