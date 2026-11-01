# @platform/web-kit

The portal kit for products built on the platform foundation, and the exemplar portal that proves it
([ADR 0005](../docs/adr/0005-web-kit.md)).

## Run

```bash
npm ci
npm run dev            # http://localhost:5173; uses a service on :8000 if one answers, otherwise the simulated API
API_MODE=http npm run dev                 # always the real service (API_URL, default http://localhost:8000)
npm run lint           # ESLint, including the atomic layer rules
npm run build          # tsc --noEmit, eslint, vite build
npm test               # vitest: conformance with the exemplar, simulated provider rules, schema forms
npm run build:single   # one self-contained HTML file on the simulated API (dist-single/index.html)
npm run registry:build # registry.json and public/r/*.json for the shadcn CLI
```

Add `?api=simulated` or `?api=http` to the URL to force a provider. Start the exemplar with
`ALLOW_DEMO=true uv run uvicorn exemplar_connections.main:app` from the repository root.

## Folder map and layer rules

```
src/
  styles/          tokens.css (light and dark), globals.css (Tailwind 4 theme, shadcn variable bridge, motion)
  lib/             cn(), locale-aware formatting, theme and language preferences
  i18n/            one table, English and Arabic, same keys by construction
  ui/atoms/        shadcn primitives restyled, plus badge, status pill, style chip, segmented, misc
  ui/molecules/    form field, search box, KPI tile, tab bar, empty, loading and error states, nav item
  ui/organisms/    data table, chart card, command palette, shell (banner, top bar, lifecycle rail, navigation)
  ui/charts/       Apache ECharts wrapped as shadcn-style components: area, bar, donut, fan, heatmap, sparkline
  ui/viz/          hand-built SVG: ranked bars, pipeline gates, lineage graph
  ui/templates/    app shell, page header, section and grids
  kit/api/         the API port: Transport, HttpTransport, SimulatedTransport, client, identity, hooks
  kit/governed/    lifecycle gates and actions, JSON Schema forms, problem details, operation progress
  pages/           the exemplar portal and the Design lab
  data/            synthetic fixtures for the simulated provider and the Design lab
  app/             composition root (the only place a provider is chosen), routes and shell configuration
```

A layer imports only from layers below it: atoms import nothing from `ui/`; molecules import atoms and only the
sparkline chart; organisms, charts and viz import molecules and atoms; templates import organisms; `kit/` imports
`ui/` but never pages or data; only `pages/` and `app/` import `data/`. Only `ui/charts` imports `echarts`, and no
other chart library is allowed. ESLint fails the build on any break; a probe file proved each rule.

## Providers

| Port | Providers |
|---|---|
| `Transport` | `HttpTransport` (a real service), `SimulatedTransport` (in the browser, synthetic data, labelled in the banner) |
| `TokenSource` | `DemoTokenSource` (demo identities, simulated); an OIDC source is the next provider |

The simulated provider follows the kernel's rules: the governed lifecycle, maker-checker, separation of duties,
revisions (If-Match), tenancy, and operations that progress and cancel. `src/kit/api/conformance/exemplar-journey.json`
is a journey recorded from the real exemplar; vitest holds the simulated provider to it, and the exemplar's pytest
suite holds the live service to it.

Business data from the API (connection names, subjects, plugin ids) is shown as it comes and is not translated.

## Registry

`npm run registry:build` writes `registry.json` (one item per component; `echart`, `i18n`, `api-kit` and
`governed-kit` ship their files together) and builds `public/r`. In a consumer with the `@` alias and
`"registries": { "@platform": "<host>/r/{name}.json" }` in `components.json`:

```bash
npx shadcn@latest add @platform/theme @platform/kpi-tile @platform/data-table
```

Proved in a fresh Vite and Tailwind 4 app: the three items installed with their dependencies (sparkline, echart,
i18n, states and others), built, and rendered in the brand colors with no console errors. The consumer imports the
fonts itself. ui.shadcn.com was unreachable from the build machine, so the shadcn primitives were mirrored from the
shadcn-ui repository (`apps/v4/registry/new-york-v4`) and restyled.

## Verified

- Type check, ESLint (with the layer probe), production and single-file builds, vitest (28 tests).
- Playwright journey on both providers: create a draft from a plugin schema, test, submit; the maker cannot approve;
  a second person approves; the approver cannot send; send once; a batch operation runs to completion; separation of
  duties hides write actions; the command palette jumps to a connection and to a Design lab section; the Design lab
  form shows its error and then saves.
- Screenshots in light, dark, Arabic (RTL) and at 390 px; no page errors, no horizontal overflow, no raw keys.
- Charts are mid-animation 250 ms after scrolling into view, and settle by 1.8 s.

## Known limits

- Demo identities only; OIDC sign-in in the browser comes with the next identity provider for `TokenSource`.
- No audit view yet: the kernel has no audit read API.
- The single-file page is about 2 MB because fonts are inlined.
