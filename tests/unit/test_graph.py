"""Folder graph from the links index, and its text / Mermaid / DOT renderings."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.graph import (
    Edge,
    folder_graph,
    render_dot,
    render_mermaid,
    render_text,
)
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.repo import ChainRepo, init_repo
from tests.support.anomalies import ANOMALY_EXPORT

APP = "P77_RISK_ENGINE"
F = "P77_CHAIN"


def _import(tmp_path: Path) -> ChainRepo:
    repo = init_repo(tmp_path, APP, ("uat", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    return repo


def test_folder_graph_has_the_chain_edges_and_the_loose_ends(tmp_path: Path) -> None:
    graph = folder_graph(_import(tmp_path), F)

    assert graph.folder == F
    assert graph.nodes == (
        f"{F}/", f"{F}/P77_A", f"{F}/P77_B", f"{F}/P77_C", f"{F}/P77_D",
        f"{F}/P77_E", f"{F}/P77_F", f"{F}/P77_F~2",
    )  # fmt: skip
    assert set(graph.edges) == {
        Edge(f"{F}/P77_A", f"{F}/P77_B", "P77_A-P77_B_OK"),
        Edge(f"{F}/P77_B", f"{F}/P77_C", "P77_B-P77_C_OK"),
        Edge(f"{F}/P77_C", f"{F}/P77_D", "P77_OLDNAME-P77_D_OK"),
    }
    assert set(graph.dangling) == {
        (f"{F}/P77_E", "P77_A-P77_E_OK"),
        (f"{F}/P77_E", "P77_GHOST-P77_E_OK"),
        (f"{F}/P77_F", "WEIRD_NAME"),
        (f"{F}/", "P77_OTHER-P77_CHAIN_OK"),
    }
    assert set(graph.unconsumed) == {
        (f"{F}/P77_A", "P77_A-P77_C_OK"),
        (f"{F}/P77_D", "P77_D-P77_NOBODY_OK"),
        (f"{F}/", "P77_CHAIN-P77_NEXT_OK"),
    }
    assert graph.externals == ()


def test_edge_produced_only_from_an_on_block_is_conditional(tmp_path: Path) -> None:
    data = ANOMALY_EXPORT.replace(
        b'            <OUTCOND NAME="UP77_B-UP77_C_OK" ODATE="ODAT" SIGN="+" />\n', b""
    )
    repo = init_repo(tmp_path, APP, ("uat", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, data, env="uat")

    graph = folder_graph(repo, F)

    edge = next(e for e in graph.edges if e.name == "P77_B-P77_C_OK")
    assert edge.conditional is True


def test_renderings(tmp_path: Path) -> None:
    graph = folder_graph(_import(tmp_path), F)

    text = render_text(graph)
    mermaid = render_mermaid(graph)
    dot = render_dot(graph)

    assert "P77_A -> P77_B  [P77_A-P77_B_OK]" in text
    assert "P77_E  waits for P77_GHOST-P77_E_OK (no producer)" in text
    assert mermaid.startswith("flowchart LR")
    assert "P77_CHAIN_P77_A -->|P77_A-P77_B_OK| P77_CHAIN_P77_B" in mermaid
    assert dot.startswith("digraph") and '"P77_A" -> "P77_B"' in dot


def test_graph_of_unknown_folder_raises(tmp_path: Path) -> None:
    with pytest.raises(ModelError):
        folder_graph(_import(tmp_path), "P77_NOPE")
