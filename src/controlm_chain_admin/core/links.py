"""Links between nodes — the source of truth for condition names.

Every INCOND / OUTCOND / DOCOND element on a node references a **link id** (``"link": "<id>"``
instead of ``NAME``). The id is the condition name as first imported (environment-neutral).
The export name of a link lives in ``folders/<F>/links.json`` of the link's *home* folder::

    {"links": {"<id>": {"name": "<export name>"}}}

Renaming a condition means editing one entry; moving or renaming jobs never touches names, and
``export --names standard`` derives names from the endpoints instead. ``folders/<F>/index.json``
is a derived view (producers, consumers, cleanup, DOCOND, kind, external) rebuilt on import and
read by ``validate``, ``graph`` and the web UI.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from controlm_chain_admin.core.repo import ChainRepo, read_json, write_json

LINKS_FILE = "links.json"  # authoritative names
INDEX_FILE = "index.json"  # derived view
LINK_KEY = "link"
INDEX_NOTE = "Derived from the nodes and links.json; regenerated on import. Do not edit."
DUPLICATE_SEPARATOR = "~"


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

    @property
    def name(self) -> str:
        """Name a standard condition embeds: the JOBNAME (without ``~n``) or the folder name."""
        base = self.job if self.job is not None else self.folder
        return base.split(DUPLICATE_SEPARATOR)[0]


@dataclass(frozen=True)
class Condition:
    """One condition element as found on a node, referencing a link id."""

    node: NodeRef
    id: str
    kind: str  # "in" | "out+" | "out-" | "do+" | "do-"
    odate: str
    and_or: str | None = None
    on_code: str | None = None  # for DOCOND: the CODE of the enclosing ON block


@dataclass(frozen=True)
class Link:
    """Everything known about one link across the repository."""

    id: str
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

    @property
    def home(self) -> str | None:
        """Folder whose links.json owns the name: first consumer, else producer, else deleter."""
        for side in (
            self.consumers,
            self.all_producers,
            self.deleters,
            tuple(n for n, _ in self.docond_delete),
        ):
            if side:
                return side[0].folder
        return None

    def standard_name(self) -> str | None:
        """``<PRODUCER>-<CONSUMER>_OK`` when the link has exactly one producer and one consumer."""
        producers = self.all_producers
        if len(producers) != 1 or len(self.consumers) != 1:
            return None
        return f"{producers[0].name}-{self.consumers[0].name}_OK"

    def to_json(self, standard: str | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "standard": standard,
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


def _conditions_of(node: NodeRef, data: Mapping[str, Any]) -> Iterable[Condition]:
    for entry in data.get("INCOND", []):
        yield Condition(node, entry[LINK_KEY], "in", entry.get("ODATE", ""), entry.get("AND_OR"))
    for entry in data.get("OUTCOND", []):
        sign = "out+" if entry.get("SIGN", "+") == "+" else "out-"
        yield Condition(node, entry[LINK_KEY], sign, entry.get("ODATE", ""))
    for on in data.get("ON", []):
        code = on.get("CODE")
        for child in on.get("children", []):
            if child.get("tag") == "DOCOND":
                sign = "do+" if child.get("SIGN", "+") == "+" else "do-"
                yield Condition(node, child[LINK_KEY], sign, child.get("ODATE", ""), on_code=code)


def folder_names(repo: ChainRepo) -> list[str]:
    """Folders present on disk, sorted."""
    if not repo.folders_dir.is_dir():
        return []
    return sorted(p.name for p in repo.folders_dir.iterdir() if (p / "folder.json").is_file())


def collect_conditions(repo: ChainRepo) -> tuple[Condition, ...]:
    """Read every condition reference from the folder and job JSON files of the repository."""
    conditions: list[Condition] = []
    for folder in folder_names(repo):
        data = read_json(repo.folder_file(folder))
        conditions.extend(_conditions_of(NodeRef(folder), data))
        for job_id in data.get("jobs", []):
            job = read_json(repo.job_file(folder, str(job_id)))
            conditions.extend(_conditions_of(NodeRef(folder, str(job_id)), job))
    return tuple(conditions)


def read_names(repo: ChainRepo) -> dict[str, str]:
    """``id -> export name`` merged from every folder's links.json."""
    names: dict[str, str] = {}
    for folder in folder_names(repo):
        path = repo.folder_dir(folder) / LINKS_FILE
        if not path.is_file():
            continue
        entries = read_json(path).get("links", {})
        if not isinstance(entries, dict):  # legacy derived index (a list): no names to keep
            continue
        for link_id, entry in entries.items():
            names[str(link_id)] = str(entry.get("name", link_id))
    return names


