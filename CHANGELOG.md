# Changelog

## 0.3.0 (unreleased)

### platform-kernel
- Added the portal API (ADR 0005): `GET /api/v1/portal/me`, `/portal/kinds` and `/portal/plugins`, served by every
  app. Capabilities drive what a portal shows; the API still checks every call.
- Added `GET /api/v1/operations` and `OperationRunner.recent()`: the operations the caller may see, newest first.
- `CapabilityCatalog.all()`; `Platform.capabilities`.

### Exemplar
- `POST /api/v1/connections/{id}/send-batch` runs as a long-running operation with progress and cancellation.
- `tests/journey.py` records the journey the web-kit's simulated provider is held to; a test keeps the live
  service on the same shapes.

### @platform/web-kit (new, `web/`)
- Atomic design system: tokens, shadcn primitives restyled as atoms, molecules, organisms, templates, ECharts
  charts and an SVG visualization kit; light and dark, English and Arabic (RTL); a Design lab page.
- API port with HTTP and simulated providers, demo identities, TanStack Query hooks.
- Governed-record kit: lifecycle gates, lifecycle actions that explain why they are disabled, forms generated from
  JSON Schema, problem details, operation progress.
- Exemplar portal: overview, connections, approvals, operations, activations, plugins, access.
- shadcn registry (60 items) generated from source.

## 0.2.0 (unreleased)

### platform-kernel
- Added `expressions` (layer 2): the `ExpressionEngine` port from ADR 0001, an `ExpressionRegistry` that runs
  languages side by side, and a JSONata provider with schema-checked compilation and limits on time, depth, steps
  and output size. Regular expressions are opt-in. Conformance cases in `spec/conformance/expressions/`.
- Added OIDC identity (ADR 0003): `OidcTokenVerifier` with a rate-limited JWKS cache, `OAuthTokenService` for client
  credentials and RFC 8693 token exchange, and `platform.service_client()` that calls onward as the user.
- Added `operations` (layer 5, ADR 0004): 202 with a status resource, background execution with the caller's
  identity, cooperative cancellation, and sagas with compensations that resume after a restart.
- Builder: `with_expressions`, `with_oidc`, `with_oauth`; the operations API is mounted on every app.
- Review fixes before release: `$eval` refused (it bypassed the regex switch); dynamic access refused on closed
  schemas; string, array and `$pad` sizes bounded during evaluation. Tokens without a tenant claim refused unless
  they carry a platform role. JWKS outages keep the last good keys and back off. `service_client(acting="caller")`
  fails closed. Operations: row locks, leases against double runs, a `stalled` status for failed compensations,
  deadline failures recorded, the creator's roles kept on resume, generic internal error details, visibility limited
  to the creator and `operations.read`. Token cache has a hard size bound.

### platform-testing
- Added `ExpressionEngineContract`.

### platform-tools
- Added `pk scaffold service` and `pk scaffold plugin`. Generated code passes `pk check`, ruff and its own tests on
  the first run, proven by a golden test (F14). Names that are keywords, standard library modules or installed
  packages are refused, `--dir` must stay inside the repository, `pyproject.toml` is edited as TOML (comments kept),
  and generation is atomic: a failure leaves the repository unchanged.


## 0.1.0 (unreleased): walking skeleton

All packages at 0.1.0. Pre-1.0: the API may change between minor versions (F1).

### platform-plugin-sdk
- Added: `Descriptor`, `Check`, `FieldError`, `PluginContext`, `Plugin` protocol.

### platform-kernel
- Added `core`: Result, DomainError, UUIDv7 IDs, Clock.
- Added `contracts`: problem details, CloudEvents envelope with integration headers, pages.
- Added `config`: settings from environment, provider selection, secret store port.
- Added `context`: request context with principal, tenant scope, correlation and deadline.
- Added `identity` (JWT and demo verifiers), `policy` (capabilities, roles, separation of duties), `tenancy`,
  `audit` (hash chain), `observability` (structured logs with redaction, OpenTelemetry), `errors` (catalog).
- Added `persistence`: unit of work with outbox, inbox, dead letters and audit; idempotency store; migration
  runner; memory and PostgreSQL providers with row-level security.
- Added `messaging`: polling relay, local transport, consumer runtime with inbox, retries and dead letters.
- Added `http`: app factory with the fixed middleware stack, authorization, resilient client with egress policy.
- Added `plugins`: one plugin host for every kind.
- Added `governance`: governed-record engine with maker-checker in code and database, and a generated API.
- Added `platform`: the builder, failing fast and refusing simulated providers in production.

### platform-testing
- Added contract suites for unit of work, outbox and idempotency store; PostgreSQL helpers.

### platform-tools
- Added `pk check` (layers, manifests, contracts, spec, migrations, guides) and `pk update`.

### Exemplar
- Added the `connections` service and the `echo` connector plugin.

### Fixed before release, from the independent review
- Public paths matched by prefix let routes such as `/docs-admin` skip authentication with platform scope.
- Idempotency keys were shared within a tenant, so one caller could receive another's stored response; replays also
  dropped ETag and Location and ignored the query string; stale in-progress keys were never released.
- Maker-checker compared the approver only with the submitter, so the person who edited a draft could approve it.
- A retired record could become active again by approving a version left pending.
- The deadline did not stop synchronous work; it is now enforced at kernel boundaries and by `statement_timeout`.
- Egress checked DNS but connected by name (rebinding), allowed carrier-grade NAT, and bounded only each phase of a call.
- Plugins got a new client, breaker and bulkhead on every call, and ran without the request context.
- The half-open breaker let every caller through instead of one trial.
- Duplicate governed ids crashed with a database error instead of returning CONFLICT.
