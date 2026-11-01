from __future__ import annotations

from collections.abc import Callable
from typing import Any

from platform_kernel.contracts import Envelope
from platform_kernel.core import DomainError, Err, Result
from platform_kernel.governance import GovernanceEngine, GovernedKind
from platform_kernel.plugins import PluginHost
from platform_plugin_sdk import Check

from ..domain import Activation
from .ports import ActivationRepository
from .specs import ConnectionSpec

CONNECTION = "connection"


def connection_kind(tests: tuple[Callable[[ConnectionSpec], list[Check]], ...]) -> GovernedKind:
    return GovernedKind(kind=CONNECTION, plural="connections", spec=ConnectionSpec, tests=tests,
                        read="connections:read", write="connections:write", approve="connections:approve",
                        display={"en": "Connection", "ar": "اتصال"})


class ConnectionChecks:
    """Kind tests: the configuration must be valid for the plugin, and the plugin's own test must pass."""

    def __init__(self, host: PluginHost, plugin_context: Callable[[], Any]) -> None:
        self._host, self._ctx = host, plugin_context

    def config_valid(self, spec: ConnectionSpec) -> list[Check]:
        result = self._host.validate_config(spec.connector, spec.connector_version, spec.config)
        if result.ok:
            return [Check(name="config", ok=True, detail="The configuration matches the connector's schema.")]
        detail = result.error.detail + " " + "; ".join(f"{f.pointer}: {f.message}" for f in result.error.fields)
        return [Check(name="config", ok=False, detail=detail.strip())]

    def plugin_test(self, spec: ConnectionSpec) -> list[Check]:
        result = self._host.call(spec.connector, spec.connector_version, "test", spec.config, self._ctx())
        if not result.ok:
            return [Check(name="connector", ok=False, detail=result.error.detail)]
        return list(result.value)


class SendThroughConnection:
    """Send a payload through the active version of a connection. Drafts never run (P13)."""

    def __init__(self, governance: GovernanceEngine, host: PluginHost, plugin_context: Callable[[], Any]) -> None:
        self._gov, self._host, self._ctx = governance, host, plugin_context

    def __call__(self, connection_id: str, payload: dict[str, Any]) -> Result[dict[str, Any], DomainError]:
        spec = self._gov.active_spec(CONNECTION, connection_id)
        if spec is None:
            return Err(DomainError("CONNECTION_NOT_ACTIVE", f"Connection {connection_id} is not active."))
        assert isinstance(spec, ConnectionSpec)
        return self._host.call(spec.connector, spec.connector_version, "send", spec.config, payload, self._ctx())


class RecordActivation:
    """Consumer of `<service>.connection.approved.v1`. Runs once per event thanks to the inbox (P19)."""

    def __init__(self, repo: ActivationRepository) -> None:
        self._repo = repo

    def __call__(self, env: Envelope, uow: Any) -> None:
        self._repo.add(uow, Activation.from_event(env.data, env.tenantid, env.time, env.id))


class ListActivations:
    def __init__(self, repo: ActivationRepository, uow: Callable[[], Any]) -> None:
        self._repo, self._uow = repo, uow

    def __call__(self) -> list[Activation]:
        with self._uow() as uow:
            return self._repo.list(uow)
