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
    volatile_attributes: list[str] = Field(
        default_factory=list,
        description="the technical attributes: kept in meta, never compared, never an exception",
    )


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


class ExceptionOut(BaseModel):
    attributes: dict[str, str | None] = Field(
        description="attribute -> value used in that environment; null: left out there"
    )
    variables: dict[str, str | None] = Field(
        description="variable -> its value in that environment; null: not there"
    )
    elements: dict[str, dict[str, Any] | None] = Field(
        default_factory=dict,
        description="line (by its locator) -> the attributes it has there, a whole line only "
        "that environment has (with 'after': the sibling before it), or null: not there",
    )


class FolderDetail(BaseModel):
    folder: dict[str, Any] = Field(description="folder.json plus its volatile metadata under 'meta'")
    jobs: list[JobSummary]
    links: list[LinkOut]
    graph: GraphOut
    groups: dict[str, dict[str, str]] = {}
    predecessors: list[RelationOut] = []
    successors: list[RelationOut] = []
    exceptions: dict[str, ExceptionOut] = Field(
        {}, description="what each environment uses instead of the base, by environment"
    )


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
    exceptions: dict[str, ExceptionOut] = Field(
        {}, description="what each environment uses instead of the base, by environment"
    )


class EffectOut(BaseModel):
    node: str
    action: str = Field(description="add | remove | change")
    element: str = Field(description='e.g. OUTCOND A-B_OK SIGN="+", INCOND A-B_OK, JOBNAME')
    before: str | None = None
    after: str | None = None


class FixOut(BaseModel):
    kind: str = Field(description="the same for this fix of every finding, to fix many at once")
    title: str
    label: str = Field(description="what the fix does to this finding")
    explanation: str
    op: str = Field(description="operation for POST /api/changes/preview (batch: several)")
    params: dict[str, Any]
    effects: list[EffectOut] = Field([], description="what the jobs will look like after it")


class FindingOut(BaseModel):
    severity: str
    code: str
    node: str
    name: str
    message: str
    link: str = Field("", description="id of the link it is about; empty when none")
    fixes: list[FixOut] = []


class ExplanationOut(BaseModel):
    looks_for: str = Field(description="what the check looks for")
    why: str = Field(description="why it matters")
    fix: str = Field(description="what its fix does, and what follows from it")


class ValidateOut(BaseModel):
    links: int
    nodes: int
    counts: dict[str, int]
    findings: list[FindingOut]
    explanations: dict[str, ExplanationOut] = Field(
        {}, description="what each code of the findings means, by code"
    )


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
    op: str = Field(
        description="operation name, e.g. set-attributes, link, unlink, rename-job, receive, "
        "take (params: base, the checked-out branch; head; items such as job:F/J, "
        "attr:F/J@ATTR, var:F/J@%%NAME, rel:F/J@LINK, group:F/J@TAG, folder:F, link:LINK, "
        "const:ENV@NAME, exception:ENV@F/J; theirs, conflicting items to take anyway; commits; "
        "merge_base)"
    )
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
    kind: str = Field(description="branch | remote | tag | commit | worktree | export")
    sha: str | None = None
    subject: str | None = None
    date: str | None = None


class GitStateOut(BaseModel):
    current: str | None = Field(description="checked-out branch; null when detached")
    head: str
    dirty: bool
    changes: int = Field(0, description="uncommitted chain files (derived index.json left out)")
    refs: list[RefOut]


class PendingOut(BaseModel):
    branch: str | None = None
    head: str
    files: list[str]
    summary: dict[str, Any]
    message: str = Field(description="suggested commit message; empty when nothing is pending")
    fingerprint: str = Field(description="send it back with the commit")
    protected: bool = Field(description="edits are refused here: the commit needs a new branch")


class CommitRequest(BaseModel):
    message: str
    fingerprint: str
    branch: str | None = Field(None, description="create this branch and commit there")


class CommittedOut(BaseModel):
    sha: str
    branch: str | None = None
    subject: str


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
    name_only: bool = Field(
        False, description="the same jobs use the condition the same way under another name"
    )
    counterpart: str | None = Field(
        None, description="that other name: the new one when removed, the old one when added"
    )


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
    name_only: bool = Field(False, description="every change of it only renames a condition")


