# Backlog — proof of concept

Think big, act small: `DESIGN.md` is the big picture; this backlog is the smallest path that
proves it. Every story ends with something runnable on the synthetic fixtures and, locally, on the
real data repository. Milestones are delivered in order; a milestone starts only when the
previous one's acceptance passes.

Sizes: **S** = one evening, **M** = two to four evenings, **L** = about a week of evenings.

## Status — PoC complete (2026-11-01)

All milestones M-1 to M4 are done except S0.2 (synthetic fixture generator, deferred by the
author). Measured on the real UAT export inside the private data repository:

| Measure | Value |
|---|---|
| Import | 329 folders, 1,492 jobs, 2,152 files, 0.5 s |
| Export uat vs original filtered to the application | byte-identical (3,881,158 bytes), 0.25 s |
| Export prod | same size, every prefixed name re-lettered 1:1 |
| Links / validate | 1,583 links, 1,821 nodes; 0 errors, 186 warnings, 198 info; 0.14 s |
| Web UI on real data | largest folder (47 jobs, 64 edges) in 0.15 s; validate page 0.11 s |
| Public test suite | 134 Python tests (95 % coverage) + 18 frontend tests; 10 real-data tests locally |

Retro notes: links are a derived index in the PoC (DESIGN §4.3); the letter rule found an
inner-token ambiguity on real data (DESIGN §13.4); duplicate JOBNAMEs inside a folder exist and
are handled with `~n` ids. Next slice: see *After the PoC* below, starting with constants and
mappings, which the real data needs before any export to another environment is deployable.

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
- **S0.2 Synthetic fixture generator (M) — DEFERRED by the author (2026-11-01)**: the PoC runs
  against the real export in the private data repo (`realdata` tests); public unit tests use
  small inline synthetic XML snippets. The generator comes back when the public suite needs a
  full export. Original scope kept below for later. — `tests/fixtures/build_fixtures.py` writes a DEFTABLE
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

## After the PoC — order agreed with the author (2026-11-01)

1. **Constants and mappings — DONE (2026-11-01).** `distinct --write` drafts, `map`,
   `import --mappings`, placeholders `@{name}` resolved at export (`--allow-unresolved` to leave
   gaps), `env constants [--missing]`, value and inline modes, selectors `TAG[K=V]/@ATTR`. On the
   real data the main NODEID group (1,160 jobs) maps from one pattern; 19 other NODEID values and
   the hosts, users and mail recipients still need their per-environment values.
2. **Links as the source of truth — DONE (2026-11-01)**, with `--names standard`, collision
   rules and `--dedupe-jobnames` (real data: 119 jobs renamed, standard-name collisions 100 → 0).
3. **Refactorings — DONE (2026-11-01)** with change-set preview and `--apply`: `rename-job`,
   `rename-folder`, `rename-subapp`, `move-job`, `insert-job`, `extract-variable`. Rename and
   rename back restores the real export byte for byte; a preview takes ~1 s on the real repo.

4. **Editing web UI — DONE (2026-11-01)**: Chains table, tabbed folder/job pages, predecessors &
   successors editor, change preview and apply through the API with a session token.

5. **Branch comparison — DONE (2026-11-02)**, asked by the author: `ctmchain compare` and the
   *Compare* web page (feature branch against develop, from the merge base; how each changed node
   was and how it is now).
6. **Import package — DONE (2026-11-02)**, asked by the author: `ctmchain package` and the
   *Generate XML* button of the Compare page; every changed folder, whole, for one environment,
   with its reasons and warnings; the comparison and the package can keep only some commits of
   the branch (any subset, applied cherry-pick style; a missing dependency is named).
7. **Resolving findings — DONE (2026-11-02)**, asked by the author: a resolve button per finding
   and for the selection on the *Validation* page, filter by type of problem, several explained
   fixes where there is a choice; `ctmchain resolve`; the page fits the screen.
8. **Commit from the UI — DONE (2026-11-02)**, asked by the author: *Commit (n)* button with a
   message written from the changes, optional new branch; `ctmchain commit`.
9. **Releases — DONE (2026-11-02)**, asked by the author: the trunk mirrors production and is
   never edited; release branches from it, installations per environment as tags, close into
   the trunk; branch button, *Releases* dialog, stash/restore, discard, push and pull in the UI;
   `ctmchain release`; rules in the `git` key of `chain.json`.

