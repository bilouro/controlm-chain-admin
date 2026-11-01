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
- `--jobnames original|deduped` chooses whether deduplicated jobs are exported with the original
  or the numbered name.

## 8. Validate, diff, show

- `validate`: everything listed for the import report, plus unresolved constants/tokens per
  environment, overrides pointing to missing jobs, stale overrides (`base_hash`), links whose
  endpoints do not exist.
- `diff A B`: plain `git diff` of the base is the first-class review tool. For XML↔XML semantic
  comparison the tool depends on `xmldiffreport` (key-aligned, N-way, Markdown/HTML report).
- `show --envs <node>`: the node resolved in every environment, side by side, differences
  highlighted.

## 9. Refactorings (change-set with preview)

`rename-job`, `rename-subapp`, `rename-folder`, `move-job`, `insert-job` (re-link a chain
around a new node), `extract-variable` (move an environment-specific literal from a command into
a job variable), `dedupe-jobnames`. Each prints the change-set and the affected links before
writing; each propagates to condition names according to the name policy.

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

Inspection
- `ls folders|jobs|envs|constants [--filter <glob>]` — listings.
- `show <node> [--envs]` — one node fully resolved, optionally side by side per environment.
- `graph <folder|node> [--upstream|--downstream] [--depth n] [--format text|mermaid|dot]` — chain graph.
- `links <node> | links --name <condition>` — edges of a node, or who produces/consumes/deletes a name.

Comparison
- `diff <A> <B>` — A and B may be repo directories, git refs, `env:<name>` resolved views or XML files; XML↔XML goes through `xmldiffreport`.

Refactorings
- `rename-job`, `rename-folder`, `rename-subapp`, `move-job`, `insert-job`, `remove-job`, `link`, `unlink`, `extract-variable`, `dedupe-jobnames`, `standardize-names`.
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
   token. The whole value is kept `literal:`, so its letter is not swapped on export to another
   environment. Options: a finer rule that marks only the inner token, or a per-value decision
   recorded in `chain.json`.
5. Values carrying another environment's letter in the UAT export (4): bug or intentional?
6. The CLI should swallow BrokenPipe when its output is piped into `head`.
