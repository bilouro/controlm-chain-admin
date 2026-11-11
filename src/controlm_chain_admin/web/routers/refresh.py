"""POST /api/refresh/preview and /apply — the full export of one environment over its branch,
or, when asked, an export onto the checked-out branch.

The body is the export file itself, byte for byte: what the branch gives back is what
Control-M gave."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request

from controlm_chain_admin.core.refresh import refresh
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.deps import get_repo, require_token
from controlm_chain_admin.web.schemas import ErrorOut, RefreshOut

router = APIRouter(
    prefix="/api/refresh", tags=["refresh"], dependencies=[Depends(require_token)]
)
ERRORS: dict[int | str, dict[str, Any]] = {
    400: {
        "model": ErrorOut,
        "description": "The environment cannot be told, or is another one; the checked-out "
        "branch holds another environment; a partial export for the branch of an environment",
    },
    401: {"description": "Missing or wrong session token"},
    404: {"model": ErrorOut, "description": "Unknown environment"},
    409: {
        "model": ErrorOut,
        "description": "Uncommitted chain changes are in the way, or the checked-out branch "
        "is protected",
    },
    422: {"model": ErrorOut, "description": "Not an export, or a git error"},
}
EXPORT = Body(media_type="application/xml", description="the export file, as it is")
SOURCE = Query("export.xml", description="the name of the file, for the commit message")
ENV = Query(None, description="the environment; default: told by the letter of the names")
HERE = Query(
    False,
    description="onto the checked-out branch instead of the environment's: somebody's work, "
    "no branch of another environment and no protected one",
)
PARTIAL = Query(
    False,
    description="the export holds some folders only and the others stay; not for the branch "
    "of an environment, which holds its full export",
)


@router.post(
    "/preview",
    response_model=RefreshOut,
    responses=ERRORS,
    summary="What the export changes on the branch it goes onto (nothing written)",
)
def preview(
    data: bytes = EXPORT,
    source: str = SOURCE,
    env: str | None = ENV,
    here: bool = HERE,
    partial: bool = PARTIAL,
    repo: ChainRepo = Depends(get_repo),
) -> RefreshOut:
    result = refresh(repo, data, source=source, env=env, here=here, partial=partial)
    return RefreshOut.model_validate(result.to_json())


@router.post(
    "/apply",
    response_model=RefreshOut,
    responses=ERRORS,
    summary="Check the branch out, overwrite it with the export, commit",
)
def apply(
    request: Request,
    data: bytes = EXPORT,
    source: str = SOURCE,
    env: str | None = ENV,
    commit: bool = Query(True, description="false leaves the result in the working tree"),
    here: bool = HERE,
    partial: bool = PARTIAL,
    repo: ChainRepo = Depends(get_repo),
) -> RefreshOut:
    with request.app.state.write_lock:
        result = refresh(
            repo, data, source=source, env=env, apply=True, commit=commit, here=here,
            partial=partial,
        )  # fmt: skip
    return RefreshOut.model_validate(result.to_json())
