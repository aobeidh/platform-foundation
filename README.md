# platform-foundation

The shared foundation that enterprise products are built on. It makes the rules of the
[engineering skills](https://github.com/aobeidh/engineering-skills) cheap to follow: a product built on it gets
contracts, governed configuration, tenant isolation, an outbox, idempotency, audit, resilience and plugins by default
instead of rebuilding them.

**Status: milestone 0.2.** Every layer exists, thin but complete, and is proven end to end by an
exemplar service on both in-memory providers and PostgreSQL. Pre-1.0 versions may change their API between minor
releases (F1).

## What is in the box

| Package | What it is |
|---|---|
| `platform-plugin-sdk` | The lowest layer: types every plugin and host share. Depends only on pydantic, so third-party plugins never pull in the kernel. |
| `platform-kernel` | Seven layers of modules (see [ADR 0002](docs/adr/0002-kernel-layers.md)), each a port with in-memory and production providers. |
| `platform-testing` | Contract suites every provider must pass, and PostgreSQL test helpers. |
| `platform-tools` | `pk`, the one command that runs every architecture and contract check, locally and in CI. |
| `exemplar/` | A reference service (`connections`) and plugin (`echo`) that use every module (F15). |
| `web/` | `@platform/web-kit`: the portal kit (atomic design system, ECharts, API port, governed-record screens) and the exemplar portal. See [web/README.md](web/README.md). |

Kernel modules, lowest first: `core`, `contracts`, `config`, `context`, `identity`, `policy`, `tenancy`, `audit`,
`observability`, `errors`, `expressions`, `persistence`, `messaging`, `http`, `plugins`, `operations`,
`governance`, `platform`. Each has a
one-page guide in [docs/modules](docs/modules).

## Interfaces, providers and plugins

- **Interface (port):** a contract the core owns, such as `UnitOfWorkFactory`, `TokenVerifier`, `PolicyEngine`,
  `SecretStore`, `GovernedStore`.
- **Provider:** one implementation per technology, exactly one active per deployment, chosen by `PROVIDER_<PORT>`.
  Every port ships an in-memory provider and a contract suite. Simulated providers are listed in the
  `X-Platform-Simulated` response header and refused when `ENVIRONMENT=production`.
- **Plugin:** a new kind of capability added at run time through a versioned SPI. One `PluginHost` serves every
  plugin kind; plugins receive a narrow context and nothing else.

## Quick start

```bash
uv sync
uv run pk check        # layers, manifests, contracts, spec, migrations, guides
uv run pytest          # memory providers; set PF_TEST_DATABASE_URL to add PostgreSQL
```

To run the PostgreSQL suites, use a **non-superuser** role so row-level security is enforced:

```bash
export PF_TEST_DATABASE_URL=postgresql://app:app@localhost:5432/pf
uv run pytest
```

Run the exemplar:

```bash
ALLOW_DEMO=true uv run uvicorn exemplar_connections.main:app --reload
curl -H "Authorization: Bearer demo:ada:integration-admin:t1" localhost:8000/api/v1/connections
```

Run the portal against it (in another terminal):

```bash
cd web && npm ci && API_MODE=http npm run dev   # http://localhost:5173, /api proxied to :8000
```

Without a service, `npm run dev` falls back to the simulated provider.

## Create a service or plugin

```bash
uv run pk scaffold service billing                       # services/billing, passes every check at once
uv run pk scaffold plugin acme-sftp --kind connector --group hub.connectors
uv sync && uv run pk check && uv run pytest
```

## Building a product on the foundation

```python
platform = (
    Platform.builder("connections", settings)
    .with_capabilities(declare)                      # capabilities in code (P21)
    .with_roles(ROLES, SEPARATION_OF_DUTIES)         # roles and SoD rules as data
    .with_plugin_kind("connector", ConnectorSpi, "0.1.0", discover_group="exemplar.connectors")
    .with_provider("activations", {"memory": ..., "postgres": ...}, default="memory")
    .with_migrations(MIGRATIONS)
    .build()                                         # fails fast, listing every problem (F6)
)
platform.governance.register(connection_kind(...))  # lifecycle, maker-checker, audit, events, API: free (F11)
app = platform.create_app([product_router])          # fixed middleware stack (F7)
```

See [exemplar/service/src/exemplar_connections/wiring.py](exemplar/service/src/exemplar_connections/wiring.py).

## Milestones

**0.4:** approval policy in the governed-record engine (auto, single, maker-checker; required test), returned and
discarded versions, specific lifecycle codes.

**0.3:** the portal kit (`@platform/web-kit`) and the exemplar portal, the kernel's portal API, and an
operation in the exemplar.

**0.2:** the expression engine port with a JSONata provider, OIDC identity with token exchange, long-running
operations and sagas, and the scaffolder.

**0.1 scope:**

In: core, contracts, config, context, identity, policy, tenancy, audit, observability, errors, persistence (memory and
PostgreSQL), messaging (polling relay, local transport), http, plugins, governance, the builder, the testing kit,
`pk check`, and the exemplar.

Later milestones: broker transports and competing relays, configuration overlays and promotion bundles, a FEEL
provider for the expression engine, Temporal behind the orchestrator port, AI, Sigstore plugin
signatures, out-of-process plugin isolation, and OpenID discovery.

## Decisions

- [ADR 0001](docs/adr/0001-expression-engine-as-port.md): the expression language is a port with providers.
- [ADR 0002](docs/adr/0002-kernel-layers.md): kernel layers as built, and the plugin SDK at the bottom.
- [ADR 0003](docs/adr/0003-identity-and-token-exchange.md): OIDC identity, and token exchange between services.
- [ADR 0004](docs/adr/0004-operations-and-sagas.md): long-running operations and sagas on an in-process orchestrator.
- [ADR 0005](docs/adr/0005-web-kit.md): the portal kit, the portal API, and the API as a port in the browser.
- [ADR 0006](docs/adr/0006-approval-policy.md): approval policy (auto, single, maker-checker), returned and discarded versions.
