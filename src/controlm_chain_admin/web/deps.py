"""FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from controlm_chain_admin.core.repo import ChainRepo, load_repo


def get_repo(request: Request) -> ChainRepo:
    """The chain repository, re-read from disk on every request (edits outside are picked up)."""
    settings = request.app.state.settings
    return load_repo(settings.repo)
