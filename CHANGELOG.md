# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/) (`0.x`: the JSON layout may still change).

## [Unreleased]

### Added

- The fix of `repeated-jobname`: `ctmchain adopt-jobname FOLDER/JOB` (a fix on the
  *Validation* page, a capability for the assistant) makes the numbered name of a job its
  JOBNAME in Control-M too, and the conditions that carry the shared name and belong to the
  job follow, in every job that uses them. The change travels: `compare` shows the job with
  the JOBNAME Control-M has for it (`JOBNAME: X -> X2`), `package` writes the new name for
  the environment that receives, and `take` carries it as an item
  (`attr:FOLDER/JOB@JOBNAME`) or with the whole job.
- What the map knows, said by `validate` for the environment checked out: `foreign-value`
  (a job has the value another environment has in an entry of the map; its fix gives it
  this environment's), `unmapped-difference` (a mapped attribute that differs in a way no
  entry says), `ambiguous-map` (one value here, several answers in another environment) and
  `suspect-map-entry` (an entry that is another one except for one environment, which has
  there the value of a third).
- `ctmchain envmap followers` and the *Followed by* column of the *Map* page: how many
  places of the branches have exactly the values of each entry. `ctmchain envmap follow
  ENTRY OTHER` (the *Follow…* action of the page, a capability, the fix of
  `suspect-map-entry`): on the branch of the environment where the two entries differ, the
  jobs that follow one get the value of the other, previewed like any change. Renaming an
  entry still changes no job.

## [0.3.4] - 2026-11-12

### Added

- Fast where small files are slow (an antivirus that inspects every file, a network drive):
  a page that took half a minute and a comparison that took ten open and write no file any
  more. A branch comes out of git into memory instead of a temporary directory, like the
  copy a comparison rewrites, the one a selection is taken into and the one a change is
  prepared in; and a file of the repository is opened once and remembered until it changes,
  the first time read from git in one piece. Measured on an application of a thousand jobs:
  opening a folder went from some five thousand files opened to none, a comparison of two
  environments from eleven thousand written and thirty-six thousand read to none. Nothing
  to install and nothing to set: the standard library only.
- `ctmchain diagnose`: why a comparison is slow on a machine. It measures the machine (a
  small file in the temporary directory and next to the repository, one git call, plain
  computing) and one real comparison, phase by phase, with the files it wrote and read, and
  says what part of the time the files explain. The report holds numbers and the two refs
  compared, no name of a job, of a folder or of a directory, so it can be passed on
  (`-o report.txt`, `--format json`).
- A comparison of two commits, and its import package, is kept by commit and answered at once
  the next time: `compare`, `take --list`, `package`, the *Compare* page and the assistant's
  tools. The key holds the two commits, the branch checked out, the environments' branches,
  the map, the rules and the options, so nothing stale is ever answered; the working tree is
  never kept. It lives under the git directory (`ctmchain-cache`, the latest sixty results);
  `CTMCHAIN_NO_CACHE=1` turns it off.

- `validate` sees a JOBNAME that several jobs of the export share, in one folder or in
  several: `repeated-jobname`, one finding per job the import numbered (`X2`, `X3`), with
  the jobs that share the name. Until now only two jobs of one folder were looked at, and
  only where the import did not number them. It has no fix yet (0.4.0 brings it).
- Every kind of finding explains itself: what it looks for, why it matters, and what its fix
  does and what follows from it. `ctmchain resolve` prints it per code, the report carries
  it (`explanations`: `validate --format json`, `GET /api/validate`, the assistant's
  `validate`), and the *Validation* page shows it in a panel when a type of problem is
  chosen (it can be hidden, and stays so).

### Changed

- A condition named after the JOBNAME a numbered job has in Control-M is no longer a
  `stale-name`: its fix renamed the condition while the job kept its name there, the
  consequence offered as the main action.
- The *Compare* page compares when *Compare* is pressed, not at every change of *Base* or
  *Head* (*Swap* too waits for it), and the last comparison stays in view, dimmed, while the
  next one is worked out.

## [0.3.3] - 2026-11-11

### Added

- The assistant knows a branch of your own. The `refresh` tool of the MCP server takes
  `here` (what an export would change in the branch checked out, the environment's left as
  it is) and `partial` (the export holds some folders only), like `ctmchain refresh --here
  [--partial]`; it is still a preview, and its answer ends with the command that applies
  it. The rules the assistant reads and the `controlm` agent of Kilo say what such a branch
  holds and when to use the two. An agent written by an earlier version keeps its old
  rules: run `ctmchain kilo init --force` once (`vocabulary.md` is kept).

### Changed

- `package` between two branches of one environment is for that environment: `ctmchain
  package env/uat work/uat-next` no longer asks for `--env` (one given is still obeyed).
  The comparison says which environment both sides hold (`environment`, in `--format json`
  and `GET /api/compare`), and the *Compare* page starts its *Environment* selector there
  instead of on uat. Where one tree holds every environment, `--env` is asked for as before.

## [0.3.2] - 2026-11-11

### Changed

