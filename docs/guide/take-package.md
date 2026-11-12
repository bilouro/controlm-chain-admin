---
description: "Carry an attribute, a job, a folder or a sub-application from one Control-M environment to another: into a branch, or as the import file."
---

# Take and package

What travels is an **item**:

| Item | Means |
|---|---|
| `attr:FOLDER/JOB@NAME` | one attribute of a job (`attr:FOLDER/@NAME` for a folder) |
| `var:FOLDER/JOB@%%NAME` | one variable |
| `job:FOLDER/JOB` | a whole job |
| `folder:FOLDER` | a whole folder |
| `subapp:NAME` | every folder and job of a sub-application |
| `link:ID` | the name of a condition |

```bash
ctmchain take env/uat --list --base env/bench     # what bench can take from uat, with ids
```

## The import file (no branch changes)

```bash
ctmchain package env/bench env/uat \
    --take 'job:P77_CHAIN/P77_NEW' --take 'attr:P77_CHAIN/P77_A@CMDLINE' \
    -o bench_import.xml
```

The file is what `env/bench` holds with those items on it and nothing else, written with
the letter, the machines, the users and the datacenter of bench. Import it in Control-M;
the next export of bench, refreshed, shows exactly what went in.

Without `--take`, every folder that differs is packaged whole. `--dry-run` says what the
file would hold and writes none.

For production it is always this way, with `main` receiving:

```bash
ctmchain package main env/uat --take 'folder:P77_WEEKLY_DAILY' -o prod_import.xml
```

`main` is never edited: it changes only when the next export of production is refreshed.

!!! note "Whole folders"
    Control-M imports whole folders. The file holds each folder an item is in, whole: as the
    receiving environment has it, except for what you chose.

## Into a branch

To record the choice on the branch of an environment that is not production:

```bash
git switch env/bench
ctmchain take env/uat --item 'folder:P77_WEEKLY_DAILY'           # preview
ctmchain take env/uat --item 'folder:P77_WEEKLY_DAILY' --apply
ctmchain commit -m "take the weekly folder from uat"
```

When the branch changed the same place too, the take stops and names the item with its
three values (yours, the starting one, theirs): leave it out, or take it with `--theirs`.

## The name of a condition

`ctmchain compare` lists the conditions the two environments call by different names. To
make production use the name UAT uses:

```bash
ctmchain package main env/uat --take 'link:ID' -o prod_import.xml
```
