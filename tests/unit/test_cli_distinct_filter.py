"""``distinct --xml`` inside a chain repository only looks at the repository's application."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.ops import only_application
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"


def test_only_application_keeps_the_folders_of_one_application() -> None:
    document = only_application(parse_xml(SAMPLE_EXPORT), APP)

    assert [f.get("FOLDER_NAME") for f in document.root.elements()] == ["UP77_INGEST_DAILY"]


def test_distinct_from_xml_filters_to_the_repo_application_when_a_repo_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    assert main(["init", "--repo", str(root), "--application", APP, "--envs", "uat"]) == 0
    xml = tmp_path / "export.xml"
    xml.write_bytes(SAMPLE_EXPORT)
    capsys.readouterr()

    assert (
        main(["distinct", "NODEID", "--xml", str(xml), "--repo", str(root), "--format", "json"])
        == 0
    )
    values = [v["value"] for v in json.loads(capsys.readouterr().out)["NODEID"]]
    assert values == ["UP77_BATCH"]  # srvu-oth-bat1 belongs to the skipped application

    assert (
        main(
            [
                "distinct",
                "NODEID",
                "--xml",
                str(xml),
                "--repo",
                str(tmp_path / "nowhere"),
                "--format",
                "json",
            ]
        )
        == 0
    )
    values = [v["value"] for v in json.loads(capsys.readouterr().out)["NODEID"]]
    assert "srvu-oth-bat1" in values  # no repository: the whole export is inspected
