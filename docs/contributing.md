---
description: "How to set up controlm-chain-admin for development, run its tests and send a change."
---

# Contributing

```bash
git clone https://github.com/bilouro/controlm-chain-admin
cd controlm-chain-admin
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,web,mcp]"

pytest                                   # the Python tests, on synthetic fixtures
ruff check . && ruff format --check . && mypy src
cd web && npm ci && npm run lint && npm run typecheck && npm test && npm run build
```

## The rules of the house

- **A failing test first.** No production code without a test that fails for the right
  reason; the test and the code go in the same commit.
- **No real data, ever.** No real export, job name, host, user or address, not even in a
  test. The fixtures are of a fictional application, `P77`.
- **The core depends on the standard library only.** FastAPI is in the `[web]` extra, the
  MCP server in `[mcp]`.
- **One core, thin adapters.** The logic, mutations included, is in
  `controlm_chain_admin.core`; the command line, the API and the MCP server only translate.
- **Conventional Commits**, a changelog in the Keep a Changelog format, SemVer.

## The documentation

```bash
pip install -e ".[docs]"
mkdocs serve          # http://127.0.0.1:8000
mkdocs build --strict
```

Every page has a Portuguese twin (`page.pt.md`) with the same headings.

The full guide is in
[`CONTRIBUTING.md`](https://github.com/bilouro/controlm-chain-admin/blob/main/CONTRIBUTING.md).
