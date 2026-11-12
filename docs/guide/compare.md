---
description: "Compare two Control-M environments by their real differences: what the map and the letter explain is read through."
---

# Compare two environments

```bash
ctmchain compare main env/uat
ctmchain compare env/bench env/uat
ctmchain compare main env/uat --format md > uat-vs-prod.md
ctmchain compare main env/uat --raw
```

The first argument is the side that receives, the second where things come from. The head
is read in the terms of the base: its letter, and the machines, users and words the map
knows. The report starts with what was read through and then lists what is left:

```text
Compare main (prod) with env/uat (uat): real differences only
  expected between prod and uat, not shown: 28 values and 2 texts of the map,
  4 names with the letter, 1 condition called another name
```

`--raw` compares the two branches as they are stored, without the map.

## A value with two answers

When one value of the source stands for two in the target (two users there for one here),
nothing is guessed: the value is kept as it is and a warning names the entries of the map
that could explain it. Repeat with `--prefer`:

```bash
ctmchain compare env/bench env/uat --prefer run_as.1
```

## A condition called by two names

A condition that links the same jobs the same way under another name is no difference,
but it is listed, with the item that takes the other name:

```text
  P77_A-P77_B_OK is P77_ALPHA-P77_B_OK in uat (link:… takes that name)
```

Each environment may keep its own name, or one takes the other's
([Take and package](take-package.md)).

## In the web UI

On the *Compare* page, choose *Base* and *Head* and press **Compare**: nothing runs until
you do, and the last comparison stays in view while the next one is worked out. A
comparison of two commits is kept, so asking for it again is immediate.
