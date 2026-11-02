"""POST /api/intake — what an export of one environment brings; receive it with the change
``receive`` (POST /api/changes/preview|apply)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from controlm_chain_admin.core.intake import analyze
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.deps import get_repo, require_token
from controlm_chain_admin.web.schemas import ErrorOut, IntakeOut, IntakeRequest

router = APIRouter(prefix="/api", tags=["intake"], dependencies=[Depends(require_token)])
ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing or wrong session token"},
    404: {"model": ErrorOut, "description": "Unknown environment"},
    422: {"model": ErrorOut, "description": "Not an export, or its environment cannot be told"},
}


@router.post(
    "/intake",
    response_model=IntakeOut,
    responses=ERRORS,
    summary="The environment of an export, the values to learn and every difference",
)
def intake(body: IntakeRequest, repo: ChainRepo = Depends(get_repo)) -> IntakeOut:
    return IntakeOut.model_validate(analyze(repo, body.xml.encode("utf-8"), body.env).to_json())
