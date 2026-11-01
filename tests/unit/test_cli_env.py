"""CLI flags of the letter rule: ``init --envs name=L --prefixes``, ``import/export --env``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from tests.support.rawxml import filter_applications
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"


def _init(tmp_path: Path) -> None:
    code = main(
        [
            "init", "--repo", str(tmp_path), "--application", APP,
            "--envs", "test=T,uat=U,bench=B,prod=P", "--prefixes", "P77,RQ_,RC_",
        ]
    )  # fmt: skip
    assert code == 0


def test_init_with_letters_and_prefixes(tmp_path: Path) -> None:
    _init(tmp_path)

    chain = json.loads((tmp_path / "chain.json").read_text("utf-8"))
    env = json.loads((tmp_path / "envs/bench/env.json").read_text("utf-8"))
    assert chain["letter_rule"]["prefixes"] == ["P77", "RQ_", "RC_"]
    assert env == {"name": "bench", "letter": "B", "display": "BENCH", "constants": {}}


def test_import_needs_env_and_export_targets_an_env(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(tmp_path)
    xml = tmp_path / "export.xml"
    xml.write_bytes(SAMPLE_EXPORT)

    assert main(["import", str(xml), "--repo", str(tmp_path)]) == 3
    assert "--env" in capsys.readouterr().err

    assert main(["import", str(xml), "--repo", str(tmp_path), "--env", "uat"]) == 0
    assert (tmp_path / "folders/P77_INGEST_DAILY/folder.json").is_file()

    out = tmp_path / "prod.xml"
    assert main(["export", "--repo", str(tmp_path), "--env", "prod", "-o", str(out)]) == 0
    assert b'FOLDER_NAME="PP77_INGEST_DAILY"' in out.read_bytes()

    same = tmp_path / "uat.xml"
    assert main(["export", "--repo", str(tmp_path), "--env", "uat", "-o", str(same)]) == 0
    assert same.read_bytes() == filter_applications(SAMPLE_EXPORT, {APP})


def test_import_report_lists_literal_marks_and_suspicious_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(tmp_path)
    data = SAMPLE_EXPORT.replace(
        b'NAME="UP77_PRICING-UP77_INGEST_DAILY_OK"', b'NAME="PP77_PRICING-UP77_INGEST_DAILY_OK"'
    ).replace(b'MEMNAME="UP77_INGEST_INIT"', b'MEMNAME="P77_RAW"')
    xml = tmp_path / "export.xml"
    xml.write_bytes(data)
    capsys.readouterr()

    code = main(["import", str(xml), "--repo", str(tmp_path), "--env", "uat", "--format", "json"])

    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["environment"] == "uat"
    assert report["suspicious_values"] == [
        "INCOND/@NAME=PP77_PRICING-UP77_INGEST_DAILY_OK",
        "OUTCOND/@NAME=PP77_PRICING-UP77_INGEST_DAILY_OK",
    ]
    assert report["literal_marks"] == ["JOB/@MEMNAME=P77_RAW"]
    job = json.loads(
        (tmp_path / "folders/P77_INGEST_DAILY/jobs/P77_INGEST_INIT.json").read_text("utf-8")
    )
    assert job["MEMNAME"] == "literal:P77_RAW"


def test_text_report_mentions_marks_and_suspicious_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(tmp_path)
    data = SAMPLE_EXPORT.replace(b'MEMNAME="UP77_INGEST_INIT"', b'MEMNAME="P77_RAW"')
    xml = tmp_path / "export.xml"
    xml.write_bytes(data)
    capsys.readouterr()

    assert main(["import", str(xml), "--repo", str(tmp_path), "--env", "uat"]) == 0

    out = capsys.readouterr().out
    assert "Literal marks" in out and "JOB/@MEMNAME=P77_RAW" in out
