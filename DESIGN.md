# controlm-chain-admin — design

Status: draft agreed in the design conversation of 2026-11-01. Everything here is a decision
unless it is listed under *Open questions*. All examples are synthetic (fictional application
`P77`, fictional hosts and addresses); no real export data is ever committed to this repository.

## 1. Purpose and scope

BMC Control-M job chains are hard to manage through the Control-M UI and its XML export
(`DEFTABLE` / `Folder.xsd`). `controlm-chain-admin` keeps the definitions of a chain in a
**git-friendly JSON repository**, converts **XML → JSON** (import) and **JSON → XML** (export, one
XML per target environment), treats IN/OUT conditions as **links between nodes**, validates the
graph, compares sources, and performs safe **refactorings**.

Scope of the first version: one application (`APPLICATION` is a literal, it carries no
environment letter). Other applications found in the same export are skipped and reported; each
may later become a separate chain with its own rules.

## 2. Concepts

| Term | Meaning |
|---|---|
| Chain repository | A git repository holding the **base** (environment-neutral definitions) plus one small directory per **environment**. |
| Base | The JSON definitions, written from a reference environment (the first one imported) with every environment-specific value replaced by a token, a constant or an override. |
| Environment | A Control-M datacenter (test, uat, bench, prod…). Identified by a letter (`T`, `U`, `B`, `P`) that appears as a prefix in names, and by a display name (`UAT`…). |
| Node | A folder or a job. Identity: `FOLDER/JOB`, both without the environment letter. Control-M allows the same JOBNAME twice in a folder (the real export has 3 cases): the second occurrence gets the file id `JOBNAME~2`, and so on; the `JOBNAME` attribute keeps the real name. |
| Link | A dependency edge: producer node OUTCOND `+` → consumer node INCOND with the same condition name. |
| Constant | A logical value `@{group.name}` resolved per environment (hosts, users, mail recipients, CFT partners). |
| Override | A per-job, per-environment replacement of whole attribute values or job variable values. |

## 3. Repository layout

```text
chain.json                        # chain-level rules: application, token rules, policies
folders/
  P77_INGEST_DAILY/
    folder.json                   # SMART_FOLDER functional attributes + folder-level variables,
                                  # calendars, controls, ON blocks
    links.json                    # edges consumed by this folder or its jobs
    jobs/
      P77_INGEST_INIT.json        # one file per job
      P77_INGEST_LOAD.json
meta/
  folders/P77_INGEST_DAILY.json   # volatile export metadata (sidecar), never needed to review
envs/
  uat/env.json                    # letter, display name, constants
  uat/overrides.json              # per-job whole-value overrides, `envs` exceptions
  prod/env.json
  prod/overrides.json
reports/                          # import/validate reports (git-ignored or committed, user choice)
```

One file per job keeps `git mv` and per-job history meaningful; a sub-application rename touches
one line per job; a job move is a rename plus two `links.json` edits.

## 4. JSON model

### 4.1 Rules common to every file

- Keys follow a fixed order per element type (the export attribute order), so files are stable
  and diffs show only real changes. Arrays keep document order.
- Names in **whitelisted attributes** are stored **without the environment letter**:
  `P77_INGEST_INIT`, `RQ_AM`, `RC_INIT` (export writes `UP77_INGEST_INIT`, `URQ_AM`, `URC_INIT`
  for `uat`). Whitelist: `FOLDER_NAME`, `JOBNAME`, `MEMNAME`, `PARENT_FOLDER`,
  `SUB_APPLICATION`, condition `NAME` (INCOND, OUTCOND, DOCOND), `QUANTITATIVE/@NAME`,
  `CONTROL/@NAME`, `RULE_BASED_CALENDAR(S)/@NAME`.
- The letter rule is **pattern-based, not attribute-wide**: import strips the letter only from
  values matching `^[LETTERS](P77|RQ|RC)` (the bare prefixes are configured in `chain.json`);
  export prepends the letter only to values that start with a bare prefix. Values that match
  neither (a calendar `*`, a script-like `MEMNAME`, a condition name without the prefix) are
  stored and exported as they are, in every environment, with no marker.
- The only ambiguous case is a value that already starts with a bare prefix in the source
  (`P77STOCKSERVICE` with no letter): import writes it as `literal:P77STOCKSERVICE` so export
  does not add a letter. Import lists every `literal:` mark in the report.
- Resource names carry the letter on their first prefix only (`letter_rule.leading_only` in
  `chain.json`, e.g. `["RQ_", "RC_"]`): `URQ_P77_AGGREGATION` is stored as
  `RQ_P77_AGGREGATION`, with the inner bare application code untouched, and exported as
  `PRQ_P77_AGGREGATION`; a resource of another environment (`TRQ_AM` in a UAT export) is kept
  and reported.
- `MEMNAME` therefore behaves as the author asked: usually equal to `JOBNAME` and adjusted with
  it; when it has the `xP77` pattern it is adjusted too; otherwise it stays identical in all
  environments.
- Table-driven values are constants: `"NODEID": "@{node.batch}"`, `"RUN_AS": "@{user.proc}"`,
  `"DEST": "@{mail.ops}"`, `"%%CFT_DIRS": "@{cft.dirs_main}"`.
