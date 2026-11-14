---
description: "The map of what is expected to differ between Control-M environments: derive it from the branches, read who follows each entry, and put an environment right."
---

# The map

The map says which value of one environment stands for which value of another: the
machine, the user, the datacenter, a word in a mail subject. With it, a comparison shows
the real differences only, and what you take arrives with the right values.

```bash
ctmchain envmap derive                         # what the branches show and the map lacks
ctmchain envmap derive --apply                 # add it
ctmchain envmap derive --text 'DOMAIL/@SUBJECT' --apply   # one word of a text
ctmchain envmap show
ctmchain envmap suggest                        # what else varies, with counts
```

`derive` looks at `NODEID`, `RUN_AS` and `DATACENTER`; `--key` adds an attribute whose whole
value varies, `--text` one whose texts differ in a single word. Values that fewer than two
places show are left out (`--min-nodes`): they are what one job has, not what the
environment has.

An entry is added, renamed or removed by hand too:

```bash
ctmchain envmap add RUN_AS prod=app77proc uat=aup77proc bench=abp77proc
ctmchain envmap rename run_as.1 the_batch_user
ctmchain envmap remove run_as.2
```

The map lives on its own branch (`map`) and is written there directly: no checkout
changes. Push it like any branch.

## Who follows each entry

```bash
ctmchain envmap followers
```

A *place* (an attribute of a job, or of an element inside it) follows an entry when its
values in every environment are exactly the entry's. The *Map* page shows the same in the
column *Followed by*. It is counted on the environments' branches **as committed**: a
change left to commit does not move it yet. A place that has one entry's values in some
environments and another's in the rest, after a follow done in some environments only, is
said to be *half-way* between them.

## New values after a refresh

A refresh can bring a value the map does not know: a user renamed in Control-M, a machine
replaced. Until it is in the map, comparing that environment with another shows every job
that has it as different.

```bash
ctmchain envmap new-values                                   # on the branch of an environment
ctmchain envmap adopt RUN_AS aup77svc --entry run_as.1       # into the entry suggested
ctmchain envmap adopt RUN_AS aup77svc --new                  # or a new entry
ctmchain envmap set run_as.4 egma aep77svc                   # fill an environment
ctmchain envmap set run_as.4 egma --clear                    # leave it to fill
```

`new-values` lists, for the environment of the branch checked out, the values no entry says
for those places, with how many places have each and the entry suggested: the one whose
values the other environments have there. It runs by itself after every refresh of an
environment's branch (`ctmchain refresh … --apply` says what it found, the *Refresh* page
lists them), and any time on the *Map* page, section *New values*.

- Into an entry: the entry takes the new value for that environment. When the old value is
  used nowhere in the environment any more (renamed everywhere), every entry that had it
  takes the new one; otherwise only the one chosen, and you are told how many places keep
  the old value.
- A new entry takes what its places have in the other environments, where they all agree;
  the rest is *to fill*, and an entry translates nothing in an environment it has no value
  for until it is filled.
- A *new combination* is a value the map knows with other values elsewhere: where two
  environments had the same value before one was renamed. It gets an entry of its own.

## Follow another entry, in every environment

Two entries of one key are often one rule and some environments set up wrongly. Renaming an
entry changes its name and no job. This does:

```bash
ctmchain envmap follow run_as.2 run_as.1           # preview, by environment
ctmchain envmap follow run_as.2 run_as.1 --apply   # one commit on the branch of each
```

In every environment where the two entries differ, the places that follow the first get the
value of the second: one commit on the branch of that environment,
`follow(<env>): run_as.2 -> run_as.1`, without checking it out (the branch checked out must
have no uncommitted chain file). Production is never edited here: the preview says when it
differs too, and production gets the change with an import file (Compare, package). The
counts move at once. Each environment's Control-M gets the change with its own import
file; until then its next export brings the old value back.

`--here` does it on the branch checked out only, left to review and commit: commit it as
the subject the command says (`follow(<env>): …`), so that the places still half-way are
told apart. On the *Map* page: *Follow…*, then *Preview* and *Follow in N environments*.

`ctmchain validate` points at such cases: see [Validate and fix](validate.md).
