"""POST /api/changes/preview and /api/changes/apply — every edit goes through a change set."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from controlm_chain_admin.core.errors import ChangeConflict
from controlm_chain_admin.core.refactor import apply, fingerprint, run_operation
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.core.workspace import ensure_editable
from controlm_chain_admin.web.deps import get_repo, require_token
from controlm_chain_admin.web.schemas import (
    ApplyOut,
    ApplyRequest,
    ChangePreview,
    ChangeRequest,
    ErrorOut,
)

router = APIRouter(prefix="/api/changes", tags=["changes"], dependencies=[Depends(require_token)])
ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing or wrong session token"},
    409: {
        "model": ErrorOut,
        "description": "The repository changed since the preview, or the branch is protected",
    },
    422: {"model": ErrorOut, "description": "The change is not allowed"},
}


@router.post("/preview", response_model=ChangePreview, responses=ERRORS, summary="Preview a change")
def preview(body: ChangeRequest, repo: ChainRepo = Depends(get_repo)) -> ChangePreview:
    change = run_operation(repo, body.op, body.params)
    return ChangePreview(
        summary=change.summary,
        warnings=list(change.warnings),
        files=change.to_json()["files"],
        diff=change.diff(),
        fingerprint=fingerprint(change),
    )


@router.post("/apply", response_model=ApplyOut, responses=ERRORS, summary="Apply a previewed change")
def apply_change(
    body: ApplyRequest, request: Request, repo: ChainRepo = Depends(get_repo)
) -> ApplyOut:
    ensure_editable(repo)
    with request.app.state.write_lock:
        change = run_operation(repo, body.op, body.params)
        if fingerprint(change) != body.fingerprint:
            raise ChangeConflict("the repository changed since the preview; review the change again")
        result = apply(repo, change)
    return ApplyOut(written=result.written, deleted=result.deleted)
