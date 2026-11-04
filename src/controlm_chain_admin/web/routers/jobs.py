"""GET /api/jobs/{folder}/{job}."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from controlm_chain_admin.core.attribute_groups import group_attributes
from controlm_chain_admin.core.graph import load_links
from controlm_chain_admin.core.inspect import show_node
from controlm_chain_admin.core.links import NodeRef
from controlm_chain_admin.core.overrides import node_exceptions
from controlm_chain_admin.core.relations import all_relations
from controlm_chain_admin.core.repo import ChainRepo
from controlm_chain_admin.web.deps import get_repo
from controlm_chain_admin.web.schemas import (
    ErrorOut,
    ExceptionOut,
    JobDetail,
    LinkOut,
    RelationOut,
)

router = APIRouter(prefix="/api", tags=["jobs"])
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorOut, "description": "Unknown folder, job or link"}
}


@router.get(
    "/jobs/{folder}/{job}", response_model=JobDetail, responses=NOT_FOUND, summary="Job detail"
)
def job_detail(
    folder: str,
    job: str,
    repo: ChainRepo = Depends(get_repo),
    env: str | None = Query(None, description="an environment: its nodes, with its values"),
) -> JobDetail:
    data = show_node(repo, f"{folder}/{job}", env)
    meta = data.pop("meta", {})
    attrs = {k: v for k, v in data.items() if isinstance(v, str)}
    ref = NodeRef(folder, job)
    relations = all_relations(repo)[str(ref)]
    links = [
        LinkOut.model_validate(link.to_json())
        for link in load_links(repo).values()
        if ref in link.consumers
        or ref in link.all_producers
        or ref in link.deleters
        or any(node == ref for node, _ in link.docond_delete)
    ]
    return JobDetail(
        id=job,
        folder=folder,
        name=attrs.get("JOBNAME", job),
        groups=group_attributes(attrs),
        meta=meta,
        on=list(data.get("ON", [])),
        links=links,
        raw=data,
        predecessors=[RelationOut.model_validate(r.to_json()) for r in relations.predecessors],
        successors=[RelationOut.model_validate(r.to_json()) for r in relations.successors],
        exceptions={
            env: ExceptionOut(attributes=o.attributes, variables=o.variables)
            for env, o in node_exceptions(repo, f"{folder}/{job}").items()
        },
    )