- Regular text tokens: `{ENV}` (display name, used in DOMAIL `SUBJECT`/`MESSAGE`), `{e}`
  (lower-case letter, used in the variable `%%GEIENV`).
- Any element (job, ON block, DO* element) may carry `"envs": ["bench", "prod"]`; export omits
  it in the other environments.

### 4.2 Job file (example)

```json
{
  "JOBNAME": "P77_INGEST_LOAD",
  "MEMNAME": "P77_INGEST_LOAD",
  "SUB_APPLICATION": "P77_BATCH",
  "APPLICATION": "P77_RISK_ENGINE",
  "DESCRIPTION": "Load daily positions",
  "TASKTYPE": "Command",
  "NODEID": "@{node.batch}",
  "RUN_AS": "@{user.proc}",
  "CMDLINE": "/%%NODEID/appli/%%APPLI/bin/load.ksh -d %%ODATE",
  "VARIABLES": [{"NAME": "%%APPLI", "VALUE": "risk"}, {"NAME": "%%GEIENV", "VALUE": "{e}"}],
  "QUANTITATIVE": [{"NAME": "RQ_AM", "QUANT": "1", "ONFAIL": "R", "ONOK": "R"}],
  "RULE_BASED_CALENDARS": [{"NAME": "P77_DAILY"}],
  "ON": [
    {"STMT": "*", "CODE": "NOTOK", "DO": [
      {"DOMAIL": {"URGENCY": "R", "DEST": "@{mail.ops}", "CC_DEST": "@{mail.cc}",
                  "SUBJECT": "[P77][CTRLM][{ENV}] Load job failed", "MESSAGE": "Job %%JOBNAME failed on %%NODEID",
                  "ATTACH_SYSOUT": "Y"}, "envs": ["bench", "prod"]}
    ]}
  ]
}
```

Attributes not listed here are kept as plain strings under their XML names; nothing is dropped.
`JOBISN`, `CREATION_*`, `CHANGE_*`, `VERSION*`, `LAST_UPLOAD`, `REAL_FOLDER_ID`, `MODIFIED`,
`FOLDER_ORDER_METHOD`, `DATACENTER` live in the `meta/` sidecar and are regenerated on export
(defaults for new jobs).

### 4.3 Links file

**Status (2026-11-01, slice 2).** Links are the source of truth for condition names. Every
INCOND / OUTCOND / DOCOND on a node carries `"link": "<id>"` instead of `NAME`, where the id is
the condition name as first imported (environment-neutral). The export name lives in
`folders/<F>/links.json` of the link's home folder (first consumer, else producer, else
deleter): `{"links": {"<id>": {"name": "<export name>"}}}`. Renaming a condition is one edit;
renaming or moving jobs never touches names. `folders/<F>/index.json` is the **derived** view
(`{"derived": true, "links": [{"id", "name", "standard", "from", "to", "cleanup", "docond",
"odates", "and_or", "kind", "external"}]}`, `kind` in `edge | fan_in | dangling | unconsumed |
delete_only`) rebuilt on import and read by `validate`, `graph`, `links` and the web UI.
`export --names standard` derives `<PRODUCER>-<CONSUMER>_OK` for links with exactly one producer
and one consumer; two distinct links that would collide get the producer's folder as prefix
(`<FOLDER>_<P>-<C>_OK`); a condition shared by several folders is one link (fan-in/fan-out) and a
name policy never splits it — that is a refactoring. The richer per-endpoint shape below remains
the long-term goal.

```json
{
  "links": [
    {
      "from": "P77_INGEST_DAILY/P77_INGEST_INIT",
      "to":   "P77_INGEST_DAILY/P77_INGEST_LOAD",
      "name": "P77_INGEST_INIT-P77_INGEST_LOAD_OK",
      "odate": "ODAT", "and_or": "A",
      "cleanup": ["to"],
      "docond": [{"node": "P77_INGEST_DAILY/P77_INGEST_INIT", "on": "COMPSTAT EQ 0", "sign": "+"}]
    },
    {
      "from": "P77_PRICING/", "to": "P77_INGEST_DAILY/",
      "name": "P77_PRICING-P77_INGEST_DAILY_OK", "odate": "ODAT", "and_or": "A", "cleanup": ["to"]
    },
    {
      "from": null, "to": "P77_INGEST_DAILY/P77_INGEST_LOAD",
      "name": "literal:EXT_FEED_READY", "odate": "ODAT", "and_or": "A", "external": true
    }
  ]
}
```

- A node reference ending in `/` is the folder itself (folder-level INCOND/OUTCOND, the normal
  way folders chain to each other).
- `cleanup` lists who emits the OUTCOND `SIGN="-"` for this condition (normally the consumer).
- `docond` records conditional add/remove of the same condition inside ON blocks, so a rename
  propagates to them.
- `external: true` marks a link whose other end is not in the repository (producer or consumer
  missing). Its name is never changed by any policy.
- Anything that does not fit an edge (N→N names, a name only ever deleted, garbage names) is
  kept as a raw condition on the node with `"raw": true`, so nothing is lost.

## 5. Environment model

`envs/<env>/env.json`:

