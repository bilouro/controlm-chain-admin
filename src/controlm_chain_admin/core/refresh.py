"""Refresh the branch of an environment from its full export.

Each environment has a branch (the trunk for production, ``env/<name>`` for the others) that
holds what its last full export said, and nothing else. A refresh shows what the new export
differs in from the branch; applied, the export overwrites the branch: folders and jobs it no
longer has go, and the branch exports the same bytes again.

An export can also go onto the checked-out branch when that is somebody's work (a branch
started from an environment's, to see what an export brings before the environment's own
branch takes it): the environment's branch stays as it is, and the two can be compared.

An export of some folders only (a package imported into the environment) goes onto either:
its folders replace the branch's and the others stay. When it is not said, a file with less
than half the folders of the branch is read that way (:data:`Refresh.looks_partial`).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.compare import Comparison, diff_snapshots
from controlm_chain_admin.core.compare import render_text as compare_render
from controlm_chain_admin.core.environments import (
    branch_exists,
    branch_of_env,
    current_branch,
    env_of_ref,
    export_subject,
    held_env,
)
from controlm_chain_admin.core.errors import (
    ChainError,
    GitError,
    ProtectedBranch,
    UncommittedChanges,
)
from controlm_chain_admin.core.history import RefInfo, _git, chain_changes, resolve, snapshot
from controlm_chain_admin.core.intake import detect_env
from controlm_chain_admin.core.memfs import copy_file, copy_tree, memory_dir, remove_tree
from controlm_chain_admin.core.ops import ImportReport, import_xml
from controlm_chain_admin.core.repo import ChainRepo, load_repo
from controlm_chain_admin.core.xmlio import parse_xml

_RULES = ("chain.json", "envs")
_CHAIN = ("chain.json", "folders", "meta", "envs")


@dataclass(frozen=True)
class Refresh:
    """What an export changes on the branch it goes onto: its environment's, unless asked."""

    env: str
    branch: str
    new_branch: bool  # the branch does not exist yet: it starts from the trunk's rules
    source: str  # the name of the export file
    evidence: tuple[str, ...]  # how the environment was recognised
    comparison: Comparison  # the branch (base) against the export (head)
    files_changed: int  # chain files that differ, the technical ones included
    report: ImportReport
    applied: bool = False
    commit: str | None = None
    empty: bool = False  # the branch is there and holds no folder yet (the trunk, at first)
    work: bool = False  # the branch is somebody's work, not the environment's own
    partial: bool = False  # the folders the export does not have stay
    export_folders: int = 0  # the folders of the application in the export
    branch_folders: int = 0  # the folders the branch holds now

    @property
    def subject(self) -> str:
        """The message of the commit that holds the export."""
        return export_subject(self.env, self.source, work=self.work, partial=self.partial)

    @property
    def looks_partial(self) -> bool:
        """The export holds less than half the folders of the branch: some folders only."""
        return looks_partial(self.export_folders, self.branch_folders)

    @property
    def removes_most(self) -> bool:
        """Read as a full export, it takes more than half the folders of the branch away."""
        removed = int(self.summary["folders"].get("removed", 0))
        return not self.partial and removed * 2 > self.branch_folders > 0

    @property
    def unchanged(self) -> bool:
        return self.files_changed == 0 and not self.new_branch

    @property
    def summary(self) -> dict[str, Any]:
        return self.comparison.summary()

    def to_json(self) -> dict[str, Any]:
        return {
            "env": self.env,
            "branch": self.branch,
            "work": self.work,
            "partial": self.partial,
            "export_folders": self.export_folders,
            "branch_folders": self.branch_folders,
            "looks_partial": self.looks_partial,
            "removes_most": self.removes_most,
            "new_branch": self.new_branch,
            "source": self.source,
            "evidence": list(self.evidence),
            "files_changed": self.files_changed,
            "unchanged": self.unchanged,
            "applied": self.applied,
            "commit": self.commit,
            "imported": {
                "folders": len(self.report.folders),
                "jobs": self.report.jobs,
                "links": self.report.links,
                "skipped": len(self.report.skipped),
                "literal_marks": len(self.report.literal_marks),
                "suspicious_values": len(self.report.suspicious_values),
            },
            "comparison": self.comparison.to_json(),
        }


def _environment(repo: ChainRepo, data: bytes, env: str | None) -> tuple[str, tuple[str, ...]]:
    """The environment of the export: the one given, checked against the letters of its names."""
    detected, evidence = detect_env(repo, parse_xml(data))
    if env is None:
        if detected is None:
            raise ChainError(
                "the export does not tell its environment (" + "; ".join(evidence) + "): "
                "give it with --env"
            )
        return detected, evidence
    repo.load_env(env)  # an unknown environment is refused here
    if detected is not None and detected != env:
        raise ChainError(
            f"the export looks like {detected}, not {env} (" + "; ".join(evidence) + ")"
        )
    return env, evidence


