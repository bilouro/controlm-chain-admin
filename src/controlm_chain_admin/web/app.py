"""Application factory: routers, error handlers and the built web UI (when present)."""

from __future__ import annotations

import secrets
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from controlm_chain_admin import __version__
from controlm_chain_admin.web import errors
from controlm_chain_admin.web.routers import changes, folders, jobs, repo, table, validate
from controlm_chain_admin.web.settings import Settings

STATIC_DIR = Path(__file__).with_name("static")

_PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>ctmchain</title></head>
<body style="font-family: system-ui; margin: 3rem auto; max-width: 40rem; line-height: 1.5">
<h1>ctmchain API is running</h1>
<p>The web UI is not built into this installation. The API is documented at
<a href="/docs">/docs</a>; try <a href="/api/repo">/api/repo</a>.</p>
<p>To get the interface, build the frontend in <code>web/</code> of the source tree
(<code>npm ci &amp;&amp; npm run build</code>) and reinstall, or install a release wheel.</p>
</body></html>
"""

TAGS = [
    {"name": "repo", "description": "The chain repository as a whole."},
    {"name": "folders", "description": "Folders, their jobs, links and chain graph."},
    {"name": "jobs", "description": "One job with grouped attributes, ON blocks and links."},
    {"name": "validate", "description": "Validation findings and links by condition name."},
    {"name": "table", "description": "Folders and jobs with predecessors and successors."},
    {"name": "changes", "description": "Preview and apply edits (needs the session token)."},
]


def create_app(settings: Settings) -> FastAPI:
    """Build the FastAPI application for one repository. Nothing is read until a request."""
    app = FastAPI(
        title="controlm-chain-admin",
        version=__version__,
        description="API over a chain repository; edits go through previewed change sets.",
        openapi_tags=TAGS,
    )
    app.state.settings = settings
    app.state.token = settings.token or secrets.token_urlsafe(18)
    app.state.write_lock = threading.Lock()
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=sorted({*settings.allowed_hosts, settings.host})
    )
    errors.register(app)
    for router in (repo.router, table.router, folders.router, jobs.router, validate.router, changes.router):
        app.include_router(router)

    if (STATIC_DIR / "index.html").is_file():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    else:

        @app.get("/", include_in_schema=False, response_class=HTMLResponse)
        def placeholder() -> str:
            return _PLACEHOLDER

    return app
