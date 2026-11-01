"""CLI: distinct, show, graph and links."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"


def _repo(tmp_path: Path, data: bytes) -> Path:
    root = tmp_path / "repo"
    assert (
        main(
            [
                "init",
                "--repo",
                str(root),
                "--application",
                APP,
                "--envs",
                "uat,prod",
                "--prefixes",
                "P77,RQ_,RC_",
            ]
        )
        == 0
    )
    xml = tmp_path / "export.xml"
    xml.write_bytes(data)
    assert main(["import", str(xml), "--repo", str(root), "--env", "uat"]) == 0
    return root


def test_distinct_from_xml_and_from_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, SAMPLE_EXPORT)
    capsys.readouterr()

    assert main(["distinct", "NODEID", "--xml", str(tmp_path / "export.xml")]) == 0
    out = capsys.readouterr().out
    assert "NODEID" in out and "UP77_BATCH" in out and "2" in out

    assert main(["distinct", "JOBNAME", "--repo", str(root), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [v["value"] for v in data["JOBNAME"]] == [
        "P77_INGEST_DAILY",
        "P77_INGEST_INIT",
        "P77_INGEST_LOAD",
    ]


def test_show_prints_the_node_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, SAMPLE_EXPORT)
    capsys.readouterr()

    assert main(["show", "P77_INGEST_DAILY/P77_INGEST_LOAD", "--repo", str(root)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["JOBNAME"] == "P77_INGEST_LOAD" and data["meta"] == {"JOBISN": "3"}

    assert main(["show", "P77_INGEST_DAILY/NOPE", "--repo", str(root)]) == 3


def test_graph_formats(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, ANOMALY_EXPORT)
    capsys.readouterr()

    assert main(["graph", "P77_CHAIN", "--repo", str(root)]) == 0
    assert "P77_A -> P77_B" in capsys.readouterr().out
    assert main(["graph", "P77_CHAIN", "--repo", str(root), "--format", "mermaid"]) == 0
    assert capsys.readouterr().out.startswith("flowchart LR")
    assert main(["graph", "P77_CHAIN", "--repo", str(root), "--format", "json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["edges"]) == 3
    assert main(["graph", "P77_NOPE", "--repo", str(root)]) == 3


def test_links_by_node_and_by_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, ANOMALY_EXPORT)
    capsys.readouterr()

    assert main(["links", "P77_CHAIN/P77_B", "--repo", str(root)]) == 0
    out = capsys.readouterr().out
    assert "P77_A-P77_B_OK" in out and "P77_B-P77_C_OK" in out and "P77_OLDNAME" not in out

    assert (
        main(["links", "--name", "P77_OLDNAME-P77_D_OK", "--repo", str(root), "--format", "json"])
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data[0]["from"] == ["P77_CHAIN/P77_C"] and data[0]["to"] == ["P77_CHAIN/P77_D"]

    assert main(["links", "--name", "NOPE", "--repo", str(root)]) == 3
