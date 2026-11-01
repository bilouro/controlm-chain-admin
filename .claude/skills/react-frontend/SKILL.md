---
name: react-frontend
description: Standards for the read-only web UI of controlm-chain-admin (web/, Vite + React + TypeScript + shadcn/ui, TanStack Query, React Flow). Use for any change to .ts/.tsx files, components, pages, API client, tests or the Vite build, and when someone asks to «criar página», «mostrar na UI», «componente», «grafo» or review the frontend. Test-first with Vitest + Testing Library + MSW, OpenAPI-generated types, accessibility, no template look.
---

# react-frontend

Adapted from Everything Claude Code `react-patterns`, `react-testing`, `vite-patterns`,
`rules/react`, `rules/typescript` and `rules/web` (MIT, see `.claude/ATTRIBUTION.md`).

## Stack and structure

```text
web/
  package.json            # scripts: dev, build, lint, typecheck, test, test:e2e, gen:api
  vite.config.ts          # /api proxy to http://127.0.0.1:<port> in dev; outDir dist (git-ignored)
  src/
    app/                  # router, providers (QueryClient, theme), layout shell
    features/<area>/      # folders/, folder-graph/, job-detail/, validate/ — components + hooks + tests side by side
    components/ui/        # shadcn/ui primitives (generated, do not hand-edit)
    lib/api/              # client.ts (fetch wrapper), types.gen.ts (openapi-typescript output), queries.ts
    lib/                  # utils, formatters
  tests/e2e/              # Playwright smoke against the built app served by ctmchain serve
```

- TypeScript `strict`; no `any` (use `unknown` and narrow); types for the API come only from
  `npm run gen:api` (openapi-typescript over the FastAPI schema). Never hand-write an API type.
- Server state only in TanStack Query (`useQuery`/`useSuspenseQuery` with query keys per
  resource); UI state local with `useState`; derived state computed in render, never duplicated.
- Components: `PascalCase.tsx`, props as `type Props = {...}` destructured in the signature,
  hooks `useX` in `use-x.ts`, boolean props `isX/hasX/canX`, handlers `handleX`, prop `onX`.
- Imports: react, third-party, `@/` absolute, relative; `import type` for types.
- Graph: React Flow (`@xyflow/react`) with `dagre` layout computed in a hook; nodes are
  jobs, folder entry/exit pseudo-nodes for folder-level conditions, edge data carries the link
  (name, ODATE, AND_OR, cleanup, docond, external). Selection drives the inspector panel.
- Read-only phase: no forms that mutate; every mutation UI comes later through
  `/api/changes/*` with preview → apply.

## Design quality (not a default template)

- Hierarchy on purpose: the chain graph and the job's execution attributes are the focus;
  metadata recedes. Attributes grouped (identity, scheduling, execution, notifications,
  resources, variables, ON/DO), not a 75-row flat table.
- Intentional hover/focus/selected states on nodes, edges and rows; keyboard navigation in
  lists and graph (Tab to nodes, Enter opens, Esc closes the inspector).
- Both light and dark themes read as finished; colour is never the only carrier of meaning
  (external links and findings also get an icon or label).
- Empty, loading and error states designed for every query; no spinner-only screens.

## Tests (TDD)

- Vitest + React Testing Library + `@testing-library/user-event` (`userEvent.setup()` once per
  test, always `await`); MSW for `/api/*` with handlers built from fixture JSON, never mocking
  TanStack Query or React internals.
- Query by role, then label, then text; `data-testid` only for the graph canvas.
- `findBy*`/`waitFor` for async, never timers; no snapshot tests of components.
- Accessibility: `vitest-axe` on every page component; no violations.
- Playwright smoke (`test:e2e`): build, start `ctmchain serve` on a fixture repo, open the
  folder list, open one folder graph, open one job, see the validate page. Runs in CI on
  Linux only.
- Coverage ≥ 80% for `features/` and `lib/`; `components/ui` excluded.

## Verify

1. `npm run lint && npm run typecheck && npm test -- --run --coverage && npm run build`.
2. `npm run gen:api` produces no diff (types in sync with the API snapshot).
3. Checklist: tests written first · no `any`, no `console.log` · no hand-written API types ·
   roles/labels queryable · axe clean · empty/loading/error states present · keyboard works ·
   both themes checked · bundle report has no unexpected large chunk · no real data in
   fixtures or MSW handlers.
4. Finish with the `verify` skill and paste its report in the PR.