```json
{
  "letter": "P", "name": "PROD",
  "constants": {
    "node.batch": "PP77_BATCH", "node.bat1": "srvp-p77-bat1",
    "user.proc": "app77proc", "user.proc_perturb": "app77procperturb",
    "mail.ops": "ops_it@example.com", "mail.cc": "",
    "cft.dirs_main": "xfer_prod_user@xfer-prod-host:Appli/NXP77"
  }
}
```

`envs/<env>/overrides.json` (whole values, never fragments):

```json
{
  "P77_INGEST_DAILY/P77_INGEST_LOAD": {
    "set": {"CMDLINE": "/%%NODEID/appli/%%APPLI/bin/load.ksh -d %%ODATE --server ALPP7701"},
    "variables": {"%%DATASERVER": "ALPP7701"},
    "base_hash": {"CMDLINE": "3f9c1a…"}
  }
}
```

Resolution order at export, per attribute: **override → constant/token → base value**.
An unresolved constant or token is an export **error** (flag `--allow-unresolved` turns it into
a warning). `base_hash` is the hash of the base value when the override was created; `validate`
warns when the base changed since (possible stale override).

### What can vary per environment

Every attribute of a job or folder, every variable value and every sub-element can differ per
environment, through exactly one of three means:

1. **Constant** `@{name}` with explicit values per environment (optional `pattern` sugar), for
   any attribute whose value repeats across nodes: `NODEID`, `RUN_AS`, `DEST`, variable values…
2. **Override** in `envs/<env>/overrides.json`, whole literal values, for one node: any `JOB` or
   `SMART_FOLDER` attribute under `set`, variable values under `variables`.
3. **Variants** for sub-elements (ON blocks, DO* actions, QUANTITATIVE, calendars…): the element
   is written once per variant with an `envs` list, and export keeps the variant of the target
   environment. No path-addressing of sub-elements is needed.

**Names are the exception.** `JOBNAME`, `FOLDER_NAME`, `SUB_APPLICATION`, `PARENT_FOLDER` and the
other whitelisted name attributes are never constants: they are the same in every environment apart
from the letter, which the letter rule adds on export. When a job really has a different name in
one environment, that is an override of `JOBNAME` for that environment, taken literally, with no
letter processing. The repository identity stays the base name; condition names derived at
export (`--names standard`) use the resolved name of that environment.

Import of a second environment into an existing repository aligns nodes by their neutral
identity and proposes, for every differing value: a constant when the old→new pair repeats
consistently, an override when it is specific to one job, and an `envs` exception when an
element exists only on one side. It runs as a dry-run report first.

## 6. Import

- Lossless by default: re-importing the XML produced by `export` yields no changes
  (idempotency test).
- Partial exports (some folders only, as a team delivers a changed or new folder) import the
  same way: only their folders are rewritten, new folders are appended to the export order, and
  the header of the last full export (declaration, *Exported at* comment, line endings) is
  kept. Line endings are recorded (`newline` in `meta/export.json`, `\r\n` for exports saved
  on Windows) and written back on export.
- Policies are opt-in flags and every applied action is written to the report:
  `--application P77_RISK_ENGINE` (skip and report other applications), `--env uat`
  (tokenise the letter, derive constants), `--dedupe-jobnames` (duplicate JOBNAMEs across
  folders get a numeric suffix: `JOBX`, `JOBX2`, `JOBX3`; the original name is kept in `meta`
  and may be restored on export with `--jobnames original`), `--standardize-names` (see §7).
- Constants are derived automatically (`UP77_BATCH` → `node.batch`, `srvu-p77-bat1` →
  `node.bat1`, `aup77proc` → `user.proc`, mail local part → `mail.<local>`) and written to the
  environment file; the report lists the table for renaming.
- Report in Markdown and JSON with the same content; exit code reflects the highest severity.
  Content: duplicates renamed; INCOND without producer; OUTCOND never consumed; INCOND nobody
  deletes; stale names (embedded job names that are no longer the real endpoints); names outside
  the `A-B_OK` pattern; N→N edges; edges produced only by DOCOND; `literal:` marks; values that
  look environment-specific but match no rule (candidates for the user to classify once in
  `chain.json`); encoding losses already present in the export (`?` for accented letters).

## 7. Export

- `ctmchain export --env prod out.xml`. The file is byte-identical to the source export for
  untouched content: same declaration, exported-at comment, 4-space indentation, self-closing
  tags written as `<X ... />`, fixed attribute order per element type, same escaping. This was
  verified on a real slice with a stdlib prototype (XML → JSON → XML, identical bytes, also with
  attributes re-sorted into the fixed per-tag order).
- Condition names: `--names original` (default) or `--names standard`. Standard pattern:
  `<PRODUCER>-<CONSUMER>_OK`; when the pair of JOBNAMEs is not unique across folders the folder
  is added as a discriminator; `external` links are never renamed; `literal:` names are kept.
- `--jobnames deduped|original` chooses whether deduplicated jobs are exported with the numbered
  name (default, the repository content) or with the original one.
- Deduplication details (implemented): the first occurrence in export order keeps its name,
  later ones get `NAME2`, `NAME3`… skipping suffixes already used by real jobs; only `JOBNAME`
  changes (`MEMNAME` and condition names do not); the original lives in
  `meta/folders/<F>.json` under `original_jobnames`; the policy is recorded in `chain.json`
  (`dedupe_jobnames`) so later imports apply it. On the real export it renames 119 jobs and
  removes all 100 standard-name collisions.

