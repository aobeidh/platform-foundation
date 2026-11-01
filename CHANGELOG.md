# Changelog

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
