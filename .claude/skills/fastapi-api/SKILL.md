---
name: fastapi-api
description: Standards for the local FastAPI server of controlm-chain-admin (src/controlm_chain_admin/web, the [web] extra, `ctmchain serve`). Use for any change to API routers, schemas, dependencies, error handling, OpenAPI metadata or API tests, and when someone asks to «criar endpoint», «expor na API», «servir», or review the API. Thin handlers over the core, typed errors, TestClient tests, OpenAPI snapshot.
---

# fastapi-api

Adapted from Everything Claude Code `fastapi-patterns`, `fastapi-reviewer` and
`rules/python/fastapi.md` (MIT, see `.claude/ATTRIBUTION.md`). Architecture: `DESIGN.md` §11.

## Structure

```text
src/controlm_chain_admin/web/
  app.py            # create_app(settings) -> FastAPI; lifespan loads ChainRepo; mounts static SPA
  settings.py       # repo path, host (127.0.0.1), port, token, open_browser
  deps.py           # get_repo() (reloads when files changed), require_token()
  errors.py         # ONE exception handler: core typed errors -> HTTP status + {"error","message","detail"}
  schemas/          # Pydantic v2 response/request models, one module per resource
  routers/          # repo.py folders.py jobs.py links.py validate.py changes.py
  static/           # built SPA (web/dist), served at "/" (not committed)
```

## Rules

- **Handlers are thin**: parse → call one `core` function → return a schema. No loops over
  folders, no name logic, no file access in a router. If a handler needs a rule, the rule goes
  to `core` and the CLI gets it too.
- The core is synchronous and in-memory, so handlers are plain `def` (FastAPI runs them in a
  threadpool). Use `async def` only for handlers that await something. Never block an `async`
  handler with file or subprocess calls.
- `response_model` on every endpoint; separate request, response and list schemas; schemas
  mirror `core` dataclasses (build them with `model_validate(dataclasses.asdict(...))` or
  `from_attributes`), never expose internals the UI does not need.
- Pagination (`limit`, `offset`) on every list endpoint even if the UI does not use it yet.
- Errors: `core` typed errors map in `errors.py` only — `NotFound` 404, `NameCollision`/
  `LiteralCollision` 409, `UnresolvedConstant`/`DanglingLink` 422, unexpected 500 with a log
  line and no stack trace in the body. Every error response has the same shape.
- Mutations (`POST/PUT/DELETE`) are `/api/changes/*`: preview returns a `ChangeSet`, apply takes
  the same `ChangeSet` back. Both require the `X-Ctmchain-Token` header checked by
  `require_token`. `GET` endpoints are read-only and need no token.
- Bind `127.0.0.1` by default; `--host` must be explicit; CORS off (same origin: the SPA is
  served by the same app). Log the request line, never request bodies.
- OpenAPI: `title`, `version` from the package, a tag per router with a description, every
  endpoint has `summary` and documented error responses. The schema is the frontend contract
  (`web/` generates TypeScript types from it), so changing it is a visible diff.
- Configuration via `settings.py` (pydantic-settings) with env prefix `CTMCHAIN_`; no reading
  `os.environ` in routers.

## Tests (TDD, like everything else)

- `tests/web/conftest.py` builds a fixture chain repo in `tmp_path`, overrides `get_repo` with
  `app.dependency_overrides`, clears it after the test, and yields a `TestClient`.
- One test module per router; assert status, body shape and the exact values from the
  fixture; one negative test per error mapping; one test proving a mutation without the token
  is 401 and with the token returns the preview.
- `tests/web/test_openapi.py` compares `app.openapi()` with
  `tests/web/openapi.snapshot.json`; updating the snapshot is a deliberate commit.
- No network, no real data, no sleeping; the server is never started in tests.

## Verify

1. `pytest tests/web -q` green, including the OpenAPI snapshot.
2. Checklist (from `fastapi-reviewer`): no logic in handlers · `response_model` everywhere ·
   one error handler, consistent error shape · token on every mutation · no `async def`
   doing blocking work · list endpoints paginated · settings only via `settings.py` ·
   no secrets, hosts or real names in code or snapshot · docs tags and summaries present.
3. Start it once by hand: `ctmchain serve --repo <fixture repo> --no-browser`, open
   `/docs`, call two endpoints, stop it.
4. Finish with the `verify` skill and paste its report in the PR.