def _unique(items: Iterable[Any]) -> tuple[Any, ...]:
    return tuple(dict.fromkeys(items))


def build_links(conditions: Iterable[Condition], names: Mapping[str, str]) -> dict[str, Link]:
    """Group condition references by link id, sorted by id; the name comes from ``names``."""
    by_id: dict[str, list[Condition]] = {}
    for condition in conditions:
        by_id.setdefault(condition.id, []).append(condition)
    links: dict[str, Link] = {}
    for link_id in sorted(by_id):
        group = by_id[link_id]
        links[link_id] = Link(
            id=link_id,
            name=names.get(link_id, link_id),
            producers=_unique(c.node for c in group if c.kind == "out+"),
            consumers=_unique(c.node for c in group if c.kind == "in"),
            deleters=_unique(c.node for c in group if c.kind == "out-"),
            docond_add=_unique((c.node, c.on_code or "") for c in group if c.kind == "do+"),
            docond_delete=_unique((c.node, c.on_code or "") for c in group if c.kind == "do-"),
            odates=tuple(sorted({c.odate for c in group})),
            and_or=tuple(sorted({c.and_or for c in group if c.and_or})),
        )
    return links


def load_links(repo: ChainRepo) -> dict[str, Link]:
    """All links of the repository with their export names (nothing written)."""
    return build_links(collect_conditions(repo), read_names(repo))


# ---------------------------------------------------------------- standard names


def standard_names(links: Mapping[str, Link]) -> dict[str, str]:
    """Export names derived from the endpoints, with folder-prefixed disambiguation on collision.

    Links without a single producer and consumer (externals, fan-in, delete-only) keep their
    current name and are left out of the result.
    """
    candidates: dict[str, list[str]] = {}
    for link in links.values():
        standard = link.standard_name()
        if standard is not None:
            candidates.setdefault(standard, []).append(link.id)
    result: dict[str, str] = {}
    for standard, ids in candidates.items():
        if len(ids) == 1:
            result[ids[0]] = standard
            continue
        prefixed: dict[str, list[str]] = {}
        for link_id in ids:
            producer = links[link_id].all_producers[0]
            prefixed.setdefault(f"{producer.folder}_{standard}", []).append(link_id)
        for name, same in prefixed.items():
            if len(same) == 1:
                result[same[0]] = name
            # still colliding: those links keep their current names
    return result


# ---------------------------------------------------------------- files


def write_names(repo: ChainRepo, links: Mapping[str, Link]) -> int:
    """Write links.json (``id -> name``) in each link's home folder. Returns the files written."""
    per_folder: dict[str, dict[str, dict[str, str]]] = {name: {} for name in folder_names(repo)}
    for link in links.values():
        home = link.home
        if home is not None:
            per_folder.setdefault(home, {})[link.id] = {"name": link.name}
    for folder, entries in per_folder.items():
        write_json(repo.folder_dir(folder) / LINKS_FILE, {"links": entries})
    return len(per_folder)


def write_index(repo: ChainRepo, links: Mapping[str, Link]) -> int:
    """Write the derived index.json per folder. Returns the number of files."""
    standards = standard_names(links)
    per_folder: dict[str, list[Link]] = {name: [] for name in folder_names(repo)}
    for link in links.values():
        home = link.home
        if home is not None:
            per_folder.setdefault(home, []).append(link)
    for folder, entries in per_folder.items():
        payload = {
            "derived": True,
            "note": INDEX_NOTE,
            "links": [link.to_json(standards.get(link.id)) for link in entries],
        }
        write_json(repo.folder_dir(folder) / INDEX_FILE, payload)
    return len(per_folder)


def rebuild_links(repo: ChainRepo) -> dict[str, Link]:
    """Collect the references, resolve names and rewrite the derived index; returns the links."""
    links = load_links(repo)
    write_index(repo, links)
    return links
