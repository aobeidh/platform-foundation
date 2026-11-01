"""Composition root: the only place providers are named (P3, F6)."""
from __future__ import annotations

from pathlib import Path

from platform_kernel.config import PlatformSettings
from platform_kernel.errors import ErrorCatalog
from platform_kernel.platform import Platform
from platform_kernel.policy import CapabilityCatalog, Role

from .adapters.inbound.http import router
from .adapters.outbound.memory_repo import MemoryActivationRepository
from .adapters.outbound.postgres_repo import PostgresActivationRepository
from .application.spi import SPI_VERSION, ConnectorSpi
from .application.use_cases import (
    ConnectionChecks,
    ListActivations,
    RecordActivation,
    SendThroughConnection,
    connection_kind,
)

SERVICE = "connections"
HERE = Path(__file__).parent
MIGRATIONS = HERE.parent.parent / "migrations"


def declare(caps: CapabilityCatalog) -> None:
    caps.declare("connections:read", "Read connections", ar="عرض الاتصالات")
    caps.declare("connections:write", "Change connections", ar="تعديل الاتصالات")
    caps.declare("connections:approve", "Approve connections", ar="اعتماد الاتصالات")
    caps.declare("connections:use", "Send through connections", ar="الإرسال عبر الاتصالات")


ROLES = [
    Role("integration-admin", frozenset({"connections:read", "connections:write", "connections:use"}), "tenant"),
    Role("integration-approver", frozenset({"connections:read", "connections:approve"}), "tenant"),
    Role("platform-operator", frozenset({"connections:read"}), "platform"),
]
SEPARATION_OF_DUTIES = [("connections:write", "connections:approve")]


def build(settings: PlatformSettings | None = None, *, discover_plugins: bool = True):
    settings = settings or PlatformSettings.from_env(SERVICE)
    platform = (
        Platform.builder(SERVICE, settings)
        .with_errors(ErrorCatalog.from_yaml(HERE / "errors.yaml"))
        .with_capabilities(declare)
        .with_roles(ROLES, SEPARATION_OF_DUTIES)
        .with_plugin_kind("connector", ConnectorSpi, SPI_VERSION,
                          discover_group="exemplar.connectors" if discover_plugins else None)
        .with_provider("activations", {"memory": lambda p: MemoryActivationRepository(),
                                       "postgres": lambda p: PostgresActivationRepository()},
                       default="postgres" if settings.database_url else "memory")
        .with_migrations(MIGRATIONS)
        .build()
    )
    host = platform.plugins("connector")
    checks = ConnectionChecks(host, platform.plugin_context)
    platform.governance.register(connection_kind((checks.config_valid, checks.plugin_test)))
    repo = platform.provider("activations")
    platform.consumers.subscribe(f"{SERVICE}.connection.approved.v1", "record-activation", RecordActivation(repo))
    app = platform.create_app([router(SendThroughConnection(platform.governance, host, platform.plugin_context),
                                      ListActivations(repo, platform.uow), platform.authz)])
    return platform, app
