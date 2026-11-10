# controlm-chain-admin — project rules for Claude Code

Read `DESIGN.md` (what we build and why) and `BACKLOG.md` (what comes next) before changing code.

## Hard rules

1. **TDD, always.** No production code without a failing test first. Red → green → refactor.
   A commit that touches `src/` or `web/src/` and no test needs a written reason.
2. **English everywhere in the repo**: code, comments, docstrings, CLI output, commit messages,
   docs (the mkdocs site is bilingual en/pt). Chat with the maintainer may be in Portuguese.
3. **No real data, ever.** Real Control-M exports, job names, hosts, users, e-mail addresses or
   URLs from any company never enter this public repository, not even in tests, docs or
   examples. Fixtures are synthetic (fictional application `P77`). The real data lives in a
   separate private repository.
4. **Stdlib-only core.** `src/controlm_chain_admin/core` has no third-party runtime
   dependency. FastAPI lives in the `[web]` extra; the frontend in `web/`.
5. **One core, thin adapters.** All logic, including mutations, is in `core` and returns
   serialisable structures (`ChangeSet`, reports). The CLI, the API and the MCP server
   (`mcpserver.py`, the `[mcp]` extra) only translate I/O.
6. **Conventional Commits**, `CHANGELOG.md` in Keep a Changelog format, SemVer.

## Which skill to use

| Area | Skill | Trigger |
|---|---|---|
| Repo hygiene, README, docs, release, naming | `oss-repo-standards` | touching docs, metadata, workflows, templates |
| `src/` core and CLI | `python-core-tdd` | any Python change |
| `src/controlm_chain_admin/web` API | `fastapi-api` | any API change |
| `web/` frontend | `react-frontend` | any TS/TSX change |
| End of every story / before a PR | `verify` | always, last step |
| A new machine with only PyPI; a data repository from the exports | `bootstrap` | «instalar na empresa», first run of the unpacked sdist |

Every story in `BACKLOG.md` ends by running the `verify` skill and pasting its PASS/FAIL report
in the PR description.

## Commands (once scaffolded)

```bash
pip install -e ".[dev,web]"      # core + CLI + API, dev tools
pytest                           # fixture tests (CI)
CTMCHAIN_DATA_REPO=~/dev/controlm-chain-data pytest -m realdata   # local only
ruff check . && ruff format --check . && mypy src
cd web && npm ci && npm run lint && npm run typecheck && npm test && npm run build
cd web && npm run test:e2e       # Playwright on two synthetic repos; CTMCHAIN_E2E_ASSISTANT=1: Kilo too
.claude/skills/verify/verify.sh  # the whole gate, PASS/FAIL
```
