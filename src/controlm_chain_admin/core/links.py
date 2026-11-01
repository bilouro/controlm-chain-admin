"""Links between nodes, derived from the INCOND / OUTCOND / DOCOND conditions stored on nodes.

In the proof of concept the conditions on the nodes remain the source of truth (they are what
the export regenerates byte for byte); ``links.json`` per folder is a derived index rebuilt on
every import and by ``ctmchain links --rebuild``. The index is what ``validate``, ``graph`` and
the web UI read.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from controlm_chain_admin.core.repo import ChainRepo, read_json, write_json

LINKS_FILE = "links.json"
INDEX_NOTE = "Derived from the conditions on the nodes; regenerated on import. Do not edit."


@dataclass(frozen=True, order=True)
class NodeRef:
    """A folder (``job`` is None) or a job in a folder; text form ``FOLDER/JOB`` or ``FOLDER/``."""

    folder: str
    job: str | None = None

    def __str__(self) -> str:
        return f"{self.folder}/{self.job or ''}"

    @classmethod
    def parse(cls, text: str) -> NodeRef:
        folder, _, job = text.partition("/")
        return cls(folder, job or None)


@dataclass(frozen=True)
class Condition:
    """One condition element as found on a node."""

    node: NodeRef
    name: str
    kind: str  # "in" | "out+" | "out-" | "do+" | "do-"
    odate: str
    and_or: str | None = None
    on_code: str | None = None  # for DOCOND: the CODE of the enclosing ON block


@dataclass(frozen=True)
class Link:
    """Everything known about one condition name across the repository."""

    name: str
    producers: tuple[NodeRef, ...]  # OUTCOND SIGN="+"
    consumers: tuple[NodeRef, ...]  # INCOND
    deleters: tuple[NodeRef, ...]  # OUTCOND SIGN="-"
    docond_add: tuple[tuple[NodeRef, str], ...]  # (node, ON code) adding the condition
    docond_delete: tuple[tuple[NodeRef, str], ...]
    odates: tuple[str, ...]
    and_or: tuple[str, ...]

    @property
    def all_producers(self) -> tuple[NodeRef, ...]:
        """Static producers plus nodes that add the condition from an ON block."""
        seen: dict[NodeRef, None] = dict.fromkeys(self.producers)
        for node, _ in self.docond_add:
            seen.setdefault(node)
        return tuple(seen)

    @property
    def kind(self) -> str:
        """edge | fan_in | dangling (no producer) | unconsumed (no consumer) | delete_only."""
        producers = self.all_producers
        if not producers and not self.consumers:
            return "delete_only"
        if not producers:
            return "dangling"
        if not self.consumers:
            return "unconsumed"
        return "fan_in" if len(producers) > 1 else "edge"

    @property
    def external(self) -> bool:
        """True when one side of the link is not in the repository."""
        return self.kind in ("dangling", "unconsumed", "delete_only")

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "from": [str(n) for n in self.producers],
            "to": [str(n) for n in self.consumers],
            "cleanup": [str(n) for n in self.deleters],
            "docond": [
                *({"node": str(n), "on": code, "sign": "+"} for n, code in self.docond_add),
                *({"node": str(n), "on": code, "sign": "-"} for n, code in self.docond_delete),
            ],
            "odates": list(self.odates),
            "and_or": list(self.and_or),
            "kind": self.kind,
            "external": self.external,
        }


# ---------------------------------------------------------------- collection


def _conditions_of(node: NodeRef, data: dict[str, Any]) -> Iterable[Condition]:
    for entry in data.get("INCOND", []):
        yield Condition(node, entry["NAME"], "in", entry.get("ODATE", ""), entry.get("AND_OR"))
    for entry in data.get("OUTCOND", []):
        sign = "out+" if entry.get("SIGN", "+") == "+" else "out-"
        yield Condition(node, entry["NAME"], sign, entry.get("ODATE", ""))
    for on in data.get("ON", []):
        code = on.get("CODE")
        for child in on.get("children", []):
            if child.get("tag") == "DOCOND":
                sign = "do+" if child.get("SIGN", "+") == "+" else "do-"
                yield Condition(node, child["NAME"], sign, child.get("ODATE", ""), on_code=code)


def folder_names(repo: ChainRepo) -> list[str]:
    """Folders present on disk, sorted."""
    if not repo.folders_dir.is_dir():
        return []
    return sorted(p.name for p in repo.folders_dir.iterdir() if (p / "folder.json").is_file())


def collect_conditions(repo: ChainRepo) -> tuple[Condition, ...]:
    """Read every condition from the folder and job JSON files of the repository."""
    conditions: list[Condition] = []
    for folder in folder_names(repo):
        data = read_json(repo.folder_file(folder))
        conditions.extend(_conditions_of(NodeRef(folder), data))
        for job_id in data.get("jobs", []):
            job = read_json(repo.job_file(folder, str(job_id)))
            conditions.extend(_conditions_of(NodeRef(folder, str(job_id)), job))
    return tuple(conditions)


def _unique(items: Iterable[Any]) -> tuple[Any, ...]:
    return tuple(dict.fromkeys(items))


def build_links(conditions: Iterable[Condition]) -> dict[str, Link]:
    """Group conditions by name into links, sorted by name."""
    by_name: dict[str, list[Condition]] = {}
    for condition in conditions:
        by_name.setdefault(condition.name, []).append(condition)
    links: dict[str, Link] = {}
    for name in sorted(by_name):
        group = by_name[name]
        links[name] = Link(
            name=name,
            producers=_unique(c.node for c in group if c.kind == "out+"),
            consumers=_unique(c.node for c in group if c.kind == "in"),
            deleters=_unique(c.node for c in group if c.kind == "out-"),
            docond_add=_unique((c.node, c.on_code or "") for c in group if c.kind == "do+"),
            docond_delete=_unique((c.node, c.on_code or "") for c in group if c.kind == "do-"),
            odates=tuple(sorted({c.odate for c in group})),
            and_or=tuple(sorted({c.and_or for c in group if c.and_or})),
        )
    return links


# ---------------------------------------------------------------- index on disk


def _home_folders(link: Link) -> set[str]:
    """Folders whose links.json lists the link: consumers, else producers, else deleters."""
    for side in (link.consumers, link.all_producers, link.deleters):
        if side:
            return {node.folder for node in side}
    return set()


def write_links_index(repo: ChainRepo, links: dict[str, Link]) -> int:
    """Write ``folders/<F>/links.json`` for every folder on disk. Returns the number of files."""
    per_folder: dict[str, list[Link]] = {name: [] for name in folder_names(repo)}
    for link in links.values():
        for folder in _home_folders(link):
            per_folder.setdefault(folder, []).append(link)
    for folder, entries in per_folder.items():
        payload = {
            "derived": True,
            "note": INDEX_NOTE,
            "links": [link.to_json() for link in sorted(entries, key=lambda link: link.name)],
        }
        write_json(repo.folder_dir(folder) / LINKS_FILE, payload)
    return len(per_folder)


def rebuild_links(repo: ChainRepo) -> dict[str, Link]:
    """Collect, build and write the index; returns the links."""
    links = build_links(collect_conditions(repo))
    write_links_index(repo, links)
    return links
