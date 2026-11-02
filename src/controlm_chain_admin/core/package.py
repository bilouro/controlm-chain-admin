"""The import package for Control-M: every folder a branch changed, whole, for one environment.

Control-M imports whole folders, so a folder goes into the package when anything in it changed
compared with the base: a job added, removed, edited, renamed or moved in or out, the folder's
own attributes, a condition it uses renamed, or a constant it uses given another value in the
target environment. A job whose only change is seen from the other end of a relation (its own
file is the same) does not pull its folder in. The package is the regular export of those
folders for the environment: letter rule and constants resolved, original JOBNAMEs by default.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.compare import Comparison, comparison
from controlm_chain_admin.core.constants import placeholder
from controlm_chain_admin.core.errors import NothingToPackage
from controlm_chain_admin.core.history import (
    CommitInfo,
    RefInfo,
    commits_between,
    file_changes,
    resolve,
)
from controlm_chain_admin.core.links import folder_names, load_links
from controlm_chain_admin.core.ops import export_document
from controlm_chain_admin.core.overrides import load_overrides
from controlm_chain_admin.core.repo import CHAIN_FILE, ChainRepo, load_repo, read_json
from controlm_chain_admin.core.selection import Sides, open_sides
from controlm_chain_admin.core.validate import Finding, validate


@dataclass(frozen=True)
class PackageFolder:
    name: str
    jobs: int
    reasons: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "jobs": self.jobs, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class Package:
    """What goes to Control-M, why, and what an import cannot do by itself."""

    base: RefInfo
    head: RefInfo
    merge_base: str | None
    env: str
    commits: tuple[CommitInfo, ...]
    selected: tuple[str, ...] | None
    folders: tuple[PackageFolder, ...]
    warnings: tuple[str, ...]
    findings: tuple[Finding, ...]  # validation findings the head side has and the base has not
    filename: str
    xml: bytes | None  # None when nothing changed

    @property
    def size(self) -> int:
        return len(self.xml or b"")

    def require_xml(self) -> bytes:
        """The XML file; raises :class:`NothingToPackage` when no folder changed."""
        if self.xml is None:
            raise NothingToPackage(
                f"nothing to package: no folder changed between {self.base.name} and "
                f"{self.head.name}"
            )
        return self.xml

    def to_json(self) -> dict[str, Any]:
        return {
            "base": self.base.to_json(),
            "head": self.head.to_json(),
            "merge_base": self.merge_base,
            "env": self.env,
            "commits": [c.to_json() for c in self.commits],
            "selected": None if self.selected is None else list(self.selected),
            "folders": [f.to_json() for f in self.folders],
            "warnings": list(self.warnings),
            "findings": [f.to_json() for f in self.findings],
            "filename": self.filename,
            "size": self.size,
        }


class _Reasons:
    """Folder -> reasons, each reason once, in the order found."""

    def __init__(self) -> None:
        self.by_folder: dict[str, list[str]] = {}

    def add(self, folder: str, reason: str) -> None:
        reasons = self.by_folder.setdefault(folder, [])
        if reason not in reasons:
            reasons.append(reason)


def _without_jobs(data: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (data or {}).items() if k != "jobs"}


def _reasons(result: Comparison, head: ChainRepo, env: str) -> _Reasons:
    reasons = _Reasons()
    renamed = {n.previous[:-1]: n.node[:-1] for n in result.folders if n.previous}
    present = set(folder_names(head))

    def at_head(folder: str) -> str | None:
        name = renamed.get(folder, folder)
        return name if name in present else None

    for node in result.folders:
        name = node.node[:-1]
        if node.change == "added":
            reasons.add(name, "folder added")
        elif node.change == "renamed" and node.previous:
            reasons.add(name, f"folder renamed from {node.previous[:-1]}")
        elif node.change == "modified" and _without_jobs(node.before) != _without_jobs(node.after):
            reasons.add(name, "folder attributes changed")
    for node in result.jobs:
        folder, _, job = node.node.partition("/")
        before_folder, _, before_job = (node.previous or node.node).partition("/")
        if node.change == "added":
            reasons.add(folder, f"job {job} added")
        elif node.change == "removed":
            source = at_head(folder)
            if source:
                reasons.add(source, f"job {job} removed")
        elif node.change == "renamed":
            reasons.add(folder, f"job {job} renamed from {before_job}")
        elif node.change == "moved":
            reasons.add(folder, f"job {job} moved here from {before_folder}")
            source = at_head(before_folder)
            if source:
                reasons.add(source, f"job {job} moved to {folder}")
        elif node.before != node.after:
            reasons.add(folder, f"job {job} modified")
    for node in result.folders:  # e.g. the order of the jobs, nothing else
        name = node.node[:-1]
        if (
            node.change == "modified"
            and name not in reasons.by_folder
            and node.before != node.after
        ):
            reasons.add(name, "folder modified")

    links = load_links(head)
    for change in result.links:
        link = links.get(change.link)
        if change.change != "renamed" or link is None:
            continue
        nodes = {
            *link.producers, *link.consumers, *link.deleters,
            *(n for n, _ in link.docond_add), *(n for n, _ in link.docond_delete),
        }  # fmt: skip
        for folder in sorted({n.folder for n in nodes}):
            reasons.add(folder, f"condition {change.before} renamed to {change.after}")

    changed = [c.name for c in result.constants if c.env == env]
    if changed:
        for folder in folder_names(head):
            files = [
                head.folder_file(folder),
                *sorted(head.folder_dir(folder).glob("jobs/*.json")),
            ]
            text = "".join(p.read_text("utf-8") for p in files if p.is_file())
            for name in changed:
                if placeholder(name) in text:
                    reasons.add(folder, f"constant {name} changed for {env}")
    return reasons


def _exception_reasons(sides: Sides, head: ChainRepo, env: str, reasons: _Reasons) -> None:
    """Folders whose exceptions for ``env`` changed (they export differently there)."""
    before = (
        load_overrides(load_repo(sides.base_root), env)
        if (sides.base_root / CHAIN_FILE).is_file()
        else {}
    )
    after = load_overrides(head, env)
    present = set(folder_names(head))
    for node in sorted(set(before) | set(after)):
        if before.get(node) == after.get(node):
            continue
        folder, _, job = node.partition("/")
        if folder in present:
            reasons.add(folder, f"exception for {env} changed: {job or 'the folder'}")


def _behind(root: Path, sides: Sides, folders: Sequence[str]) -> list[str]:
    """Warnings for packaged folders that the base changed after the head side left it."""
    if sides.base.sha is None or (sides.selected is not None and sides.compared == sides.base.sha):
        return []  # nothing to compare with, or the selection was applied on the base tip
    head = sides.head.sha or resolve(root, "HEAD").sha or "HEAD"
    by_folder: dict[str, list[str]] = {}
    for commit in commits_between(root, head, sides.base.sha):
        if commit.merge:
            continue
        for change in file_changes(root, commit.sha):
            parts = change.path.split("/")
            if len(parts) > 2 and parts[0] == "folders" and parts[1] in folders:
                found = by_folder.setdefault(parts[1], [])
                if commit.sha[:7] not in found:
                    found.append(commit.sha[:7])
    return [
        f"folder {folder} was also changed on {sides.base.name} by {len(shas)} commit(s) not in "
        f"{sides.head.name} ({', '.join(shas)}): this package would undo them; "
        f"merge {sides.base.name} into {sides.head.name} first"
        for folder in folders
        if (shas := by_folder.get(folder, []))
    ]


def _warnings(result: Comparison, sides: Sides, root: Path, folders: Sequence[str]) -> list[str]:
    warnings = []
    if sides.head.kind == "worktree":
        warnings.append("the head side is the working tree: the package has uncommitted changes")
    for node in result.folders:
        if node.change == "removed":
            warnings.append(
                f"folder {node.node[:-1]} was removed: an import does not delete it; "
                "delete it in Control-M by hand"
            )
        elif node.change == "renamed" and node.previous:
            warnings.append(
                f"folder {node.previous[:-1]} was renamed to {node.node[:-1]}: the package "
                "creates the new folder and the old one stays; delete it in Control-M by hand"
            )
    if result.rules_changed:
        warnings.append(
            "chain.json changed (letter rule, attributes or constants): folders that are not "
            "in the package may export differently too; consider a full export"
        )
    return [*warnings, *_behind(root, sides, folders)]


def _new_findings(sides: Sides, head: ChainRepo) -> tuple[Finding, ...]:
    def key(f: Finding) -> tuple[str, str, str, str]:
        return (f.severity, f.code, f.name, f.message)

    known: set[tuple[str, str, str, str]] = set()
    if (sides.base_root / CHAIN_FILE).is_file():
        base = validate(load_repo(sides.base_root), write_index=False)
        known = {key(f) for f in base.findings}
    found = validate(head, write_index=False).findings
    return tuple(f for f in found if key(f) not in known)


def _filename(env: str, sides: Sides, today: str) -> str:
    if sides.head.kind == "worktree":
        label = "worktree"
    else:
        label = re.sub(r"[^A-Za-z0-9._-]+", "-", sides.head.name).strip("-") or "head"
    part = ""
    if sides.selected is not None:
        total = sum(1 for c in sides.commits if not c.merge)
        part = f"_{len(sides.selected)}-of-{total}"
    return f"deploy_{env}_{label}{part}_{today}.xml"


def build_package(
    root: Path,
    base: str,
    head: str = "HEAD",
    *,
    env: str,
    commits: Sequence[str] | None = None,
    use_merge_base: bool = True,
    names: str = "original",
    jobnames: str = "original",
    today: str | None = None,
) -> Package:
    """The Control-M import file for ``env`` with every folder changed from ``base`` to ``head``.

    ``commits`` packages only those commits of the branch (see :func:`compare`). Unresolved
    constants in a packaged folder raise :class:`UnresolvedConstant`.
    """
    with open_sides(root, base, head, use_merge_base=use_merge_base, commits=commits) as sides:
        result = comparison(sides)
        repo = load_repo(sides.head_root)
        repo.load_env(env)  # an unknown environment fails before anything else
        found = _reasons(result, repo, env)
        _exception_reasons(sides, repo, env, found)
        reasons = found.by_folder
        order = [str(f) for f in read_json(repo.export_meta_file).get("folder_order", [])]
        missing = [f for f in reasons if f not in order]
        packaged = [f for f in order if f in reasons]
        xml = None
        if packaged:
            xml, _ = export_document(
                repo, env, names=names, jobnames=jobnames, folders=set(packaged)
            )
        folders = tuple(
            PackageFolder(
                f, len(read_json(repo.folder_file(f)).get("jobs", [])), tuple(reasons[f])
            )
            for f in packaged
        )
        warnings = _warnings(result, sides, root, packaged)
        warnings += [
            f"folder {f.name} has no jobs left: the import empties it in Control-M; "
            "delete it there if it is no longer needed"
            for f in folders
            if f.jobs == 0
        ]
        warnings += [f"folder {f} is not in meta/export.json; it is not packaged" for f in missing]
        findings = _new_findings(sides, repo)
        filename = _filename(env, sides, today or datetime.date.today().isoformat())
    return Package(
        sides.base, sides.head, sides.merge_base, env, sides.commits, sides.selected,
        folders, tuple(warnings), findings, filename, xml,
    )  # fmt: skip
