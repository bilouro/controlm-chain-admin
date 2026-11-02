"""GET /api/git and /api/compare — branches and what changed between two refs."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.history import git_state, resolve
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.deps import get_repo
from controlm_chain_admin.web.schemas import ComparisonOut, ErrorOut, GitStateOut

router = APIRouter(prefix="/api", tags=["history"])
ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorOut, "description": "Not a git repository, or unknown ref"}
}
_CACHE_SIZE = 8


@router.get("/git", response_model=GitStateOut, responses=ERRORS, summary="Branches, tags and HEAD")
def git(repo: ChainRepo = Depends(get_repo)) -> GitStateOut:
    return GitStateOut.model_validate(git_state(repo.root).to_json())


@router.get("/compare", response_model=ComparisonOut, responses=ERRORS, summary="Compare two refs")
def compare_refs(
    request: Request,
    repo: ChainRepo = Depends(get_repo),
    base: str = Query(description="base ref, e.g. develop"),
    head: str = Query("WORKTREE", description="head ref, or WORKTREE for uncommitted changes"),
    merge_base: bool = Query(True, description="compare from the merge base (pull-request style)"),
) -> ComparisonOut:
    cache: OrderedDict[tuple[str, str, bool], dict[str, Any]] = request.app.state.compare_cache
    key = None
    head_sha = resolve(repo.root, head).sha  # None for the working tree: never cached
    if head_sha is not None:
        key = (str(resolve(repo.root, base).sha), head_sha, merge_base)
        if key in cache:
            cache.move_to_end(key)
            return ComparisonOut.model_validate(cache[key])
    data = compare(repo.root, base, head, use_merge_base=merge_base).to_json()
    if key is not None:
        cache[key] = data
        while len(cache) > _CACHE_SIZE:
            cache.popitem(last=False)
    return ComparisonOut.model_validate(data)
