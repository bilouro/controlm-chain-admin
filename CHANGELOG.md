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
- `compare --commit <sha>` and commit checkboxes on the *Compare* page: compare only some commits
  of the branch, applied on the base cherry-pick style; a selection that needs a left-out commit
  names it; every change lists the commits that made it.
- `ctmchain package <base> [<head>] --env <env>` and the *Generate XML* button: the Control-M
  import file with every folder the comparison changed, whole, for one environment (letter rule
  and constants resolved, original JOBNAMEs), with the reason of each folder, warnings for what
  an import cannot do and new validation findings (`GET /api/package`, `GET /api/package/xml`).
- `export_document(..., folders=)` exports a subset of the folders; `validate(write_index=False)`.
- Fixes for validation findings: `ctmchain resolve [CODE=KIND...]`, each finding of
  `GET /api/validate` with its fixes and link id, new operations `emit`, `stop-emitting` and
  `batch` (several changes previewed and applied as one). The *Validation* page selects every
  finding by default, filters by type of problem, resolves one finding (a button per fix, each
  explained) or the selection (one choice per type of problem, one reviewed change), and uses the
  full width of the screen without horizontal scrolling.
- Every fix lists its effects (which job gets which element added, removed or changed, before
  and after); the review dialog shows them above the diff as *What will change*, says that
  nothing is written before *Apply change*, and asks for the editing URL or token when the tab
  has none. `ctmchain serve` keeps `CTMCHAIN_TOKEN` when it is set, so open tabs survive a
  restart.
- Committing edits: `ctmchain commit [-m MESSAGE] [--branch NAME] [--dry-run]` and the *Commit
  (n)* button of the web UI header, with a Conventional Commits message written from the
  semantic comparison of HEAD with the working tree (editable), the files, and a new release
  branch when on a protected branch. Only the chain files are committed
  (`git commit --only`); a commit prepared before other edits is refused
  (`GET /api/git/pending`, `POST /api/git/commit`, `changes` in `GET /api/git`).
- *Copy Markdown* on the Compare page (`GET /api/compare/markdown`): the comparison for a pull
  request description; left-out commits are marked in the Markdown and the text reports.
- Releases: the trunk (`main`) mirrors production and is never edited; edits and commits are
  refused on protected branches and a detached HEAD. `ctmchain release
  status|start|switch|installed|update|close`: a release branch `release/<name>` starts from the
  trunk, each installation in an environment is a tag `<env>/<name>-<n>`, a release is closed
  (merged into the trunk) once its last commit is installed in production, after merging the
  trunk in when it moved. The web UI header shows the branch and opens the *Releases* dialog
  (start, switch, stash and restore, discard, update, close, push and pull); a banner and the
  review dialog explain why a branch is read-only; the package preview asks whether to hold
  only what changed since the last installation in that environment, and marks the
  installation (`GET /api/workspace`, `POST /api/workspace/...`). Rules in the optional `git`
  key of `chain.json`.
- Exceptions per environment (`envs/<env>/overrides.json`): attributes and variables one
  environment uses for one job or folder instead of the base, applied at export before the
  constants; `ctmchain set-exception` and the `set-exception` change; a changed exception
  puts its folder in that environment's package. `ctmchain rename-constant` (and the change of
  the same name) renames a constant everywhere it is used.
- Package skeleton, CI (lint, types, tests, web, build) and release workflows, community files.
- `DESIGN.md` (architecture and data model) and `BACKLOG.md` (proof-of-concept plan and status).

### Fixed

- Resource names with an inner application code (`URQ_P77_AGGREGATION`) were kept literally,
  with the letter of the imported environment, so another environment's export would have used
  that environment's resource: prefixes listed in `letter_rule.leading_only` carry the letter on
  the first token only.
- Exports saved with Windows line endings (`\r\n`) are written back with them.
- Importing an export of some folders only replaced the header of the full export (the
  *Exported at* comment); it is now kept. `JOBS_IN_GROUP` is a volatile attribute by default.
- A folder-prefixed standard name (`F_A-B_OK`, given when two links would collide) is no longer
  reported as `stale-name`, and the fix to rename to it is offered.
- Renaming a job or a folder, or inserting a job, could give a condition a name another link
  already used, joining two chains in Control-M; the condition now keeps its name, with a
  warning, and the new link of `insert-job` never reuses a name.

- Piping CLI output into a reader that closes early (`| head`) no longer prints a BrokenPipe error.
- Reloading or opening a web UI page other than the home page (for example `/compare?...` or a
  job page) returned 404; the server now answers client routes with the app.
- On Windows, unknown `/api/...` paths and missing assets were answered with the app instead of
  404 (the static files handler sees `\` separators there).

[Unreleased]: https://github.com/bilouro/controlm-chain-admin/commits/main
