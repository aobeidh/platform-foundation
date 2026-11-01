"""The Platform builder: the only way to assemble the kernel (F6). Products call it from wiring.py; embedding hosts
call it from their own startup. It validates the configuration and fails fast with every problem listed."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI

from ..config import MemorySecretStore, PlatformSettings, SecretStore, UnknownProvider
from ..core import Clock, SystemClock
from ..errors import ErrorCatalog, kernel_catalog
from ..governance import GovernanceEngine, GovernedKind, MemoryGovernedStore, PostgresGovernedStore, governed_router
from ..http import Authorizer, EgressPolicy, HttpSettings, ResilientClient, create_app
from ..identity import DemoTokenVerifier, TokenVerifier
from ..messaging import ConsumerRuntime, LocalTransport, PollingRelay
from ..observability import get_logger
from ..persistence import (
    IdempotencyStore,
    MemoryIdempotencyStore,
    MemoryOutboxReader,
    MemoryUnitOfWorkFactory,
    OutboxReader,
    UnitOfWorkFactory,
)
from ..plugins import AllowUnsignedVerifier, PluginHost, SignatureVerifier
from ..policy import CapabilityCatalog, InProcessPolicyEngine, PolicyEngine, Role


class ConfigurationError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("platform configuration is not valid:\n  - " + "\n  - ".join(problems))
        self.problems = problems


@dataclass
class _PluginKind:
    kind: str
    spi: type
    spi_version: str
    group: str | None


class _PluginContext:
    """The narrow context handed to plugins (P12)."""

    def __init__(self, secrets: SecretStore, http: ResilientClient, clock: Clock, log: Any) -> None:
        self.secrets, self.http, self.clock, self.log = secrets, http, clock, log


@dataclass
class Platform:
    settings: PlatformSettings
    clock: Clock
    errors: ErrorCatalog
    uow: UnitOfWorkFactory
    outbox: OutboxReader
    idempotency: IdempotencyStore
    verifier: TokenVerifier
    policy: PolicyEngine
    authz: Authorizer
    secrets: SecretStore
    egress: EgressPolicy
    governance: GovernanceEngine
    consumers: ConsumerRuntime
    relay: PollingRelay
    simulated: list[str]
    _plugin_hosts: dict[str, PluginHost] = field(default_factory=dict)
    _migrations: list[Path] = field(default_factory=list)
    _engine: Any = None
    _providers: dict[str, Any] = field(default_factory=dict)
    _plugin_ctx: _PluginContext | None = None

    @staticmethod
    def builder(service: str, settings: PlatformSettings | None = None) -> PlatformBuilder:
        return PlatformBuilder(service, settings)

    def plugins(self, kind: str) -> PluginHost:
        return self._plugin_hosts[kind]

    def provider(self, port: str) -> Any:
        """Product ports registered through the builder (with_provider)."""
        return self._providers[port]

    def http_client(self, name: str, base_url: str, **kwargs: Any) -> ResilientClient:
        return ResilientClient(name, base_url, egress=self.egress, **kwargs)

    def plugin_context(self) -> _PluginContext:
        """One context, one egress-bound client, one breaker and bulkhead for all plugin calls (P12, P26)."""
        if self._plugin_ctx is None:
            self._plugin_ctx = _PluginContext(self.secrets, self.http_client("plugins", "https://invalid.local"),
                                              self.clock, get_logger("platform.plugin"))
        return self._plugin_ctx

    def governed_routers(self) -> list[APIRouter]:
        return [governed_router(self.governance, k.kind, self.authz) for k in self.governance.kinds()]

    def create_app(self, routers: Iterable[APIRouter] = (), *, include_governed: bool = True,
                   readiness: dict[str, Callable[[], bool]] | None = None, version: str = "0.1.0") -> FastAPI:
        all_routers = list(routers) + (self.governed_routers() if include_governed else [])
        probes = dict(readiness or {})
        if self._engine is not None:
            probes.setdefault("database", self._database_ready)
        return create_app(
            settings=HttpSettings(service=self.settings.service,
                                  request_timeout=timedelta(seconds=self.settings.request_timeout_seconds),
                                  max_body_bytes=self.settings.max_body_bytes, simulated=self.simulated,
                                  production=self.settings.production),
            verifier=self.verifier, catalog=self.errors, idempotency=self.idempotency, routers=all_routers,
            readiness=probes, version=version)

    def migrate(self) -> list[str]:
        """Apply kernel and product migrations. Run as the migration role, not the application role (P7)."""
        if self._engine is None:
            return []
        from ..persistence.migrations import migrate

        return migrate(self._engine, self.settings.schema_name or self.settings.service.replace("-", "_"),
                       self._migrations)

    def _database_ready(self) -> bool:
        from sqlalchemy import text

        with self._engine.connect() as c:
            return c.execute(text("select 1")).scalar() == 1

    def close(self) -> None:
        for host in self._plugin_hosts.values():
            host.close()
        if self._plugin_ctx is not None:
            self._plugin_ctx.http.close()
        if self._engine is not None:
            self._engine.dispose()


class PlatformBuilder:
    def __init__(self, service: str, settings: PlatformSettings | None) -> None:
        self._settings = settings or PlatformSettings.from_env(service)
        self._clock: Clock = SystemClock()
        self._errors = kernel_catalog()
        self._verifier: TokenVerifier | None = None
        self._policy: PolicyEngine | None = None
        self._capabilities = CapabilityCatalog()
        self._roles: list[Role] = []
        self._sod: list[tuple[str, str]] = []
        self._secrets: SecretStore | None = None
        self._kinds: list[GovernedKind] = []
        self._plugin_kinds: list[_PluginKind] = []
        self._signature: SignatureVerifier | None = None
        self._migrations: list[Path] = []
        self._providers: dict[str, dict[str, Callable[[Platform], Any]]] = {}
        self._defaults: dict[str, str] = {}
        self._egress: EgressPolicy | None = None

    # Configuration ----------------------------------------------------------------------------------------------

    def with_clock(self, clock: Clock) -> PlatformBuilder:
        self._clock = clock
        return self

    def with_errors(self, catalog: ErrorCatalog) -> PlatformBuilder:
        self._errors.merge(catalog)
        return self

    def with_identity(self, verifier: TokenVerifier) -> PlatformBuilder:
        self._verifier = verifier
        return self

    def with_capabilities(self, declare: Callable[[CapabilityCatalog], None]) -> PlatformBuilder:
        declare(self._capabilities)
        return self

    def with_roles(self, roles: list[Role],
                   separation_of_duties: list[tuple[str, str]] | None = None) -> PlatformBuilder:
        self._roles.extend(roles)
        self._sod.extend(separation_of_duties or [])
        return self

    def with_policy_engine(self, engine: PolicyEngine) -> PlatformBuilder:
        self._policy = engine
        return self

    def with_secrets(self, store: SecretStore) -> PlatformBuilder:
        self._secrets = store
        return self

    def with_egress(self, policy: EgressPolicy) -> PlatformBuilder:
        self._egress = policy
        return self

    def with_governed_kinds(self, kinds: Iterable[GovernedKind]) -> PlatformBuilder:
        self._kinds.extend(kinds)
        return self

    def with_plugin_kind(self, kind: str, spi: type, spi_version: str,
                         discover_group: str | None = None) -> PlatformBuilder:
        self._plugin_kinds.append(_PluginKind(kind, spi, spi_version, discover_group))
        return self

    def with_signature_verifier(self, verifier: SignatureVerifier) -> PlatformBuilder:
        self._signature = verifier
        return self

    def with_migrations(self, directory: str | Path) -> PlatformBuilder:
        self._migrations.append(Path(directory))
        return self

    def with_provider(self, port: str, providers: dict[str, Callable[[Platform], Any]],
                      default: str) -> PlatformBuilder:
        """Register a product port's providers; PROVIDER_<PORT> picks one (P9)."""
        self._providers[port] = providers
        self._defaults[port] = default
        return self

    # Build ------------------------------------------------------------------------------------------------------

    def build(self) -> Platform:
        s = self._settings
        problems: list[str] = []
        simulated: list[str] = []
        persistence = s.provider("persistence", "postgres" if s.database_url else "memory")
        engine = None
        if persistence == "memory":
            uow_factory = MemoryUnitOfWorkFactory()
            outbox: OutboxReader = MemoryOutboxReader(uow_factory.db)
            idem: IdempotencyStore = MemoryIdempotencyStore(
                uow_factory.db, timedelta(hours=s.idempotency_retention_hours))
            store: Any = MemoryGovernedStore()
            simulated.append("persistence")
        elif persistence == "postgres":
            if not s.database_url:
                problems.append("PROVIDER_PERSISTENCE=postgres needs DATABASE_URL")
                uow_factory, outbox, idem, store = MemoryUnitOfWorkFactory(), None, None, None  # type: ignore[assignment]
            else:
                from ..persistence.postgres import (
                    PostgresIdempotencyStore,
                    PostgresOutboxReader,
                    PostgresUnitOfWorkFactory,
                    create_engine,
                )

                schema = s.schema_name or s.service.replace("-", "_")
                engine = create_engine(s.database_url)
                uow_factory = PostgresUnitOfWorkFactory(engine, schema)
                outbox = PostgresOutboxReader(engine, schema)
                idem = PostgresIdempotencyStore(engine, schema, timedelta(hours=s.idempotency_retention_hours))
                store = PostgresGovernedStore()
        else:
            problems.append(str(UnknownProvider("persistence", persistence, ["memory", "postgres"])))
            uow_factory, outbox, idem, store = MemoryUnitOfWorkFactory(), None, None, None  # type: ignore[assignment]

        verifier = self._verifier
        if verifier is None:
            if s.allow_demo:
                verifier = DemoTokenVerifier()
            else:
                problems.append("no identity provider: call with_identity(...) or set ALLOW_DEMO=true for development")
                verifier = DemoTokenVerifier()
        if getattr(verifier, "simulated", False):
            simulated.append("identity")

        if self._policy is not None:
            policy = self._policy
        else:
            try:
                policy = InProcessPolicyEngine(self._capabilities, self._roles, self._sod)
            except ValueError as exc:
                problems.append(str(exc))
                policy = InProcessPolicyEngine(CapabilityCatalog(), [], [])

        secrets = self._secrets or MemorySecretStore()
        if getattr(secrets, "simulated", False):
            simulated.append("secrets")

        signature = self._signature or AllowUnsignedVerifier()
        if self._plugin_kinds and getattr(signature, "simulated", False):
            simulated.append("plugin-signatures")

        for k in self._kinds:
            for cap in (k.read, k.write, k.approve):
                if cap not in self._capabilities and self._policy is None:
                    problems.append(f"governed kind {k.kind!r} uses undeclared capability {cap!r}")

        if s.production:
            # F23: simulated providers and demo conveniences are refused in production.
            for name in simulated:
                problems.append(f"simulated provider {name!r} is not allowed when ENVIRONMENT=production")
            if s.allow_demo:
                problems.append("ALLOW_DEMO is not allowed when ENVIRONMENT=production")

        built_providers: dict[str, Callable[[Platform], Any]] = {}
        for port, options in self._providers.items():
            choice = s.provider(port, self._defaults[port])
            if choice not in options:
                problems.append(str(UnknownProvider(port, choice, list(options))))
            else:
                built_providers[port] = options[choice]

        if problems:
            if engine is not None:
                engine.dispose()
            raise ConfigurationError(problems)

        governance = GovernanceEngine(uow=uow_factory, store=store, source=s.service, clock=self._clock,
                                      maker_checker_policy=True)
        for k in self._kinds:
            governance.register(k)
        consumers = ConsumerRuntime(uow_factory)
        relay = PollingRelay(outbox, LocalTransport([consumers]))
        platform = Platform(
            settings=s, clock=self._clock, errors=self._errors, uow=uow_factory, outbox=outbox, idempotency=idem,
            verifier=verifier, policy=policy, authz=Authorizer(policy), secrets=secrets,
            egress=self._egress or EgressPolicy(allowlist=s.egress_allowlist), governance=governance,
            consumers=consumers, relay=relay, simulated=sorted(set(simulated)), _migrations=list(self._migrations),
            _engine=engine)
        for pk in self._plugin_kinds:
            host = PluginHost(pk.kind, pk.spi_version, pk.spi, signature)
            if pk.group:
                for reg in host.discover(pk.group):
                    if not reg.ok:
                        get_logger("platform.builder").warning("plugin.refused", plugin=reg.id, reason=reg.reason)
            platform._plugin_hosts[pk.kind] = host
        for port, factory in built_providers.items():
            platform._providers[port] = factory(platform)
        return platform