def looks_partial(export_folders: int, branch_folders: int) -> bool:
    """Less than half the folders of the branch: an export of some folders only."""
    return export_folders * 2 < branch_folders


def _target(repo: ChainRepo, env: str, here: bool) -> tuple[str, bool]:
    """The branch the export goes onto, and whether that is somebody's work: the branch of
    the environment, or with ``here`` the checked-out one when it holds no environment."""
    config = repo.config
    own = branch_of_env(config, env)
    current = current_branch(repo.root)
    if not here or current == own:
        return own, False
    if current is None:
        raise GitError("HEAD is detached: check a branch out to import the export onto it")
    holder = env_of_ref(repo.root, config, current)
    if holder is not None:
        raise ChainError(f"{current} holds {holder}: an export of {env} goes onto {own}")
    reason = config.git_rules.refusal(current)
    if reason:
        raise ProtectedBranch(reason)
    return current, True


def _one_environment(repo: ChainRepo, env: str, branch: str) -> None:
    """Some folders of ``env`` onto a branch of one's own that holds another environment
    would leave it with two."""
    held = held_env(repo.root, repo.config, branch)
    if held not in (None, env):
        raise ChainError(
            f"{branch} holds {held}: some folders of {env} would leave it with two "
            f"environments; start a branch from {branch_of_env(repo.config, env)}"
        )


def _copy(source: Path, target: Path, names: tuple[str, ...]) -> None:
    for name in names:
        origin = source / name
        if origin.is_dir():
            copy_tree(origin, target / name)
        elif origin.is_file():
            copy_file(origin, target / name)


def _files(root: Path) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for name in _CHAIN:
        origin = root / name
        paths = sorted(origin.rglob("*")) if origin.is_dir() else [origin]
        found.update(
            {p.relative_to(root).as_posix(): p.read_bytes() for p in paths if p.is_file()}
        )
    return found


@contextmanager
def _base(root: Path, branch: str, trunk: str, exists: bool) -> Iterator[Path]:
    """What the branch holds now; for a branch to come, the rules of the trunk alone."""
    if exists:
        with snapshot(root, branch) as held:
            yield held
        return
    try:
        resolve(root, trunk)
    except GitError as error:
        raise GitError(
            f"the branch {trunk} has no commit yet: commit the rules (chain.json, envs/) first"
        ) from error
    with snapshot(root, trunk) as held, memory_dir("rules") as tmp:
        _copy(held, tmp, _RULES)
        yield tmp


def _switch(root: Path, branch: str, trunk: str, exists: bool) -> None:
    if current_branch(root) == branch:
        return
    if exists:
        _git(root, "switch", "-q", branch)
    else:
        _git(root, "switch", "-q", "-c", branch, trunk)


def _install(imported: Path, root: Path) -> None:
    """Put the imported files in the working tree, in place of the chain files there."""
    for name in ("folders", "meta"):
        if (root / name).exists():
            remove_tree(root / name)
    (root / "chain.json").unlink(missing_ok=True)
    _copy(imported, root, ("chain.json", "folders", "meta"))


def _commit(root: Path, message: str) -> str | None:
    paths = [p for p in _CHAIN if (root / p).exists() or str(_git(root, "ls-files", "--", p))]
    _git(root, "add", "-A", "--", *paths)
    if not str(_git(root, "status", "--porcelain", "--", *paths)).strip():
        return None
    _git(root, "commit", "-q", "-m", message, "--", *paths)
    return str(_git(root, "rev-parse", "HEAD")).strip()


