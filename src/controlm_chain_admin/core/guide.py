"""The ``CLAUDE.md`` a new chain repository starts with: its rules, for people and for agents."""

from __future__ import annotations

from controlm_chain_admin.core.repo import ChainRepo

GUIDE_FILE = "CLAUDE.md"

_TEMPLATE = """\
# {application} — chain repository

The Control-M chains of {application} as neutral JSON, managed with `ctmchain`
(controlm-chain-admin). This repository holds real data: it stays private, and nothing of it
goes into the controlm-chain-admin source, its tests or its issues.

Environments: {environments}. Production is {production}: `{trunk}` mirrors it.

## Rules

1. **never edit `{trunk}`**: it mirrors production. Work on a release
   (`ctmchain release start <name>`); the web UI and `--apply` refuse `{trunk}`.
2. A release is installed environment by environment (`ctmchain release installed <env>` tags
   it) and closed into `{trunk}` once {production} has it (`ctmchain release close`).
3. Exports come in through `ctmchain receive <xml>` or the *Import* page: preview, decide,
   `--apply`, commit. A full export of an environment other than {production} leaves
   {production} alone by default; a delivery (some folders) changes the release. When that
   environment has releases {production} has not, take only its values (`--values-only`, box
   *Only the values* of the *Import* page): the releases come from their deliveries.
4. Never hand-edit `index.json` (derived) or `meta/` (volatile attributes, export header);
   edit through `ctmchain` or the web UI, which preview every change.
5. Exports are big: read them with scripts and counts, never whole.
6. Commit messages say what changed and why (`feat: ...`, `fix: ...`, `chore: ...`).

## Layout

- `chain.json`: application, environments, letter rule, constants (what differs per
  environment), git rules.
- `envs/<env>/env.json`: letter, display name and the value of each constant there;
  `envs/<env>/overrides.json`: exceptions of single jobs there.
- `folders/<FOLDER>/`: `folder.json`, `jobs/<JOB>.json`, `links.json` (condition names) and
  `index.json` (derived). `"envs": [...]` on a folder or job: it exists there only.
- `meta/`: what makes exports byte for byte identical.

## Everyday commands

```bash
ctmchain release status                        # branch, releases, what may be edited
ctmchain receive exports/uat/delivery.xml      # preview the decisions of an export
ctmchain receive exports/uat/delivery.xml --apply
ctmchain receive exports/uat/full.xml --values-only   # machines, users, mails of uat only
ctmchain take release/<other> --list           # what another release changed, item by item
ctmchain validate                              # broken chains, dirty names, suggested fixes
ctmchain export --env uat -o uat.xml
ctmchain serve                                 # the web UI
```
"""


def write_guide(repo: ChainRepo) -> bool:
    """Write ``CLAUDE.md`` in a new repository unless one is there; True when written."""
    path = repo.root / GUIDE_FILE
    if path.exists():
        return False
    config = repo.config
    letters = {env: repo.load_env(env).letter for env in config.environments}
    environments = ", ".join(
        f"{env} ({letters[env]})" if letters[env] else env for env in config.environments
    )
    rules = config.git_rules
    path.write_text(
        _TEMPLATE.format(
            application=config.application,
            environments=environments,
            production=rules.production,
            trunk=rules.trunk,
        ),
        encoding="utf-8",
    )
    return True
