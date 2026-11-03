---
name: bootstrap
description: Set up controlm-chain-admin where only PyPI is reachable (no GitHub), then build a new chain repository from the full exports of every environment, step by step, with the conventions agreed for environments, constants and exceptions. Use when someone says «instalar na empresa», «set up at work», «criar o repositório de dados», «começar do zero», «bootstrap», or opens this source for the first time on a new machine.
---

# bootstrap — the code from PyPI, the data repository from the exports

Two separate directories, never one inside the other:

- **the code**: this project, unpacked from its source distribution, to run and adjust;
- **the data**: a new git repository with the chains of one application, built from the
  exports. It holds real data and never mixes with the code.

Ask the person before anything that is hard to undo (pushing, deleting, `--apply` on many
files) and number every question so they can answer «1 sim, 2 não».

## Part A — the code

1. Check what the machine has: `python --version` (3.11 or newer), `git --version`, and
   whether `pip download` reaches PyPI (or the company mirror). npm is only needed to change
   the web UI; the built UI already ships in the package.
2. Unpack the source and make it a git repository of its own (adjustments made here stay
   here; the next version brings them back from upstream):

   ```bash
   pip download controlm-chain-admin==<version> --no-deps --no-binary :all:
   tar -xzf controlm_chain_admin-<version>.tar.gz
   cd controlm_chain_admin-<version>
   git init -b main && git add -A && git commit -m "chore: controlm-chain-admin <version>"
   python -m venv .venv
   .venv/bin/pip install -e ".[dev,web]"          # Windows: .venv\Scripts\pip ...
   ```

3. Create `.claude/no-real-data.patterns` (git-ignored, one regular expression per line) with
   the names that must never enter this code: the company, its domains, the application
   code, machine and user prefixes. Ask the person for them. The gate scans for them.
4. Run the gate once: `PATH="$PWD/.venv/bin:$PATH" .claude/skills/verify/verify.sh` (on
   Windows from Git Bash, with `.venv/Scripts`). Without npm the frontend steps are skipped.
5. From here on the project rules apply (`CLAUDE.md`): TDD, English in the code, no real data
   in this directory, not even in tests.

## Part B — the data repository

### 1. What the exports say

Put the full exports in `exports/<env>/` of the new data directory (they are big: look at
them with scripts and counts, never whole). Then ask, numbered, what the exports do not say:

1. the application (`APPLICATION` of its folders) and the environments with their letters,
   e.g. `test=T,uat=U,bench=B,prod=P`;
2. the bare prefixes of the letter rule (the application code, `RQ_`, `RC_`) and which of
   them carry the letter on their first token only (`--leading-only RQ_,RC_`: resources such
   as `URQ_P77_AGGREGATION`);
3. which environment is production (default `prod`).

### 2. Production first: it is the trunk

```bash
mkdir chains && cd chains && git init -b main
ctmchain init --application <APP> --envs test=T,uat=U,bench=B,prod=P \
    --prefixes P77,RQ_,RC_ --leading-only RQ_,RC_
ctmchain import ../exports/prod/<prod>.xml --env prod --dedupe-jobnames
ctmchain export --env prod --jobnames original -o /tmp/prod-check.xml
cmp /tmp/prod-check.xml ../exports/prod/<prod>.xml && echo "prod: byte for byte"
git add -A && git commit -m "chore: production baseline"
```

This first commit is the only one made on `main` by hand: from now on `main` mirrors
production and every change goes through a release.

### 3. The values of the other environments, one release

The full exports of the other environments also carry the releases that are installed there
but not in production yet. Take only their *values* from them (machines, users, mails, the
environment's name in texts, variables): the jobs stay as production has them, and the
releases come later from their deliveries (step 6).

```bash
ctmchain release start environments
ctmchain receive ../exports/uat/<uat>.xml --values-only   # preview: the decisions
```

Read the decisions with the person, by section, before `--apply`:

- **groups** (a machine, user, mail or variable, or the environment's name in a text): a new
  constant with a value per environment. Give them readable names with
  `--choose 'group:...=new:<name>'`, or in the *Import* page of `ctmchain serve` (box *Only
  the values of <env>*).
- everything else is left out by default: changes of jobs (**differences**, **children**),
  jobs the environment lacks (**removed**: kept) and folders or jobs only it has
  (**added**: left out). A difference the person knows is the environment's own (a job that
  is Dummy there, another command line) may be made an **exception** instead.

Then `--apply`, look at `ctmchain export --env uat`, and commit. Same for bench and test (they
only learn the values of the constants that exist by now). Production is untouched:
`ctmchain export --env prod --jobnames original` is still byte for byte the prod export.

### 4. The conventions agreed for these chains

- **Machines**: neutral names by order, `node.bat1` (first) and `node.bat2` (second); each
  environment has its own machines behind them.
- **Users**: `user.<role>_user_proc`, e.g. `user.batch_user_proc`, `user.per_user_proc`. A
  value that fits none: ask whether it is an existing one (`use:<name>`) or a new one (e.g.
  `user.lala_user_proc`).
- **Mails, transfer (CFT) settings, variables such as the environment code**: one value per
  environment (a constant), which a single job may still change (an exception).
- **Time windows, MAXWAIT, calendars, file age limits**: the same everywhere; a difference is
  an exception for that job, after asking.
- **TASKTYPE Dummy, another CMDLINE in one environment**: exceptions of that environment.
- **Dirty names** (another environment's letter in a condition, a resource of another
  environment, a letter in place of the application's first letter): not fixed on the way
  in. `ctmchain validate` lists them with suggested fixes, to correct in later releases.

### 5. Close the environments release

```bash
ctmchain release installed prod     # nothing to install: it only describes the environments
ctmchain release close
```

### 6. The releases already on their way, from their deliveries

For each release installed somewhere but not in production yet, ask, numbered: its name,
the delivery XML of each of its parts, and the environments it is installed in. Then, from
`main`, one release each:

```bash
ctmchain release start <name>
ctmchain receive ../exports/deliveries/<name>.xml --stat   # a delivery: its differences
ctmchain receive ../exports/deliveries/<name>.xml --apply  # are the release's changes
ctmchain commit -m "feat: release <name>"
ctmchain release installed uat                             # each environment it is in
```

A folder two releases both changed comes whole in each delivery: when the first one is closed
into `main`, *Update from main* in the other merges them. Check each release with
`ctmchain receive ../exports/<env>/<env>.xml` (preview only) on the release branch: what is
left is what differs for another reason (often conditions whose names differ per
environment).

Then the everyday flow of the data repository's own `CLAUDE.md` (written by `init`):
deliveries through `ctmchain receive`, a full prod export now and then to catch up with
production, releases installed environment by environment.
