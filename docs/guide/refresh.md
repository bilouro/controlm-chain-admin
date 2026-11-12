---
description: "Bring a new full export of a Control-M environment into its branch: see what changed, then overwrite."
---

# Refresh an environment

A branch is what the last full export of its environment said, and nothing else. A new
export replaces it, after showing what changed.

```bash
ctmchain refresh ../exports/uat.xml            # what it would change; nothing written
ctmchain refresh ../exports/uat.xml --apply    # overwrite env/uat and commit
git push origin env/uat
```

The first command lists what came in, what went out and what changed, attribute by
attribute. The second checks the branch out, overwrites its chain files and commits
(`refresh(uat): uat.xml`). Folders and jobs the export no longer has go.

The environment is told by the letter of the names. When it cannot be, name it:

```bash
ctmchain refresh ../exports/uat.xml --env uat
```

## Good to know

- With uncommitted chain files the refresh refuses: commit or discard them first.
- The same export again changes nothing (`already holds this export`).
- `--stat` gives the counts only; `--no-commit` leaves the result uncommitted.
- A file with some folders only (a delivery) is not a full export: it goes onto a
  [branch of your own](own-branch.md) with `--here --partial`.
- In the web UI: the *Refresh* page.
