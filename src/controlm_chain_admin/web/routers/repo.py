"""GET /api/repo — summary of the chain repository."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from controlm_chain_admin.core.links import folder_names
from controlm_chain_admin.core.repo import ChainRepo, read_json
from controlm_chain_admin.web.deps import get_repo
from controlm_chain_admin.web.schemas import LetterRuleOut, RepoInfo

router = APIRouter(prefix="/api", tags=["repo"])


@router.get("/repo", response_model=RepoInfo, summary="Repository summary")
def repo_info(repo: ChainRepo = Depends(get_repo)) -> RepoInfo:
    folders = folder_names(repo)
    jobs = sum(len(read_json(repo.folder_file(f)).get("jobs", [])) for f in folders)
    rule = repo.config.letter_rule
    return RepoInfo(
        application=repo.config.application,
        environments=list(repo.config.environments),
        folders=len(folders),
        jobs=jobs,
        letter_rule=LetterRuleOut(prefixes=list(rule.prefixes), attributes=list(rule.attributes)),
        root=str(repo.root),
        volatile_attributes=list(repo.config.volatile_attributes),
    )
