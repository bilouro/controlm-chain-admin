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
   .venv/bin/pip install -e ".[dev,web,mcp]"      # Windows: .venv\Scripts\pip ...
   ```

   In PowerShell on Windows (`tar` ships with Windows 10 and later):

   ```powershell
   py -m pip download controlm-chain-admin==<version> --no-deps --no-binary :all:
   tar -xzf controlm_chain_admin-<version>.tar.gz
   cd controlm_chain_admin-<version>
   git init -b main; git add -A; git commit -m "chore: controlm-chain-admin <version>"
   py -m venv .venv
   .venv\Scripts\python -m pip install -e ".[dev,web,mcp]"
   ```

   Only to use the tool, without adjusting it: `pip install "controlm-chain-admin[web,mcp]"`
   in a venv of its own (the README, *On Windows, from scratch*).

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
ctmchain check ../exports/prod/<prod>.xml --env prod   # "the same byte for byte", exit 0
git add -A && git commit -m "chore: production baseline"
```

This first commit is the only one made on `main` by hand: from now on `main` mirrors
production and every change goes through a release.

### 3. The other environments, one release

The full export of another environment says what that environment has: its machines, users
and mails (constants), and everything it has otherwise (its exceptions). Nothing of it changes
production by default.

```bash
ctmchain release start environments
ctmchain receive ../exports/uat/<uat>.xml   # preview: the decisions
```

Read the decisions with the person, by section, before `--apply`:

- **groups** (a machine, user, mail or variable, or the environment's name in a text): a new
  constant with a value per environment. Give them readable names with
  `--choose 'group:...=new:<name>'`, or in the *Import* page of `ctmchain serve`;
- a group that mixes things that are not alike (the sign of a condition, a text): *One by one*
  in the Import page (`--choose 'FOLDER/JOB@FIELD=exception'` in the CLI) decides each job
  apart from the group;
- **differences**: every other difference, attribute or line (a condition, a SHOUT, an action
  of an ON block, a variable only one side has), is an exception of the environment by
  default: the base stays, the environment keeps what it has. *Change the base* only for what
  the person knows production should get; *Ignore* only for noise (then consider
  `ctmchain technical --add NAME`, which stops comparing that attribute for good);
- jobs the environment lacks (**removed**: noted as not there) and folders or jobs only it has
  (**added**: only there). The folders and jobs of a release that production has not yet may
  be left out instead (*Leave out*) and come from their deliveries (step 6); either is fine,
  ask the person.

Then `--apply` and check, before the commit:

```bash
ctmchain check ../exports/uat/<uat>.xml --env uat     # counts per field, never values
ctmchain check ../exports/prod/<prod>.xml --env prod  # must still be "the same byte for byte"
```

The *repository vs uat* column is what the repository's uat export still differs in: with the
defaults it is 0 for every field, and the folders and jobs are all "in both" (what was left
out shows as "only in the export"). `--format json` names the nodes of a field that is not 0.
Report the counts to the person; if production is not byte for byte any more, stop and say so.
Then commit, and the same for bench and test. Receiving the same export again changes nothing;
when a release reaches production (step 6), the exceptions equal to the new base go by
themselves.

### 4. The conventions agreed for these chains

- **Machines**: neutral names by order, `node.bat1` (first) and `node.bat2` (second); each
  environment has its own machines behind them.
- **Users**: `user.<role>_user_proc`, e.g. `user.batch_user_proc`, `user.per_user_proc`. A
  value that fits none: ask whether it is an existing one (`use:<name>`) or a new one (e.g.
  `user.lala_user_proc`). A few jobs that run as another user in one environment only (the
  group's default is `exceptions`, since production's user is the same as everyone's): ask
  whether they are a role; `--choose 'group:RUN_AS=<prod>><env>=new:user.<role>_user_proc'`
  makes them a constant of their own, bound to those jobs.
- **A name with the letter inside a command line** (`-j UP77_LOAD`): an inline constant with
  the letter of each environment, by default when two jobs or more carry it (an exception of
  the one job otherwise); `new` makes it a constant anyway.
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

### 6. The releases already on their way

For each release installed somewhere but not in production yet, ask, numbered: its name, the
environments it is installed in, and what carries it: a delivery XML of its parts, or the full
export of an environment that has it whole (bench carries 26.6.3, uat 26.7.0...). Then, from
`main`, one release each.

From a delivery:

```bash
ctmchain release start <name>
ctmchain receive ../exports/deliveries/<name>.xml --stat   # a delivery: its differences
ctmchain receive ../exports/deliveries/<name>.xml --apply  # are the release's changes
ctmchain commit -m "feat: release <name>"
ctmchain release installed uat                             # each environment it is in
```

From a full export, in the *Import* page of `ctmchain serve` on the release branch: analyze
the export; its differences are *Already exceptions of <env>* (folded: *Show*); *All N:
Change the base* makes the base of the release take them, and *All N: Everywhere* in *Only in
this export* brings the jobs only it has; review, apply, commit, `release installed <env>`.
What the person knows is the environment's own (a Dummy job there) stays an exception.

A folder two releases both changed comes whole in each delivery: when the first one is closed
into `main`, *Update from main* in the other merges them. Check each release with
`ctmchain check ../exports/<env>/<env>.xml --env <env>` on the release branch (and
`ctmchain receive ../exports/<env>/<env>.xml`, preview only, for the decisions): what is left
is what differs for another reason (often conditions whose names differ per environment).

Then the everyday flow of the data repository's own `CLAUDE.md` (written by `init`):
deliveries through `ctmchain receive`, a full prod export now and then to catch up with
production, releases installed environment by environment.

## Part C — asking in plain words (Kilo)

When the person uses Kilo (with the model the company allows), once the data repository is
there:

1. In the data repository: `ctmchain kilo init --repo chains` (the code's venv active). It
   writes `.kilo/` at the top of the git repository: `kilo.json` (the server with this
   machine's Python and repository), the agent `controlm`, the skill `ctmchain` and
   `vocabulary.md`.
2. `kilo.json` holds paths of this machine: ask, numbered, whether to keep it out of git
   (`.kilo/kilo.json` in the data repository's `.gitignore`); the agent, the skill and the
   vocabulary may be committed for the team.
3. Fill `vocabulary.md` with the team's words (which attribute «servidor» or «agente» means,
   the nicknames of folders): it stays in the private data repository.
4. Open Kilo in the data repository with `kilo --agent controlm`; try a question («what does
   <job> wait for?»), then a change on a release branch: it previews field by field and asks
   before `ctmchain_apply`. Nothing is committed by the agent.
5. In the web UI: `ctmchain serve --assistant` (optionally `--assistant-model
   provider/model`; default: Kilo's own, the model the company set) starts Kilo with the
   server; *Assistant* in the header opens the conversation, and every change waits there for
   *Apply* or *Reject*. On Windows it starts `kilo.cmd` from the PATH; a Kilo elsewhere:
   `$env:CTMCHAIN_KILO = "C:\path\to\kilo.cmd"`.
6. `kilo mcp list` shows `ctmchain connected`; if not, run the command of `kilo.json` by hand
   (`<python> -m controlm_chain_admin mcp --repo <chains>`): it waits on stdin when it works.
