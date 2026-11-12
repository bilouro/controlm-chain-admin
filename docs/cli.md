---
description: "Every ctmchain command, by what it is for."
---

# Command reference

Every command takes `--repo DIR` (default: the current directory) and prints its own help
with `--help`. Commands that change something preview first and write only with `--apply`.
Exit codes: `0` ok, `1` findings, `2` usage, `3` error.

## The repository

| Command | What it does |
|---|---|
| `ctmchain init --application APP --envs prod=P,uat=U [--prefixes ...] [--leading-only ...] [--dedupe-jobnames]` | turn a directory into a chain repository |
| `ctmchain refresh XML [--env ENV] [--apply] [--here] [--partial] [--no-commit] [--stat]` | the export of an environment onto its branch (or onto the branch checked out) |
| `ctmchain check XML [--env ENV]` | an export against what the repository gives back for that environment |
| `ctmchain export [--env ENV] -o FILE` | regenerate the XML of the branch checked out |
| `ctmchain commit [-m MESSAGE]` | commit the chain files, with a message written from what changed |

## Between environments

| Command | What it does |
|---|---|
| `ctmchain envmap show\|derive\|suggest\|add\|rename\|remove` | the map of what varies |
| `ctmchain envmap followers`, `ctmchain envmap follow ENTRY OTHER [--apply]` | who follows each entry; make the jobs of one follow another |
| `ctmchain compare BASE [HEAD] [--raw] [--prefer ENTRY] [--format text\|md\|json]` | what differs |
| `ctmchain take HEAD [--list] [--base BASE] [--item ID ...] [--theirs ID ...] [--apply]` | items of another branch into the checked-out one |
| `ctmchain package BASE [HEAD] [--take ID ...] [--env ENV] [-o FILE] [--dry-run]` | the import file |
| `ctmchain delivery save\|list\|remove\|package` | items kept for later, and one file from several |

## Looking

| Command | What it does |
|---|---|
| `ctmchain show NODE`, `ctmchain graph FOLDER`, `ctmchain links NODE` | one node, the graph of a folder, the links of a node |
| `ctmchain distinct ATTR ...` | the distinct values of attributes, with counts |
| `ctmchain validate`, `ctmchain resolve [CODE=KIND ...] [--apply]` | findings, and their fixes |
| `ctmchain diagnose [BASE HEAD] [-o FILE]` | why something is slow here (numbers only) |

## Changing

| Command | What it does |
|---|---|
| `ctmchain rename-job NODE NEW`, `rename-folder`, `rename-subapp`, `move-job`, `insert-job` | refactorings; condition names follow |
| `ctmchain adopt-jobname NODE` | the numbered name of a job becomes its JOBNAME |
| `ctmchain extract-variable`, `ctmchain technical` | a literal into a variable; the technical attributes |
| `ctmchain set-exception`, `promote-exception`, `map`, `rename-constant` | for a repository that keeps every environment in one tree |

## Interfaces

| Command | What it does |
|---|---|
| `ctmchain serve [--port N] [--assistant]` | the local web UI and API (`[web]`) |
| `ctmchain mcp`, `ctmchain menu`, `ctmchain kilo init [--force]` | the tools for an assistant (`[mcp]`) |
