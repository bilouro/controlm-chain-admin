"""The ``CLAUDE.md`` a new chain repository starts with: its rules, for people and for agents."""

from __future__ import annotations

from controlm_chain_admin.core.repo import ChainRepo

GUIDE_FILE = "CLAUDE.md"

_TEMPLATE = """\
# {application} — chain repository

The Control-M chains of {application} as JSON files, managed with `ctmchain`
(controlm-chain-admin). This repository holds real data: it stays private, and nothing of it
goes into the controlm-chain-admin source, its tests or its issues.

Environments: {environments}.

## One branch per environment

- `{trunk}` holds {production}; `{prefix}<name>` holds each other environment ({branches}).
  A branch is what the last full export of its environment said, plus what was taken into it
  since then.
- `{map}` holds `map.json`, the map of what is expected to differ from one environment to
  another: the letter of the names, machines, users, a word of a mail subject. It belongs to
  no environment and is read from its branch, never checked out.

## Rules

1. `{trunk}` changes only by a refresh from a full export of {production}. `ctmchain take
   --apply` refuses it: {production} gets an import file
   (`ctmchain package {trunk} {prefix}{other} --take ...`), and its next export brings the
   change back to `{trunk}`.
2. A full export comes in through `ctmchain refresh <xml>`: it lists what the export differs in
   from the branch of its environment and writes nothing. `--apply` overwrites the branch with
   the export and commits; folders and jobs the export no longer has go.
3. Two environments are compared by their real differences: what the map explains (the
   letter, a machine, a user, a condition name that links the same jobs) is not one. `--raw`
   shows the two branches as they are stored.
4. Never hand-edit `index.json` (derived) or `meta/` (technical attributes, export header);
   edit through `ctmchain` or the web UI, which preview every change.
5. Exports are big: read them with scripts and counts, never whole.
6. Commit messages say what changed and why (`feat: ...`, `fix: ...`, `chore: ...`).

## Layout

- `chain.json`: application, environments, letter rule, git rules.
- `envs/<env>/env.json`: the letter and the display name of each environment.
- `folders/<FOLDER>/`: `folder.json`, `jobs/<JOB>.json`, `links.json` (condition names) and
  `index.json` (derived). Names are stored without the letter of the environment.
- `meta/`: what makes the export of the branch byte for byte the one that came in.

## Everyday commands

```bash
ctmchain refresh exports/{other}/full.xml          # what a new export of {other} changes; --apply
ctmchain envmap show                           # the map: letters and entries
ctmchain envmap derive                         # what the branches show and the map lacks; --apply
ctmchain compare {trunk} {prefix}{other}                  # the real differences between the two
git switch {prefix}{other}                         # take: on the branch that receives
ctmchain take {prefix}<other> --list               # what can be taken, item by item
ctmchain take {prefix}<other> --item folder:<FOLDER> --apply
ctmchain take {prefix}{other} --list --base {trunk}       # what {production} could get of {other}
ctmchain package {trunk} {prefix}{other} --take job:<FOLDER>/<JOB> -o {production}_import.xml
ctmchain export --env {other} -o {other}.xml          # the whole branch, on it
ctmchain validate                              # broken chains, dirty names, suggested fixes
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
    others = [env for env in config.environments if env != rules.production]
    path.write_text(
        _TEMPLATE.format(
            application=config.application,
            environments=environments,
            production=rules.production,
            trunk=rules.trunk,
            prefix=rules.env_prefix,
            map=rules.map_branch,
            branches=", ".join(f"`{rules.env_prefix}{env}`" for env in others) or "none yet",
            other=others[0] if others else rules.production,
        ),
        encoding="utf-8",
    )
    return True
