# controlm-chain-admin

[![CI](https://github.com/bilouro/controlm-chain-admin/actions/workflows/ci.yml/badge.svg)](https://github.com/bilouro/controlm-chain-admin/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/controlm-chain-admin.svg?cacheSeconds=3600)](https://pypi.org/project/controlm-chain-admin/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Your BMC Control-M environments in git: one branch per environment, compared by their real
differences, promoted item by item.** Export an environment from Control-M, refresh its
branch, see what really differs from another environment, pick a job, a folder or a whole
sub-application, and get the import file already written for the environment that receives it.

```text
   Control-M (full XML export of each environment)
        |  ctmchain refresh <export.xml>      preview first, --apply overwrites the branch
        v
   main        production          \
   env/uat     UAT                  |   ctmchain compare main env/uat    real differences only
   env/egma    another test level   |   ctmchain take env/uat --list     what can be taken
   env/bench   bench               /    ctmchain package main env/uat --take folder:...
   map         what is expected to differ: the letter of the names, machines, users
        |
        v
   import file for the target environment (its letter, its machines, its users)
```

> Status: alpha, used on a real application of a few hundred folders and well over a thousand
> jobs in four environments. Three ways to the same thing: the command line, a local web UI
> and an assistant you ask in plain words. Design: [`DESIGN.md`](DESIGN.md); the needs it
> answers: [`NEEDS.md`](NEEDS.md).

## The problem

The same chains live in several Control-M environments, and no two are the same: every name
carries the letter of its environment, jobs run on other machines as other users, and each
environment is some changes ahead of or behind the others. The Control-M interface does not
compare environments, and two XML exports differ on almost every line, so a plain `diff` says
nothing. Moving a change from UAT to production means retyping it, or editing XML by hand.

`controlm-chain-admin` (the `ctmchain` command) answers three questions with one git
repository of small JSON files:

1. **What does each environment have right now?** One branch each, refreshed from its export.
2. **What is really different between two of them?** Not the letter, the machine or the user.
3. **How do I move this job, this folder, this sub-application over there?** An import file
   in the terms of the target, ready for Control-M.

## What it does

| You want to | Command |
|---|---|
| Keep production on `main` and every other environment on a branch of its own | `ctmchain refresh prod.xml --apply`, `ctmchain refresh uat.xml --apply`, ... |
| Export an environment again and see what changed before accepting it | `ctmchain refresh uat.xml` (nothing is written), then `--apply` |
| Try an export (whole, or some folders with `--partial`) on a branch of your own and compare it with the environment's | `git switch -c work/uat-next env/uat`, `ctmchain refresh uat-new.xml --here --apply`, `ctmchain compare env/uat work/uat-next` |
| Carry what a branch of your own holds to another environment: it is read as the environment it started from | `ctmchain compare env/bench work/uat-next`, `ctmchain package env/bench work/uat-next --take folder:F -o bench_import.xml` |
| The import file of what a branch of your own changes in its own environment (no `--env`: both hold uat) | `ctmchain package env/uat work/uat-next -o uat_import.xml` |
| Know what is expected to differ between environments, without it belonging to any of them | `ctmchain envmap derive --apply`, `ctmchain envmap show` (kept on the branch `map`) |
| Compare two environments by their real differences | `ctmchain compare main env/uat` (`--raw`: as stored) |
| Give a job whose JOBNAME others share the numbered name the repository calls it, in Control-M too | `ctmchain adopt-jobname FOLDER/JOB2 --apply`, then `ctmchain package` for each environment |
| Put right an environment set up with another one's value: its jobs follow the right entry of the map | `ctmchain envmap followers`, `ctmchain envmap follow run_as.2 run_as.1 --apply` (on that environment's branch) |
| Put items aside under a name, today and next week, and make one import file from several when it is time | `ctmchain delivery save "new job" env/uat --item 'job:F/J' --base env/bench`, `ctmchain delivery list`, `ctmchain delivery package env/bench "new job" weekly -o bench_import.xml` |
| See why a comparison is slow on a machine (numbers only, safe to pass on) | `ctmchain diagnose` (`-o report.txt` writes it to a file too) |
| Take one attribute, one variable, one job, one folder or a sub-application into another environment's branch | `ctmchain take env/uat --list`, `ctmchain take env/uat --item job:F/J --apply` |
| Get the import file of what was chosen, adapted to the target, without changing any branch | `ctmchain package main env/uat --take folder:F -o prod_import.xml` |
| Export a whole environment as it stands on its branch | `ctmchain export --env bench -o bench.xml` |

What "adapted to the target" means: the letter of every name (folders, jobs, conditions,
resources, calendars), the machine, the user, the datacenter and any other value of the map
are written as the target environment has them. What the map cannot settle is never guessed:
the value is kept, a warning names it, and `--prefer` settles it.

## A session

All examples use the fictional application `P77`; this repository never contains real
exports.

```bash
# once: the rules of the repository, then one branch per environment from its full export
git init -b main my-chains && cd my-chains
ctmchain init --application P77_RISK_ENGINE --envs prod=P,uat=U,egma=E,bench=B \
    --prefixes P77,RQ_,RC_ --leading-only RQ_,RC_
git add -A && git commit -m "chore: the rules of the repository"
ctmchain refresh ../exports/prod.xml --apply     # main
ctmchain refresh ../exports/uat.xml --apply      # env/uat, created from the rules of main
ctmchain refresh ../exports/egma.xml --apply     # env/egma
ctmchain refresh ../exports/bench.xml --apply    # env/bench
```

Every branch now gives its export back byte for byte (`ctmchain export`, with the JOBNAMEs
of Control-M even where the repository numbered repeated ones). The map comes from the
branches themselves:

```console
$ ctmchain envmap derive --apply
3 new entries from main (prod), env/uat (uat), env/egma (egma), env/bench (bench)
  nodeid.1  NODEID  7 nodes
      prod=srvp-bat1  uat=srvu-bat1  egma=srve-bat1  bench=srvb-bat1
  run_as.1  RUN_AS  11 nodes
      prod=app77proc  uat=aup77proc  egma=aep77proc  bench=abp77proc
  datacenter.1  DATACENTER  2 nodes
      prod=CTMPROD  uat=CTMUAT  egma=CTMEGMA  bench=CTMBENCH
Written on map: 3 entries added
```

`ctmchain envmap suggest` lists what else varies, with the command that adds it: here a
variable that holds the environment's code and a word of a mail subject, two more entries.
`envmap add`, `remove` and `rename` edit the map by hand.

Now the comparison says what matters. As stored, production and UAT differ everywhere; read
through the map, a handful of real differences is left:

```console
$ ctmchain compare main env/uat
Compare main (prod) with env/uat (uat): real differences only
  expected between prod and uat, not shown: 28 values and 2 texts of the map, 4 names with the letter, 0 conditions called another name

modified folder P77_INGEST_DAILY/
    variable %%RETRY: (none) -> 3
added    folder P77_WEEKLY_DAILY/
    jobs added: P77_WEEKLY_DAILY/P77_WEEKLY_INIT, P77_WEEKLY_DAILY/P77_WEEKLY_LOAD
added    job P77_CHAIN/P77_NEW
modified job P77_CHAIN/P77_A
    CMDLINE: /opt/p77/bin/a.ksh -> /opt/p77/bin/a2.ksh -x
...
```

An `INCOND`/`OUTCOND` pair whose name carries another letter, or is simply called something
else, but links the same jobs with the same sign, is not a difference either.

Take what you choose, at the size you choose, into the branch that is checked out:

```console
$ git switch env/bench
$ ctmchain take env/uat --list
Items env/uat (uat) has that can be taken into env/bench (bench):
  subapp:P77_BATCH  3 folders that differ
  folder:P77_INGEST_DAILY  the whole folder, modified
  var:P77_INGEST_DAILY/@%%RETRY  (none) -> 3
  folder:P77_CHAIN  the whole folder, modified
  folder:P77_WEEKLY_DAILY  the whole folder, added
  job:P77_CHAIN/P77_NEW  the whole job, added
  job:P77_CHAIN/P77_A  the whole job, modified
  attr:P77_CHAIN/P77_A@CMDLINE  /opt/p77/bin/a.ksh -> /opt/p77/bin/a2.ksh -x
  ...
$ ctmchain take env/uat --item folder:P77_WEEKLY_DAILY --item attr:P77_CHAIN/P77_A@CMDLINE --apply
$ ctmchain commit                                # a message written from what changed
$ ctmchain export --env bench -o bench.xml       # bench, with what it took
```

Or skip the branch and get the import file for the target directly. Production's branch is
never edited by hand: it gets a file, and its next export brings the change back to `main`.

```console
$ ctmchain package main env/uat --take folder:P77_WEEKLY_DAILY -o prod_import.xml
Package env/uat (uat) for prod (main): 1 folder, 1 item taken
  P77_WEEKLY_DAILY (2 jobs): folder added; job P77_WEEKLY_INIT added; job P77_WEEKLY_LOAD added
warning: P77_PRICING-P77_WEEKLY_DAILY_OK: a job waits for it but no job emits it here
Wrote prod_import.xml (2078 bytes)
```

`prod_import.xml` holds `PP77_WEEKLY_DAILY` with production's machine, user and datacenter,
although it was read from UAT, and the warning says what the folder will wait for there.

When Control-M is exported again, `ctmchain refresh` shows
what the export changes on the branch, and nothing is written until `--apply`:

```console
$ ctmchain refresh ../exports/bench-new.xml
Refresh env/bench (bench) from bench-new.xml: 2 folders, 9 jobs in the export

  jobs: 1 modified

modified job P77_CHAIN/P77_C
    CMDLINE: /opt/p77/bin/c.ksh -> /opt/p77/bin/c9.ksh

Nothing written: --apply overwrites env/bench with this export.
```

## In the browser, or in plain words

`ctmchain serve` opens the same repository as a local web UI (`127.0.0.1` only; what writes
asks for the token the command prints):

- **Refresh**: choose the export of an environment. The page says which environment it is
  and why, what was read, and what differs on its branch, node by node; the branch is
  overwritten only after you confirm. From a branch of your own (*New branch* in the dialog
  of the branch button starts one from the branch that is checked out, `env/uat` say) the
  export goes *Onto* that branch instead, whole or some folders only, and a link opens
  *Compare* on the environment's branch against it: what the export brings, before the
  environment's branch takes it. Against the branch of another environment, a branch of
  your own is read as the environment it holds (the one of the last export in its
  history), so *Compare*, taking and packaging work from it as from `env/uat`.
- **Map**: the environments with their letters and branches, and every entry of the map.
  *Look at the branches* previews what they show before adding it; *Show what else varies*
  lists the rest, with a button per key; an entry is added, renamed or removed by hand.
  *Followed by* says how many places of the branches have exactly an entry's values, and
  *Follow…* makes the jobs of one entry follow another of the same key, on the branch
  checked out, as a change you review: the cure when one environment was set up with
  another one's value and the map took it for a rule.
- **Deliveries**: what you put aside for later. On *Compare*, the checked items are kept
  under a name (*Keep N items…*) instead of packaged at once; on the page of a job or of a
  folder, *Keep for a delivery…* keeps it as the branch checked out has it, changed or not
  (a job whole, or one attribute of it). The *Deliveries* page lists them; check one or
  several, choose the environment that receives, and one import file comes out with their
  sum, written as that environment writes it. Each is as it was on the day it was kept.
- **Compare**: choose two environments. Only the real differences are listed, each with a
  box. The checked items are taken into the branch that is checked out, or downloaded as the
  import file of the other environment, with those items and nothing else. A value the map
  gives two answers for comes with one *Prefer* button per answer. Choosing another branch
  compares nothing until you press *Compare*, and the last comparison stays in view while
  the next one is worked out.

`ctmchain serve --assistant` adds an assistant to the page, and `ctmchain mcp` gives the
same tools to Kilo, Claude or any MCP client: "what does uat have that prod has not?",
"take the new job of uat into bench", "the import file for production with that folder".
It previews every change and writes only when you agree.

## Why git, why JSON

- **One small file per folder and per job**, with stable ordering: `git diff`, `git log` and
  a pull request work on a chain change.
- **Byte-identical export.** A branch gives back exactly the export it was refreshed from;
  what Control-M adds on every upload (dates, versions, user of the change) is kept apart
  and never compared.
- **Links instead of condition names.** `OUTCOND`/`INCOND` pairs become edges between jobs;
  the original names are kept, and an export can keep them or standardise them.
- **Nothing leaves your machine.** The core and the command line use the Python standard
  library only; the web UI and the assistant are optional extras and bind `127.0.0.1`.

## Install

```bash
pip install controlm-chain-admin          # core + ctmchain CLI (standard library only)
pip install "controlm-chain-admin[web]"   # + the local web UI (ctmchain serve)
pip install "controlm-chain-admin[mcp]"   # + the tools for an assistant (Kilo, Claude)
```

Requires Python 3.11 or newer and git.

## On Windows, from scratch (with Kilo)

In PowerShell, with Python 3.11 or newer, git, and optionally the Kilo CLI (`kilo
--version`, signed in with the model your company allows) on the PATH. Only PyPI needs to be
reachable.

```powershell
# 1. The tool, in a virtual environment of its own (an older one: the same pip line in it)
py -m venv $HOME\ctmchain-venv
& $HOME\ctmchain-venv\Scripts\Activate.ps1   # blocked? Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
python -m pip install --upgrade "controlm-chain-admin[web,mcp]"
ctmchain --version

# 2. The data repository, outside the code: the full exports in exports\, the chains in
#    chains\ (a private git repository; the exports stay out of it)
mkdir $HOME\dev\my-data\chains; cd $HOME\dev\my-data\chains
git init -b main
# the quotes matter: PowerShell splits a bare word at its commas
ctmchain init --application P77_RISK_ENGINE --envs 'prod=P,uat=U,egma=E,bench=B' `
    --prefixes 'P77,RQ_,RC_' --leading-only 'RQ_,RC_' --dedupe-jobnames
Add-Content .gitignore ".kilo/"
git add -A; git commit -m "chore: the rules of the repository"

# 3. One branch per environment, production first (--stat: counts, not every difference)
ctmchain refresh ..\exports\prod.xml --apply --stat      # main
ctmchain refresh ..\exports\uat.xml --apply --stat       # env/uat
ctmchain refresh ..\exports\egma.xml --apply --stat      # env/egma
ctmchain refresh ..\exports\bench.xml --apply --stat     # env/bench
git switch main

# 4. The map of what is expected to differ, read from the four branches
ctmchain envmap derive                  # what it found; --apply writes it on the branch map
ctmchain envmap derive --apply
ctmchain envmap suggest                 # what else varies, with the command for each
ctmchain envmap show

# 5. Compare, choose, export
ctmchain compare main env/uat --format md | Out-File -Encoding utf8 uat-vs-prod.md
ctmchain take env/uat --list --base main
ctmchain package main env/uat --take 'folder:P77_WEEKLY_DAILY' -o prod_import.xml

# 6. Optional: the web UI and the assistant
ctmchain kilo init --repo .             # set up by an earlier version: again, with --force
ctmchain serve --assistant              # Refresh, Map, Compare; Assistant in the header
```

`--dedupe-jobnames` is for exports where a folder repeats a `JOBNAME`: the repository gives
the repeated ones a numeric suffix; `package` and `export` give the original names back
(`export --jobnames deduped` gives the stored ones).
`ctmchain serve --assistant` starts `kilo serve` itself, with the model Kilo is set to
(`--assistant-model provider/model` for another one, `kilo models` lists them) and stops it
with the server. A `kilo` that is not on the PATH: `$env:CTMCHAIN_KILO = "C:\path\to\kilo.cmd"`.

### Where only PyPI is reachable

The source distribution carries the whole project (rules, skills, tests, the web sources and
the built UI), so it can be read and adjusted where GitHub is out of reach:

```bash
pip download controlm-chain-admin==<version> --no-deps --no-binary :all:
tar -xzf controlm_chain_admin-<version>.tar.gz && cd controlm_chain_admin-<version>
git init -b main && git add -A && git commit -m "chore: controlm-chain-admin <version>"
python -m venv .venv && .venv/bin/pip install -e ".[dev,web]"
```

`.claude/skills/bootstrap/SKILL.md` in the archive is the step by step, for a person or an
agent: the gate, then a data repository from the exports.

## Also in the box

- **Validation with fixes** the Control-M interface does not offer: conditions nobody emits
  or nobody cleans, chains broken by a rename, condition names that differ only by a copy's
  suffix or by case, a JOBNAME that several jobs of the export share. Every kind of finding
  says what it looks for, why it matters and what its fix does (`ctmchain resolve` lists
  them; the *Validation* page shows it when a type is chosen). `ctmchain validate`,
  `ctmchain resolve <finding>=<fix> --apply`.
- **Refactorings with a preview**: `rename-job`, `rename-folder`, `rename-subapp`,
  `move-job`, `insert-job` (between two jobs of a chain), `extract-variable`,
  `set-variable`. Each prints the change and writes only with `--apply`.
- **A local web UI** (`ctmchain serve`): the folders, the graph of a chain, a job with its
  attributes grouped, findings, an editing form with preview. Between environments: *Refresh*
  (the export of an environment, what differs, then the overwrite; onto a branch of your own
  to try it first), *Map* (what varies per
  environment, derived from the branches and edited), and *Compare* of two environments with
  a box per item to take it or to package it for the other environment.
- **Ask in plain words.** `ctmchain mcp` gives an assistant (Kilo, Claude, any MCP client)
  the repository as tools: it answers questions and proposes changes, previewed field by
  field, and writes one only when you agree. Between environments too: "what does uat have
  that prod has not?", "take the new job of uat into bench", "the import file for production
  with that folder" (it compares, lists what can be taken, takes into the branch checked out,
  and writes the import file once you agree; it never switches a branch, commits or applies
  an export). On a branch of your own it also says what an export, whole or some folders
  only, would change there ("what does delivery.xml change on this branch?"), and tells you
  the `refresh --here` command that applies it. `ctmchain kilo init` sets Kilo up with an
  agent that may use those tools only; after an upgrade, `ctmchain kilo init --force` gives
  the agent the rules of the new version (your `vocabulary.md` is kept).
  The assistant's model reads the names and fields of your jobs: use one your company allows.
- **`--format json`** wherever a report is printed, for scripts and agents; exit codes 0 (ok),
  1 (findings), 2 (usage), 3 (error).
- **Another way to hold the environments**, from the first releases and still there: one
  branch with a neutral base, a constant per value that differs (`@{name}`) and the
  exceptions of each environment, with releases installed environment by environment
  (`receive`, `check`, `release`, `env constants`). See [`DESIGN.md`](DESIGN.md) section 5.

## Concepts

| Term | Meaning |
|---|---|
| Chain repository | A git repository of JSON files: `chain.json` (the rules), `folders/<FOLDER>/folder.json`, `jobs/<JOB>.json`, `links.json` |
| Environment branch | `main` for production, `env/<name>` for every other environment: what its last full export said, plus what was taken into it |
| Refresh | A full export overwriting the branch of its environment, after showing what it changes |
| Map | `map.json` on the branch `map`: the letter of each environment and the values that stand for each other (a machine, a user, a word of a subject) |
| Real difference | What is left between two environments once the map and the letter are read through |
| Item | Something of a comparison that can be taken alone: `subapp:S`, `folder:F`, `job:F/J`, `attr:F/J@NAME`, `var:F/J@%%NAME` |
| Import file | A Control-M XML of the chosen folders, in the terms of the target environment (`ctmchain package`) |
| Node | A folder or a job, identified as `FOLDER/JOB` without the environment letter |
| Link | A dependency edge: producer `OUTCOND +` → consumer `INCOND` with the same condition name |

## Development

```bash
pip install -e ".[dev,web]"
pytest                                   # unit, functional and end-to-end, synthetic fixtures
cd web && npm ci && npm run build        # builds the web UI into the package
.claude/skills/verify/verify.sh          # the whole quality gate
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md). The project is developed test-first.

## License

MIT — see [`LICENSE`](LICENSE).
