"""GET /api/folders and /api/folders/{name}."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from controlm_chain_admin.core.attribute_groups import group_attributes
from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.graph import folder_graph
from controlm_chain_admin.core.inspect import show_node
from controlm_chain_admin.core.links import INDEX_FILE, folder_names, rebuild_links
from controlm_chain_admin.core.relations import all_relations
from controlm_chain_admin.core.repo import ChainRepo, read_json
from controlm_chain_admin.web.deps import get_repo
from controlm_chain_admin.web.schemas import (
    ErrorOut,
    FolderDetail,
    FolderList,
    FolderSummary,
    GraphOut,
    JobSummary,
    LinkOut,
    RelationOut,
)

router = APIRouter(prefix="/api", tags=["folders"])
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorOut, "description": "Unknown folder, job or link"}
}


def _links_index(repo: ChainRepo, folder: str) -> list[dict[str, Any]]:
    path = repo.folder_dir(folder) / INDEX_FILE
    if not path.exists():
        rebuild_links(repo)
    entries: list[dict[str, Any]] = read_json(path).get("links", []) if path.exists() else []
    return entries


@router.get("/folders", response_model=FolderList, summary="List folders")
def list_folders(
    repo: ChainRepo = Depends(get_repo),
    q: str = Query("", description="case-insensitive substring of the folder name"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> FolderList:
    names = [n for n in folder_names(repo) if q.lower() in n.lower()]
    items = []
    for name in names[offset : offset + limit]:
        data = read_json(repo.folder_file(name))
        items.append(
            FolderSummary(
                name=name,
                sub_application=data.get("SUB_APPLICATION"),
                description=data.get("DESCRIPTION"),
                jobs=len(data.get("jobs", [])),
                links=len(_links_index(repo, name)),
            )
        )
    return FolderList(total=len(names), items=items)


@router.get(
    "/folders/{name}",
    response_model=FolderDetail,
    responses=NOT_FOUND,
    summary="Folder with jobs, links and graph",
)
def folder_detail(name: str, repo: ChainRepo = Depends(get_repo)) -> FolderDetail:
    if not repo.folder_file(name).is_file():
        raise ModelError(f"unknown folder {name!r}")
    folder = show_node(repo, f"{name}/")
    jobs = []
    for job_id in (str(j) for j in folder.get("jobs", [])):
        job = read_json(repo.job_file(name, job_id))
        jobs.append(
            JobSummary(id=job_id, name=job.get("JOBNAME", job_id), task_type=job.get("TASKTYPE"))
        )
    links = [LinkOut.model_validate(entry) for entry in _links_index(repo, name)]
    graph = GraphOut.model_validate(folder_graph(repo, name).to_json())
    relations = all_relations(repo)[f"{name}/"]
    return FolderDetail(
        folder=folder,
        jobs=jobs,
        links=links,
        graph=graph,
        groups=group_attributes(
            {k: v for k, v in folder.items() if isinstance(v, str) and k != "tag"}
        ),
        predecessors=[RelationOut.model_validate(r.to_json()) for r in relations.predecessors],
        successors=[RelationOut.model_validate(r.to_json()) for r in relations.successors],
    )
