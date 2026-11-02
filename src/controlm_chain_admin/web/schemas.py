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


class RefOut(BaseModel):
    name: str
    kind: str = Field(description="branch | remote | tag | commit | worktree")
    sha: str | None = None
    subject: str | None = None
    date: str | None = None


class GitStateOut(BaseModel):
    current: str | None = Field(description="checked-out branch; null when detached")
    head: str
    dirty: bool
    refs: list[RefOut]


class CommitOut(BaseModel):
    sha: str
    subject: str
    author: str
    date: str
    merge: bool = Field(False, description="merge commits cannot be selected")


class ValueChangeOut(BaseModel):
    name: str
    before: str | None = None
    after: str | None = None


class RelationChangeOut(BaseModel):
    direction: str
    link: str
    name: str
    change: str
    peers_before: list[str]
    peers_after: list[str]
    details: list[ValueChangeOut]


class NodeChangeOut(BaseModel):
    node: str
    kind: str
    change: str = Field(description="added | removed | modified | renamed | moved")
    previous: str | None = None
    attributes: list[ValueChangeOut]
    variables: list[ValueChangeOut]
    relations: list[RelationChangeOut]
    groups: list[str]
    jobs_added: list[str]
    jobs_removed: list[str]
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    diff: str
    commits: list[str] = Field([], description="compared commits that changed it, newest first")


class LinkChangeOut(BaseModel):
    link: str
    change: str
    before: str | None = None
    after: str | None = None


class ConstantChangeOut(BaseModel):
    env: str
    name: str
    before: str | None = None
    after: str | None = None


class ComparisonOut(BaseModel):
    base: RefOut
    head: RefOut
    merge_base: str | None = None
    summary: dict[str, Any]
    commits: list[CommitOut]
    folders: list[NodeChangeOut]
    jobs: list[NodeChangeOut]
    links: list[LinkChangeOut]
    constants: list[ConstantChangeOut]
    rules_changed: bool
    metadata_files_changed: int
    selected: list[str] | None = Field(
        None, description="commits compared, newest first; null when every commit is"
    )


class PackageFolderOut(BaseModel):
    name: str
    jobs: int
    reasons: list[str]


class PackageOut(BaseModel):
    base: RefOut
    head: RefOut
    merge_base: str | None = None
    env: str
    commits: list[CommitOut]
    selected: list[str] | None = None
    folders: list[PackageFolderOut]
    warnings: list[str]
    findings: list[FindingOut] = Field(description="validation findings the base side has not")
    filename: str
    size: int = Field(description="bytes of the XML file; 0 when nothing changed")
