# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/) (`0.x`: the JSON layout may still change).

## [Unreleased]

### Added

- Faithful XML reader and serializer for Control-M exports (`DEFTABLE`): byte-identical round
  trip, including attribute order, prolog comment and escaping.
- Chain repository: `ctmchain init`, `import` (lossless, folders of other applications skipped
  and reported, volatile metadata in `meta/`, repeated JOBNAMEs as `NAME~n`), `export`
  (identical for untouched content).
- Environment letter rule: `--prefixes` and per-environment letters; neutral names on disk;
  `import --env` / `export --env`; `literal:` marks and suspicious values in the import report.
- Derived links index per folder; `validate` with severities, text/Markdown/JSON output and exit
  codes; `distinct`, `show`, `graph` (text, Mermaid, DOT, JSON) and `links` commands.
- `[web]` extra: read-only FastAPI (`ctmchain serve`) and a Vite + React web UI with folder
  list, chain graph, job detail and validation pages; OpenAPI snapshot as the frontend contract.
- Constants: `@{name}` placeholders in the base resolved per environment at export
  (`distinct --write` mapping drafts, `map`, `import --mappings`, `env constants --missing`,
  `export --allow-unresolved`); value and inline modes; selectors `ATTR`, `TAG/@ATTR`,
  `TAG[K=V]/@ATTR`.
- Links are the source of truth for condition names: nodes reference `"link": "<id>"`,
  `folders/<F>/links.json` holds the export name of each link, `index.json` is the derived view.
  Renaming a condition is one edit; ids stay stable when a renamed export is imported again.
- `export --names standard`: `<PRODUCER>-<CONSUMER>_OK` from the endpoints, producer folder as
  prefix when two links would collide; external, fan-in and delete-only links keep their names.
- `import --dedupe-jobnames`: repeated JOBNAMEs get a numeric suffix (`X`, `X2`, `X3`), the
  originals are kept in `meta/` and the policy in `chain.json`; `export --jobnames original`
  restores them byte for byte.
- Refactorings with change-set preview and `--apply`: `rename-job`, `rename-folder`,
  `rename-subapp`, `move-job`, `insert-job`, `extract-variable`. Previews show a unified diff
  (`--stat`, `--format json`); apply refuses files changed since the preview.
- Editing web UI: the *Chains* table (folders collapsible, application, sub-application, folder,
  job, predecessors, successors) and tabbed folder and job pages to edit attributes, variables,
  raw JSON and predecessors/successors with their AND_OR, ODATE and `+`/`−` details. Edits are
  previewed as a diff and applied through `POST /api/changes/preview|apply` with a session token.
- `ctmchain compare <base> [<head>]`: what a branch changed in the chain (folders and jobs added,
  removed, modified, renamed or moved; attribute and variable values before and after;
  predecessor and successor changes with AND_OR, ODATE, `+` and `−`; conditions; constants per
  environment; commits), from the merge base by default, with `--worktree`, `--no-merge-base` and
  text, Markdown or JSON output. The *Compare* web page shows the same comparison with ref
  pickers, summary cards, a change list grouped by folder and a before/after detail
  (`GET /api/git`, `GET /api/compare`).
- Package skeleton, CI (lint, types, tests, web, build) and release workflows, community files.
- `DESIGN.md` (architecture and data model) and `BACKLOG.md` (proof-of-concept plan and status).

### Fixed

- Piping CLI output into a reader that closes early (`| head`) no longer prints a BrokenPipe error.
- Reloading or opening a web UI page other than the home page (for example `/compare?...` or a
  job page) returned 404; the server now answers client routes with the app.

[Unreleased]: https://github.com/bilouro/controlm-chain-admin/commits/main
