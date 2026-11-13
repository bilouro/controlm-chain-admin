"""GET /api/resources — the CONTROL and QUANTITATIVE resources, with the jobs that use each.

A resource is added, changed, renamed or removed through the changes API (``set-resource``,
``remove-resource``, ``rename-resource``), previewed like any edit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.core.resources import usage
from controlm_chain_admin.web.deps import get_repo
from controlm_chain_admin.web.schemas import ResourcesOut

router = APIRouter(prefix="/api", tags=["resources"])


@router.get(
    "/resources",
    response_model=ResourcesOut,
    summary="Every resource of the repository with the folders and jobs that use it",
)
def resources(
    repo: ChainRepo = Depends(get_repo),
    name: str | None = Query(None, description="only the resources whose name has this text"),
) -> ResourcesOut:
    uses = [use.to_json() for use in usage(repo)]
    if name:
        uses = [use for use in uses if name.upper() in str(use["name"]).upper()]
    return ResourcesOut.model_validate({"resources": uses})