## 8. Validate, diff, show

- `validate`: everything listed for the import report, plus unresolved constants/tokens per
  environment, overrides pointing to missing jobs, stale overrides (`base_hash`), links whose
  endpoints do not exist.
- `resolve [CODE=KIND...]` (implemented 2026-11-02): fixes for validation findings. Each finding
  gets its fixes as data (an operation of the change-set registry with its parameters, a kind
  shared by every finding, a label with the names, an explanation): `dangling` → the job the name
  points to emits it (`emit`) or the consumer stops waiting (`stop-waiting`); `dangling-unknown`
  and `dangling-external` → stop waiting (external: only if the producer is gone); `unconsumed`
  → the job the name points to waits for it (`wait`) or the producer stops emitting
  (`stop-emitting`); `unconsumed-external` → stop emitting; `never-cleaned` → the consumer
  deletes it after use (`add-cleanup`); `stale-name` and `non-standard-name` → the standard name
  when it is unambiguous (`standard-name`, folder-prefixed `F_A-B_OK` included, which validate
  accepts as standard); `duplicate-jobname` → number the copies (`number-copies`, the JOBNAME changes in
  Control-M). Without arguments it lists the kinds per code; `CODE=KIND` previews one change for
  every finding of the code with exactly one fix of that kind, `--apply` writes it. Several fixes
  run as one `batch` operation: each step runs in place in one sandbox, the diff is computed
  once (94 fixes on the real chain: ~12 s).
- `diff A B`: plain `git diff` of the base is the first-class review tool. For XML↔XML semantic
  comparison the tool depends on `xmldiffreport` (key-aligned, N-way, Markdown/HTML report).
- `show --envs <node>`: the node resolved in every environment, side by side, differences
  highlighted.
