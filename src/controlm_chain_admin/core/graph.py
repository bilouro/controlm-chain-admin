"""Chain graph of one folder, built from the links, with text/Mermaid/DOT renderers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.links import Link, NodeRef, build_links, collect_conditions
from controlm_chain_admin.core.repo import ChainRepo, read_json


@dataclass(frozen=True)
class Edge:
    source: str  # node identity "FOLDER/JOB" or "FOLDER/"
    target: str
    name: str
    conditional: bool = False  # produced only from an ON block (DOCOND)


@dataclass(frozen=True)
class Graph:
    folder: str
    nodes: tuple[str, ...]  # the folder itself, then its jobs in folder order
    edges: tuple[Edge, ...]
    externals: tuple[str, ...]  # nodes of other folders that appear at an edge end
    dangling: tuple[tuple[str, str], ...]  # (consumer node, condition name) with no producer
    unconsumed: tuple[tuple[str, str], ...]  # (producer node, condition name) with no consumer

    def to_json(self) -> dict[str, Any]:
        return {
            "folder": self.folder,
            "nodes": list(self.nodes),
            "edges": [
                {"from": e.source, "to": e.target, "name": e.name, "conditional": e.conditional}
                for e in self.edges
            ],
            "externals": list(self.externals),
            "dangling": [{"node": n, "name": c} for n, c in self.dangling],
            "unconsumed": [{"node": n, "name": c} for n, c in self.unconsumed],
        }


def load_links(repo: ChainRepo) -> dict[str, Link]:
    """All links of the repository, computed from the nodes (nothing written)."""
    return build_links(collect_conditions(repo))


def _touches(link: Link, folder: str) -> bool:
    nodes = [*link.consumers, *link.all_producers, *link.deleters]
    return any(node.folder == folder for node in nodes)


def folder_graph(repo: ChainRepo, folder: str) -> Graph:
    """Nodes and edges of one folder, including edges to and from other folders."""
    if not repo.folder_file(folder).is_file():
        raise ModelError(f"unknown folder {folder!r}")
    data = read_json(repo.folder_file(folder))
    nodes = [str(NodeRef(folder)), *(str(NodeRef(folder, str(j))) for j in data.get("jobs", []))]
    in_folder = set(nodes)

    edges: list[Edge] = []
    externals: dict[str, None] = {}
    dangling: list[tuple[str, str]] = []
    unconsumed: list[tuple[str, str]] = []
    for link in load_links(repo).values():
        if not _touches(link, folder):
            continue
        static = set(link.producers)
        producers = link.all_producers
        if producers and link.consumers:
            for producer in producers:
                for consumer in link.consumers:
                    edges.append(
                        Edge(str(producer), str(consumer), link.name, producer not in static)
                    )
                    for end in (str(producer), str(consumer)):
                        if end not in in_folder:
                            externals[end] = None
        elif link.consumers:
            dangling.extend((str(c), link.name) for c in link.consumers if c.folder == folder)
        elif producers:
            unconsumed.extend((str(p), link.name) for p in producers if p.folder == folder)
    return Graph(
        folder=folder,
        nodes=tuple(nodes),
        edges=tuple(edges),
        externals=tuple(externals),
        dangling=tuple(dangling),
        unconsumed=tuple(unconsumed),
    )


# ---------------------------------------------------------------- renderers


def _short(node: str, folder: str) -> str:
    """Job id for nodes of the folder, ``FOLDER/`` for the folder, full identity elsewhere."""
    ref = NodeRef.parse(node)
    if ref.folder != folder:
        return node
    return ref.job if ref.job is not None else f"{folder}/"


def render_text(graph: Graph) -> str:
    lines = [f"Folder {graph.folder}: {len(graph.nodes) - 1} jobs, {len(graph.edges)} edges"]
    for edge in graph.edges:
        marker = "  (conditional)" if edge.conditional else ""
        lines.append(
            f"{_short(edge.source, graph.folder)} -> {_short(edge.target, graph.folder)}"
            f"  [{edge.name}]{marker}"
        )
    for node, name in graph.dangling:
        lines.append(f"{_short(node, graph.folder)}  waits for {name} (no producer)")
    for node, name in graph.unconsumed:
        lines.append(f"{_short(node, graph.folder)}  emits {name} (no consumer)")
    if graph.externals:
        lines.append("external nodes: " + ", ".join(graph.externals))
    return "\n".join(lines) + "\n"


def _mermaid_id(node: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", node)


def render_mermaid(graph: Graph) -> str:
    lines = ["flowchart LR"]
    for node in [*graph.nodes, *graph.externals]:
        lines.append(f'    {_mermaid_id(node)}["{_short(node, graph.folder)}"]')
    for edge in graph.edges:
        arrow = "-.->" if edge.conditional else "-->"
        lines.append(
            f"    {_mermaid_id(edge.source)} {arrow}|{edge.name}| {_mermaid_id(edge.target)}"
        )
    return "\n".join(lines) + "\n"


def render_dot(graph: Graph) -> str:
    lines = [f'digraph "{graph.folder}" {{', "    rankdir=LR;"]
    for node in [*graph.nodes, *graph.externals]:
        shape = "box" if node in graph.externals else "ellipse"
        lines.append(f'    "{_short(node, graph.folder)}" [shape={shape}];')
    for edge in graph.edges:
        style = ', style="dashed"' if edge.conditional else ""
        lines.append(
            f'    "{_short(edge.source, graph.folder)}" -> "{_short(edge.target, graph.folder)}"'
            f' [label="{edge.name}"{style}];'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"
