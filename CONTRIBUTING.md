# Contributing to controlm-chain-admin

Thanks for your interest! Bug reports, ideas, docs and code are all welcome. Please read
`DESIGN.md` (what we build and why) and `BACKLOG.md` (what comes next) first.

## Project layout

```text
src/controlm_chain_admin/
  core/        model, XML reader and serializer, links, operations — standard library only
  cli.py       the `ctmchain` command: a thin adapter over core
  web/         FastAPI server (`[web]` extra), another thin adapter over core
web/           web UI (Vite + React + TypeScript)
tests/         pytest suite; `realdata` tests need a private data repository and are skipped in CI
.claude/       Claude Code rules and skills used to develop this project
```

## Ground rules

1. **Tests first.** Every change starts with a failing test (red → green → refactor). A PR that
   touches `src/` without touching `tests/` must say why.
2. **No real data.** Never commit a real Control-M export, job name, host, user, e-mail or
   URL. Examples and tests use the fictional application `P77`. The maintainer runs a local
   scan before merging; a PR with real data is closed without review.
3. **Stdlib-only core.** New runtime dependencies are accepted only in the `[web]` extra.
4. **English** in code, comments, docs and commit messages. Documentation pages are bilingual
   (English first, Portuguese twin).
5. **Conventional Commits**: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`.

## Development setup

```bash
git clone https://github.com/bilouro/controlm-chain-admin.git
cd controlm-chain-admin
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,web]"
pre-commit install            # optional: ruff on every commit
```

## Checks before opening a PR

```bash
ruff check . && ruff format --check .
mypy src
pytest --cov=controlm_chain_admin
.claude/skills/verify/verify.sh    # the same gate, as one PASS/FAIL report
```

If you have access to a private data repository with real exports:

```bash
CTMCHAIN_DATA_REPO=/path/to/clone pytest -m realdata
```

## Pull requests

- Keep PRs small and focused on one backlog story; reference it in the title.
- Fill the PR template: summary, the TDD checkbox and the `verify` report.
- CI must be green; a maintainer reviews within a few days.

## Reporting bugs and proposing features

Use the issue templates. For security problems see `SECURITY.md`.