- A branch of your own is read as the environment it holds when it meets the branch of
  another environment. Until now only the name told the environment (the trunk,
  `env/<name>`), so `compare main work/uat-next` compared the files as stored,
  `take` from it brought uat's machines and users along, and `package env/bench
  work/uat-next` asked for `--env`. Now such a branch holds the environment of the last
  export in its history (the nearest `refresh(<env>): …` or `import(<env>): …` commit on its
  own line), and the three commands, the *Compare* page and the assistant's tools read it
  through the letter and the map like that environment's branch. With the branch of its own
  environment (`compare env/uat work/uat-next`) nothing changes.
- `refresh --here --partial` refuses some folders of another environment than the branch
  holds (`work/x holds prod: some folders of uat would leave it with two environments`);
  the full export of another environment is still taken, and makes the branch that
  environment.
- `refresh --here --apply --no-commit` prints the subject to commit with
  (`import(<env>): <file>`), since that subject is how the branch tells its environment.

## [0.3.1] - 2026-11-11

### Added

- A branch of your own, to try an export before it reaches the branch of its environment.
  The branch dialog of the web UI has *New branch*: the name given (`work/uat-next`) is
  created from whatever is checked out, `env/uat` say, and checked out (uncommitted chain
  files go with it, and the answer says so). `POST /api/workspace/branch`; the trunk, the
  map, `env/` and `release/` are not names for it. The dialog lists such branches, on the
  remote only too, with *Switch* (`branches` in `GET /api/workspace`).
- An export goes onto the checked-out branch instead of the branch of its environment:
  `ctmchain refresh <export.xml> --here`, and in the web UI the *Onto* choice of the
  *Refresh* page, which is there (and set to the checked-out branch) on a branch of your
  own. The branch of the environment is not touched, so *Compare* `env/uat` with
  `work/uat-next` shows what the export brings: the page links to it once the export is
  in. The commit is `import(<env>): <file>`. A branch that holds an environment takes the
  full export of that environment only, and a protected branch or a detached HEAD none.
- `--partial` (with `--here`; *The export holds some folders only* in the web UI): the
  folders of the export are rewritten and the others stay, for the export of one folder or
  of a delivery. Refused on the branch of an environment, which holds its full export.
  `here` and `partial` are query parameters of `POST /api/refresh/preview` and `/apply`,
  and the answer says `work` and `partial`.

### Changed

- The web UI shows the day colours unless asked: a *Theme* selector in the header (day, night,
  as the system) replaces following the system alone, and the choice is kept in the browser.
- The *View* selector of the web UI's header is shown only in a repository of the earlier
  model (a neutral base with constants and exceptions). Where every environment has its
  branch it changed nothing and is gone: the dialog of the branch button switches to the
  branch of the environment to look at.

### Fixed

- The branch dialog of the web UI lists the branch of every environment (`env/<name>`), on
  the remote only too, with *Switch*: it listed the trunk and the release branches alone, so
  the chains of another environment could not be opened from the page. `GET /api/workspace`
  gives them in `env_branches`.

## [0.3.0] - 2026-11-10

### Added

- The assistant works between environments. New MCP tools: `envmap` (the environments, their
  branches and the map), `takeable` (what a branch or an environment has that another has not,
  with the ids to take), `package` (what the import file of an environment would hold) and
  `write_package` (writes that file, never over another; Kilo asks first), `refresh` (what a
  full export would change in the branch of its environment; a preview only). `compare` takes
  `prefer` and `raw`.
- `take` is a capability like the others (`ctmchain do`, the MCP tools `preview` and `apply`,
  `POST /api/changes/*`): into the branch checked out, with `prefer` for a value two entries
  of the map explain. A conflict reaches the assistant with the item and its three values.
- `ctmchain kilo init` writes an agent and a skill that know the model of one branch per
  environment; `ctmchain_write_package` is asked like `ctmchain_apply`. Run it again with
  `--force` in a project set up by 0.2.0.
- `ctmchain take HEAD --list --prefer ENTRY`.
- The name of an environment given where its branch is expected (`compare main uat`) is
  answered with the branch it is (`the environment uat is the branch env/uat`); an item
  without its kind, with how an id looks.
- `ctmchain envmap show --format json` also gives `branches`: the branch of each environment
  that has one.
- The web UI has the model of one branch per environment:
  - *Refresh*: choose the full export of one environment; the page says which environment it
    is and why, what was read and what was left out, and what differs on the branch, node by
    node. *Overwrite …* asks first, then checks the branch out, overwrites it and commits
    (or not: a checkbox).
  - *Map*: the environments with their letters and branches, and the entries of the map.
    *Look at the branches* previews the entries the branches show and adds them; *Show what
    else varies* lists the other keys with a *Derive* button each; an entry is added by hand,
    renamed or removed (confirmed).
  - *Compare* between the branches of two environments says what was read in the terms of
    the base (values, texts, names, conditions), shows each warning of a value the map gives
    two answers for with a *Prefer* button per entry, and can show the branches as they are
    stored (to look at: nothing is taken or packaged from there). The chosen items are taken
    into the base when it is checked out, or go to *Package N items for <environment>*: the
    import file of that environment with only those items, no branch changed, from any
    checkout. *Generate XML* gives the file with every folder that differs.
- API: `GET /api/envmap`, `GET|POST /api/envmap/derive`, `GET /api/envmap/suggest`,
  `POST /api/envmap/entries`, `PATCH|DELETE /api/envmap/entries/{name}`,
  `POST /api/refresh/preview` and `POST /api/refresh/apply` (the export is the body of the
  request). Everything that writes needs the session token.
- A key that cannot be read (`ctmchain envmap derive --key`, `envmap add`, the API) is
  answered with what a key looks like (`InvalidSpec`; 422 in the API).

### Changed

- `ctmchain kilo init` gives the MCP server 120 s to answer (30 s before): comparing two
  environments of a large repository takes several seconds, more on a slow disk.
- `ctmchain export` writes the JOBNAMEs of Control-M by default (`--jobnames original`), as
  `package` always did: the export of a branch is its export byte for byte without an option.
  `--jobnames deduped` gives the names as stored. It only matters in a repository that numbers
  repeated JOBNAMEs (`--dedupe-jobnames`).

## [0.2.0] - 2026-11-10

One branch per environment. The needs it answers are in `NEEDS.md`, the model in `DESIGN.md`
section 14. A repository of 0.1 keeps working with the commands of 0.1; the new model is built
beside it, from the full exports alone.

### Added

- `ctmchain refresh <export.xml> [--env ENV] [--apply] [--no-commit] [--stat] [--format
  text|json]`: what the full export of one environment changes on its branch (`main` for
  production, `env/<name>` for the others; the environment is read from the letter of the
  names). Without `--apply` nothing is written: folders, jobs and conditions added, removed
  and changed, each attribute before -> after. With it the branch is checked out (created from
  the rules of the trunk the first time), the export overwrites its chain files and the result
  is committed as `refresh(<env>): <file>`. The same export again changes nothing; uncommitted
  chain files and an export of another environment are refused.
- The map of what is expected to differ between environments, `map.json` on a branch of its
  own (`map`, an orphan, never checked out): `ctmchain envmap show`, `derive [--key SPEC]
  [--text SPEC] [--min-nodes N] [--apply]` (reads the environments' branches: machines, users
  and datacenter by default, any other attribute or a word inside a text on request),
  `suggest` (what else varies, counted), `add KEY ENV=VALUE... [--text] [--as NAME]`,
  `remove`, `rename`.
- Two environments compared by their real differences: `ctmchain compare main env/uat` reads
  the head in the terms of the base's environment first (the letter of the names, the values
  and words of the map, conditions that link the same jobs under another name) and says how
  much it read through; `--raw` compares the branches as stored. The API takes `raw` on
  `/api/compare`.
- `ctmchain take <branch>` between environments: `--list` names every item that differs
  (`subapp:S`, `folder:F`, `job:F/J`, `attr:F/J@NAME`, `var:F/J@%%NAME`, relations, groups),
  `--item ID... --apply` writes them into the checked-out branch in its own terms;
  `--list --format json` for scripts.
- `ctmchain package <target> <source> --take ID... [-o FILE]`: the Control-M import file of
  the target environment with only the chosen items on it (an attribute, a variable, a job, a
  folder, several, a sub-application). No branch and no working tree changes. Without `--env`
  the target is the base's environment.
- `--prefer ENTRY` on `compare`, `take` and `package` (`prefer` in the API): when one value of
  the source stands for several of the target (two users there for one here), the entry of the
  map to use. Without it the value the target has at that place wins, else the value is kept
  and a warning names the candidates.
- `ctmchain init --dedupe-jobnames`: the policy for JOBNAMEs repeated in a folder, set when
  the repository is created.
- Functional and end-to-end tests of the whole path on four synthetic environments
  (`tests/functional`, `tests/e2e`).

### Changed

- The `CLAUDE.md` that `init` writes into a new repository describes the branch model: where
  each environment lives, what may change `main`, the everyday commands.
- `take --apply` is refused on the trunk: production changes in Control-M, and `main` follows
  by its next refresh (`package main env/<x> --take ...` builds what production must receive).
- The first refresh of a branch that holds no folder yet prints counts, not every folder and
  job of the export.
- README and package description rewritten around the branch model.

### Fixed

- A refresh of the export a branch already holds changes nothing where git converts line
  endings on checkout (`core.autocrlf`, the default of Git for Windows): the branch is read as
  it is stored.
- `take <branch> --list --base <other>` names the base it was given, not the branch checked
  out.
- The PowerShell examples quote the lists with commas (`--envs 'prod=P,uat=U'`): PowerShell
  splits a bare word at its commas.

## [0.1.4] - 2026-11-06

### Added

- Ask in plain words. `ctmchain mcp` serves the repository to an assistant (Kilo, Claude, any
  MCP client) over stdio, with the `[mcp]` extra: questions (`find` jobs and folders by name,
  attribute or value, also as one environment has them; `show` one with what it waits for and
  releases and its exceptions; `condition`; `validate`; `compare`) and changes as steps of the
  capabilities file, previewed (each field before -> after, the warnings, the diff) and
  written by `apply` only with the same steps and the preview's id: refused on a protected
  branch, or once the repository moved since the preview; nothing is committed.
  `capabilities.json` is the one source of what can be asked, how (parameters as JSON Schema,
  rules, an example tested on the synthetic chain) and how the assistant works;
  `ctmchain menu [capability] [--format json]` prints it. `ctmchain kilo init` writes `.kilo/`
  for Kilo: the server (this Python, this repository), an agent `controlm` that may use the
  ctmchain tools only (`ctmchain_apply` asks first), the skill, and `vocabulary.md` for the
  team's words, never overwritten.
- `set-variable`: add, change or remove one variable of a job or folder.
- The *Assistant* panel of the web UI: *Assistant* in the header opens a conversation beside
  the page, kept across pages and reloads of the tab. It shows the assistant's text and every
  tool it called, and what it waits to be allowed to do: an apply comes with this
  repository's own preview of its steps (each field before -> after, the warnings, the diff),
  *Apply* or *Reject*; one the repository moved away from cannot be applied. *Stop*
  interrupts it; the pages read the chains again after a change. `ctmchain serve --assistant
  [--assistant-model provider/model]` starts Kilo (`kilo serve`, on 127.0.0.1 with a password
  of its own, in the Kilo project; `.kilo/` written when missing) and stops it with the
  server; `CTMCHAIN_ASSISTANT_URL` (and `_PASSWORD`) uses one already running. `/api/assistant`
  (status, sessions, messages, approvals, stop; the posts need the session token).
- `npm run test:e2e` in `web/`: Playwright against the built UI served on a synthetic
  repository; `CTMCHAIN_E2E_ASSISTANT=1` adds a real conversation with Kilo and a model (a
  question, a change approved, a change rejected).
- The web UI shows one environment: *View* in the header switches the chain table, the folder
  pages and the job pages to the folders and jobs that environment has, with its values (its
  exceptions applied, its constants resolved; a constant without a value there stays
  `@{name}`), and says so with a badge; the chain table gains a *Node* column, where the
  machine of each job changes with the view. `?env=<name>` on `/api/table`, `/api/folders`,
  `/api/folders/{name}` and `/api/jobs/{folder}/{job}`; `ctmchain show` and `ctmchain graph`
  take `--env`.
- `ctmchain receive`: a group (the same difference in several jobs) can be decided job by
  job: each member is a decision of its own (`members` in the JSON; the *One by one* button
  of the *Import* page), chosen with its id (`FOLDER/JOB@FIELD=ignore`) apart from the
  group, which keeps the rest. The values no constant has (`unmatched`) say which folders
  and jobs they are in (`nodes`); the *Import* page leaves out the ones of jobs left out.
- The *Import* page sets every decision of a section at once (*All N: Exceptions*, *Ignore*,
  …), where the decision offers that option.
- `ctmchain receive`: a group whose value another pair shares (a few jobs run as another user
  in one environment, while production's user is the same) offers `new` too: a constant of
  their own, with production's value where it is the same, bound job by job. Later exports
  keep each job's constant where the values of two constants agree. The default stays
  `exceptions`.
- `ctmchain receive`: a name with the environment's letter inside a text (`-j UP77_LOAD` in a
  `CMDLINE` for `-j PP77_LOAD`) is an inline constant, with the letter of each environment:
  the default when two jobs or more carry it, an exception of the one job otherwise.
- Exceptions for any line of a folder or job. `envs/<env>/overrides.json` holds, besides the
  attributes and variables, the lines one environment has otherwise (`elements`, by locator):
  an attribute of a condition, a SHOUT or an action of an ON block
  (`"OUTCOND[link=P77_A-P77_B_OK,ODATE=ODAT]": {"SIGN": "-"}`), a line only that environment
  has (its attributes, and `after`: the sibling before it), a line it lacks (`null`), and a
  variable it lacks (`"variables": {"%%X": null}`). The export applies them, `check` counts
  them, the job and folder pages list them on the *Environments* tab, and `set-exception`
  takes `elements` (the API) and drops a line by its locator.
- A locator names a line by its tag and what tells it from its siblings, from the node down:
  conditions by their link and ODATE, SHOUT by WHEN and DEST, ON blocks by STMT and CODE, the
  rest by their position among their tag (`ON[STMT=*,CODE=NOTOK]/DOMAIL[0]`). Positions move;
  locators hold.
- `ctmchain receive` compares the lines of every folder and job one by one: a line both
  sides have attribute by attribute (`value` decisions, named by the locator), a line only
  the export or only the repository has as an `element` decision (change the base, an
  exception, ignore), shown in *Differences* of the *Import* page. The `children` decision
  (change or ignore everything inside a node) is gone.
- `ctmchain technical [--add NAME] [--remove NAME]` and the *Technical attributes* box of the
  *Environments* page: the attributes Control-M writes by itself (`volatile_attributes` of
  `chain.json`) are listed and changed with a preview; a name added moves its values to
  `meta/`, a name removed brings them back; the exports do not change, what is compared does.
  `GET /api/repo` carries `volatile_attributes`; the change is `set-technical`.
- A job or folder viewed as one environment says what that environment has otherwise: a
  strip under the header lists its exceptions, and every attribute, variable, condition and
  ON action it has otherwise carries a mark with the base's value beside (an attribute or
  variable it leaves out is shown as such). On the *Environments* tab, *Make it the base*
  gives the base what the environment has (`ctmchain promote-exception <env> <node> NAME...`,
  the change `promote-exception`): the exception goes, and so do the exceptions of other
  environments equal to the new base.
- What an environment has as exceptions already comes back in every receive of its export,
  as decisions marked `known` (the *Already exceptions of <env>* section of the *Import*
  page, folded): kept by default, *change the base* makes the base take it, *ignore* drops
  it. So a release that an environment carries whole (its full export) becomes the base of a
  release branch in one go: *All N: Change the base*.
- `ctmchain compare` and the *Compare* page tell the changes that only call a condition
  another name from the real ones: a condition gone and one arrived that the same jobs use
  the same way (the same producers and consumers, ODATE, signs, AND_OR and cleanup), or a
  condition renamed, is marked *name only* with the other name beside, and so is a folder or
  job whose every change is such (`name_only` and `counterpart` in the JSON,
  `summary.name_only`). Everything is still listed by default; *All / Real only* beside *Copy
  Markdown* (`real=1` in the address) and `--real-only` leave them out, the counts and the
  Markdown follow (`real_only=true` on `/api/compare/markdown`). What is packaged does not
  change.
- *On Windows, from scratch (with Kilo)* in the README: the tool in a venv from PyPI, the data
  repository from the exports, the assistant; the `bootstrap` skill has the PowerShell lines.

### Changed

- The summary of `set-attributes` names the attributes: `set MAXWAIT on P77_CHAIN/P77_B`.
- The assistant answers in the language the person writes in and keeps it for the
  conversation; when a message does not show one (only names or values) it answers in English
  and asks which language they prefer, and it never translates the names, fields and values of
  the chains. It is a rule of the capabilities file, so the `controlm` agent, the skill and
  `ctmchain mcp` all carry it; a `.kilo/` written before takes it with
  `ctmchain kilo init --force` (the vocabulary is kept). The Kilo that `serve --assistant`
  starts no longer reads `~/.claude/CLAUDE.md`, what a person wants of Claude Code (its
  language too); `KILO_DISABLE_CLAUDE_CODE_PROMPT=0` reads it again.
- A full export of an environment other than production makes every difference an exception
  of that environment by default: attributes and variables (present or absent), the lines of
  the folders and jobs, and the same difference repeated in several jobs (`exceptions`).
  Production stays as it was. Receiving the same export again changes nothing. When a later
  export of production or a delivery gives the base what an environment had as an exception,
  that exception goes by itself; a line whose block the base lost is dropped with a warning.
- A value of a new folder or job that no constant has (`unmatched`) stays as it is in every
  environment by default (`literal`); `new` is the default only when the value carries the
  environment's letter.
- Every difference and every group offers an exception, inside ON blocks too; in a delivery,
  a repeated difference changes the base by default.

### Removed

- `ctmchain receive --values-only`, the `values_only` field of `POST /api/intake` and the
  *Only the values of <env>* box: a full export of another environment is received with its
  differences as exceptions instead; the folders and jobs of the releases on their way may
  still be left out one by one (*Leave out*) and come from their deliveries.

### Fixed

- `ctmchain serve` stopped by SIGTERM or SIGHUP (a closed terminal) cleans up like Ctrl+C: the
  Kilo of `--assistant` stops with it instead of running on.
- `set-variables` keeps a variable without a value (Control-M allows it) instead of refusing
  the change.
- Receiving an export of an environment no longer drops from the base the jobs that
  environment does not have (`"envs"` without it): they stay as they are. A second full
  export of uat used to remove them.
- *Validate*: the fix of a resource of another environment (`foreign-resource`) failed on a
  job that exists in some environments only (an internal error that also stopped every
  batch holding it). It is now a targeted rename (`rename-resource`), so two such fixes on
  one job in one batch both apply. Replacing the JSON of such a job (*Raw JSON*) works too,
  and a list that holds no elements is refused with a message instead of an error.
- *Validate*: while the findings are computed again after a change (seconds on a big
  repository), the fixes and *Resolve selected* wait, with a note: a fix clicked from the
  old list could name a condition that is gone.

## [0.1.3] - 2026-11-03

### Added

- `ctmchain check <xml> [--env ENV]`: the export of one environment against the repository's
  export of it, folder by folder, job by job and field by field (every attribute but the
  volatile ones, child elements such as `INCOND` or `ON/DOMAIL`). Per field: how many nodes the
  environment differs in from production, and in how many the repository's export still
  differs; whether it is byte for byte, the nodes on one side only, the constants and the
  exceptions of the environment. Counts only, never values (`--format json` names the nodes);
  exit 1 when anything but volatile attributes differs. The `bootstrap` skill and the guide
  of a new data repository check every environment with it.

### Fixed

- Receiving the export of another environment no longer stops with "order of <JOB> in this
  export contradicts the order recorded in chain.json". The order of two attributes that
  never meet in one job (`DAYS` and `WEEKDAYS`) was taken from the first export as if it
  were a rule; only what the exports show counts now. An element really written in another
  order (another client) keeps its own order in its metadata, so no attribute order stops an
  import any more and the export stays byte for byte.
- An export that starts with a UTF-8 byte order mark is exported with it again (production
  was no longer byte for byte).
- Two constants with one value in an environment (one machine of test for two of production)
  no longer move the jobs of one constant to the other when that environment's export is
  received: the job keeps the constant the repository has, and production stays as it was.
- When the full export of an environment shows most uses of a constant on another value than
  the one the repository has there (a value guessed from the letter when the constant was
  made), that value becomes the constant's (`set-value`) and only the jobs that keep the old
  one become exceptions: test went from 1529 exceptions to 12 on a real rehearsal. A partial
  export (a delivery) never moves the value of a constant.

## [0.1.2] - 2026-11-03

### Added

- `receive --values-only` and the *Only the values of <env>* box of the Import page: an export
  of an environment whose jobs carry releases production does not have yet gives its
  machines, users, mails, variables and its name in texts (new constants or their values) and
  nothing else by default (differences and children ignored, jobs and folders it lacks kept,
  folders and jobs only it has left out).
- *added* decisions have the option `skip` ("Leave out"): the folder or job does not enter the
  repository.
- *adopt* decisions: where the repository still has production's value of a constant and the
  export has the constant (a job no earlier export of that environment had), use the
  constant; production does not change. Also inside texts (`[P77][PROD]` and
  `@{env.subject}`).
- The `bootstrap` skill takes only the values from the full exports, then builds the releases
  on their way from their deliveries; the data repository's `CLAUDE.md` mentions
  `--values-only`.

### Fixed

- A job numbered by `--dedupe-jobnames` (`X2`) that a full export of another environment names
  otherwise lost its original JOBNAME when kept: production's export changed.
- Values taken inside the children of a job (a mail of an ON block) were put back when the
  job's children were kept as they were.

## [0.1.1] - 2026-11-03

### Added

- `validate` reports `similar-names` (warning): conditions whose names differ only by the
  suffix a copy of a chain appended (`…_OK-U26`, `…_OK-U26-U31`) or by case (`_OK`, `_Ok`).
  The fix `number-similar` gives them the common name with a number (`…_OK1`, `…_OK2`, …) in
  every job that uses them; a condition with an end outside the repository keeps its name.
  Names made of their own jobs (`A-TO-LOAD-S1`, `A-TO-LOAD-S2`) are not reported.

### Changed

- A numbered standard name (`A-B_OK2`, `A-TO-B2`) is a standard name for `validate`.

### Fixed

- Resolving several findings at once failed ("a batch cannot contain another batch") when a
  fix was itself several changes (numbering repeated JOBNAMEs or similar names): a batch now
  runs the changes of a batch inside it in its place.

## [0.1.0] - 2026-11-03

First release on PyPI.

### Added

- Faithful XML reader and serializer for Control-M exports (`DEFTABLE`): byte-identical round
  trip, including attribute order, prolog comment and escaping.
- Chain repository: `ctmchain init`, `import` (lossless, folders of other applications skipped
  and reported, volatile metadata in `meta/`, repeated JOBNAMEs as `NAME~n`), `export`
  (identical for untouched content).
- Environment letter rule: `--prefixes` and per-environment letters; neutral names on disk;
  `import --env` / `export --env`; `literal:` marks and suspicious values in the import report.
- Derived links index per folder; `validate` with severities, text/Markdown/JSON output and exit
  codes; `distinct`, `show`, `graph` (text, Mermaid, DOT, JSON) and `links` commands.
- `[web]` extra: read-only FastAPI (`ctmchain serve`) and a Vite + React web UI with folder
  list, chain graph, job detail and validation pages; OpenAPI snapshot as the frontend contract.
- Constants: `@{name}` placeholders in the base resolved per environment at export
  (`distinct --write` mapping drafts, `map`, `import --mappings`, `env constants --missing`,
  `export --allow-unresolved`); value and inline modes; selectors `ATTR`, `TAG/@ATTR`,
  `TAG[K=V]/@ATTR`.
- Links are the source of truth for condition names: nodes reference `"link": "<id>"`,
  `folders/<F>/links.json` holds the export name of each link, `index.json` is the derived view.
  Renaming a condition is one edit; ids stay stable when a renamed export is imported again.
- `export --names standard`: `<PRODUCER>-<CONSUMER>_OK` from the endpoints, producer folder as
  prefix when two links would collide; external, fan-in and delete-only links keep their names.
- `import --dedupe-jobnames`: repeated JOBNAMEs get a numeric suffix (`X`, `X2`, `X3`), the
  originals are kept in `meta/` and the policy in `chain.json`; `export --jobnames original`
  restores them byte for byte.
- Refactorings with change-set preview and `--apply`: `rename-job`, `rename-folder`,
  `rename-subapp`, `move-job`, `insert-job`, `extract-variable`. Previews show a unified diff
  (`--stat`, `--format json`); apply refuses files changed since the preview.
- Editing web UI: the *Chains* table (folders collapsible, application, sub-application, folder,
  job, predecessors, successors) and tabbed folder and job pages to edit attributes, variables,
  raw JSON and predecessors/successors with their AND_OR, ODATE and `+`/`−` details. Edits are
  previewed as a diff and applied through `POST /api/changes/preview|apply` with a session token.
- `ctmchain compare <base> [<head>]`: what a branch changed in the chain (folders and jobs added,
  removed, modified, renamed or moved; attribute and variable values before and after;
  predecessor and successor changes with AND_OR, ODATE, `+` and `−`; conditions; constants per
  environment; commits), from the merge base by default, with `--worktree`, `--no-merge-base` and
  text, Markdown or JSON output. The *Compare* web page shows the same comparison with ref
  pickers, summary cards, a change list grouped by folder and a before/after detail
  (`GET /api/git`, `GET /api/compare`).
- `compare --commit <sha>` and commit checkboxes on the *Compare* page: compare only some commits
  of the branch, applied on the base cherry-pick style; a selection that needs a left-out commit
  names it; every change lists the commits that made it.
- `ctmchain package <base> [<head>] --env <env>` and the *Generate XML* button: the Control-M
  import file with every folder the comparison changed, whole, for one environment (letter rule
  and constants resolved, original JOBNAMEs), with the reason of each folder, warnings for what
  an import cannot do and new validation findings (`GET /api/package`, `GET /api/package/xml`).
- `export_document(..., folders=)` exports a subset of the folders; `validate(write_index=False)`.
- Fixes for validation findings: `ctmchain resolve [CODE=KIND...]`, each finding of
  `GET /api/validate` with its fixes and link id, new operations `emit`, `stop-emitting` and
  `batch` (several changes previewed and applied as one). The *Validation* page selects every
  finding by default, filters by type of problem, resolves one finding (a button per fix, each
  explained) or the selection (one choice per type of problem, one reviewed change), and uses the
  full width of the screen without horizontal scrolling.
- Every fix lists its effects (which job gets which element added, removed or changed, before
  and after); the review dialog shows them above the diff as *What will change*, says that
  nothing is written before *Apply change*, and asks for the editing URL or token when the tab
  has none. `ctmchain serve` keeps `CTMCHAIN_TOKEN` when it is set, so open tabs survive a
  restart.
- Committing edits: `ctmchain commit [-m MESSAGE] [--branch NAME] [--dry-run]` and the *Commit
  (n)* button of the web UI header, with a Conventional Commits message written from the
  semantic comparison of HEAD with the working tree (editable), the files, and a new release
  branch when on a protected branch. Only the chain files are committed
  (`git commit --only`); a commit prepared before other edits is refused
  (`GET /api/git/pending`, `POST /api/git/commit`, `changes` in `GET /api/git`).
- *Copy Markdown* on the Compare page (`GET /api/compare/markdown`): the comparison for a pull
  request description; left-out commits are marked in the Markdown and the text reports.
- Releases: the trunk (`main`) mirrors production and is never edited; edits and commits are
  refused on protected branches and a detached HEAD. `ctmchain release
  status|start|switch|installed|update|close`: a release branch `release/<name>` starts from the
  trunk, each installation in an environment is a tag `<env>/<name>-<n>`, a release is closed
  (merged into the trunk) once its last commit is installed in production, after merging the
  trunk in when it moved. The web UI header shows the branch and opens the *Releases* dialog
  (start, switch, stash and restore, discard, update, close, push and pull); a banner and the
  review dialog explain why a branch is read-only; the package preview asks whether to hold
  only what changed since the last installation in that environment, and marks the
  installation (`GET /api/workspace`, `POST /api/workspace/...`). Rules in the optional `git`
  key of `chain.json`.
- Exceptions per environment (`envs/<env>/overrides.json`): attributes and variables one
  environment uses for one job or folder instead of the base, applied at export before the
  constants; `ctmchain set-exception` and the `set-exception` change; a changed exception
  puts its folder in that environment's package. `ctmchain rename-constant` (and the change of
  the same name) renames a constant everywhere it is used.
- The intake analysis of an export of one environment (`core/intake.py`): its environment
  told by the letter of the names, the values of constants to learn, values the export
  contradicts, exceptions, changes of the base, removed jobs and unresolved values.
- Receiving an export of one environment into the release: `ctmchain receive` (the decisions,
  `--choose ID=OPTION`, preview, `--apply`), the `receive` change, `POST /api/intake` and the
  *Import* page of the web UI (upload, analysis, a choice per decision, review). `ctmchain env
  learn` and the `set-values` change take only the values of the constants.
- Validation of dirty names, each with its fix: `foreign-letter` (a condition name with another
  environment's letter), `foreign-resource` (a resource of another environment, an error),
  `letter-for-p` (a letter in place of the P of the application prefix, in a condition or a
  MEMNAME) and `replaced-first-letter` (`PALES` for `SALES`).
- The *Environments* tab of the job and folder pages: the exceptions of each environment
  (e.g. `TASKTYPE` Dummy or another `CMDLINE` in one environment), remove one, add one; job
  and folder details carry their `exceptions`.
- Receiving an export, a value no constant has is a decision instead of a refusal: a new
  constant (suggested name, or `new:NAME`), another existing constant (`use:NAME`), or the same
  value in every environment (`literal`); a job that disagrees with a constant can get its own.
- The *Environments* page of the web UI: every constant with its value per environment, the
  missing ones marked, where it is used; give a value or rename a constant through the review
  (`GET /api/environments`, `constants_overview`).
- A new repository learns its environments from their exports: receiving another
  environment's export groups the same difference in many jobs (and any machine, user, mail
  or variable) into one decision. Its new constant gets a value in every environment: from the
  letter of the environment when the value carries it (`{L}P77_BATCH`), the base's value
  elsewhere until their exports come. The name of the environment inside a text
  (`[UAT] Load failed`) becomes an inline constant with the display names. Values inside ON
  blocks (mails, subjects) are decisions of their own instead of one "children" decision.
  Jobs the export does not change keep their values. `ctmchain receive` prints the groups;
  the *Import* page has a section for them; decisions carry `values` and `inline`.
- `ctmchain init --leading-only RQ_,RC_`: the whole letter rule from the start; `init` also
  writes the new repository's `CLAUDE.md` (its rules, layout and everyday commands) unless one
  is there.
- Taking changes of another branch into the checked-out one, item by item: `ctmchain take`
  (`--list`, `--item`, `--theirs`) and the boxes of the *Compare* page (base: the checked-out
  branch). One attribute, variable, predecessor or successor (both ends), group of children,
  job without its folder, folder, condition name, constant value or exception at a time,
  applied cherry-pick style; a value the checkout changed too is a conflict (`TakeConflict`,
  409) shown value by value, kept or taken; constants the taken content uses come along.
- The *Releases* dialog marks the last commit of the checked-out release as installed in an
  environment (*Installed in <env>*), next to *Close release*, without going through the package
  preview.
- The comparison lists the exceptions per environment (`exceptions`, an *Exceptions* tab, the
  text and Markdown reports).
- The `bootstrap` skill: from the source distribution to a new chain repository built from the
  full exports of every environment, production first, with the agreed conventions.
- Folders and jobs that exist in some environments only: `"envs": ["uat"]` in their JSON; the
  export of another environment leaves them out, importing an export that has them adds that
  environment. Receiving a *full* export (more than half of the folders, or `--full`,
  `--partial`, the *Full export* box of the Import page) of an environment other than
  production leaves production alone: exceptions instead of changes, children ignored, a
  job or folder it lacks noted as not there, one only it has noted as only there, production's
  header, job order and volatile attributes kept. A prod baseline then still exports byte for
  byte after uat and bench came in.
- The source distribution carries the whole project (rules, skills, docs, tests, the `web/`
  sources and the built web UI), so it can be developed where only PyPI is reachable.
- Package skeleton, CI (lint, types, tests, web, build) and release workflows, community files.
- `DESIGN.md` (architecture and data model) and `BACKLOG.md` (proof-of-concept plan and status).

### Fixed

- `receive --choose` split a group's id at its first `=` (`group:RUN_AS=a>b=new:NAME`): the
  choice is split at the last one.
- In a full export of another environment, a production text naming another environment
  (`[UAT]` in prod) or a production value with another environment's letter was taken for the
  name or letter of production and changed production: only production's own count.
- Conditions of a node whose children are kept in their own order (an ON block before the
  conditions, not the order of the rest of the export) were not links: `links.json` missed
  them and the export failed with "references unknown link".
- With deduplicated JOBNAMEs, importing some folders only gave their jobs new names (`X`
  instead of the `X2` the full export gave); a job now keeps the name a previous import gave
  it, and folders that are not in the export keep theirs.
- Resource names with an inner application code (`URQ_P77_AGGREGATION`) were kept literally,
  with the letter of the imported environment, so another environment's export would have used
  that environment's resource: prefixes listed in `letter_rule.leading_only` carry the letter on
  the first token only.
- Exports saved with Windows line endings (`\r\n`) are written back with them.
- Importing an export of some folders only replaced the header of the full export (the
  *Exported at* comment); it is now kept. `JOBS_IN_GROUP` is a volatile attribute by default.
- A folder-prefixed standard name (`F_A-B_OK`, given when two links would collide) is no longer
  reported as `stale-name`, and the fix to rename to it is offered.
- Renaming a job or a folder, or inserting a job, could give a condition a name another link
  already used, joining two chains in Control-M; the condition now keeps its name, with a
  warning, and the new link of `insert-job` never reuses a name.

- Piping CLI output into a reader that closes early (`| head`) no longer prints a BrokenPipe error.
- Reloading or opening a web UI page other than the home page (for example `/compare?...` or a
  job page) returned 404; the server now answers client routes with the app.
- On Windows, unknown `/api/...` paths and missing assets were answered with the app instead of
  404 (the static files handler sees `\` separators there).

[Unreleased]: https://github.com/bilouro/controlm-chain-admin/compare/v0.3.4...HEAD
[0.3.4]: https://github.com/bilouro/controlm-chain-admin/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/bilouro/controlm-chain-admin/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/bilouro/controlm-chain-admin/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/bilouro/controlm-chain-admin/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/bilouro/controlm-chain-admin/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/bilouro/controlm-chain-admin/compare/v0.1.4...v0.2.0
[0.1.4]: https://github.com/bilouro/controlm-chain-admin/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/bilouro/controlm-chain-admin/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/bilouro/controlm-chain-admin/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/bilouro/controlm-chain-admin/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/bilouro/controlm-chain-admin/releases/tag/v0.1.0
