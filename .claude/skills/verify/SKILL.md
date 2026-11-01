---
name: verify
description: End-of-part quality gate for controlm-chain-admin. Runs lint, types, tests with coverage, the no-real-data scan and a diff review, then writes a PASS/FAIL report. Use at the end of every backlog story, before opening a PR, after a refactor, or whenever someone asks to «verificar», «validar», «está ok?», «run the gate» or «check before PR».
---

# verify — the common gate

Adapted from Everything Claude Code `verification-loop` (MIT, see `.claude/ATTRIBUTION.md`).
Every area skill (`python-core-tdd`, `fastapi-api`, `react-frontend`, `oss-repo-standards`)
ends by invoking this one. The report goes into the PR description.

## 1. Run the script

```bash
.claude/skills/verify/verify.sh            # whole repo
.claude/skills/verify/verify.sh --python   # only the Python gate
.claude/skills/verify/verify.sh --web      # only the frontend gate
```

The script detects what exists (`pyproject.toml`, `web/package.json`) and runs, in order:

| Phase | Python | Frontend |
|---|---|---|
| Lint | `ruff check .` and `ruff format --check .` | `npm run lint` |
| Types | `mypy src` | `npm run typecheck` |
| Tests | `pytest --cov=controlm_chain_admin --cov-fail-under=<gate>` | `npm test -- --run --coverage` |
| Build | `python -m build` (when `build` is installed) | `npm run build` |
| No real data | `git ls-files` grepped with the patterns in `.claude/no-real-data.patterns` (local, git-ignored) | same |
| Debug leftovers | `breakpoint()`, `pdb` in `src/` | `console.log` in `web/src/` |
| Diff | `git diff --stat` against the base branch | same |

A phase that fails stops the gate with `FAIL`; fix it before continuing. The no-real-data
patterns file is deliberately not in the repository; when it is missing the phase reports
`SKIPPED (no patterns file)` and the maintainer must run the gate locally before merging.

## 2. Review the diff by hand

After the script passes, read `git diff <base>...HEAD` and answer, per file:

- Is every change intended and within the story's scope?
- Does each new behaviour have a test that was written first (test file in the same commit)?
- Are errors handled explicitly, with typed errors from `core`, never swallowed?
- Is anything duplicated that `core` already provides?
- Does any string look like real data (job names with a real application prefix, hostnames,
  user names, e-mail addresses, internal URLs)?

## 3. Write the report

```text
VERIFICATION REPORT — <story id> — <date>
Lint:          PASS/FAIL
Types:         PASS/FAIL (n errors)
Tests:         PASS/FAIL (x/y passed, z% coverage, gate g%)
Build:         PASS/FAIL/SKIPPED
No real data:  PASS/FAIL/SKIPPED
Debug left:    PASS/FAIL
Diff:          n files, +a/−b, reviewed by hand: yes/no
Overall:       READY / NOT READY for PR
Issues:
1. ...
```

`READY` requires every phase `PASS` (or `SKIPPED` only for Build and, locally run later, No
real data) and the hand review done. Never report `READY` from memory: paste the script output.
