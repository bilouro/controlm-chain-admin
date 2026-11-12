---
description: "Why controlm-chain-admin stays fast where small files are slow, and how to measure a machine with ctmchain diagnose."
---

# Performance

On some machines every small file is costly: an antivirus inspects each one, or the
directory is on a network drive or in a synchronised folder. A tool that works through
thousands of small files spends nearly all of its time there.

Since 0.3.4 the tool does not use the disk as its working memory:

- **Working copies live in memory.** A branch comes out of git in one piece, into memory:
  the snapshot of a ref, the copy a comparison rewrites, the one a selection is taken into,
  the one a change is prepared in.
- **A file of the repository is opened once.** Its text is remembered until the file
  changes, and the first reading of a clean working tree comes from git in one piece.
- **A comparison of two commits is kept.** The same question again is answered at once.
  `CTMCHAIN_NO_CACHE=1` turns that off.

## Measure a machine

```bash
ctmchain diagnose
ctmchain diagnose -o diagnose.txt
```

It measures the machine (a small file in the temporary directory and next to the
repository, one git call, plain computing) and one real comparison, phase by phase, with the
files it opened and wrote. The report holds numbers and the two refs compared: no name of a
job, of a folder or of a directory, so it can be passed on.

## If it is still slow

- Keep the repository on a local disk, outside any synchronised or network folder.
- On Windows: `git config core.fscache true` and `git config core.untrackedCache true`.
- Restart `ctmchain serve` after an upgrade: a running server keeps the old version.