class LinkChangeOut(BaseModel):
    link: str
    change: str
    before: str | None = None
    after: str | None = None
    name_only: bool = Field(
        False, description="renamed, or the same jobs use it the same way under another link"
    )
    counterpart: str | None = Field(None, description="the name of that other link")


class ConstantChangeOut(BaseModel):
    env: str
    name: str
    before: str | None = None
    after: str | None = None


class ExceptionChangeOut(BaseModel):
    env: str
    node: str = Field(description="FOLDER/ or FOLDER/JOB")
    before: dict[str, Any] | None = Field(
        None, description='{"set": {ATTR: value}, "variables": {%%NAME: value}}'
    )
    after: dict[str, Any] | None = None


class TranslationOut(BaseModel):
    source: str = Field(description="the environment of the head")
    target: str = Field(description="the environment of the base, whose terms are used")
    values: int = Field(description="whole values the map knows")
    texts: int = Field(description="values with a word the map knows")
    letters: int = Field(description="names with the letter of the environment")
    links: int = Field(description="conditions called as the target calls them")
    warnings: list[str] = Field(description="values the map could not turn into one of the base")


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
    exceptions: list[ExceptionChangeOut] = []
    environments: list[str] | None = Field(
        None,
        description="[the base's environment, the head's] when the two refs are the branches "
        "of two environments; null otherwise",
    )
    environment: str | None = Field(
        None,
        description="the one environment both refs hold, where each environment has its "
        "branch: what a package of the two is for; null otherwise",
    )
    translation: TranslationOut | None = Field(
        None,
        description="between two environments: what was read in the base's terms before "
        "comparing, so it is not a difference; null when compared as stored",
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
    taken: list[str] | None = Field(
        None, description="the items packaged; null: everything that differs"
    )
    source: str | None = Field(
        None, description="the environment of the head, when it is another one than env"
    )


class InstallationOut(BaseModel):
    env: str
    tag: str
    sha: str
    behind: int = Field(description="commits of the release after the installed one")


class ReleaseOut(BaseModel):
    name: str
    branch: str
    sha: str
    local: bool
    remote: bool = Field(description="the branch is on the remote too")
    ahead: int = Field(description="commits the trunk does not have")
    trunk_behind: int = Field(description="trunk commits the release does not have")
    installed: list[InstallationOut] = Field(description="latest installation per environment")
    closable: bool = Field(description="last commit installed in production, trunk merged")


class EnvBranchOut(BaseModel):
    env: str
    branch: str
    local: bool
    remote: bool = Field(description="the branch is on the remote too")


class BranchOut(BaseModel):
    branch: str
    local: bool
    remote: bool = Field(description="the branch is on the remote too")


class StashOut(BaseModel):
    ref: str
    branch: str | None = Field(None, description="where the stash was made")
    message: str


class WorkspaceOut(BaseModel):
    branch: str | None = Field(description="checked-out branch; null when detached")
    head: str
    trunk: str = Field(description="the branch that mirrors production; never edited")
    prefix: str = Field(description="prefix of the release branches, e.g. release/")
    editable: bool
    reason: str | None = Field(None, description="why edits are refused here")
    release: str | None = Field(None, description="name of the checked-out release")
    changes: int = Field(description="uncommitted chain files")
    releases: list[ReleaseOut]
    stashes: list[StashOut]
    environments: list[str]
    production: str
    remote: str | None = None
    upstream: str | None = None
    ahead: int = Field(description="commits not pushed to the upstream")
    behind: int = Field(description="commits of the upstream not pulled (as of the last fetch)")
    env_branches: list[EnvBranchOut] = Field(
        description="the branch of every environment but production's, where it exists"
    )
    branches: list[BranchOut] = Field(
        description="every other branch: not the trunk, an environment's, a release or the map"
    )


class ActionOut(BaseModel):
    message: str
    workspace: WorkspaceOut


class StartReleaseRequest(BaseModel):
    name: str = Field(description="the release name; the branch is <prefix><name>")
    stash: bool = Field(False, description="stash uncommitted chain files first")


class StartBranchRequest(BaseModel):
    name: str = Field(description="the whole name of the branch, e.g. work/uat-next")


class SwitchRequest(BaseModel):
    branch: str
    stash: bool = Field(False, description="stash uncommitted chain files first")


class PopRequest(BaseModel):
    ref: str = Field(description="e.g. stash@{0}")


class DiscardRequest(BaseModel):
    fingerprint: str = Field(description="fingerprint of GET /api/git/pending")


class InstalledRequest(BaseModel):
    env: str
    release: str | None = Field(None, description="default: the checked-out release")
    sha: str | None = Field(None, description="the installed commit; default: the release tip")


class IntakeRequest(BaseModel):
    xml: str = Field(description="the export, as text")
    env: str | None = Field(None, description="its environment; default: told by the names")
    full: bool | None = Field(
        None, description="every folder of the environment; default: more than half of them"
    )


class DecisionOut(BaseModel):
    id: str
    kind: str = Field(
        description="learn | set-value | adopt | constant | group | value | element | removed "
        "| added | absent | unmatched"
    )
    options: list[str]
    default: str
    known: bool = Field(
        False,
        description="already an exception of the environment: the default keeps it, change "
        "makes the base take it, ignore drops it",
    )
    node: str | None = None
    field: str | None = None
    constant: str | None = None
    current: str | None = Field(None, description="the repository value (neutral)")
    expected: str | None = Field(None, description="the value of the constant there")
    incoming: str | None = Field(None, description="the export value (neutral)")
    count: int = 1
    suggested: str | None = Field(None, description="name of a new constant (option new)")
    values: dict[str, str | None] | None = Field(
        None, description="the value of the new constant in each environment (option new)"
    )
    inline: bool = Field(False, description="the new constant replaces a token inside a text")
    members: list[DecisionOut] = Field(
        default_factory=list,
        description="of a group: the decision of each job on its own, to choose apart from it",
    )
    nodes: list[str] = Field(
        default_factory=list,
        description="of a value no constant has: the folders and jobs (only in the export) it is in",
    )


class FolderIntakeOut(BaseModel):
    name: str
    status: str = Field(description="new | changed | same")
    jobs_added: list[str]
    jobs_removed: list[str]
    jobs_changed: list[str]


class IntakeOut(BaseModel):
    env: str
    evidence: list[str]
    partial: bool = Field(description="some folders of the repository are not in the export")
    full: bool = Field(False, description="taken as every folder of the environment")
    folders: list[FolderIntakeOut]
    decisions: list[DecisionOut]
    unresolved: list[str] = Field(description="values no constant explains: they block")
    warnings: list[str]
    skipped: list[str] = Field(description="folders of other applications")


class EnvironmentOut(BaseModel):
    name: str
    letter: str
    display: str


class ConstantOut(BaseModel):
    name: str
    spec: str = Field(description="what it replaces: ATTR, TAG/@ATTR or TAG[K=V]/@ATTR")
    values: dict[str, str | None] = Field(description="value per environment; null: missing")
    missing: list[str] = Field(description="environments without a value")
    uses: int = Field(description="placeholders in jobs, folders and exceptions")
    nodes: list[str] = Field(description="FOLDER/JOB or FOLDER/ that use it")


class EnvironmentsOut(BaseModel):
    environments: list[EnvironmentOut]
    constants: list[ConstantOut]


# ---------------------------------------------------------------- assistant


class AssistantOut(BaseModel):
    available: bool
    reason: str | None = Field(None, description="why there is no assistant, and how to start one")
    agent: str
    model: str | None = Field(None, description="provider/model; null: the one Kilo is set to")
    directory: str | None = Field(None, description="the Kilo project the conversations run in")


class AssistantSessionOut(BaseModel):
    id: str


class AssistantPartOut(BaseModel):
    kind: str = Field(description="text, tool or error")
    text: str | None = None
    tool: str | None = Field(None, description="a ctmchain tool: find, show, preview, apply...")
    status: str | None = Field(None, description="of a tool: pending, running, completed, error")
    input: Any = None
    output: str | None = Field(None, description="what the tool gave back (cut when long)")


class AssistantMessageOut(BaseModel):
    id: str
    role: str
    parts: list[AssistantPartOut]


class FieldChangeOut(BaseModel):
    where: str
    field: str | None
    before: str | None
    after: str | None


class StepsPreviewOut(BaseModel):
    preview_id: str | None
    summary: str
    warnings: list[str]
    changes: list[FieldChangeOut]
    files: list[str]
    diff: str


class ApprovalOut(BaseModel):
    id: str
    tool: str
    input: Any = None
    preview: StepsPreviewOut | None = Field(
        None, description="this repository's preview of an apply's steps"
    )
    problem: str | None = Field(None, description="why the apply would not do what was shown")


class ConversationOut(BaseModel):
    id: str
    busy: bool
    messages: list[AssistantMessageOut]
    approvals: list[ApprovalOut]


class PromptRequest(BaseModel):
    text: str = Field(min_length=1)


class ApprovalRequest(BaseModel):
    approve: bool


class AckOut(BaseModel):
    ok: bool = True



class MapEntryOut(BaseModel):
    name: str
    key: str = Field(description="ATTR, TAG/@ATTR or TAG[K=V]/@ATTR")
    values: dict[str, str] = Field(description="environment -> what it has there")
    inline: bool = Field(False, description="a word inside a text, not the whole value")


class EnvMapOut(BaseModel):
    branch: str = Field(description="the branch the map is kept on")
    letters: dict[str, str] = Field(description="environment -> the letter of its names")
    branches: dict[str, str] = Field(description="environment -> its branch, where there is one")
    version: int
    entries: list[MapEntryOut]


class DerivedEntryOut(MapEntryOut):
    nodes: int = Field(description="folders and jobs that show these values")


class KnownEntryOut(BaseModel):
    name: str
    nodes: int


class LeftOutOut(BaseModel):
    key: str
    values: dict[str, str]
    nodes: int
    inline: bool = False


class DerivedOut(BaseModel):
    environments: list[str] = Field(description="the environments whose branches were read")
    entries: list[DerivedEntryOut] = Field(description="what the map lacks")
    known: list[KnownEntryOut] = Field(description="entries the map has already")
    left_out: list[LeftOutOut] = Field(description="values fewer than min_nodes nodes show")
    applied: bool = Field(description="whether the entries were written on the map's branch")


class DeriveRequest(BaseModel):
    keys: list[str] = Field([], description="more attributes whose whole value varies")
    text_keys: list[str] = Field([], description="attributes whose texts differ in one word")
    min_nodes: int = Field(2, ge=1, description="nodes that must show the same values")


class SuggestionOut(BaseModel):
    key: str
    nodes: int
    tuples: int = Field(description="distinct sets of whole values")
    words: int | None = Field(
        None, description="distinct sets of the one word that differs; null when more differs"
    )
    text: bool = Field(description="the values are texts that differ in one word")
    example: dict[str, str]


class SuggestionsOut(BaseModel):
    total: int
    suggestions: list[SuggestionOut]


class FollowersOut(BaseModel):
    environments: list[str] = Field(description="the environments whose branches were read")
    followers: dict[str, int] = Field(
        description="entry -> the places (an attribute of a job, or of an element inside it) "
        "whose values are the entry's"
    )
    unmapped: int = Field(description="places of a mapped key whose values no entry says")


class MapEntryRequest(BaseModel):
    key: str = Field(min_length=1, description="ATTR, TAG/@ATTR or TAG[K=V]/@ATTR")
    values: dict[str, str] = Field(description="environment -> value; two or more")
    name: str | None = Field(None, description="the name of the entry; default: key.N")
    inline: bool = Field(False, description="a word inside a text, not the whole value")


class RenameEntryRequest(BaseModel):
    name: str = Field(min_length=1, description="the new name")


class ImportedOut(BaseModel):
    folders: int
    jobs: int
    links: int
    skipped: int = Field(description="folders of other applications, left out")
    literal_marks: int
    suspicious_values: int


class RefreshOut(BaseModel):
    env: str
    branch: str = Field(
        description="the branch the export goes onto: the environment's, or the checked-out one"
    )
    work: bool = Field(description="the branch is somebody's work, not the environment's own")
    partial: bool = Field(description="the folders the export does not have stay")
    new_branch: bool = Field(description="the branch is not there yet: apply creates it")
    source: str = Field(description="the name of the export file")
    evidence: list[str] = Field(description="how the environment was told")
    files_changed: int
    unchanged: bool = Field(description="the branch holds this export already")
    applied: bool
    commit: str | None = Field(None, description="the commit made by apply")
    imported: ImportedOut
    comparison: ComparisonOut = Field(description="the branch (base) against the export (head)")