- `compare <base> [<head>]` (implemented 2026-11-02): what a branch changed in the chain, in the
  terms of the chain and not of the JSON files. Both refs are read with `git archive` into a
  temporary directory (the working tree is never touched; `--worktree` or the `WORKTREE` ref use
  the uncommitted files). By default the base side is the merge base of the two refs, as in a
  pull request, so changes made on develop after the branch started are not shown;
  `--no-merge-base` compares the two tips. The result lists, per folder and job, the kind of
  change (added, removed, modified, renamed, moved, with the previous identity), attribute and
  variable values before and after, predecessor and successor changes with their details
  (AND_OR, ODATE, `+` emission, `−` cleanup, peers before and after), other changed groups and a
  JSON diff; then conditions added, removed or renamed, constant values per environment, and the
  commits. Renames are matched by content (a job renamed or moved keeps its body or its links; a
  folder keeps its body or most of its jobs), and effects of a rename elsewhere (peers,
  `PARENT_FOLDER`, the folder's job list) are not reported twice. Volatile metadata alone is only
  counted (`metadata_files_changed`). Output: text, Markdown (for a pull request description) or
  JSON; the web UI shows the same structure.
  `--commit <sha>` (repeatable) compares only some commits of the branch (implemented
  2026-11-02): they are applied on the base side in their order, cherry-pick style, file by file
  and in memory (a change is taken as it is when the file is as the commit found it, merged three
  ways with `git merge-file` when a left-out commit changed other lines, refused when they
  overlap or the file is missing). A refusal names the commit and the left-out commits that
  touched the same files before it (`SelectionConflict`). Merge commits cannot be selected and
  are skipped. Every change lists the commits that touched its files.
- `package <base> [<head>] --env <env>` (implemented 2026-11-02): the Control-M import file with
  every folder the comparison changed, whole (Control-M imports folders, not jobs). A folder is
  packaged when a job in it was added, removed, edited, renamed or moved in or out, when its own
  attributes or job order changed, when a condition one of its nodes uses was renamed, or when a
  constant it uses got another value in the target environment. A job whose only change is seen
  from the other end of a relation (its own file is unchanged) does not pull its folder in; nor
  does volatile metadata. The file is the regular export of those folders for the environment:
  letter rule and constants resolved, original JOBNAMEs (`--jobnames original` by default),
  unresolved constants refuse the package. Each folder comes with its reasons; warnings cover
  what an import cannot do (a removed or renamed folder stays in Control-M, a folder left
  without jobs is emptied), uncommitted changes, `chain.json` rule changes, and packaged folders
  that the base changed after the branch started (the package would undo them: merge first).
  Validation findings the head side has and the base has not are listed. The same `--commit`
  selection applies.
- Releases (implemented 2026-11-02, asked by the author: "work only with the trunk, tags and
  release branches; forbid edits on main"). One trunk (`main`) mirrors production and is never
  edited, nor any other protected branch nor a detached HEAD: applying a change set (CLI
  `--apply` and `POST /api/changes/apply`) and committing are refused there (`ProtectedBranch`);
  a commit can still go to a new branch. Work happens on a release branch `release/<name>`,
  always started from the trunk; it is committed, packaged against the trunk, installed in one
  environment after the other, and each installation is recorded as an annotated tag
  `<env>/<name>-<n>` on the installed commit (`ctmchain release installed <env>`). A later
  change after an installation is a new commit on the same release; the package for that
  environment can then hold only the folders changed since its last tag (base = the tag) or the
  whole release. Once the last commit is installed in production, *closing* merges the release
  into the trunk (one merge commit, without checking the trunk out, the tags listed in the
  message) and deletes the branch; closing is refused while the trunk has commits the release
  lacks: *update* merges the trunk into the release first (a conflict aborts and names the
  files), and the merged commit is installed again. Starting or switching with uncommitted chain
  files is refused unless they are stashed first (`git stash` of the chain paths, untracked
  files included); a stash is restored on an editable branch, and a stash that no longer applies
  changes nothing and is kept. *Discard* restores the chain files of HEAD after the same
  fingerprint check as a commit. *Push* sends the branch and its installation tags
  (`--follow-tags`, upstream set on the first push) and, from the trunk, deletes the remote
  branches of closed releases; *pull* fetches with tags and prunes, then fast-forwards the branch
  and the trunk only. Network commands never prompt (`GIT_TERMINAL_PROMPT=0`, ssh in batch mode)
  and give up after 120 s. The names come from the `git` key of `chain.json`, all optional:
  `{"trunk": "main", "protected": ["main", "master"], "release_prefix": "release/",
  "tag_format": "{env}/{release}-{n}", "production": "prod", "remote": "origin"}`.

## 9. Refactorings (change-set with preview)

Implemented (2026-11-01) in `core/refactor.py`, all through the same engine: the refactoring
runs on a temporary copy of the tracked files (`chain.json`, `meta/`, `folders/` without the
derived `index.json`), `links.json` is recomputed there, and the change set is the diff of the two
trees. The CLI prints the summary, warnings and a unified diff (`--stat` for the file list,
`--format json` for tools) and writes only with `--apply`. `apply` refuses when any file changed
since the preview, stages every write before replacing, prunes emptied folder directories and
rebuilds `index.json`. On the real repository a preview takes about 1 s.

| Command | What it changes |
|---|---|
| `rename-job F/J NEW [--keep-names] [--with-memname]` | job file, `folder.json` order, metadata; condition names whose dash-separated parts embed the old name follow (`A-B_OK`, `A-TO-B`, `A-B_OK-U26`); MEMNAME only with the flag; an explicit rename drops the deduplication original |
| `rename-folder F NEW [--keep-names]` | directory, `FOLDER_NAME`/`JOBNAME`/`PARENT_FOLDER`, every job's `PARENT_FOLDER`, metadata file, folder order; names of folder-level conditions follow |
| `rename-subapp OLD NEW [--folder F]` | `SUB_APPLICATION` on the folder and jobs that carry it |
| `move-job F/J TARGET` | job file and metadata move, `PARENT_FOLDER`, both folder lists; links travel with the job and their home follows the consumer; warns when the sub-application differs |
| `insert-job F/NEW --after F/A --before F/B [--like F/J] [--link ID]` | the A→B link now ends at NEW (its name follows when it embeds B); a new link `NEW-B_OK` takes NEW to B, which now waits for and cleans it up; `--like` clones a job without its conditions; otherwise a minimal Dummy |
| `extract-variable F/J\|F/ --literal V --as %%NAME [--attribute CMDLINE]` | replaces the literal by the variable and adds `VARIABLE NAME=%%NAME VALUE=V` to each job; refuses a variable already defined with another value |

Names given to refactorings are environment-neutral; a name that looks lettered, or that lacks a
prefix of the letter rule, produces a warning. Renaming a job or folder and renaming it back
restores the export byte for byte (verified on the real export). Not yet: `remove-job`, `link`,
`unlink`, and the same change sets through the web API (preview → apply endpoints).

## 10. Packaging and interface

- Python ≥ 3.11, stdlib-only core, hatchling, `src/` layout, ruff + mypy + pytest, bilingual
  mkdocs, Trusted Publishing release on `v*` tags (same house style as `xmldiffreport`).
- PyPI name `controlm-chain-admin`, CLI command `ctmchain`.
- Phase 1 is the CLI over JSON in git. Phase 2 is an optional `[web]` extra: a local web UI
  (see §11), read-only first, then the mapping editor, then editing. CSV/Excel is not planned.
- Test fixtures are synthetic, generated by a script that mimics the measured distributions
  (linear chains, one `NOTOK` ON block per job, 2–4 quantitative resources, ~85 % of names in
  the `A-B_OK` pattern, a few stale/dangling cases).

## 11. Architecture: one core, two adapters

All logic, including every mutation, lives in the `core` package (stdlib only). The CLI and the
web API are thin adapters that translate input and output; neither contains business rules.

```python
# controlm_chain_admin/core/ops.py
@dataclass(frozen=True)
class ChangeSet:
    summary: str
    file_edits: list[FileEdit]        # path, before, after
    affected_links: list[LinkRef]
    warnings: list[str]

def rename_job(repo: ChainRepo, node: NodeRef, new_name: str, *, names: NamePolicy) -> ChangeSet:
    """Compute every edit needed to rename a job; writes nothing."""

def apply(repo: ChainRepo, change: ChangeSet) -> ApplyResult:
    """Write the edits atomically (all files or none) and reload the affected nodes."""
```

```python
# cli.py — print the preview, write only with --apply
change = ops.rename_job(repo, NodeRef.parse(args.node), args.new_name, names=args.names)
print(render(change, args.format))
if args.apply:
    ops.apply(repo, change)

# web/api.py — the UI shows the same preview, then calls /changes/apply
@router.post("/jobs/{node}/rename")
def rename_job(node: str, body: RenameBody, repo: ChainRepo = Depends(get_repo)) -> ChangeSet:
    return ops.rename_job(repo, NodeRef.parse(node), body.new_name, names=body.names)
```

Consequences:
- Each operation (`import_xml`, `export_xml`, `validate`, `rename_job`, `move_job`, …) is
  implemented once and unit-tested on the core without CLI or HTTP.
- Preview and apply are identical on both sides: what the UI shows is what the CLI would do.
- The core raises typed errors (`UnresolvedConstant`, `DanglingLink`, `NameCollision`); the CLI
  maps them to exit codes, the API to HTTP status codes, with the same message.
- The core returns serialisable structures (reports, change-sets, resolved nodes), never
  formatted text; rendering belongs to the adapters.

Server-side concerns (not in the core):
1. State: the CLI loads the repository per invocation; the server keeps a `ChainRepo` in memory
   and reloads what changed when files are modified from outside (editor, `git checkout`),
   checking directory mtimes / git HEAD per request.
2. One writer at a time: a lock around `apply`; `apply` writes all files or none.
3. Local only: bound to `127.0.0.1`; mutating endpoints require a token generated by
   `ctmchain serve` and placed in the opened URL, so that another website open in the browser
   cannot POST to the local server.

### Web UI

- Backend: FastAPI + uvicorn, calling the core directly (never the CLI by subprocess), shipped in
  the `[web]` extra. `ctmchain serve --repo <dir>` starts it and opens the browser.
- Frontend: Vite + React + TypeScript + Tailwind, in `web/` of this repository. React Flow
  (xyflow) with dagre layout for chain graphs; TanStack Query; a Monaco-style diff viewer later.
  PoC status: design tokens in `index.css` and a few hand-written primitives (`components/ui.tsx`)
  instead of shadcn/ui, which comes in with the editing forms; API types generated from the
  OpenAPI snapshot (`npm run gen:api`); MSW fixtures dumped from the real API on the synthetic
  repository (`web/scripts/dump_fixtures.py`).
  Built assets are produced in the release workflow and included in the wheel; `web/dist/` is
  git-ignored; in development Vite proxies `/api` to FastAPI. Users never need Node.
- Not chosen: Next.js (a second server, or a static export that offers nothing over Vite),
  HTMX + Jinja (graph and mapping editor need client state), a separate frontend repository.
- Milestones: (1) read-only — folder list with search, folder graph with edge inspector
  (condition name, ODATE, cleanup, external), job detail with attributes grouped (identity,
  scheduling, execution, notifications) and one column per environment with resolved values,
  validate report, diff between refs or environments; (2) mapping editor — the `distinct` table
  with one input column per environment, overrides, missing constants; (3) editing — job forms
  with change-set preview, refactorings, git bar (branch, status, commit).
- Scale is comfortable: the largest folder measured has ~52 nodes / 63 edges; the folder-level
  graph has 339 nodes / 452 edges.
- **Editing (implemented 2026-11-01).** Home page is the *Chains* table: one row per folder
  (collapsible) and per job, with application, sub-application, folder, job, type, predecessors
  and successors; external ends are shown as such; the filter opens the folders whose jobs match.
  Folder and job pages have tabs (attribute groups, variables, predecessors & successors, ON
  blocks, metadata, raw JSON; the folder page also has the chain graph and its jobs). The
  predecessors & successors tab keeps the Control-M details per relation: the producer's `+`
  (static or from an ON block), the consumer's AND_OR, the ODATE, and the consumer's cleanup `−`;
  it adds (new link or wait for an existing condition), removes, renames conditions and changes
  AND_OR / ODATE / cleanup. Every edit is a core operation (`refactor.run_operation`: set-attributes,
  set-variables, replace-node, link, unlink, update-relation, rename-link and the refactorings)
  previewed with `POST /api/changes/preview` (summary, warnings, files, diff, fingerprint) and
  written with `POST /api/changes/apply`, which recomputes the change and refuses it (409) when the
  fingerprint no longer matches. Both need the session token generated by `ctmchain serve` and
  passed once in the URL it opens (`?token=…`, kept in sessionStorage); the server only accepts
  its own Host names. `GET /api/table` builds the table in ~0.2 s on the real repository.
- **Compare (implemented 2026-11-02).** The *Compare* page answers "what did this branch change,
  how was it and how is it now". The header picks the base and head refs (branches, tags, remote
  branches and the working tree; by default the trunk, against the checked-out branch)
  and the merge-base option; the choice lives in the URL so a comparison can be shared. Summary
  cards count folders, jobs, conditions, relations and constants. The *Folders & jobs* tab lists
  the changed nodes grouped by folder, with a badge per kind of change and filters by kind; the
  detail of the selected node shows the previous identity, an attributes table and a variables
  table (name, before, after), the predecessor and successor changes with peers before and after
  and the `+`/`−`, AND_OR and ODATE details, and the JSON diff, with a link to open the node.
  Other tabs list the conditions and the constants per environment. Above them, the commits of
  head have a checkbox each, all checked by default: unchecking some compares only the others
  (`commits=` in the URL and the API), the detail of a node lists the commits that changed it,
  and a selection that needs a left-out commit says which one, with a button to include it.
  *Generate XML* with an environment picker (uat by default) opens the package preview: folders,
  jobs per folder, reasons, warnings and new validation findings, then the download. Read-only,
  no token needed: `GET /api/git` (refs, current branch, dirty flag),
  `GET /api/compare?base=&head=&merge_base=&commits=`, `GET /api/package?…&env=` and
  `GET /api/package/xml?…` (cached per pair of commits and options; the working tree is never
  cached). *Copy Markdown* copies `GET /api/compare/markdown` (the `--format md` report, left-out
  commits marked) for a pull request description.

- **Validation (resolving, implemented 2026-11-02).** The findings table uses the whole width
  (condition or job, node and message stacked in one column, no horizontal scrolling), filters
  by severity and by type of problem, and every finding starts selected. *Resolve* on a row
  opens its fixes under it: one button per fix with its explanation, each opening the usual
  preview. *Resolve selected* groups the selection by type of problem and asks for one fix per
  type (or *leave as is*), showing how many findings it applies to; the result is one `batch`
  change, reviewed and applied like any other edit (session token). Each fix carries its
  effects (job, add/remove/change, element such as `OUTCOND A-B_OK SIGN="-"`, before and
  after), shown under every option and in the review dialog as *What will change*; rows are
  tinted on hover. Without a token in the tab, the review dialog asks for the URL printed by
  `ctmchain serve` (`CTMCHAIN_TOKEN` keeps the same token across restarts).
- **Commit (implemented 2026-11-02).** Applying a change writes files, it does not commit.
  The header shows *Commit (n)* with the uncommitted chain files (derived `index.json` left
  out); the dialog lists them and proposes the message (editable); on a read-only branch the
  commit goes to a new release branch named from the subject (`release/update-job-x-in-f`).
  The commit needs the session token and is refused when the files changed since the dialog
  opened.
- **Releases (implemented 2026-11-02).** The header shows the checked-out branch (*read-only*
  on the trunk) and opens the *Releases* dialog: the current branch and its uncommitted files
  (*Stash changes*, *Discard changes…* with a confirmation), *Update from main* and *Close
  release* (disabled with the reason until the last commit is installed in production), the
  trunk and every release with its latest installation per environment and how many commits
  behind it is, *Switch* (with uncommitted files it offers to stash them first), *Start
  release* from the trunk, the stashes with *Restore*, and *Push*/*Pull* with the counts. On a
  read-only branch a banner under the header, and the review dialog of every change, say why
  and offer the dialog; *Apply change* stays disabled. In the package preview, when the
  environment already has an earlier commit of the release, the panel first asks whether the
  file holds only what changed since that installation or the whole release; after the
  download, *Mark as installed in <env>* creates the tag. `GET /api/workspace` and
  `POST /api/workspace/{release,switch,stash,pop,discard,installed,update,close,push,pull}`
  (session token), each answering a message and the new state.

## 12. CLI reference (`ctmchain`)

Every writing command previews its change-set and writes only with `--apply` (import/export
excepted: they write their target but never touch the other side). Every command accepts
`--repo <dir>` (default: current directory) and `--format text|md|json` where a report is produced.

Repository lifecycle
- `init --repo <cloned-git-dir> --application <APP> --envs test,uat,bench,prod` — the git repository already exists (cloned by the user); `init` only adds `chain.json` (rules, whitelist, policies) and one `envs/<env>/` per declared environment.
- `distinct <ATTR>... [--xml <export.xml>] [--write <mappings.json>]` — distinct values of one or more attributes (e.g. `NODEID RUN_AS DOMAIL/@DEST VARIABLE/@VALUE`), with counts and sample nodes, read from an XML before import or from the repository after. `--write` produces a mapping draft to fill in.
- `map <ATTR|TAG/@ATTR|TAG[K=V]/@ATTR> <value> --as <name> (--pattern "<tpl>" | --value ENV=VALUE ... | --env <env>) [--inline]` — declare one constant: the base gets `@{name}` wherever `<value>` appears in the selected attribute, each environment gets its value. `--pattern` fills every environment from a template with `{L}` (upper letter) / `{l}` (lower letter), e.g. `"{L}P77_BATCH"`, `"a{l}p77proc"`; `--value` sets one environment explicitly (repeatable); `--env` says which environment `<value>` belongs to. `--inline` binds a token inside free text (e.g. `[UAT]` in `DOMAIL/@SUBJECT`). Unknown values stay `null` until provided; export to such an environment fails unless `--allow-unresolved`. Constants cannot be bound to attributes governed by the letter rule.
- `override <node> --env <env> <ATTR>=<value>... [--var %%NAME=value]` — per-job exception for one environment (whole values).
- `import <export.xml> --env <env> [--mappings <mappings.json>] [--application <APP>] [--dedupe-jobnames] [--standardize-names] [--dry-run]` — first import builds the base, applying the declared mappings; later imports of other environments learn constants/overrides. Always writes a report; values left unmapped in constant-bearing attributes are listed as to-dos.
- `export --env <env> -o <out.xml> [--names original|standard] [--jobnames original|deduped] [--folders ...] [--allow-unresolved]` — JSON → XML for one environment.

Mapping draft written by `distinct --write` and consumed by `import --mappings`:

```json
{
  "NODEID": {
    "UP77_BATCH":    {"count": 1160, "as": "node.batch", "pattern": "{L}P77_BATCH"},
    "srvu-p77-bat3": {"count": 12,   "as": "node.bat3",
                      "values": {"test": null, "uat": "srvu-p77-bat3", "bench": null, "prod": "srvp-p77-bat3"}}
  },
  "RUN_AS": {
    "aup77proc": {"count": 1479, "as": "userproc",
                  "values": {"test": "atp77proc", "uat": "aup77proc", "bench": "svc_bench_p77", "prod": "p77_prod_user"}},
    "root":      {"count": 3,    "as": null}
  }
}
```

Explicit `values` per environment is the general form and needs no regularity between
environments; `pattern` is optional sugar for values that only differ by the letter, and when
both are given `values` wins for the environments it lists. Constant names are free
(`userproc`, `node.batch`, …). `"as": null` keeps the value literal in every environment. The
same draft can be re-generated later against the repository to catch values that appeared after
the first import.

Quality
- `validate [--env <env>] [--strict]` — graph, naming, overlay and resolution checks; exit code = highest severity.
- `resolve [CODE=KIND...] [--apply] [--stat]` — implemented: fixes for the findings (see §8); without arguments, the fix kinds per code.
- `release status|start <name>|switch <branch>|installed <env>|update|close` — implemented: the release flow of §8 (`--stash` to stash uncommitted files first, `installed --release --commit` to tag another commit). Stash, discard, push and pull are plain git on the command line.
- `commit [-m <message>] [--branch <name>] [--dry-run]` — implemented: commits the chain files only (`chain.json`, `folders/`, `meta/`, `envs/`, with `git commit --only`, so other staged or untracked files are left alone). Without `-m` the message is suggested from the semantic comparison of HEAD with the working tree: a Conventional Commits subject (`feat` when jobs or folders are added, `refactor` for renames and moves only, `fix` otherwise; e.g. `fix: update job X in F`, `feat: add 1 job, rename 2 conditions, update 3 jobs`) and a body listing every change. A batch of fixes is one apply and one commit.

Inspection
- `ls folders|jobs|envs|constants [--filter <glob>]` — listings.
- `show <node> [--envs]` — one node fully resolved, optionally side by side per environment.
- `graph <folder|node> [--upstream|--downstream] [--depth n] [--format text|mermaid|dot]` — chain graph.
- `links <node> | links --name <condition>` — edges of a node, or who produces/consumes/deletes a name.

Comparison
- `compare <base> [<head>] [--worktree] [--no-merge-base] [--commit <sha>...] [--format text|md|json]` — implemented: semantic comparison of two git refs of the repository (see §8). `head` defaults to `HEAD`; `--worktree` compares `base` with the uncommitted files; `--commit` keeps only those commits of head.
- `package <base> [<head>] --env <env> [--commit <sha>...] [--worktree] [--no-merge-base] [--jobnames original|deduped] [--names original|standard] [-o <file>] [--dry-run] [--format text|json]` — implemented: the Control-M import file with every changed folder, whole, and why (see §8). Default file name `deploy_<env>_<head>[_<n>-of-<m>]_<date>.xml`.
- `diff <A> <B>` — planned: A and B may be repo directories, `env:<name>` resolved views or XML files; XML↔XML goes through `xmldiffreport`.

Refactorings
- Implemented: `rename-job`, `rename-folder`, `rename-subapp`, `move-job`, `insert-job`, `extract-variable` (see §9); deduplication and standard names are import/export policies (`--dedupe-jobnames`, `--names standard`). Planned: `remove-job`, `link`, `unlink`.
- `set --where <filter> <ATTR>=<value>...` — bulk attribute change on the nodes matching a filter (folder, sub-application, task type…).

Environments
- `env add <name> --letter <L> --display <NAME> [--from <env>]` — new environment file, constants copied as to-do.
- `env constants [--env <name>] [--missing]` — constant table, missing values per environment.

MVP (phase 1): `init`, `distinct`, `map`, `override`, `import`, `export`, `validate`, `show`,
`graph`, `diff`. Refactorings and `env` helpers follow once import/export is byte-identical on
the fixtures.

## 13. Open questions

1. Suffixes such as `-U26` in some condition names: environment marker or not? Not covered by
   the prefix rule; the report lists them.
2. Values in the UAT export that point to other environments (CFT partner of prod, `-env prod`
   flags, `prod_*` directories): bugs or deliberate? To be classified once in `chain.json`.
3. Whether `reports/` is committed or git-ignored (git-ignored in the data repository for now).
4. Inner-token ambiguity of the letter rule (found on real data, 113 values): a name such as
   `URQ_<APP>_AGGREGATION` has a lettered prefix *and* the bare application code as an inner
   token. Resolved 2026-11-02 with the author: resource prefixes are leading-only (see §4.1).
5. Values carrying another environment's letter in the UAT export (4): bug or intentional?
6. The CLI should swallow BrokenPipe when its output is piped into `head`.
