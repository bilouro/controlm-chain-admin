---
name: python-core-tdd
description: TDD and coding standards for the Python core and CLI of controlm-chain-admin (src/controlm_chain_admin, tests/). Use for any change to Python code — new feature, bug fix, refactor — and when someone asks to «implementar», «corrigir», «testar» or «refatorar» the core, the parser, the serializer, links, validate or the CLI. Enforces test-first, stdlib-only core, one-core-two-adapters, coverage gate.
---

# python-core-tdd

Adapted from Everything Claude Code `tdd-workflow`, `python-testing`, `python-reviewer` and
`rules/python` (MIT, see `.claude/ATTRIBUTION.md`). Architecture rules come from `DESIGN.md` §11.

## The loop (every change, no exceptions)

1. **Red** — write the test in `tests/` that describes the behaviour; run it; it must fail for
   the right reason (not an import error). Name it after the behaviour:
   `test_export_reproduces_bytes_for_untouched_folder`.
2. **Green** — write the smallest code that passes. No extra features.
3. **Refactor** — remove duplication, name things, keep functions < 50 lines; tests stay green.
4. **Commit** test and code together (`feat:`/`fix:`/`test:`), the test file visible in the diff.

A bug fix starts with a failing regression test that reproduces it. If a test must change,
the behaviour changed on purpose and the commit message says so.

## Test layout

```text
tests/
  conftest.py                 # fixture_repo, fixture_xml, tmp chain repos
  fixtures/
    build_fixtures.py         # deterministic synthetic export of application P77
    p77_export.xml            # committed output of the generator
  unit/test_<module>.py       # pure functions, one module per file
  integration/test_cli_*.py   # CLI through main(argv), tmp repo, exit codes
  realdata/test_roundtrip.py  # @pytest.mark.realdata, skipped unless CTMCHAIN_DATA_REPO is set
```

- Arrange / Act / Assert, one behaviour per test, `pytest.mark.parametrize` for tables.
- Fixtures over setup code; `tmp_path` for every file write; never write inside the repo.
- Byte-level assertions for the serializer (`assert out == original_bytes`), not string
  "looks like" checks. Compare with a filtered original when applications are skipped.
- `realdata` tests read the private clone path from `CTMCHAIN_DATA_REPO`, never a hardcoded
  path, and never print real values on failure beyond counts and positions.
- Coverage gate: `fail_under = 90` in `pyproject.toml` for `controlm_chain_admin`; adapters
  (`cli.py`, `web/`) count too, so keep them thin.

## Architecture rules (checked in review)

- `core/` imports only the standard library. Third-party code lives in `web/` (`[web]` extra)
  or dev tooling.
- `core` functions take a loaded `ChainRepo` and parameters, return frozen dataclasses
  (`ChangeSet`, `Report`, resolved nodes) or raise typed errors (`UnresolvedConstant`,
  `DanglingLink`, `NameCollision`, `LiteralCollision`). Nothing in `core` prints or exits.
- `cli.py` only parses arguments, calls one `core` function, renders (`text|md|json`), maps
  errors to exit codes (0 ok, 1 findings, 2 usage, 3 error).
- Writes go through `ops.apply(repo, change)`: all files or none; the preview is the same
  object the user saw.
- Immutability by default: `@dataclass(frozen=True)`, tuples, `Mapping`; build new objects
  instead of mutating. Document order is kept with lists, never with dict insertion assumptions.
- Determinism: no `datetime.now()` or randomness in model code; the export comment timestamp
  is a parameter.

## Style

- Python ≥ 3.11, `from __future__ import annotations` not needed; use `X | None`.
- Type annotations on every public signature; `mypy src` clean; no `Any` without a comment.
- `ruff` (line 99; rules E, F, I, UP, B, SIM, C4, RUF) and `ruff format`; no `print` in
  `core`; `logging` for diagnostics; `pathlib` for paths; `with` for every file.
- Docstrings in English on public modules, classes and functions: one line what, then why if
  non-obvious. Comments explain intent, not mechanics.
- Errors: catch specific exceptions; never `except: pass`; messages name the folder/job
  identity, never dump a whole element.
- Encoding: read and write bytes explicitly as UTF-8; never let the platform default decide.

## Verify

1. `pytest -q` green; `pytest -m realdata` green locally when the change touches parsing,
   serialization or links.
2. `ruff check . && ruff format --check . && mypy src` clean.
3. Checklist: test written first (test file in the diff) · no third-party import under
   `core/` · no `print`/`sys.exit` outside `cli.py` · new behaviour has a byte- or
   value-level assertion · errors typed · no real data in tests or fixtures · functions
   < 50 lines, files < 800 lines · CHANGELOG `Unreleased` updated for user-visible changes.
4. Finish with the `verify` skill and paste its report in the PR.
