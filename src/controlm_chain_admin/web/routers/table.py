"""GET /api/table — folders and jobs with their predecessors and successors."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from controlm_chain_admin.core.relations import chain_table
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.deps import get_repo
from controlm_chain_admin.web.schemas import TableOut

router = APIRouter(prefix="/api", tags=["table"])


@router.get("/table", response_model=TableOut, summary="Folders and jobs with their neighbours")
def table(
    repo: ChainRepo = Depends(get_repo),
    env: str | None = Query(None, description="an environment: its nodes, with its values"),
) -> TableOut:
    return TableOut.model_validate({"folders": chain_table(repo, env)})
