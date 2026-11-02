"""GET /api/workspace and its actions: releases from the trunk, installations, stash, push."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request

from controlm_chain_admin.core import workspace as ws
from controlm_chain_admin.core.commit import discard
from controlm_chain_admin.core.repo import ChainRepo, load_repo
from controlm_chain_admin.web.deps import get_repo, require_token
from controlm_chain_admin.web.schemas import (
    ActionOut,
    DiscardRequest,
    ErrorOut,
    InstalledRequest,
    PopRequest,
    StartReleaseRequest,
    SwitchRequest,
    WorkspaceOut,
)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])
ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing or wrong session token"},
    404: {"model": ErrorOut, "description": "Unknown environment"},
    409: {
        "model": ErrorOut,
        "description": "Protected branch, uncommitted changes in the way, or a conflict",
    },
    422: {"model": ErrorOut, "description": "Not allowed now (see the message) or a git error"},
}
ACTION: dict[str, Any] = {
    "response_model": ActionOut,
    "responses": ERRORS,
    "dependencies": [Depends(require_token)],
}


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _state(repo: ChainRepo) -> WorkspaceOut:
    return WorkspaceOut.model_validate(ws.workspace(load_repo(repo.root)).to_json())


def _act(request: Request, repo: ChainRepo, action: Callable[[], str]) -> ActionOut:
    with request.app.state.write_lock:
        message = action()
    return ActionOut(message=message, workspace=_state(repo))


@router.get(
    "",
    response_model=WorkspaceOut,
    responses=ERRORS,
    summary="The branch, whether it may be edited, releases and their installations, stashes",
)
def get_workspace(repo: ChainRepo = Depends(get_repo)) -> WorkspaceOut:
    return _state(repo)


@router.post("/release", summary="Start a release from the trunk and switch to it", **ACTION)
def start_release(
    body: StartReleaseRequest, request: Request, repo: ChainRepo = Depends(get_repo)
) -> ActionOut:
    return _act(request, repo, lambda: ws.start_release(repo, body.name, stash=body.stash))


@router.post("/switch", summary="Switch to another branch", **ACTION)
def switch(body: SwitchRequest, request: Request, repo: ChainRepo = Depends(get_repo)) -> ActionOut:
    return _act(request, repo, lambda: ws.switch(repo, body.branch, stash=body.stash))


@router.post("/stash", summary="Put the uncommitted chain files aside", **ACTION)
def stash(request: Request, repo: ChainRepo = Depends(get_repo)) -> ActionOut:
    return _act(request, repo, lambda: ws.stash(repo))


@router.post("/pop", summary="Restore a stash on the checked-out branch", **ACTION)
def pop(body: PopRequest, request: Request, repo: ChainRepo = Depends(get_repo)) -> ActionOut:
    return _act(request, repo, lambda: ws.pop(repo, body.ref))


@router.post("/discard", summary="Throw the uncommitted chain changes away", **ACTION)
def discard_changes(
    body: DiscardRequest, request: Request, repo: ChainRepo = Depends(get_repo)
) -> ActionOut:
    def action() -> str:
        count = discard(repo.root, body.fingerprint)
        return f"Discarded {_plural(count, 'chain file')}"

    return _act(request, repo, action)


@router.post("/installed", summary="Record that a release is installed in an environment", **ACTION)
def installed(
    body: InstalledRequest, request: Request, repo: ChainRepo = Depends(get_repo)
) -> ActionOut:
    def action() -> str:
        done = ws.mark_installed(repo, body.env, body.release, body.sha)
        return f"Tagged {done.tag} on {done.sha[:7]}"

    return _act(request, repo, action)


@router.post("/update", summary="Merge the trunk into the checked-out release", **ACTION)
def update(request: Request, repo: ChainRepo = Depends(get_repo)) -> ActionOut:
    return _act(request, repo, lambda: ws.update_from_trunk(repo))


@router.post("/close", summary="Merge the release into the trunk once in production", **ACTION)
def close(request: Request, repo: ChainRepo = Depends(get_repo)) -> ActionOut:
    return _act(request, repo, lambda: ws.close_release(repo))


@router.post("/push", summary="Push the checked-out branch and its installation tags", **ACTION)
def push(request: Request, repo: ChainRepo = Depends(get_repo)) -> ActionOut:
    return _act(request, repo, lambda: ws.push(repo))


@router.post("/pull", summary="Fetch, then fast-forward the branch and the trunk", **ACTION)
def pull(request: Request, repo: ChainRepo = Depends(get_repo)) -> ActionOut:
    return _act(request, repo, lambda: ws.pull(repo))
