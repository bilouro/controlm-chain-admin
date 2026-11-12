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
column *Followed by*.

## One environment set up with another one's value

Two entries of one key that differ in a single environment are, more often than not, one
rule and one environment set up wrongly. Renaming an entry changes its name and no job.
This does:

```bash
git switch -c work/fix-bench env/bench
ctmchain envmap follow run_as.2 run_as.1           # preview
ctmchain envmap follow run_as.2 run_as.1 --apply
ctmchain commit -m "run_as.2 follows run_as.1"
ctmchain package env/bench work/fix-bench -o bench_import.xml
```

On the branch checked out, which must hold the environment where the two entries differ,
the jobs that follow the first entry get the value of the second. The map is left alone:
once the import file is in Control-M and the next export of that environment is refreshed,
nothing follows the wrong entry and it can be removed.

`ctmchain validate` points at such cases: see [Validate and fix](validate.md).