def refresh(
    repo: ChainRepo,
    data: bytes,
    *,
    source: str = "export.xml",
    env: str | None = None,
    apply: bool = False,
    commit: bool = True,
    here: bool = False,
    partial: bool | None = False,
) -> Refresh:
    """What the full export ``data`` changes on the branch of its environment.

    With ``apply`` the branch is checked out (created from the trunk when it is not there),
    the export overwrites its chain files and the result is committed (left in the working
    tree with ``commit=False``). The same export again changes nothing.

    With ``here`` the export goes onto the checked-out branch instead, which must be
    somebody's work (no environment's branch but the export's own, no protected one).

    ``partial`` keeps the folders the export does not have, on either branch; ``None`` lets
    the file tell: less than half the folders of the branch is some folders only.
    """
    repo = load_repo(repo.root)
    root = repo.root
    env, evidence = _environment(repo, data, env)
    rules = repo.config.git_rules
    branch, work = _target(repo, env, here)
    exists = branch_exists(root, branch)
    if apply and chain_changes(root):
        count = chain_changes(root)
        raise UncommittedChanges(
            f"{count} uncommitted chain file(s): commit or discard them before a refresh", count
        )
    with ExitStack() as stack:
        held = stack.enter_context(_base(root, branch, rules.trunk, exists))
        on_branch = len(list((held / "folders").glob("*/folder.json")))
        imported, report = _imported(stack, held, data, env, partial=bool(partial))
        if partial is None and looks_partial(len(report.folders), on_branch):
            partial = True
            imported, report = _imported(stack, held, data, env, partial=True)
        partial = bool(partial)
        if partial and work:
            _one_environment(repo, env, branch)
        folders, jobs, links, constants, rules_changed, meta, exceptions = diff_snapshots(
            held, imported
        )
        before, after = _files(held), _files(imported)
        changed = sum(1 for path in before.keys() | after.keys()
                      if before.get(path) != after.get(path))  # fmt: skip
        comparison = Comparison(
            RefInfo(branch, "branch", resolve(root, branch).sha if exists else None),
            RefInfo(source, "export", None),
            None, (), folders, jobs, links, constants, rules_changed, meta, None, exceptions,
        )  # fmt: skip
        empty = exists and not any((held / "folders").glob("*/folder.json"))
        result = Refresh(env, branch, not exists, source, evidence, comparison, changed,
                         report, empty=empty, work=work, partial=partial,
                         export_folders=len(report.folders),
                         branch_folders=on_branch)  # fmt: skip
        if not apply or result.unchanged:
            return result
        _switch(root, branch, rules.trunk, exists)
        _install(imported, root)
    sha = _commit(root, result.subject) if commit else None
    return replace(result, applied=True, commit=sha)


def _imported(
    stack: ExitStack, held: Path, data: bytes, env: str, *, partial: bool
) -> tuple[Path, ImportReport]:
    """The export imported beside what the branch holds: over its folders when ``partial``,
    else over its rules alone."""
    imported = stack.enter_context(memory_dir("imported"))
    _copy(held, imported, _CHAIN if partial else _RULES)
    report = import_xml(load_repo(imported), data, env, replace_all=not partial)
    return imported, report


def _counts(summary: dict[str, Any]) -> list[str]:
    lines = []
    for kind in ("folders", "jobs", "links", "relations"):
        parts = [f"{n} {change}" for change, n in summary[kind].items() if n]
        if parts:
            lines.append(f"  {kind}: {', '.join(parts)}")
    return lines


def render_text(result: Refresh, *, stat: bool = False) -> str:
    """The refresh for a terminal: what the export holds, what differs, what was done."""
    report = result.report
    what = f"Import onto {result.branch}" if result.work else f"Refresh {result.branch}"
    lines = [
        f"{what} ({result.env}) from {result.source}: "
        f"{len(report.folders)} folders, {report.jobs} jobs in the export"
    ]
    if result.partial:
        lines.append("  some folders only: the folders it does not have stay")
    elif result.looks_partial:
        lines.append(
            f"  this export holds {result.export_folders} of the {result.branch_folders} "
            f"folders of {result.branch}: --partial keeps the others"
        )
    if result.removes_most:
        removed = result.summary["folders"].get("removed", 0)
        lines.append(
            f"  warning: this would remove {removed} of the {result.branch_folders} folders "
            f"of {result.branch}"
        )
    if result.new_branch:
        lines.append(f"  {result.branch} is a new branch, from the rules of the trunk")
    if result.empty:
        lines.append(f"  {result.branch} holds no folder yet: the whole export is new")
    if report.skipped:
        lines.append(f"  {len(report.skipped)} folder(s) of other applications left out")
    if report.suspicious_values:
        lines.append(
            f"  {len(report.suspicious_values)} value(s) carry another environment's letter"
        )
    if result.unchanged:
        lines.append(f"{result.branch} already holds this export: nothing to do.")
        return "\n".join(lines) + "\n"
    comparison = result.comparison
    lines.append("")
    lines += _counts(comparison.summary())
    if comparison.rules_changed:
        lines.append("  the rules of chain.json differ")
    if comparison.metadata_files_changed:
        lines.append(
            f"  {comparison.metadata_files_changed} technical file(s) differ (dates, versions)"
        )
    if not (stat or result.new_branch or result.empty):
        body = compare_render(comparison).split("\n")[1:]
        lines += [line for line in body if not line.startswith("(")]
    lines.append("")
    if not result.applied and result.partial:
        lines.append(
            f"Nothing written: --apply rewrites the folders of this export on {result.branch}."
        )
    elif not result.applied:
        lines.append(f"Nothing written: --apply overwrites {result.branch} with this export.")
    elif result.commit:
        lines.append(f"Committed on {result.branch}: {result.subject}")
    elif result.work:
        lines.append(
            f"Written on {result.branch}, not committed: review with git diff, then commit it "
            f'as "{result.subject}" (the subject says which environment the branch holds).'
        )
    else:
        lines.append(
            f"Written on {result.branch}, not committed: review with git diff, then commit."
        )
    return "\n".join(lines) + "\n"
