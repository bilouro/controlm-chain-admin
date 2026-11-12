---
description: "Validate Control-M job chains: dangling conditions, misleading names, repeated job names, values of another environment, with a fix for most."
---

# Validate and fix

```bash
ctmchain validate                 # the findings; exit 1 when there are any
ctmchain resolve                  # each kind of finding, what it means and its fixes
ctmchain resolve never-cleaned=add-cleanup            # preview that fix for every finding
ctmchain resolve never-cleaned=add-cleanup --apply
```

Every kind of finding says what it looks for, why it matters and what its fix does: in
`ctmchain resolve`, and on the *Validation* page when a type of problem is chosen.

## The kinds of finding

| Code | It looks for | Its fix |
|---|---|---|
| `dangling` | a job waits for a condition nobody emits, named after a job that exists | the named job emits it, or the job stops waiting |
| `dangling-unknown` | the same, and the name does not say who should emit it | the job stops waiting |
| `dangling-external` | the same, named after a job of another application | usually none is needed |
| `unconsumed` | a job emits a condition nobody waits for | the named job waits for it, or the job stops emitting |
| `unconsumed-external` | the same, for a job of another application | usually none is needed |
| `never-cleaned` | a job waits for a condition and never deletes it | the job deletes it after use |
| `stale-name` | the name of a condition names two jobs and it links two others | renamed after the jobs it links |
| `non-standard-name` | a name not made of the two jobs it links | renamed to the standard name |
| `similar-names` | conditions that differ only by a copy's suffix or by case | each gets a number |
| `duplicate-jobname` | two jobs of one folder with one JOBNAME, left unnumbered | the later ones get a number |
| `repeated-jobname` | a JOBNAME several jobs share, anywhere | the numbered name becomes the real one |
| `foreign-letter`, `letter-for-p`, `replaced-first-letter`, `foreign-resource` | a name that carries the letter of an environment | the letter is taken out |
| `foreign-value` | a job with the value another environment has in the map | this environment's value |
| `unmapped-difference` | a mapped attribute that differs with no entry saying so | none: add an entry, or correct the job |
| `ambiguous-map` | one value here, several answers in another environment | none: prefer an entry |
| `suspect-map-entry` | an entry that is another one with one environment set up like a third | its jobs follow the other entry |

## A JOBNAME that several jobs share

With `--dedupe-jobnames` the import numbers every later job of a repeated JOBNAME (`X2`,
`X3`) inside the repository; Control-M still has the one name for all of them. To make the
numbered name the real one, with the conditions that carry the old name following:

```bash
git switch -c work/names env/uat
ctmchain adopt-jobname 'P77_CHAIN/P77_A2'           # preview
ctmchain adopt-jobname 'P77_CHAIN/P77_A2' --apply
ctmchain commit -m "adopt P77_A2"
ctmchain compare env/uat work/names                 # JOBNAME: P77_A -> P77_A2
ctmchain package env/uat work/names -o uat_import.xml
```

The JOBNAME changes in Control-M when the import file is imported: what shows in monitoring
and in the history changes with it.

## The findings that come from the map

The last four codes of the table need one branch per environment and a map; they are
worked out for the environment the checked-out branch holds. See [The map](map.md).