10. **Environments and deliveries — in progress (2026-11-02)**, asked by the author: resource
    names with the letter on the first prefix only, Windows line endings, partial exports keep
    the header and the deduplicated names; exceptions per environment (`set-exception`),
    `rename-constant`; the intake analysis and *receive* (CLI, API, *Import* page), `env learn`.
    Done too: the dev data repository migrated on `release/environments` (`leading_only`,
    `JOBS_IN_GROUP` volatile, `node.bat1`/`node.bat2`, bench and prod values of users,
    machines and `%%GEIENV`), `env learn --only`, validations of dirty names with fixes.
    Exceptions in the UI (*Environments* tab of jobs and folders) done too.
    **DONE (2026-11-03)**: folders and jobs of some environments (`envs`), full exports of
    another environment leaving production alone, repeated differences grouped into constants
    (letter patterns, the environment's name in texts, values inside ON blocks), so a new
    repository is built from the exports alone. The prod baseline into the trunk is done at the
    company with real exports (these are anonymised), with the `bootstrap` skill.
11. **Working where only PyPI is reachable — DONE (2026-11-03)**, asked by the author: the
    sdist carries the whole project (rules, skills, tests, web sources, the built UI); the
    `bootstrap` skill takes it from there to a new chain repository; `init` writes the data
    repository's `CLAUDE.md`. Rehearsed here with the 4 exports: prod byte for byte after uat
    and bench came in.
12. **Taking changes of another branch — DONE (2026-11-03)**, asked by the author: `ctmchain
    take` and the boxes of the *Compare* page; one attribute, variable, condition, group, job,
    folder, condition name, constant value or exception at a time, conflicts value by value.
13. **PyPI release 0.1.0 — DONE (2026-11-03)**: Trusted Publishing from the `v0.1.0` tag.
14. **Similar condition names — DONE (2026-11-03), released in 0.1.1**, asked by the author:
    `validate` reports names that differ only by a copy's suffix or by case (`similar-names`)
    and offers to number them (`number-similar`: `…_OK1`, `…_OK2`).
15. **Only the values of an environment — DONE (2026-11-03), released in 0.1.2**, asked by
    the author for the company (uat and bench carry releases production does not have yet):
    `receive --values-only`, `skip` for added folders and jobs, *adopt* decisions; the
    `bootstrap` skill builds the releases on their way from their deliveries.
16. **Exceptions for any line, technical attributes — DONE (2026-11-05), released in 0.1.4**, asked by
    the author («qualquer elemento do xml pode ser exception»): any attribute or line of a
    folder or job (a condition, a SHOUT, an action of an ON block, a variable it lacks) may be
    an exception of one environment (`elements` of `overrides.json`, by locator); a full
    export of another environment makes every difference an exception by default and may be
    received again without a change; what the base gains later drops the exceptions equal to
    it; `--values-only` is gone; the technical list (`volatile_attributes`) is edited in the
    CLI (`technical`) and the *Environments* page. Compare marks the changes that only call a
    condition another name and shows the real ones only on request (*All / Real only*,
    `--real-only`).
17. **Choosing the name of a condition per environment — later**, asked by the author: for a
    name-only change of a received release, three options per condition: each environment
    keeps its own name (an exception of the environment), every environment takes
    production's name (the environment's package carries the fix), or the base takes the
    environment's name (production's package carries it).
