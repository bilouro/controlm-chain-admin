"""FastAPI dependencies."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

from controlm_chain_admin.core.repo import ChainRepo, load_repo

TOKEN_HEADER = "X-Ctmchain-Token"


def get_repo(request: Request) -> ChainRepo:
    """The chain repository, re-read from disk on every request (edits outside are picked up)."""
    settings = request.app.state.settings
    return load_repo(settings.repo)


def require_token(request: Request) -> None:
    """Mutating requests must carry the session token of this server."""
    sent = request.headers.get(TOKEN_HEADER, "")
    if not secrets.compare_digest(sent, request.app.state.token):
        raise HTTPException(
            status_code=401,
            detail="editing needs the session token: open the URL printed by ctmchain serve",
        )
