"""Response models of the API. They mirror core structures; nothing here computes anything."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LetterRuleOut(BaseModel):
    prefixes: list[str]
    attributes: list[str]


class RepoInfo(BaseModel):
    application: str
    environments: list[str]
    folders: int
    jobs: int
    letter_rule: LetterRuleOut
    root: str


class FolderSummary(BaseModel):
    name: str
    sub_application: str | None = None
    description: str | None = None
    jobs: int
    links: int


class FolderList(BaseModel):
    total: int
    items: list[FolderSummary]


class JobSummary(BaseModel):
    id: str = Field(description="file stem: JOBNAME, or JOBNAME~n for a repeated name")
    name: str
    task_type: str | None = None


class LinkOut(BaseModel):
    id: str
    name: str
    standard: str | None = None
    from_: list[str] = Field(alias="from")
    to: list[str]
    cleanup: list[str]
    docond: list[dict[str, Any]]
    odates: list[str]
    and_or: list[str]
    kind: str
    external: bool

    model_config = {"populate_by_name": True}


class EdgeOut(BaseModel):
    from_: str = Field(alias="from")
    to: str
    name: str
    conditional: bool

    model_config = {"populate_by_name": True}


class LooseEnd(BaseModel):
    node: str
    name: str


class GraphOut(BaseModel):
    folder: str
    nodes: list[str]
    edges: list[EdgeOut]
    externals: list[str]
    dangling: list[LooseEnd]
    unconsumed: list[LooseEnd]


class PeerOut(BaseModel):
    node: str
    and_or: str | None = None
    cleanup: bool = False
    conditional: str | None = None


class RelationOut(BaseModel):
    link: str
    name: str
    peers: list[PeerOut]
    odate: str
    and_or: str | None = None
    cleanup: bool = False
    sign: str = ""
    on_code: str | None = None
    kind: str
    external: bool


class FolderDetail(BaseModel):
    folder: dict[str, Any] = Field(description="folder.json plus its volatile metadata under 'meta'")
    jobs: list[JobSummary]
    links: list[LinkOut]
    graph: GraphOut
    groups: dict[str, dict[str, str]] = {}
    predecessors: list[RelationOut] = []
    successors: list[RelationOut] = []


class JobDetail(BaseModel):
    id: str
    folder: str
    name: str
    groups: dict[str, dict[str, str]]
    meta: dict[str, str]
    on: list[dict[str, Any]]
    links: list[LinkOut]
    raw: dict[str, Any]
    predecessors: list[RelationOut] = []
    successors: list[RelationOut] = []


class FindingOut(BaseModel):
    severity: str
    code: str
    node: str
    name: str
    message: str


class ValidateOut(BaseModel):
    links: int
    nodes: int
    counts: dict[str, int]
    findings: list[FindingOut]


class ErrorOut(BaseModel):
    error: str
    message: str
    detail: Any = None


class Neighbour(BaseModel):
    node: str | None = Field(description="FOLDER/JOB or FOLDER/; null when outside the repository")
    link: str
    name: str
    external: bool


class TableJob(BaseModel):
    id: str
    name: str
    task_type: str | None = None
    node_id: str | None = None
    application: str | None = None
    sub_application: str | None = None
    description: str | None = None
    predecessors: list[Neighbour]
    successors: list[Neighbour]


class TableFolder(BaseModel):
    name: str
    application: str | None = None
    sub_application: str | None = None
    description: str | None = None
    predecessors: list[Neighbour]
    successors: list[Neighbour]
    jobs: list[TableJob]


class TableOut(BaseModel):
    folders: list[TableFolder]


class ChangeRequest(BaseModel):
    op: str = Field(description="operation name, e.g. set-attributes, link, unlink, rename-job")
    params: dict[str, Any] = {}


class ApplyRequest(ChangeRequest):
    fingerprint: str = Field(description="fingerprint returned by the preview")


class ChangedFile(BaseModel):
    path: str
    change: str


class ChangePreview(BaseModel):
    summary: str
    warnings: list[str]
    files: list[ChangedFile]
    diff: str
    fingerprint: str


class ApplyOut(BaseModel):
    written: int
    deleted: int
