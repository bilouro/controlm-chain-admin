# Needs

What the tool must do for the maintainer's work with Control-M chains, as stated by the
maintainer after a day of testing it at work (2026-11-09). Part 1 is each need as stated;
part 2 is the evaluation of what the tool did then and how 0.2.0 meets each need.

# Part 1: the needs

## 1. The model, with production on `main`

There is a model of the chains, and the `main` branch of the git repository holds the
representation of production.

## 2. A branch for UAT

A branch holds the representation of UAT.

## 3. A branch for EGMA

A branch holds the representation of EGMA.

## 4. A branch for bench

A branch holds the representation of bench.

## 5. Refresh an environment's branch from its full export

Go to EGMA, download the whole XML export from Control-M, import it into EGMA, and refresh
EGMA as many times as needed: the export overwrites what the EGMA branch has with this
version. The same for bench.

## 6. See the differences of a new export, and decide

When the environment is exported again, the differences between the new export and the
branch are shown, and the maintainer decides whether to apply them on that branch or not.

## 7. Compare two environments' branches, and take what is chosen

From an environment's branch, compare it with another branch (UAT with bench, bench with
prod...), see the differences between them, and decide to take specific things from one
environment to the other:

- one attribute of a job;
- one job;
- one attribute of a folder;
- a whole folder;
- a whole sub-application.

## 8. The map of what changes from one environment to another

`main` holds one thing and each branch another. A map is needed, like the one built today
on `main` with every value called an environment value (the constants), to recognise the
peculiarities that change from one environment to another.

- The map must be known, but it is not part of any environment.
- Where to keep it is open: a branch of its own, apart; a cached file, git-ignored; a branch
  fetched elsewhere to consult it; maybe `main`, though `main` is protected and it is not
  clear how the map would live there. It may be part of no branch at all.
- When and how the map is reached is open too. One way: a branch that loads every
  environment, to conclude what differs per environment, and only that: the NODEID, the
  RUN_AS, the letters of the environment at the start of the names.

## 9. Compare environments by their real differences

Fundamental once the environments are there: compare one environment with another and,
through what the map knows varies (the first letter, the NODEID, the RUN_AS...), see the
real differences, not the expected ones.

- The first letter of the names differs, obviously: that does not make a job different.
- An `INCOND`/`OUTCOND` pair whose names carry other letters, but that links the same jobs
  with the same sign, is not a difference.

## 10. Export what was chosen, adapted to the target environment

After comparing, export to another environment, adapted to it:

- a variable of a job;
- a whole job;
- a variable of a folder;
- a whole folder, or several folders;
- a sub-application with all its folders.

# Part 2: evaluation, and how each need is met (0.2.0)

## What 0.1 did, and why it did not serve

0.1 kept every environment in one branch: a base without environment (production's values
behind constants `@{name}`), a file of values per environment and a file of exceptions per
environment. A full export of another environment was *received*: each difference became a
decision (a constant, an exception, a change of the base). Changes travelled as releases.

Measured against the needs:

| Need | 0.1 | Why it failed |
|---|---|---|
| 1 | met | `main` mirrored production |
| 2, 3, 4 | not met | an environment was never stored, only derived from the base, its values and its exceptions; nothing in git said "this is UAT today" |
| 5 | not met | an export did not overwrite anything: it had to be received, decision by decision, and a second export of the same environment met the decisions of the first |
| 6 | partly | the preview of `receive` listed decisions to take, not the differences between two states of the same environment |
| 7 | not met | two environments were compared through the base: "UAT against bench" was two lists of exceptions to read side by side; nothing could be taken from one to the other |
| 8 | partly | the constants were the map, yet they lived inside the base, were created as a side effect of receiving an export, and every job had to be bound to them |
| 9 | partly | name-only changes of conditions were recognised; machines and users only where a constant had been bound |
| 10 | not met | a package was every changed folder of a release, whole; no way to say "this job, for bench" |

The cost showed on the real application: building the repository took a session of decisions
per environment, and the result answered questions nobody asked.

## What changed

One branch per environment, refreshed from its full export, and the map apart
([`DESIGN.md`](DESIGN.md) section 14). The import, the JSON layout, the letter rule, the
byte-for-byte export, `validate`, the refactorings, the comparison engine and the packaging of
0.1 are kept; what is new is where an environment lives, how two of them are compared, and
what travels between them.

| Need | Met by | How |
|---|---|---|
| 1 | `refresh prod.xml --apply` | `main` holds production, and changes by a refresh from its export only (`take --apply` is refused there) |
| 2, 3, 4 | `refresh <env>.xml --apply` | `env/uat`, `env/egma`, `env/bench`: each created from the rules of `main` at its first refresh |
| 5 | `refresh --apply`, again and again | the export overwrites the chain files of the branch and is committed; what it no longer has goes |
| 6 | `refresh <env>.xml` | without `--apply`: folders, jobs and conditions added, removed, changed, each attribute before -> after; nothing is written |
| 7 | `compare`, `take --list`, `take --item ... --apply` | items `attr:F/J@NAME`, `var:F/J@%%NAME`, `job:F/J`, `folder:F`, `subapp:S`; of a folder: `attr:F/@NAME`, `var:F/@%%NAME` |
| 8 | `envmap derive`, `suggest`, `add`, `show` | `map.json` on the orphan branch `map`: derived from the environments' branches, part of none, never checked out, pushed like any branch |
| 9 | `compare <base> <head>` | the head is read in the base's terms first: the letter, the values and words of the map, the conditions that link the same jobs under another name; `--raw` shows everything |
| 10 | `package <target> <source> --take ID... -o file.xml` | the target with only those items on it, as the Control-M import file of the target (its letter, machines, users); no branch changes. Or `take` into the target's branch and `export` from there |

## What was tried

- Unit, functional and end-to-end tests on four synthetic environments (`tests/unit`,
  `tests/functional`, `tests/e2e`): each need above has a test named after it.
- The real application, in its four environments, from the full exports alone: the repository
  was built in minutes with no decision to take; the map was derived (machines, users,
  datacenter by default; one variable and one word of a mail subject on request); comparisons
  between each pair; a folder, three folders, a sub-application, a job, an attribute and a
  variable packaged for each of the other environments, with only the target's letter in the
  file; a folder and a sub-application taken into an environment's branch, exported and
  validated.

## What is open

- The assistant previews a refresh and does not apply it, and does not edit the map: the
  command line and the web UI do.
- A value of the source that stands for two of the target (two users there for one here) is
  never guessed: it is reported, and `--prefer ENTRY` settles it.
- A taken folder or job carries the technical attributes of its source until the next refresh
  of the target.
- The commands of 0.1 (`receive`, `check`, `release`, `env constants`, `override`) are kept
  for repositories of that model; whether they stay is to be decided.
