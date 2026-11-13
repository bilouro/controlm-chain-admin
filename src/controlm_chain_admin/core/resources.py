"""The resources of a job or of a folder: CONTROL (a resource it holds, exclusively or
shared) and QUANTITATIVE (a number of units it takes).

Control-M shows them one job at a time. Here they are seen by resource as well (who uses
each one, with what attributes), and one resource is put on several jobs at once, with the
attributes the jobs that have it already use, so that they all ask for the same thing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from controlm_chain_admin.core.errors import InvalidChange
from controlm_chain_admin.core.links import NodeRef, folder_names
from controlm_chain_admin.core.refactor import (
    ChangeSet,
    _finish,
    _name_warnings,
    _node_file,
    _require_node,
    _sandbox,
    _tracked,
    _write_node,
)
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json

TAGS = ("QUANTITATIVE", "CONTROL")
#: what a resource nobody uses yet starts with: one unit, or held exclusively; released at
#: the end whatever the outcome
DEFAULTS: dict[str, dict[str, str]] = {
    "QUANTITATIVE": {"QUANT": "1", "ONFAIL": "R", "ONOK": "R"},
    "CONTROL": {"TYPE": "E", "ONFAIL": "R"},
}
_LITERAL = "literal:"


@dataclass(frozen=True)
class ResourceUse:
    """One resource and the nodes that use it; ``attributes`` are those of its first use."""

    tag: str
    name: str
    nodes: tuple[str, ...]
    attributes: Mapping[str, str]

    def to_json(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "name": self.name,
            "nodes": list(self.nodes),
            "count": len(self.nodes),
            "attributes": dict(self.attributes),
        }


def _bare(name: Any) -> str:
    return str(name or "").removeprefix(_LITERAL)


def _attributes(item: Mapping[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in item.items() if k not in ("NAME", "tag") and isinstance(v, str)}


def _grouped(data: Mapping[str, Any], tag: str) -> list[dict[str, Any]]:
    items = data.get(tag)
    return (
        [dict(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    )


def usage(repo: ChainRepo) -> tuple[ResourceUse, ...]:
    """Every resource of the repository with the folders and jobs that use it, by kind and
    by name."""
    found: dict[tuple[str, str], tuple[list[str], dict[str, str]]] = {}
    for folder in folder_names(repo):
        data = read_json(repo.folder_file(folder))
        nodes = [(f"{folder}/", data)] + [
            (f"{folder}/{job}", read_json(repo.job_file(folder, str(job))))
            for job in data.get("jobs", [])
        ]
        for node, body in nodes:
            for tag in TAGS:
                for item in _grouped(body, tag):
                    key = (tag, _bare(item.get("NAME")))
                    found.setdefault(key, ([], _attributes(item)))[0].append(node)
    return tuple(
        ResourceUse(tag, name, tuple(nodes), attributes)
        for (tag, name), (nodes, attributes) in sorted(found.items())
    )


def _kind(repo: ChainRepo, name: str, tag: str | None) -> tuple[str, dict[str, str]]:
    """The kind of the resource and the attributes a new use of it starts with: those of a job
    that has it already, else the usual ones of its kind."""
    asked = None if tag is None else tag.strip().upper()
    if asked is not None and asked not in TAGS:
        raise InvalidChange(f"a resource is CONTROL or QUANTITATIVE, not {tag!r}")
    known = [use for use in usage(repo) if use.name == name]
    if known and asked is not None and all(use.tag != asked for use in known):
        raise InvalidChange(
            f"{name} is a {known[0].tag} resource in this repository ({known[0].nodes[0]}): "
            "give it another name, or leave the kind out"
        )
    if asked is None and not known:
        raise InvalidChange(
            f"no job uses {name} yet: say whether it is a CONTROL or a QUANTITATIVE resource"
        )
    use = next((u for u in known if asked in (None, u.tag)), None)
    if use is not None:
        return use.tag, dict(use.attributes)
    assert asked is not None
    return asked, dict(DEFAULTS[asked])


def set_resource(
    repo: ChainRepo,
    node: str,
    name: str,
    *,
    tag: str | None = None,
    attributes: Mapping[str, str | None] | None = None,
) -> ChangeSet:
    """Give a job or a folder the resource ``name``, or change the one it has.

    A resource another job uses comes with the attributes it has there, so that every job
    asks for the same; one nobody uses yet needs its kind (``tag``: CONTROL or QUANTITATIVE)
    and gets the usual attributes. ``attributes`` set others (``None`` removes one).
    """
    repo = load_repo(repo.root)
    ref = _require_node(repo, node)
    name = name.strip()
    if not name:
        raise InvalidChange("a name is needed for the resource")
    kind, wanted = _kind(repo, name, tag)
    given = dict(attributes or {})
    warnings = _name_warnings(repo, name)
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        data = dict(read_json(_node_file(box, ref)))
        items = _grouped(data, kind)
        current = next((item for item in items if _bare(item.get("NAME")) == name), None)
        if current is None:
            fresh = {**wanted, **{k: v for k, v in given.items() if v is not None}}
            for key, value in given.items():
                if value is None:
                    fresh.pop(key, None)
            items.append({"NAME": name, **fresh})
            summary = f"add {kind} {name} to {ref}"
        else:
            before = _attributes(current)
            for key, value in given.items():
                if value is None:
                    current.pop(key, None)
                else:
                    current[key] = value
            after = _attributes(current)
            if after == before:
                return _finish(original, box, f"{ref} already has {kind} {name} as asked", [])
            changed = ", ".join(
                f"{key} {before.get(key, 'none')} -> {after.get(key, 'none')}"
                for key in dict.fromkeys([*before, *after])
                if before.get(key) != after.get(key)
            )
            summary = f"change {kind} {name} on {ref}: {changed}"
        _write_node(box, ref, data, {kind: items})
        return _finish(original, box, summary, warnings)


def remove_resource(repo: ChainRepo, node: str, name: str) -> ChangeSet:
    """Take the resource ``name`` (of either kind) off a job or a folder."""
    repo = load_repo(repo.root)
    ref: NodeRef = _require_node(repo, node)
    name = name.strip()
    original = _tracked(repo.root)
    with _sandbox(original) as box:
        data = dict(read_json(_node_file(box, ref)))
        updates: dict[str, list[dict[str, Any]]] = {}
        for tag in TAGS:
            items = _grouped(data, tag)
            kept = [item for item in items if _bare(item.get("NAME")) != name]
            if len(kept) != len(items):
                updates[tag] = kept
        if not updates:
            raise InvalidChange(f"{ref} has no resource {name}")
        _write_node(box, ref, data, updates)
        kinds = " and ".join(updates)
        return _finish(original, box, f"remove {kinds} {name} from {ref}", [])
