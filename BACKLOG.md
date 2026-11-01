# Backlog — proof of concept

Think big, act small: `DESIGN.md` is the big picture; this backlog is the smallest path that
proves it. Every story ends with something runnable on the synthetic fixtures and, locally, on the
real data repository. Milestones are delivered in order; a milestone starts only when the
previous one's acceptance passes.

Sizes: **S** = one evening, **M** = two to four evenings, **L** = about a week of evenings.

## PoC goal

Import the UAT export of one application into the private chain repository as JSON, export it
back **byte-identical**, validate the chain graph, and browse folders, chains and jobs in a local
**read-only** web UI.

## Out of scope for the PoC

Constants, overrides and `envs` variants (the environment model beyond the letter rule); import
of a second environment; `--names standard`; `--dedupe-jobnames`; refactorings; editing in the
UI; diff UI; `xmldiffreport` integration; PyPI release; documentation site.

---

## M-1 — Tooling (standards, skills, verification)

- **T1 Project `CLAUDE.md` (S)** — hard rules (TDD always, English in code, no real data,
  stdlib-only core), pointers to `DESIGN.md`/`BACKLOG.md`, which skill applies to which area.
- **T2 Skill `verify` (S)** — the common end-of-part protocol adapted from ECC's
  `verification-loop`: lint, types, tests with coverage, no-real-data grep, diff review, PASS/FAIL
  report. Script `.claude/skills/verify/verify.sh`.
- **T3 Skill `oss-repo-standards` (S)** — README, community files, Conventional Commits,
  Keep a Changelog, SemVer, templates, Trusted Publishing, naming conventions, bilingual docs.
  Script `check_repo.sh` + GitHub community-profile check.
- **T4 Skill `python-core-tdd` (S)** — TDD loop, test layout and markers, coverage gate,
  core/adapter architecture rules, style; verify checklist.
- **T5 Skill `fastapi-api` (S)** — structure, thin handlers, typed errors, OpenAPI, localhost +
  token, TestClient and schema snapshot; verify checklist.
- **T6 Skill `react-frontend` (S)** — Vite + React + TS + shadcn/ui conventions, TanStack Query,
  Vitest + RTL + MSW, axe, Playwright smoke, OpenAPI-generated types; verify checklist.
- **T7 Attribution (S)** — `.claude/ATTRIBUTION.md` crediting Everything Claude Code (MIT).

*Accept:* every skill ≤ 150 lines, has a `Verify` section, and its script runs on the empty repo.

## M0 — Scaffold

- **S0.1 Package skeleton (S)** — `pyproject.toml` (hatchling, `src/controlm_chain_admin`,
  Python ≥ 3.11, stdlib-only core, `[web]` and `[dev]` extras), ruff, mypy, pytest, CI workflow
  (lint + test matrix), README stub, MIT licence, CHANGELOG. `ctmchain --version` works.
  *Accept:* CI green with one trivial test.
- **S0.2 Synthetic fixture generator (M)** — `tests/fixtures/build_fixtures.py` writes a DEFTABLE
  export of the fictional application `P77` (about 6 folders, 30 jobs) reproducing every measured
  structure: folder-level IN/OUT conditions chaining folders, job chains `A-B_OK` with
  self-cleanup `-`, `ON NOTOK` with DOSHOUT and DOMAIL, a DOCOND conditional edge, QUANTITATIVE,
  RULE_BASED_CALENDAR(S), folder and job VARIABLEs, plus one of each anomaly: dangling INCOND,
  unconsumed OUTCOND, stale name, never-cleaned INCOND, duplicated JOBNAME across two folders,
  calendar `*`, a non-prefixed name, and a second application to be skipped. Generated file and
  generator both committed. *Accept:* deterministic output; parses with `xml.etree`.
- **S0.3 Real-data test hook (S)** — tests marked `realdata` run only when
  `CTMCHAIN_DATA_REPO` points to the private clone, skipped otherwise. A helper filters the
  original export to one application at the raw-bytes level, to compare against an export that
  skips the other applications. *Accept:* `pytest -m realdata` runs locally, skips in CI.

## M1 — Faithful XML ↔ JSON (core)

- **S1.1 XML reader (S)** — expat-based parser keeping attribute order; in-memory model
  (folders, jobs, children in document order, no text content). *Accept:* fixture counts match;
  real data gives 339 folders / 1524 jobs.
- **S1.2 Serializer (M)** — rules captured from the prototype: declaration, exported-at comment,
  4-space indentation, ` />` self-closing, fixed attribute order per element type, escaping.
  *Accept:* XML → model → XML byte-identical on the fixture and on the real export.
- **S1.3 JSON layout (M)** — `folders/<F>/folder.json`, `folders/<F>/jobs/<J>.json`, `meta/`
  sidecar for volatile attributes, fixed key order, arrays in document order. Conditions stay on
  the nodes for now (they move to `links.json` in M2). *Accept:* model → JSON → model equal;
  export still identical.
