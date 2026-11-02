"""GET /api/environments — the constants of every environment; edits go through the changes
``set-values`` and ``rename-constant``."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from controlm_chain_admin.core.constants import constants_overview
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.deps import get_repo
from controlm_chain_admin.web.schemas import ConstantOut, EnvironmentOut, EnvironmentsOut

router = APIRouter(prefix="/api", tags=["environments"])


@router.get(
    "/environments",
    response_model=EnvironmentsOut,
    summary="Every constant with its value per environment and the nodes that use it",
)
def environments(repo: ChainRepo = Depends(get_repo)) -> EnvironmentsOut:
    envs = [repo.load_env(name) for name in repo.config.environments]
    return EnvironmentsOut(
        environments=[EnvironmentOut(name=e.name, letter=e.letter, display=e.display) for e in envs],
        constants=[ConstantOut.model_validate(row.to_json()) for row in constants_overview(repo)],
    )
