# ADR 0002: Kernel layers as built, and where the plugin SDK sits

Status: accepted
Date: 2026-11-01   Principles: F3, F12, P11, P57

## Context

The `platform-foundation` skill sketches the kernel in five layers with persistence, messaging, http, governance and
plugins side by side in one layer. Building milestone 0.1 showed that this cannot hold: messaging, http and
governance all need the unit of work, and governance needs messaging (events) and http (its generated API). Siblings
in one layer may not import each other, so the sketch would force cycles or duplication.

The skill also says the plugin SDK depends only on the kernel's `core` and `contracts` layers. A third-party plugin
would then still install the whole kernel package to reach those types.

## Decision

The kernel layers, enforced by `.importlinter`:

| Layer | Modules |
|---|---|
| 6 | `platform` |
| 5 | `operations`, `governance` (independent; added in 0.2: `operations`) |
| 4 | `messaging`, `http`, `plugins` (independent of each other) |
| 3 | `persistence` |
| 2 | `identity`, `policy`, `tenancy`, `audit`, `observability`, `errors`, `expressions` (independent; `expressions` added in 0.2) |
| 1 | `contracts`, `config`, `context` (independent) |
| 0 | `core` |

`Principal` and `TenantScope` live in `context` (layer 1) because the request context carries them; `identity`
re-exports `Principal`.

`platform-plugin-sdk` is the lowest package of the foundation and depends only on pydantic. The kernel imports its
types (`Descriptor`, `Check`, `FieldError`, `PluginContext`); the SDK never imports the kernel or a product.

## Consequences

- The skill's layer table should be updated to match (feedback to the engineering-skills repo).
- A plugin author installs one small package. SDK changes follow the strictest compatibility rules (P57).
- Persistence becomes the shared base for all runtime modules; it must stay generic.
