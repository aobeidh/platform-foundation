# ADR 0005: The portal kit (`@platform/web-kit`)

## Status

Accepted (milestone 0.3).

## Context

Every product on the foundation needs a portal, and every portal needs the same things: a shell, menus that follow
the caller's capabilities, screens for governed records (draft, test, submit, approve), plugin configuration forms,
operation progress and a consistent design. Built per product, these drift apart and re-implement P14 and P21 in
the browser. The reference stack names TypeScript and React for portals.

## Decision

- One web project, `web/`, holds the kit and the exemplar portal. It follows atomic design: `ui/atoms`, `molecules`,
  `organisms`, `charts` (ECharts, the only chart library), `viz` (hand-built SVG) and `templates`. ESLint enforces
  the layers, as import-linter does for the kernel (F3).
- The kernel serves a **portal API** that the kit reads instead of hard-coding product knowledge:
  `GET /api/v1/portal/me` (subject, tenant, roles, capabilities with their names in each language, simulated ports),
  `GET /api/v1/portal/kinds` (each governed kind with its JSON Schema, capabilities and the lifecycle transitions)
  and `GET /api/v1/portal/plugins` (installed plugins with their configuration schemas). Operations gained
  `GET /api/v1/operations`. Capabilities only decide what the portal shows; the API still checks every call.
- The API is a **port** in the browser too. `Transport` has two providers: `HttpTransport` for a real service and
  `SimulatedTransport`, which follows the kernel's rules (lifecycle, maker-checker, separation of duties, revisions,
  tenancy, operations) for demos and tests. The token source is a port as well; demo identities are its simulated
  provider and are labelled in the shell. The composition root (`src/app/wiring.ts`) is the only place a provider
  is chosen.
- A recorded journey through the exemplar (`web/src/kit/api/conformance/exemplar-journey.json`) is the contract
  between the two providers: the exemplar's pytest suite checks the live service still answers with those shapes,
  and the kit's vitest suite checks the simulated provider does. Neither side can drift alone.
- Plugin configuration forms are generated from the plugin's own schema, so a new connector needs no portal change
  (F12). Governed-record screens are driven by the kind's lifecycle and capabilities (F11).
- The kit is distributed as a shadcn registry (`registry.json`, built into `public/r`), one item per component,
  so products copy and own the source while staying on the same design.

## Consequences

- A product portal is wiring plus product pages; shell, lifecycle actions, schema forms and states come from the kit.
- The simulated provider must be kept in step with the kernel. The conformance fixture makes drift fail CI; new
  kernel endpoints the portal uses must be added to the journey.
- The kit uses React 19, because the shadcn v4 primitives pass refs as props.
