"""Application factory: routers, error handlers and the built web UI (when present)."""

from __future__ import annotations

import secrets
import threading
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from controlm_chain_admin import __version__
from controlm_chain_admin.web import errors
from controlm_chain_admin.web.routers import (
    changes,
    folders,
    history,
    jobs,
    package,
    repo,
    table,
    validate,
)
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


class SpaStaticFiles(StaticFiles):
    """Built UI files; client routes (no file extension, not under api/) get index.html."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not _client_route(path):
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404 and _client_route(path):
            return await super().get_response("index.html", scope)
        return response


def _client_route(path: str) -> bool:
    first, _, _ = path.partition("/")
    return first != "api" and "." not in path.rsplit("/", 1)[-1]


TAGS = [
    {"name": "repo", "description": "The chain repository as a whole."},
    {"name": "folders", "description": "Folders, their jobs, links and chain graph."},
    {"name": "jobs", "description": "One job with grouped attributes, ON blocks and links."},
    {"name": "validate", "description": "Validation findings and links by condition name."},
    {"name": "table", "description": "Folders and jobs with predecessors and successors."},
    {"name": "changes", "description": "Preview and apply edits (needs the session token)."},
    {"name": "history", "description": "Git refs and the comparison of two refs."},
    {
        "name": "package",
        "description": "The Control-M import file with every folder a comparison changed.",
    },
]


def create_app(settings: Settings, *, static_dir: Path = STATIC_DIR) -> FastAPI:
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
    app.state.compare_cache = OrderedDict()
    app.state.package_cache = OrderedDict()
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=sorted({*settings.allowed_hosts, settings.host})
    )
    errors.register(app)
    for router in (
        repo.router,
        table.router,
        folders.router,
        jobs.router,
        validate.router,
        changes.router,
        history.router,
        package.router,
    ):
        app.include_router(router)

    if (static_dir / "index.html").is_file():
        app.mount("/", SpaStaticFiles(directory=static_dir, html=True), name="ui")
    else:

        @app.get("/", include_in_schema=False, response_class=HTMLResponse)
        def placeholder() -> str:
            return _PLACEHOLDER

    return app