18. **Asking in plain words — DONE (2026-11-05)**, asked by the author («um lugar onde pudesse
    colocar um prompt»), with Kilo first: a capabilities file (`capabilities.json`, the menu
    and the tools come from it, every example tested), `ctmchain menu`, `ctmchain mcp` (the
    `[mcp]` extra: find, show, condition, validate, compare, preview, apply; apply takes the
    same steps and the preview's id, so it holds across restarts of the server) and
    `ctmchain kilo init` (server, `controlm` agent, skill, vocabulary). Tried with Kilo and an
    OpenAI model on the synthetic chain: a question, a change, a prod-only exception with a
    rename in one preview. Then the *Assistant* panel of the web UI over `kilo serve`
    (`ctmchain serve --assistant`), approvals with the repository's own preview, and
    Playwright end-to-end tests (`npm run test:e2e`, with a real model on request). Tried on
    the real data (a clone of the rehearsal repository, OpenAI): questions answered right, a
    change and a prod-only exception written after approval, a rejected one left out. Next:
    `claude init` for Claude Code.

19. **One branch per environment — DONE (2026-11-10), released in 0.2.0**, asked by the author
    after a day with 0.1 at work ([`NEEDS.md`](NEEDS.md), needs 1 to 10; `DESIGN.md` §14):
    `refresh` (an environment's branch from its full export: preview, `--apply`, as many times
    as needed), the map on its own branch (`envmap derive|suggest|show|add|remove|rename`),
    two environments compared by their real differences (the head read in the base's terms;
    `--raw`; `--prefer` for a value that stands for two), `take` between environments item by
    item (attribute, variable, job, folder, sub-application), `package --take` (the import
    file of the target with only the chosen items, no branch changed), the trunk refusing a
    take, `init --dedupe-jobnames`, the repository guide rewritten for this model. Unit,
    functional and end-to-end tests on four synthetic environments; tried on the real
    application in four environments, built from its exports alone.
20. **The branch model in the web UI — DONE (2026-11-10), released in 0.3.0**: a *Refresh* page (the export of
    one environment, what differs on its branch, then the overwrite, confirmed), a *Map* page
    (the environments and their branches, the entries, derive with a preview, what else
    varies, add, rename and remove), and the compare page between the branches of two
    environments: what was read in the terms of the base, the warnings with *Prefer*, the
    branches as stored, the chosen items taken into the base when it is checked out or
    packaged for its environment from any checkout. `/api/envmap*` and `/api/refresh/*`.
    A Playwright run on four synthetic environments (local, like the other one).
21. **The branch model for the assistant — DONE (2026-11-10), released in 0.3.0**: MCP tools `envmap`,
    `takeable`, `package`, `write_package` (the import file, never over another; asked like
    `apply`) and `refresh` (a preview: only the user applies an export); `prefer` and `raw` on
    `compare`; `take` a capability like the others (previewed, then applied into the branch
    checked out); the Kilo agent and skill know the model. Timed on the real application in
    four environments: every tool answers in 3 to 7 s.
22. **A branch of one's own — DONE (2026-11-11), released in 0.3.1**, asked by the author (a branch from uat's,
    an export onto it, uat compared with it): *New branch* in the branch dialog, from the
    branch that is checked out (`POST /api/workspace/branch`; the dialog lists such branches);
    `refresh --here [--partial]` and the *Onto* choice of the *Refresh* page put an export,
    whole or some folders only, onto the checked-out branch and leave the environment's as it
    is; the page links to *Compare* of the two. Also since 0.3.0: every environment's branch
    in the dialog, a *Theme* selector (day colours unless asked), the *View* selector only in
    the one-base model. The Playwright run covers it.
23. **The commands of the one-base model — to decide**: `receive`, `check`, `release`,
    `env constants`, `override` stay for repositories of that model; remove them, or keep
    them, once nobody uses one.
24. **A branch of one's own, read as its environment — A DONE (2026-11-11), released in 0.3.2, B to
    wait**, found while writing the 0.3.1 instructions. Two gaps of story 22:
    - **A. Against another environment.** Which environment a ref holds is known from its
      name alone (the trunk, `env/<name>`), so `compare main work/x`,
      `take work/x --base env/bench` and `package env/bench work/x` do not read a branch
      started from uat's through the letter and the map, and `package` asks for `--env`.
      Done: a branch of one's own holds the environment of the last export the tool put in
      its history (the nearest `refresh(<env>): …` or `import(<env>): …` commit on its
      first-parent line; `held_env`, `DESIGN.md` §14.2), so the three commands, the
      *Compare* page and the assistant's tools treat it like that environment's branch;
      `compare env/uat work/x` (the same environment) stays as it is. A partial export of
      another environment than the branch holds is refused (the branch would hold two).
      Left out on purpose: `package` between two branches of one environment still asks
      for `--env`.
    - **B. The assistant.** The `controlm` agent of Kilo and the `refresh` tool of the MCP
      server preview an export against the environment's branch only: they do not know
      `--here` and `--partial`. To wait: the CLI and the *Refresh* page cover it.

Later, unordered: second-environment import with learning; `diff` of environments and XML
files with `xmldiffreport`; mapping editor; upstream graph explorer (paused by the author);
cycle detection in `validate`; a check for one condition name used by two links; bilingual
docs.
