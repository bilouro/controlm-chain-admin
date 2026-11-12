---
description: "Try a Control-M export on a branch of your own without touching the environment's branch, and carry what it holds elsewhere."
---

# A branch of your own

To see what an export brings, kept, before the branch of the environment is overwritten:
start a branch from the environment's and import the export onto it.

```bash
git switch -c work/uat-next env/uat
ctmchain refresh ../exports/uat-next.xml --here            # what it would change
ctmchain refresh ../exports/uat-next.xml --here --apply
ctmchain compare env/uat work/uat-next                     # UAT today against what arrived
```

For a file with some folders only (a delivery), add `--partial`: the folders the file does
not have stay as they are.

```bash
ctmchain refresh ../exports/delivery.xml --here --partial --apply
```

Without `--here` a refresh goes onto the environment's branch, whatever is checked out.
Without `--partial` a file with some folders only is read as a full export and would remove
the others: the preview shows it.

## What such a branch holds

A branch of your own is read as the environment it holds: the one of the branch it started
from, until the full export of another environment goes onto it. So it works as a source
like the environment's branch does:

```bash
ctmchain compare main work/uat-next
ctmchain take work/uat-next --list --base env/bench
ctmchain package env/bench work/uat-next --take 'folder:P77_WEEKLY_DAILY' -o bench_import.xml
ctmchain package env/uat work/uat-next -o uat_import.xml
```

The tool knows the environment by the subject of the last export commit in the branch's
history (`refresh(uat): …` or `import(uat): …`). With `--no-commit` the command prints the
subject to commit with.

When the export becomes the official state of the environment, do the normal
[refresh](refresh.md) and delete your branch.
