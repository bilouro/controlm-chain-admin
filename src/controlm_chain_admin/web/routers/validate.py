"""GET /api/validate and /api/links/{name}."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.graph import load_links
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.core.validate import validate
from controlm_chain_admin.web.deps import get_repo
from controlm_chain_admin.web.schemas import ErrorOut, LinkOut, ValidateOut

router = APIRouter(prefix="/api", tags=["validate"])
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorOut, "description": "Unknown folder, job or link"}
}


@router.get("/validate", response_model=ValidateOut, summary="Validate the repository")
def validate_repo(repo: ChainRepo = Depends(get_repo)) -> ValidateOut:
    return ValidateOut.model_validate(validate(repo).to_json())


@router.get(
    "/links/{name}", response_model=LinkOut, responses=NOT_FOUND, summary="One link by condition name"
)
def link_by_name(name: str, repo: ChainRepo = Depends(get_repo)) -> LinkOut:
    links = load_links(repo)
    if name not in links:
        raise ModelError(f"no link named {name!r}")
    return LinkOut.model_validate(links[name].to_json())
