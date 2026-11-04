"""Predecessors and successors of every node, with the details of each relation.

A *predecessor* relation of node N is a link N waits for (an INCOND): its peers are the nodes
that emit it (OUTCOND ``+``, or DOCOND ``+`` from an ON block, marked ``conditional``), and the
relation carries N's own AND_OR, the ODATE and whether N deletes the condition (OUTCOND ``-``).
A *successor* relation is a link N emits: its peers are the consumers, each with its own AND_OR
and cleanup flag. These are the details the editing UI must preserve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from controlm_chain_admin.core.constants import resolve_json
from controlm_chain_admin.core.links import (
    Condition,
    NodeRef,
    build_links,
    collect_conditions,
    folder_names,
    read_names,
)
from controlm_chain_admin.core.membership import belongs
from controlm_chain_admin.core.repo import ChainRepo, read_json


@dataclass(frozen=True)
class Peer:
    """The other end of a relation."""

    node: str
    and_or: str | None = None  # the consumer's AND_OR (successor relations)
    cleanup: bool = False  # the consumer deletes the condition (successor relations)
    conditional: str | None = None  # ON code when the producer emits from an ON block

    def to_json(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "and_or": self.and_or,
            "cleanup": self.cleanup,
            "conditional": self.conditional,
        }


@dataclass(frozen=True)
class Relation:
    link: str
    name: str
    peers: tuple[Peer, ...]
    odate: str
    and_or: str | None  # this node's AND_OR (predecessor relations)
    cleanup: bool  # this node deletes the condition (predecessor relations)
    sign: str  # "+" static emission or "do+" from an ON block (successor relations)
    on_code: str | None
    kind: str
    external: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "link": self.link,
            "name": self.name,
            "peers": [peer.to_json() for peer in self.peers],
            "odate": self.odate,
            "and_or": self.and_or,
            "cleanup": self.cleanup,
            "sign": self.sign,
            "on_code": self.on_code,
            "kind": self.kind,
            "external": self.external,
        }


@dataclass(frozen=True)
class NodeRelations:
    predecessors: tuple[Relation, ...] = ()
    successors: tuple[Relation, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "predecessors": [r.to_json() for r in self.predecessors],
            "successors": [r.to_json() for r in self.successors],
        }


def _nodes(repo: ChainRepo) -> list[NodeRef]:
    nodes: list[NodeRef] = []
    for folder in folder_names(repo):
        nodes.append(NodeRef(folder))
        jobs = read_json(repo.folder_file(folder)).get("jobs", [])
        nodes.extend(NodeRef(folder, str(job)) for job in jobs)
    return nodes


def all_relations(repo: ChainRepo) -> dict[str, NodeRelations]:
    """Relations of every node of the repository, keyed by ``FOLDER/JOB`` or ``FOLDER/``."""
    conditions = collect_conditions(repo)
    links = build_links(conditions, read_names(repo))
    by_node: dict[NodeRef, list[Condition]] = {}
    kinds: dict[tuple[str, NodeRef], set[str]] = {}
    and_or: dict[tuple[str, NodeRef], str | None] = {}
    for condition in conditions:
        by_node.setdefault(condition.node, []).append(condition)
        kinds.setdefault((condition.id, condition.node), set()).add(condition.kind)
        if condition.kind == "in":
            and_or.setdefault((condition.id, condition.node), condition.and_or)

    def deletes(link_id: str, node: NodeRef) -> bool:
        return bool(kinds.get((link_id, node), set()) & {"out-", "do-"})

    result: dict[str, NodeRelations] = {}
    for node in _nodes(repo):
        predecessors: list[Relation] = []
        successors: list[Relation] = []
        seen_in: set[str] = set()
        seen_out: set[str] = set()
        for condition in by_node.get(node, []):
            link = links[condition.id]
            if condition.kind == "in" and condition.id not in seen_in:
                seen_in.add(condition.id)
                static = set(link.producers)
                peers = [Peer(str(p)) for p in link.producers]
                peers += [
                    Peer(str(n), conditional=code)
                    for n, code in link.docond_add
                    if n not in static
                ]
                predecessors.append(
                    Relation(
                        link.id, link.name, tuple(peers), condition.odate, condition.and_or,
                        deletes(link.id, node), "", None, link.kind, link.external,
                    )
                )  # fmt: skip
            elif condition.kind in ("out+", "do+") and condition.id not in seen_out:
                seen_out.add(condition.id)
                own = kinds.get((condition.id, node), set())
                sign = "+" if "out+" in own else "do+"
                peers = [
                    Peer(str(c), and_or=and_or.get((link.id, c)), cleanup=deletes(link.id, c))
                    for c in link.consumers
                ]
                successors.append(
                    Relation(
                        link.id, link.name, tuple(peers), condition.odate, None, False, sign,
                        None if sign == "+" else condition.on_code, link.kind, link.external,
                    )
                )  # fmt: skip
        result[str(node)] = NodeRelations(tuple(predecessors), tuple(successors))
    return result


def _compact(relation: Relation) -> list[dict[str, Any]]:
    entry = {"link": relation.link, "name": relation.name, "external": relation.external}
    if not relation.peers:
        return [{"node": None, **entry}]
    return [{"node": peer.node, **entry} for peer in relation.peers]


def _row(identity: str, data: dict[str, Any], relations: NodeRelations) -> dict[str, Any]:
    return {
        "application": data.get("APPLICATION"),
        "sub_application": data.get("SUB_APPLICATION"),
        "description": data.get("DESCRIPTION"),
        "predecessors": [e for r in relations.predecessors for e in _compact(r)],
        "successors": [e for r in relations.successors for e in _compact(r)],
    }


def chain_table(repo: ChainRepo, env: str | None = None) -> list[dict[str, Any]]:
    """Folders in export order, each with its jobs and their neighbours (the table view);
    with ``env``, the folders and jobs of that environment with its values."""
    values = repo.load_env(env).constants if env is not None else {}
    relations = all_relations(repo)
    present = folder_names(repo)
    order: list[str] = []
    if repo.export_meta_file.exists():
        order = [
            f for f in read_json(repo.export_meta_file).get("folder_order", []) if f in present
        ]
    order += [f for f in present if f not in order]
    table: list[dict[str, Any]] = []
    for folder in order:
        data = read_json(repo.folder_file(folder))
        if not belongs(data, env):
            continue
        data = resolve_json(data, repo.config.constants, values)
        row = {"name": folder, **_row(f"{folder}/", data, relations[f"{folder}/"]), "jobs": []}
        for job_id in (str(j) for j in data.get("jobs", [])):
            job = read_json(repo.job_file(folder, job_id))
            if not belongs(job, env):
                continue
            job = resolve_json(job, repo.config.constants, values)
            identity = f"{folder}/{job_id}"
            row["jobs"].append(
                {
                    "id": job_id,
                    "name": job.get("JOBNAME", job_id),
                    "task_type": job.get("TASKTYPE"),
                    "node_id": job.get("NODEID"),
                    **_row(identity, job, relations[identity]),
                }
            )
        table.append(row)
    return table
