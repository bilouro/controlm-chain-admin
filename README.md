# controlm-chain-admin

[![CI](https://github.com/bilouro/controlm-chain-admin/actions/workflows/ci.yml/badge.svg)](https://github.com/bilouro/controlm-chain-admin/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/controlm-chain-admin.svg?cacheSeconds=3600)](https://pypi.org/project/controlm-chain-admin/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Manage BMC Control-M job chains as a git-friendly JSON repository.** Import the Control-M
XML export, keep the links between jobs explicit, hold one environment-neutral definition for
test/uat/bench/prod, validate the chains, refactor safely, and export the XML back for the
environment you choose.

> Status: alpha. Byte-identical import and export, environments (letter rule, constants,
> exceptions, folders and jobs of some environments) learned from the exports themselves,
> releases with installations per environment, comparison of branches and taking their
> changes item by item, validation with fixes, an editing web UI. The design is in
> [`DESIGN.md`](DESIGN.md) and the plan in [`BACKLOG.md`](BACKLOG.md). Nothing is published to
> PyPI yet; install from source.

## Why

The Control-M user interface is slow for reviewing or changing whole chains, and its XML
export (`DEFTABLE`) is hard to diff, review and version. `controlm-chain-admin` turns that
export into:

- **JSON files in git**, one per folder and per job, with stable ordering, so a plain
  `git diff` shows what really changed and a pull request can review a chain change.
- **Links instead of condition names.** `OUTCOND`/`INCOND` pairs become edges between nodes;
  the original names are kept, and the export can keep them or standardize them.
- **One base, many environments.** The environment letter in names, hosts, users, mail
  recipients and other per-environment values become tokens and constants; each environment
  is a small file. Exporting for another environment is one flag.
- **Environments learned from their exports.** Start from the production export; the export
  of each other environment is grouped into a few decisions (a machine, a user, a mail, the
  environment's name in a subject becomes a constant with a value per environment; what only
  one environment has or lacks is noted), and production stays byte for byte as it was.
- **Releases and comparison.** The trunk mirrors production; a release is installed
  environment by environment; two branches compare in Control-M terms, and any change of the
  other branch (one attribute, one job without its folder, one condition) can be taken into
  yours, conflicts shown value by value.
- **Validation and refactorings** that the Control-M UI does not offer: dangling or stale
  conditions, chains broken by renames, renaming a sub-application across a folder, moving
  a job, inserting a job in a chain.
- **Byte-identical export.** Untouched definitions export exactly as they were imported.

## Install

```bash
pip install controlm-chain-admin          # core + ctmchain CLI (standard library only)
pip install "controlm-chain-admin[web]"   # + local read-only web UI
```

Requires Python 3.11 or newer.

### Where only PyPI is reachable

The source distribution carries the whole project (rules, skills, tests, the web sources and
the built UI), so it can be adjusted where GitHub is out of reach:

```bash
pip download controlm-chain-admin==<version> --no-deps --no-binary :all:
tar -xzf controlm_chain_admin-<version>.tar.gz && cd controlm_chain_admin-<version>
git init -b main && git add -A && git commit -m "chore: controlm-chain-admin <version>"
python -m venv .venv && .venv/bin/pip install -e ".[dev,web]"
```

The `bootstrap` skill (`.claude/skills/bootstrap/SKILL.md`) takes it from there, for a person
or Claude Code: the gate, then a new chain repository built from the full export of each
environment, production first.

## Quickstart

```bash
# a git repository (new or existing) becomes a chain repository
ctmchain init --repo ./my-chains --application P77_RISK_ENGINE \
    --envs test=T,uat=U,bench=B,prod=P --prefixes P77,RQ_,RC_ --leading-only RQ_,RC_

ctmchain distinct NODEID RUN_AS DOMAIL/@DEST --xml uat_export.xml   # what varies per environment
ctmchain import uat_export.xml --env uat --repo ./my-chains         # XML -> JSON, with a report
ctmchain validate --repo ./my-chains                                # chain findings, exit 1 if any
ctmchain resolve never-cleaned=add-cleanup --repo ./my-chains       # preview the fixes; --apply
ctmchain release start 2026-11 --repo ./my-chains                   # edits go to release/2026-11
ctmchain commit --dry-run --repo ./my-chains                        # the message it would use
ctmchain graph P77_INGEST_DAILY --repo ./my-chains --format mermaid # the chain of one folder
ctmchain export --env uat -o uat.xml --repo ./my-chains             # byte-identical to the import
ctmchain export --env prod -o prod.xml --repo ./my-chains           # same chain, prod letters
ctmchain serve --repo ./my-chains                                   # local web UI
ctmchain compare main release/2026-11 --repo ./my-chains            # what the release changed
ctmchain package main release/2026-11 --env uat --repo ./my-chains  # import file, changed folders
ctmchain release installed uat --repo ./my-chains                   # tag uat/2026-11-1
ctmchain receive delivery.xml --repo ./my-chains                    # a team's folders, made neutral
ctmchain receive uat_full.xml --full --repo ./my-chains             # all of uat: constants, what only uat has
ctmchain take release/2026-10 --list --repo ./my-chains             # what another release changed
ctmchain take release/2026-10 --item job:P77_CHAIN/P77_D --repo ./my-chains   # one job of it; --apply
ctmchain release close --repo ./my-chains                           # once installed in prod
```

Refactorings preview a change set and write only with `--apply`:

```bash
ctmchain rename-job P77_INGEST_DAILY/P77_INGEST_LOAD P77_INGEST_POSITIONS   # diff only
ctmchain rename-subapp P77_BATCH P77_CORE --folder P77_INGEST_DAILY --apply
ctmchain insert-job P77_INGEST_DAILY/P77_CHECK --after P77_INGEST_DAILY/P77_INGEST_INIT \
    --before P77_INGEST_DAILY/P77_INGEST_LOAD --apply
```

Also `rename-folder`, `move-job`, `extract-variable`, `map`, `env constants`, `show FOLDER/JOB`,
`links FOLDER/JOB`, `links --name <condition>`. Every command takes `--format json` where a
report is produced. All examples use the fictional
application `P77`; the repository never contains real exports.

## Development

```bash
pip install -e ".[dev,web]"
pytest                                   # synthetic fixtures
cd web && npm ci && npm run build        # builds the web UI into the package
.claude/skills/verify/verify.sh          # the whole quality gate
```

## Concepts

| Term | Meaning |
|---|---|
| Chain repository | A git repository with the environment-neutral **base** plus one small directory per **environment** |
| Node | A folder or a job, identified as `FOLDER/JOB` without the environment letter |
| Link | A dependency edge: producer `OUTCOND +` → consumer `INCOND` with the same condition name |
| Constant | A logical value `@{name}` resolved per environment (hosts, users, recipients) |
| Exception | A per-job, per-environment whole-value replacement (`envs/<env>/overrides.json`) |
| Environments of a node | `"envs": [...]` on a folder or job that exists in some environments only |
| Release | A branch `release/<name>` started from the trunk (production), installed per environment, closed into the trunk |

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). The project is developed test-first; the quality gate
is `.claude/skills/verify/verify.sh`.

## License

MIT — see [`LICENSE`](LICENSE).