- **S1.4 `init`, `import`, `export` (M)** — `init --repo --application --envs`;
  `import <xml> --application <APP>` lossless, other applications skipped and reported;
  `export -o <xml>`. *Accept:* import the real export into the data repo, export, compare with the
  application-filtered original: identical bytes.
- **S1.5 Idempotency (S)** — re-importing the exported XML changes no file. *Accept:* test on
  fixture and real data.

## M2 — Letter rule, links, validate, report

- **S2.1 Letter rule (M)** — `chain.json` holds the whitelist of attributes and the prefixes
  (`P77`, `RQ`, `RC`); `import --env uat` strips the anchored letter and marks non-matching values
  in whitelisted attributes with `literal:`; `envs/uat/env.json` holds letter and display name;
  `export --env uat` re-adds the letter. File and directory names use the neutral identity.
  *Accept:* round trip still identical; report lists every `literal:` mark.
- **S2.2 Links (L)** — edges from OUTCOND `+` / INCOND by name, `cleanup` from `-`, `docond`
  references, folder-level nodes (`FOLDER/`), `external` flag, `raw` conditions for whatever is
  not an edge; written to `folders/<F>/links.json` on the consumer side; export regenerates
  INCOND/OUTCOND/DOCOND in the original order. *Accept:* round trip identical; real data yields
  about 1519 edges, 13 dangling, 40 unconsumed.
- **S2.3 `validate` (M)** — dangling, unconsumed, never-cleaned, stale names, duplicated
  JOBNAME, names outside `A-B_OK`, unresolved node references; severities; Markdown and JSON;
  exit code. *Accept:* the fixture triggers each check exactly once; real-data numbers match the
  analysis of 2026-11-01.
- **S2.4 Import report (S)** — skipped folders, `literal:` marks, validate findings, encoding
  losses (`?`), environment-looking values with no rule. Written to `reports/` (git-ignored in
  the data repo). *Accept:* produced on every import, in both formats.
- **S2.5 `distinct` (S)** — distinct values with counts and sample nodes, from an XML or from the
  repo. *Accept:* `distinct NODEID` on real data lists 21 values.
- **S2.6 `show`, `graph`, `links` (M)** — `show <node>`; `graph <folder> --format
  text|mermaid|dot`; `links <node>` and `links --name`. A data file groups the JOB attributes
  (identity, scheduling, execution, notifications, resources) and is shared with the UI.
  *Accept:* Mermaid output of a fixture folder renders.

## M3 — Read-only web UI

- **S3.1 API (M)** — FastAPI in the `[web]` extra calling the core directly: `GET /api/repo`
  (branch, head, counts), `/api/folders?q=`, `/api/folders/{f}` (jobs, links, graph),
  `/api/jobs/{f}/{j}` (grouped and raw attributes), `/api/validate`. Bound to `127.0.0.1`;
  `ctmchain serve --repo --port --no-browser`. *Accept:* endpoints tested with the FastAPI test
  client on a fixture repository.
- **S3.2 Frontend scaffold (M)** — `web/` with Vite + React + TypeScript + shadcn/ui + TanStack
  Query; dev proxy of `/api`; `web/dist/` git-ignored and served by FastAPI at `/`.
  *Accept:* `npm run build` then `ctmchain serve` shows the app.
- **S3.3 Folder list (S)** — search, counts of jobs, links in/out and findings per folder.
- **S3.4 Folder graph (L)** — React Flow with dagre layout; jobs as nodes, folder entry/exit
  pseudo-nodes for folder-level conditions; cross-folder edges as ports that navigate to the
  other folder; edge inspector with name, ODATE, AND_OR, cleanup, docond, external.
  *Accept:* the largest real folder (~52 nodes) renders in under a second.
- **S3.5 Job detail (M)** — grouped attributes, variables, resources, calendars, ON/DO blocks,
  raw tab.
- **S3.6 Validate page (S)** — findings table with severity filter and links to nodes.

## M4 — PoC wrap-up

- **S4.1 Run on real data (S)** — import UAT into the data repo and commit; export identical;
  validate numbers; UI walkthrough. Numbers recorded in a PoC report inside the private repo.
- **S4.2 Retro (S)** — what changed versus `DESIGN.md`, update it; go/no-go for the next slice.

## Definition of done (every story)

Fixture tests pass in CI; `realdata` tests pass locally when applicable; ruff and mypy clean;
CLI `--help` text written; README updated when a command appears; no real data, real names, hosts
or addresses anywhere in this public repository.

## After the PoC (not ordered yet)

Constants and mappings (`distinct --write`, `map`, `import --mappings`); overrides and `envs`
variants; second-environment import with learning; `--names standard` and collision rules;
`--dedupe-jobnames`; refactorings with change-set preview; `diff` and `xmldiffreport`; mapping
editor and editing in the UI; git bar; PyPI release and bilingual docs.
