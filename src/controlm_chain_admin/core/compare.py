"""Semantic comparison of a chain repository between two git refs (a feature branch vs develop).

Instead of a text diff of JSON files, the comparison reports what changed in Control-M terms:
folders and jobs added, removed, modified, renamed or moved; attribute and variable values before
and after; predecessors and successors with their AND_OR, ODATE and cleanup (``-``) details;
conditions renamed, added or removed; constant values per environment; and the commits involved.
By default the base side is the merge base of the two refs, like a pull request, so only what the
head branch changed is shown. A selection of the head's commits compares only their changes (see
:mod:`controlm_chain_admin.core.selection`).
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from controlm_chain_admin.core.history import CommitInfo, RefInfo
from controlm_chain_admin.core.links import LINK_KEY, folder_names, load_links
from controlm_chain_admin.core.relations import NodeRelations, Relation, all_relations
from controlm_chain_admin.core.repo import CHAIN_FILE, EnvConfig, load_repo, read_json
from controlm_chain_admin.core.selection import Sides, open_sides

_NAME_KEYS = ("JOBNAME", "MEMNAME", "PARENT_FOLDER", "FOLDER_NAME")
_RELATION_GROUPS = ("INCOND", "OUTCOND")
_SKIP_ATTRS = ("tag",)


# ---------------------------------------------------------------- result types


@dataclass(frozen=True)
class ValueChange:
    name: str
    before: str | None
    after: str | None

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "before": self.before, "after": self.after}


@dataclass(frozen=True)
class RelationChange:
    direction: str  # predecessor | successor
    link: str
    name: str
    change: str  # added | removed | modified
    peers_before: tuple[str, ...]
    peers_after: tuple[str, ...]
    details: tuple[ValueChange, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "link": self.link,
            "name": self.name,
            "change": self.change,
            "peers_before": list(self.peers_before),
            "peers_after": list(self.peers_after),
            "details": [d.to_json() for d in self.details],
        }


@dataclass(frozen=True)
class NodeChange:
    node: str  # identity at head (at base when removed)
    kind: str  # folder | job
    change: str  # added | removed | modified | renamed | moved
    previous: str | None  # identity at base when renamed or moved
    attributes: tuple[ValueChange, ...] = ()
    variables: tuple[ValueChange, ...] = ()
    relations: tuple[RelationChange, ...] = ()
    groups: tuple[str, ...] = ()  # other element groups that changed (ON, QUANTITATIVE...)
    jobs_added: tuple[str, ...] = ()  # folders only
    jobs_removed: tuple[str, ...] = ()
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    diff: str = ""
    commits: tuple[str, ...] = ()  # shas of the compared commits that changed it, newest first

    def to_json(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "kind": self.kind,
            "change": self.change,
            "previous": self.previous,
            "attributes": [a.to_json() for a in self.attributes],
            "variables": [v.to_json() for v in self.variables],
            "relations": [r.to_json() for r in self.relations],
            "groups": list(self.groups),
            "jobs_added": list(self.jobs_added),
            "jobs_removed": list(self.jobs_removed),
            "before": self.before,
            "after": self.after,
            "diff": self.diff,
            "commits": list(self.commits),
        }


@dataclass(frozen=True)
class LinkChange:
    link: str
    change: str  # added | removed | renamed
    before: str | None
    after: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "link": self.link,
            "change": self.change,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True)
class ConstantChange:
    env: str
    name: str
    before: str | None
    after: str | None

    def to_json(self) -> dict[str, Any]:
        return {"env": self.env, "name": self.name, "before": self.before, "after": self.after}


@dataclass(frozen=True)
class Comparison:
    base: RefInfo
    head: RefInfo
    merge_base: str | None  # sha actually compared on the base side when it differs from base
    commits: tuple[CommitInfo, ...]
    folders: tuple[NodeChange, ...]
    jobs: tuple[NodeChange, ...]
    links: tuple[LinkChange, ...]
    constants: tuple[ConstantChange, ...]
    rules_changed: bool
    metadata_files_changed: int
    selected: tuple[str, ...] | None = None  # commits compared when not all of them

    def summary(self) -> dict[str, Any]:
        def count(
            items: Sequence[Any], kinds: Sequence[str], attr: str = "change"
        ) -> dict[str, int]:
            return {k: sum(1 for i in items if getattr(i, attr) == k) for k in kinds}

        relations = [r for node in (*self.folders, *self.jobs) for r in node.relations]
        return {
            "folders": count(self.folders, ("added", "removed", "modified", "renamed")),
            "jobs": count(self.jobs, ("added", "removed", "modified", "renamed", "moved")),
            "links": count(self.links, ("added", "removed", "renamed")),
            "relations": count(relations, ("added", "removed", "modified")),
            "constants": len(self.constants),
            "commits": len(self.commits),
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "base": self.base.to_json(),
            "head": self.head.to_json(),
            "merge_base": self.merge_base,
            "summary": self.summary(),
            "commits": [c.to_json() for c in self.commits],
            "folders": [f.to_json() for f in self.folders],
            "jobs": [j.to_json() for j in self.jobs],
            "links": [lk.to_json() for lk in self.links],
            "constants": [c.to_json() for c in self.constants],
            "rules_changed": self.rules_changed,
            "metadata_files_changed": self.metadata_files_changed,
            "selected": None if self.selected is None else list(self.selected),
        }


# ---------------------------------------------------------------- one side


@dataclass
class _Side:
    folders: dict[str, dict[str, Any]] = field(default_factory=dict)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)  # "F/J" -> job JSON
    order: list[str] = field(default_factory=list)
    relations: dict[str, NodeRelations] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)  # link id -> export name
    constants: dict[str, dict[str, str | None]] = field(default_factory=dict)
    meta: dict[str, str] = field(default_factory=dict)
    rules: dict[str, Any] = field(default_factory=dict)

    def position(self, identity: str) -> tuple[int, int]:
        folder, _, job = identity.partition("/")
        index = self.order.index(folder) if folder in self.order else len(self.order)
        jobs = [str(j) for j in self.folders.get(folder, {}).get("jobs", [])]
        return index, (jobs.index(job) + 1 if job in jobs else 0)


def _load(root: Path) -> _Side:
    side = _Side()
    if not (root / CHAIN_FILE).is_file():
        return side
    repo = load_repo(root)
    for folder in folder_names(repo):
        data = dict(read_json(repo.folder_file(folder)))
        side.folders[folder] = data
        for job in (str(j) for j in data.get("jobs", [])):
            side.jobs[f"{folder}/{job}"] = dict(read_json(repo.job_file(folder, job)))
    if repo.export_meta_file.is_file():
        side.order = list(read_json(repo.export_meta_file).get("folder_order", []))
    side.order += [f for f in side.folders if f not in side.order]
    side.relations = all_relations(repo)
    side.names = {link_id: link.name for link_id, link in load_links(repo).items()}
    for env in repo.config.environments:
        if repo.env_file(env).is_file():
            side.constants[env] = dict(
                EnvConfig.from_json(read_json(repo.env_file(env))).constants
            )
    meta_dir = root / "meta"
    if meta_dir.is_dir():
        side.meta = {
            p.relative_to(root).as_posix(): p.read_text("utf-8") for p in meta_dir.rglob("*.json")
        }
    rules = repo.config.to_json()
    rules.pop("attribute_order", None)
    rules.pop("child_order", None)
    side.rules = rules
    return side


# ---------------------------------------------------------------- matching


def _strip(data: Mapping[str, Any], keys: Sequence[str] = _NAME_KEYS) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k not in keys}


def _link_refs(data: Mapping[str, Any]) -> frozenset[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    for group in _RELATION_GROUPS:
        for entry in data.get(group, []):
            refs.add((group + str(entry.get("SIGN", "")), str(entry.get(LINK_KEY))))
    for block in data.get("ON", []):
        for child in block.get("children", []):
            if child.get("tag") == "DOCOND":
                refs.add(("DOCOND" + str(child.get("SIGN", "")), str(child.get(LINK_KEY))))
    return frozenset(refs)


def _match_folders(base: _Side, head: _Side) -> dict[str, str]:
    """Base folder name -> head folder name (same name, or detected rename)."""
    mapping = {name: name for name in base.folders if name in head.folders}
    removed = [f for f in base.folders if f not in head.folders]
    added = [f for f in head.folders if f not in base.folders]
    for old in removed:
        old_data = base.folders[old]
        old_jobs = set(old_data.get("jobs", []))
        for new in added:
            if new in mapping.values():
                continue
            new_data = head.folders[new]
            same_body = _strip(old_data, (*_NAME_KEYS, "jobs")) == _strip(
                new_data, (*_NAME_KEYS, "jobs")
            )
            shared = len(old_jobs & set(new_data.get("jobs", [])))
            if same_body or (old_jobs and shared * 2 >= len(old_jobs)):
                mapping[old] = new
                break
    return mapping


def _match_jobs(
    base: _Side, head: _Side, folders: Mapping[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """(base identity -> head identity, head identity -> change kind for renames and moves)."""
    mapping: dict[str, str] = {}
    kinds: dict[str, str] = {}
    unmatched_base: list[str] = []
    for identity in base.jobs:
        folder, _, job = identity.partition("/")
        target = f"{folders.get(folder, folder)}/{job}"
        if target in head.jobs:
            mapping[identity] = target
        else:
            unmatched_base.append(identity)
    unmatched_head = [i for i in head.jobs if i not in mapping.values()]
    for identity in unmatched_base:
        folder, _, job = identity.partition("/")
        before = base.jobs[identity]
        refs = _link_refs(before)
        for candidate in unmatched_head:
            cfolder, _, cjob = candidate.partition("/")
            after = head.jobs[candidate]
            same_body = _strip(before) == _strip(after)
            same_refs = bool(refs) and refs == _link_refs(after)
            if cjob == job and cfolder != folders.get(folder, folder) and (same_body or same_refs):
                kinds[candidate] = "moved"
            elif cfolder == folders.get(folder, folder) and (same_body or same_refs):
                kinds[candidate] = "renamed"
            else:
                continue
            mapping[identity] = candidate
            unmatched_head.remove(candidate)
            break
    return mapping, kinds


# ---------------------------------------------------------------- node comparison


def _values(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None, ignore: Mapping[str, str]
) -> tuple[ValueChange, ...]:
    """Changes of plain attributes; ``ignore`` maps an attribute to an expected new value."""
    b = {k: v for k, v in (before or {}).items() if isinstance(v, str) and k not in _SKIP_ATTRS}
    a = {k: v for k, v in (after or {}).items() if isinstance(v, str) and k not in _SKIP_ATTRS}
    changes = []
    for key in [*b, *(k for k in a if k not in b)]:
        if b.get(key) != a.get(key) and ignore.get(key, object()) != a.get(key):
            changes.append(ValueChange(key, b.get(key), a.get(key)))
    return tuple(changes)


def _variables(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> tuple[ValueChange, ...]:
    b = {str(v["NAME"]): str(v.get("VALUE", "")) for v in (before or {}).get("VARIABLE", [])}
    a = {str(v["NAME"]): str(v.get("VALUE", "")) for v in (after or {}).get("VARIABLE", [])}
    return tuple(
        ValueChange(name, b.get(name), a.get(name))
        for name in [*b, *(n for n in a if n not in b)]
        if b.get(name) != a.get(name)
    )


def _groups(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> tuple[str, ...]:
    skip = {*_RELATION_GROUPS, "VARIABLE", "jobs", "children"}
    b = {k: v for k, v in (before or {}).items() if isinstance(v, list) and k not in skip}
    a = {k: v for k, v in (after or {}).items() if isinstance(v, list) and k not in skip}
    return tuple(sorted(k for k in set(b) | set(a) if b.get(k) != a.get(k)))


def _flag(value: bool) -> str:
    return "yes" if value else "no"


def _emission(relation: Relation) -> str:
    return "+ OUTCOND" if relation.sign == "+" else f"ON {relation.on_code}"


def _relations(
    before: NodeRelations | None,
    after: NodeRelations | None,
    nodes: Mapping[str, str],
    names_before: Mapping[str, str],
    names_after: Mapping[str, str],
) -> tuple[RelationChange, ...]:
    """Relation changes of one node; a removed relation keeps the condition name it had."""
    changes: list[RelationChange] = []
    for direction in ("predecessor", "successor"):
        attr = "predecessors" if direction == "predecessor" else "successors"
        b = {r.link: r for r in getattr(before, attr, ())} if before else {}
        a = {r.link: r for r in getattr(after, attr, ())} if after else {}
        for link in [*b, *(k for k in a if k not in b)]:
            rb, ra = b.get(link), a.get(link)
            peers_b = tuple(nodes.get(p.node, p.node) for p in rb.peers) if rb else ()
            peers_a = tuple(p.node for p in ra.peers) if ra else ()
            if ra is not None:
                name = names_after.get(link, ra.name)
            else:
                name = names_before.get(link, rb.name if rb else link)
            if rb is None or ra is None:
                change = "added" if rb is None else "removed"
                changes.append(RelationChange(direction, link, name, change, peers_b, peers_a))
                continue
            details: list[ValueChange] = []
            if direction == "predecessor":
                if rb.and_or != ra.and_or:
                    details.append(ValueChange("AND_OR", rb.and_or, ra.and_or))
                if rb.cleanup != ra.cleanup:
                    details.append(ValueChange("cleanup", _flag(rb.cleanup), _flag(ra.cleanup)))
            elif _emission(rb) != _emission(ra):
                details.append(ValueChange("emitted", _emission(rb), _emission(ra)))
            if rb.odate != ra.odate:
                details.append(ValueChange("ODATE", rb.odate, ra.odate))
            if details or sorted(peers_b) != sorted(peers_a):
                changes.append(
                    RelationChange(
                        direction, link, name, "modified", peers_b, peers_a, tuple(details)
                    )
                )
    return tuple(changes)


def _diff(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None, b: str, a: str
) -> str:
    text_b = (
        json.dumps(before, indent=2, ensure_ascii=False).splitlines(keepends=True)
        if before
        else []
    )
    text_a = (
        json.dumps(after, indent=2, ensure_ascii=False).splitlines(keepends=True) if after else []
    )
    return "".join(difflib.unified_diff(text_b, text_a, fromfile=b, tofile=a, n=2))


def _node(
    kind: str,
    change: str,
    identity: str,
    previous: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    ignore: Mapping[str, str],
    relations: tuple[RelationChange, ...],
    jobs_added: tuple[str, ...] = (),
    jobs_removed: tuple[str, ...] = (),
) -> NodeChange:
    return NodeChange(
        node=identity,
        kind=kind,
        change=change,
        previous=previous,
        attributes=_values(before, after, ignore),
        variables=_variables(before, after),
        relations=relations,
        groups=_groups(before, after),
        jobs_added=jobs_added,
        jobs_removed=jobs_removed,
        before=before,
        after=after,
        diff=_diff(before, after, f"a/{previous or identity}", f"b/{identity}"),
    )


def _significant(node: NodeChange) -> bool:
    return bool(
        node.change in ("added", "removed", "renamed", "moved")
        or node.attributes
        or node.variables
        or node.relations
        or node.groups
        or node.jobs_added
        or node.jobs_removed
    )


def diff_snapshots(base_root: Path, head_root: Path) -> tuple[Any, ...]:
    """Compare two directories holding a chain repository; see :func:`compare`."""
    base, head = _load(base_root), _load(head_root)
    folder_map = _match_folders(base, head)
    job_map, job_kinds = _match_jobs(base, head, folder_map)
    node_map = {f"{old}/": f"{new}/" for old, new in folder_map.items()} | job_map
    reverse = {new: old for old, new in node_map.items()}

    def folder_order(name: str) -> tuple[int, int]:
        if name in head.folders:
            return head.position(f"{name}/")
        return len(head.order) + base.position(f"{name}/")[0], 0

    gone = {f for f in base.folders if f not in folder_map}
    folders: list[NodeChange] = []
    for name in sorted(set(head.folders) | gone, key=folder_order):
        identity = f"{name}/"
        old = reverse.get(identity) if name in head.folders else identity
        before = base.folders.get(old[:-1]) if old else None
        after = head.folders.get(name)
        if before is None:
            change = "added"
        elif after is None:
            change = "removed"
        else:
            change = "renamed" if old != identity else "modified"
        old_name = old[:-1] if old else ""
        # base identity -> head identity, so renames inside the folder are not listed;
        # a job that left is shown where it was, a job that arrived where it is
        jobs_before = {
            f"{old_name}/{j}": job_map.get(f"{old_name}/{j}", f"{old_name}/{j}")
            for j in (before or {}).get("jobs", [])
        }
        jobs_after = [f"{name}/{j}" for j in (after or {}).get("jobs", [])]
        arrived = set(jobs_before.values())
        relations = _relations(
            base.relations.get(old) if old else None,
            head.relations.get(identity),
            node_map,
            base.names,
            head.names,
        )
        node = _node(
            "folder", change, identity, old if change == "renamed" else None, before, after, {},
            relations,
            tuple(j for j in jobs_after if j not in arrived),
            tuple(b for b, a in jobs_before.items() if a not in jobs_after),
        )  # fmt: skip
        if change != "modified" or _significant(node):
            folders.append(node)

    jobs: list[NodeChange] = []
    removed = [i for i in base.jobs if i not in job_map]
    for identity in sorted(head.jobs, key=head.position):
        old = reverse.get(identity)
        before = base.jobs.get(old) if old else None
        after = head.jobs[identity]
        change = "added" if before is None else job_kinds.get(identity, "modified")
        ignore: dict[str, str] = {}
        if old is not None and change == "modified":
            folder_before = str((before or {}).get("PARENT_FOLDER", ""))
            if folder_map.get(folder_before) == after.get("PARENT_FOLDER"):
                ignore["PARENT_FOLDER"] = str(after.get("PARENT_FOLDER"))
        relations = _relations(
            base.relations.get(old) if old else None,
            head.relations.get(identity),
            node_map,
            base.names,
            head.names,
        )
        previous = old if change in ("renamed", "moved") else None
        node = _node("job", change, identity, previous, before, after, ignore, relations)
        if change != "modified" or _significant(node):
            jobs.append(node)
    for identity in sorted(removed, key=base.position):
        relations = _relations(
            base.relations.get(identity), None, node_map, base.names, head.names
        )
        jobs.append(
            _node("job", "removed", identity, None, base.jobs[identity], None, {}, relations)
        )

    links: list[LinkChange] = []
    for link in [*head.names, *(k for k in base.names if k not in head.names)]:
        before_name, after_name = base.names.get(link), head.names.get(link)
        if before_name is None:
            links.append(LinkChange(link, "added", None, after_name))
        elif after_name is None:
            links.append(LinkChange(link, "removed", before_name, None))
        elif before_name != after_name:
            links.append(LinkChange(link, "renamed", before_name, after_name))

    constants: list[ConstantChange] = []
    for env in [*head.constants, *(e for e in base.constants if e not in head.constants)]:
        b, a = base.constants.get(env, {}), head.constants.get(env, {})
        for name in [*b, *(n for n in a if n not in b)]:
            if b.get(name) != a.get(name):
                constants.append(ConstantChange(env, name, b.get(name), a.get(name)))

    meta_changed = sum(
        1 for path in set(base.meta) | set(head.meta) if base.meta.get(path) != head.meta.get(path)
    )
    return (
        tuple(folders),
        tuple(jobs),
        tuple(links),
        tuple(constants),
        base.rules != head.rules,
        meta_changed,
    )


def _job_path(identity: str) -> str:
    folder, _, job = identity.partition("/")
    return f"folders/{folder}/jobs/{job}.json"


def _attribute(nodes: Sequence[NodeChange], sides: Sides) -> tuple[NodeChange, ...]:
    """Each change with the commits that touched its files (a job: its file, else its peers')."""
    touched: dict[str, list[str]] = {}
    for sha in sides.applied:
        for change in sides.changes.get(sha, ()):
            touched.setdefault(change.path, []).append(sha)

    def commits_of(paths: Sequence[str], prefixes: tuple[str, ...] = ()) -> tuple[str, ...]:
        found = {sha for path in paths for sha in touched.get(path, ())}
        for path, shas in touched.items():
            if prefixes and path.startswith(prefixes):
                found.update(shas)
        return tuple(sha for sha in sides.applied if sha in found)

    result = []
    for node in nodes:
        names = [n for n in (node.node, node.previous) if n]
        if node.kind == "folder":
            shas = commits_of((), tuple(f"folders/{n[:-1]}/" for n in names))
        else:
            shas = commits_of([_job_path(n) for n in names])
            if not shas and node.relations:
                peers = {p for r in node.relations for p in (*r.peers_before, *r.peers_after)}
                shas = commits_of([_job_path(p) for p in sorted(peers) if not p.endswith("/")])
        result.append(replace(node, commits=shas))
    return tuple(result)


def compare(
    root: Path,
    base: str,
    head: str,
    *,
    use_merge_base: bool = True,
    commits: Sequence[str] | None = None,
) -> Comparison:
    """Compare the chain repository at ``base`` and ``head`` (refs, shas or ``WORKTREE``).

    ``commits`` limits the head side to those commits of the branch (any subset, any order),
    applied on the base side; every commit of the branch is still listed, to choose from.
    """
    with open_sides(root, base, head, use_merge_base=use_merge_base, commits=commits) as sides:
        return comparison(sides)


def comparison(sides: Sides) -> Comparison:
    """The :class:`Comparison` of two opened sides."""
    folders, jobs, links, constants, rules, meta = diff_snapshots(sides.base_root, sides.head_root)
    return Comparison(
        sides.base, sides.head, sides.merge_base, sides.commits,
        _attribute(folders, sides), _attribute(jobs, sides),
        links, constants, rules, meta, sides.selected,
    )  # fmt: skip


# ---------------------------------------------------------------- renderings


def _value(value: str | None) -> str:
    return "(none)" if value is None else value


def _relation_line(change: RelationChange) -> str:
    line = f"{change.direction} {change.name} {change.change}"
    if change.details:
        line += ": " + "; ".join(
            f"{d.name} {_value(d.before)} -> {_value(d.after)}" for d in change.details
        )
    if sorted(change.peers_before) != sorted(change.peers_after):
        before = ", ".join(change.peers_before) or "nobody"
        after = ", ".join(change.peers_after) or "nobody"
        line += f" ({before} -> {after})"
    return line


def _node_lines(node: NodeChange) -> list[str]:
    title = f"{node.change:8} {node.kind} {node.node}"
    if node.previous:
        title += f" (was {node.previous})"
    lines = [title]
    if node.change in ("added", "removed"):
        # every value of a new or deleted node is a change: count them, list the relations
        counts = f"{len(node.attributes)} attributes"
        if node.variables:
            counts += f", {len(node.variables)} variables"
        lines.append(f"    {counts} (see --format json)")
    else:
        lines += [
            f"    {a.name}: {_value(a.before)} -> {_value(a.after)}" for a in node.attributes
        ]
        lines += [
            f"    variable {v.name}: {_value(v.before)} -> {_value(v.after)}"
            for v in node.variables
        ]
    lines += [f"    {_relation_line(r)}" for r in node.relations]
    if node.groups:
        lines.append(f"    changed: {', '.join(node.groups)}")
    if node.jobs_added:
        lines.append(f"    jobs added: {', '.join(node.jobs_added)}")
    if node.jobs_removed:
        lines.append(f"    jobs removed: {', '.join(node.jobs_removed)}")
    return lines


def _commits_label(result: Comparison) -> str:
    if result.selected is None:
        return f"{len(result.commits)} commits"
    total = sum(1 for c in result.commits if not c.merge)
    return f"{len(result.selected)} of {total} commits"


def _headline(result: Comparison) -> str:
    line = f"Compare {result.base.name}..{result.head.name}: {_commits_label(result)}"
    if result.merge_base:
        line += f" (from merge base {result.merge_base[:7]})"
    return line


def render_text(result: Comparison) -> str:
    lines = [_headline(result)]
    left_out = set() if result.selected is None else {c.sha for c in result.commits}
    left_out -= set(result.selected or ())
    lines += [
        f"  {c.sha[:7]} {c.subject} — {c.author}" + (" (left out)" if c.sha in left_out else "")
        for c in result.commits
    ]
    nodes = (*result.folders, *result.jobs)
    if not (nodes or result.links or result.constants):
        lines.append(f"No changes between {result.base.name} and {result.head.name}.")
        return "\n".join(lines) + "\n"
    lines.append("")
    for node in nodes:
        lines += _node_lines(node)
    for link in result.links:
        if link.change == "renamed":
            lines.append(f"condition renamed {link.before} -> {link.after}")
        else:
            lines.append(f"condition {link.change} {link.after or link.before}")
    for c in result.constants:
        lines.append(f"constant {c.env} {c.name}: {_value(c.before)} -> {_value(c.after)}")
    if result.metadata_files_changed:
        lines.append(
            f"({result.metadata_files_changed} export metadata file(s) changed, not shown)"
        )
    return "\n".join(lines) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render_markdown(result: Comparison) -> str:
    """A summary suitable for a pull request description."""
    lines = [f"## Chain changes: {result.base.name}..{result.head.name}", ""]
    origin = f" · from merge base `{result.merge_base[:7]}`" if result.merge_base else ""
    lines += [f"{_commits_label(result)}{origin}", ""]
    nodes = (*result.folders, *result.jobs)
    if nodes:
        lines += ["| change | kind | node | details |", "|---|---|---|---|"]
        for node in nodes:
            details = _node_lines(node)[1:]
            if node.previous:
                details.insert(0, f"was {node.previous}")
            text = "<br>".join(_cell(d.strip()) for d in details) or "—"
            lines.append(f"| {node.change} | {node.kind} | {_cell(node.node)} | {text} |")
        lines.append("")
    if result.links:
        lines += ["### Conditions", "", "| change | before | after |", "|---|---|---|"]
        lines += [
            f"| {lk.change} | {_cell(_value(lk.before))} | {_cell(_value(lk.after))} |"
            for lk in result.links
        ]
        lines.append("")
    if result.constants:
        lines += ["### Constants", "", "| env | constant | before | after |", "|---|---|---|---|"]
        lines += [
            f"| {c.env} | {_cell(c.name)} | {_cell(_value(c.before))} | {_cell(_value(c.after))} |"
            for c in result.constants
        ]
        lines.append("")
    if result.commits:
        lines += ["### Commits", ""]
        lines += [f"- `{c.sha[:7]}` {_cell(c.subject)} — {c.author}" for c in result.commits]
    return "\n".join(lines).rstrip() + "\n"
