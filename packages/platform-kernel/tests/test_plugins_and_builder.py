from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

import pytest
from fastapi.testclient import TestClient
from platform_kernel.config import PlatformSettings
from platform_kernel.governance import GovernedKind
from platform_kernel.platform import ConfigurationError, Platform
from platform_kernel.plugins import AllowUnsignedVerifier, PluginHost, PublisherAllowlistVerifier
from platform_kernel.policy import Role
from platform_plugin_sdk import Check, Descriptor, FieldError, PluginContext
from pydantic import BaseModel


@runtime_checkable
class Widget(Protocol):
    descriptor: Descriptor

    def validate(self, config: dict[str, Any]) -> list[FieldError]: ...
    def test(self, config: dict[str, Any], ctx: PluginContext) -> list[Check]: ...
    def migrate_config(self, config: dict[str, Any], from_version: str) -> dict[str, Any]: ...
    def spin(self, seconds: float) -> str: ...


class GoodWidget:
    def __init__(self, version: str = "1.0.0", spi: str = ">=0.1,<1", kind: str = "widget", publisher: str = "acme"):
        self.descriptor = Descriptor(id="good", version=version, spi=spi, kind=kind, display={"en": "Good"},
                                     publisher=publisher, config_schema={
                                         "type": "object", "required": ["size"],
                                         "properties": {"size": {"type": "integer", "minimum": 1}}})

    def validate(self, config):
        return [] if config.get("size", 0) < 100 else [FieldError(pointer="/size", code="too_big", message="Too big")]

    def test(self, config, ctx):
        return [Check(name="ok", ok=True, detail="fine")]

    def migrate_config(self, config, from_version):
        return config

    def spin(self, seconds: float) -> str:
        if seconds < 0:
            raise ValueError("negative")
        time.sleep(seconds)
        return "done"


def host(verifier=None) -> PluginHost:
    return PluginHost("widget", "0.1.0", Widget, verifier or AllowUnsignedVerifier(), call_timeout_seconds=0.3)


def test_register_and_pick_latest_version():
    h = host()
    assert h.register(GoodWidget("1.0.0")).ok and h.register(GoodWidget("1.2.0")).ok
    assert h.get("good").value.descriptor.version == "1.2.0"
    assert [d.version for d in h.descriptors()] == ["1.0.0", "1.2.0"]


@pytest.mark.parametrize("plugin,reason", [
    (GoodWidget(spi=">=1.0"), "SPI_INCOMPATIBLE"),
    (GoodWidget(kind="gadget"), "PLUGIN_KIND_MISMATCH"),
    (object(), "PLUGIN_DESCRIPTOR_INVALID"),
])
def test_refusals(plugin, reason):
    assert host().register(plugin).reason.startswith(reason)


def test_publisher_allowlist():
    h = host(PublisherAllowlistVerifier({"acme"}))
    assert h.register(GoodWidget()).ok
    assert h.register(GoodWidget(version="2.0.0", publisher="mallory")).reason == "PLUGIN_SIGNATURE_INVALID"


def test_config_validation_uses_schema_then_plugin():
    h = host()
    h.register(GoodWidget())
    assert h.validate_config("good", "1.0.0", {"size": 5}).ok
    bad = h.validate_config("good", "1.0.0", {"size": 0})
    assert bad.error.fields[0].pointer == "/size"
    too_big = h.validate_config("good", "1.0.0", {"size": 500})
    assert too_big.error.fields[0].code == "too_big"


def test_calls_time_out_and_failures_are_translated():
    h = host()
    h.register(GoodWidget())
    assert h.call("good", "1.0.0", "spin", 0).value == "done"
    assert h.call("good", "1.0.0", "spin", 2).error.code == "PLUGIN_FAILED"
    failed = h.call("good", "1.0.0", "spin", -1)
    assert failed.error.code == "PLUGIN_FAILED" and "negative" in failed.error.detail
    h.close()


# Builder ---------------------------------------------------------------------------------------------------------

class Note(BaseModel):
    text: str


NOTE = GovernedKind(kind="note", plural="notes", spec=Note, read="notes:read", write="notes:write",
                    approve="notes:approve")


def declare(caps):
    caps.declare("notes:read", "Read notes")
    caps.declare("notes:write", "Write notes")
    caps.declare("notes:approve", "Approve notes")


def test_builder_fails_fast_with_every_problem_listed():
    s = PlatformSettings(service="svc", environment="production", allow_demo=True)
    with pytest.raises(ConfigurationError) as e:
        Platform.builder("svc", s).with_governed_kinds([NOTE]).build()
    text = str(e.value)
    assert "undeclared capability" in text
    assert "'persistence' is not allowed" in text and "ALLOW_DEMO" in text


def test_builder_requires_identity_unless_demo():
    with pytest.raises(ConfigurationError) as e:
        Platform.builder("svc", PlatformSettings(service="svc")).build()
    assert "no identity provider" in str(e.value)


def test_unknown_provider_lists_valid_choices():
    s = PlatformSettings(service="svc", allow_demo=True, providers={"persistence": "mongo"})
    with pytest.raises(ConfigurationError) as e:
        Platform.builder("svc", s).build()
    assert "memory, postgres" in str(e.value)


def test_built_platform_serves_governed_api_with_capabilities():
    s = PlatformSettings(service="svc", allow_demo=True)
    p = (Platform.builder("svc", s).with_capabilities(declare)
         .with_roles([Role("author", frozenset({"notes:read", "notes:write"}), "tenant"),
                      Role("reviewer", frozenset({"notes:read", "notes:approve"}), "tenant")])
         .with_governed_kinds([NOTE]).build())
    client = TestClient(p.create_app())
    author = {"Authorization": "Bearer demo:ann:author:t1"}
    reviewer = {"Authorization": "Bearer demo:rev:reviewer:t1"}
    r = client.post("/api/v1/notes", json={"spec": {"text": "hello"}}, headers=author)
    assert r.status_code == 201 and r.headers["etag"] == '"1"'
    rid = r.json()["id"]
    r = client.post(f"/api/v1/notes/{rid}/test", headers=author | {"If-Match": '"1"'})
    r = client.post(f"/api/v1/notes/{rid}/submit", headers=author | {"If-Match": r.headers["etag"]})
    assert client.post(f"/api/v1/notes/{rid}/approve", headers=author | {"If-Match": r.headers["etag"]}
                       ).json()["code"] == "FORBIDDEN"
    r = client.post(f"/api/v1/notes/{rid}/approve", headers=reviewer | {"If-Match": r.headers["etag"]})
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert client.post(f"/api/v1/notes/{rid}/pause", headers=author).json()["code"] == "VALIDATION_FAILED"
    assert p.relay.run_once() == 4
    assert set(p.simulated) == {"identity", "persistence", "secrets"}
