"""GET /api/git, /api/git/pending, POST /api/git/commit and GET /api/compare."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from controlm_chain_admin.core.commit import commit, pending
from controlm_chain_admin.core.compare import Comparison, compare, render_markdown
from controlm_chain_admin.core.history import git_state, resolve
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.deps import get_repo, require_token
from controlm_chain_admin.web.schemas import (
    CommitRequest,
    CommittedOut,
    ComparisonOut,
    ErrorOut,
    GitStateOut,
    PendingOut,
)

router = APIRouter(prefix="/api", tags=["history"])
ERRORS: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorOut, "description": "A selected commit needs one that was left out"},
    422: {"model": ErrorOut, "description": "Not a git repository, or unknown ref or commit"},
}
_CACHE_SIZE = 8
T = TypeVar("T")

COMMITS = Query(
    None,
    description="comma-separated shas of the head commits to compare, applied on the base "
    "cherry-pick style; omitted: every commit; empty: none",
)


def parse_commits(commits: str | None) -> list[str] | None:
    if commits is None:
        return None
    return [c.strip() for c in commits.split(",") if c.strip()]


def cached(
    request: Request,
    name: str,
    repo: ChainRepo,
    refs: tuple[str, str],
    options: tuple[Hashable, ...],
    build: Callable[[], T],
) -> T:
    """``build()`` memoised by the shas of the refs; the working tree is never cached."""
    cache: OrderedDict[tuple[Hashable, ...], Any] = getattr(request.app.state, name)
    head_sha = resolve(repo.root, refs[1]).sha
    if head_sha is None:
        return build()
    key = (str(resolve(repo.root, refs[0]).sha), head_sha, *options)
    if key in cache:
        cache.move_to_end(key)
        return cache[key]  # type: ignore[no-any-return]
    value = build()
    cache[key] = value
    while len(cache) > _CACHE_SIZE:
        cache.popitem(last=False)
    return value


@router.get("/git", response_model=GitStateOut, responses=ERRORS, summary="Branches, tags and HEAD")
def git(repo: ChainRepo = Depends(get_repo)) -> GitStateOut:
    return GitStateOut.model_validate(git_state(repo.root).to_json())


@router.get(
    "/git/pending",
    response_model=PendingOut,
    responses=ERRORS,
    summary="Uncommitted chain changes and a suggested message",
)
def git_pending(repo: ChainRepo = Depends(get_repo)) -> PendingOut:
    return PendingOut.model_validate(pending(repo.root).to_json())


@router.post(
    "/git/commit",
    response_model=CommittedOut,
    dependencies=[Depends(require_token)],
    responses={
        401: {"description": "Missing or wrong session token"},
        409: {"model": ErrorOut, "description": "The files changed since the commit was prepared"},
        422: {"model": ErrorOut, "description": "Nothing to commit, empty message, bad branch"},
    },
    summary="Commit the chain files",
)
def git_commit(
    body: CommitRequest, request: Request, repo: ChainRepo = Depends(get_repo)
) -> CommittedOut:
    with request.app.state.write_lock:
        done = commit(repo.root, body.message, body.fingerprint, branch=body.branch or None)
    return CommittedOut.model_validate(done.to_json())


def _comparison(
    request: Request,
    repo: ChainRepo = Depends(get_repo),
    base: str = Query(description="base ref, e.g. develop"),
    head: str = Query("WORKTREE", description="head ref, or WORKTREE for uncommitted changes"),
    merge_base: bool = Query(True, description="compare from the merge base (pull-request style)"),
    commits: str | None = COMMITS,
) -> Comparison:
    selection = parse_commits(commits)
    return cached(
        request,
        "compare_cache",
        repo,
        (base, head),
        (merge_base, None if selection is None else tuple(selection)),
        lambda: compare(repo.root, base, head, use_merge_base=merge_base, commits=selection),
    )


@router.get("/compare", response_model=ComparisonOut, responses=ERRORS, summary="Compare two refs")
def compare_refs(result: Comparison = Depends(_comparison)) -> ComparisonOut:
    return ComparisonOut.model_validate(result.to_json())


@router.get(
    "/compare/markdown",
    response_class=PlainTextResponse,
    responses={**ERRORS, 200: {"content": {"text/markdown": {}}, "description": "Markdown"}},
    summary="The comparison as Markdown, for a pull request",
)
def compare_markdown(result: Comparison = Depends(_comparison)) -> PlainTextResponse:
    return PlainTextResponse(render_markdown(result), media_type="text/markdown")
