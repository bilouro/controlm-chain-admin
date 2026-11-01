"""CLI of the refactorings: preview by default, --apply writes; plus a quiet BrokenPipe."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.samples import SAMPLE_EXPORT
from tests.unit.test_repo_ops import snapshot

APP = "P77_RISK_ENGINE"


def _repo(tmp_path: Path, *exports: bytes) -> Path:
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
                "uat",
                "--prefixes",
                "P77,RQ_,RC_",
            ]
        )
        == 0
    )
    for index, data in enumerate(exports or (ANOMALY_EXPORT,)):
        xml = tmp_path / f"export{index}.xml"
        xml.write_bytes(data)
        assert main(["import", str(xml), "--repo", str(root), "--env", "uat"]) == 0
    return root


def test_preview_prints_summary_and_diff_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    before = snapshot(root)
    capsys.readouterr()

    assert main(["rename-job", "P77_CHAIN/P77_B", "P77_BETA", "--repo", str(root)]) == 0

    out = capsys.readouterr().out
    assert out.startswith("rename job P77_CHAIN/P77_B -> P77_CHAIN/P77_BETA")
    assert "+++ b/folders/P77_CHAIN/jobs/P77_BETA.json" in out
    assert "Preview only" in out and "--apply" in out
    assert snapshot(root) == before


def test_apply_writes_and_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    capsys.readouterr()

    assert (
        main(
            ["rename-job", "P77_CHAIN/P77_B", "P77_BETA", "--repo", str(root), "--apply", "--stat"]
        )
        == 0
    )

    out = capsys.readouterr().out
    assert "  create  folders/P77_CHAIN/jobs/P77_BETA.json" in out
    assert "Applied: 4 written, 1 deleted" in out
    assert (root / "folders/P77_CHAIN/jobs/P77_BETA.json").is_file()


def test_json_format_and_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, ANOMALY_EXPORT, SAMPLE_EXPORT)
    capsys.readouterr()

    assert (
        main(
            [
                "rename-subapp",
                "P77_BATCH",
                "P77_CORE",
                "--folder",
                "P77_CHAIN",
                "--repo",
                str(root),
                "--format",
                "json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["applied"] is False and len(data["files"]) == 8

    assert main(["rename-job", "P77_CHAIN/NOPE", "P77_X", "--repo", str(root)]) == 3
    assert "unknown job" in capsys.readouterr().err


def test_every_refactoring_is_wired(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, ANOMALY_EXPORT, SAMPLE_EXPORT)
    r = ["--repo", str(root), "--apply", "--stat"]

    assert main(["rename-folder", "P77_CHAIN", "P77_FLOW", *r]) == 0
    assert main(["move-job", "P77_INGEST_DAILY/P77_INGEST_LOAD", "P77_FLOW", *r]) == 0
    assert (
        main(
            [
                "insert-job",
                "P77_FLOW/P77_NEW",
                "--after",
                "P77_FLOW/P77_A",
                "--before",
                "P77_FLOW/P77_B",
                "--like",
                "P77_FLOW/P77_B",
                *r,
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "extract-variable",
                "P77_FLOW/P77_INGEST_LOAD",
                "--literal",
                "/opt/p77/bin",
                "--as",
                "%%BINDIR",
                *r,
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["graph", "P77_FLOW", "--repo", str(root)]) == 0
    out = capsys.readouterr().out
    assert "P77_A -> P77_NEW" in out and "P77_NEW -> P77_B" in out
    assert (root / "folders/P77_FLOW/jobs/P77_INGEST_LOAD.json").is_file()


def test_output_piped_into_a_closed_reader_does_not_print_a_broken_pipe_error(
    tmp_path: Path,
) -> None:
    folders = b"".join(
        f'    <SMART_FOLDER APPLICATION="{APP}" FOLDER_NAME="UP77_F{i:04d}">\n'
        f'        <INCOND NAME="UP77_FAR-UP77_F{i:04d}_OK" ODATE="ODAT" AND_OR="A" />\n'
        "    </SMART_FOLDER>\n".encode()
        for i in range(800)
    )
    data = b'<?xml version="1.0" encoding="utf-8"?>\n<DEFTABLE>\n' + folders + b"</DEFTABLE>\n"
    root = _repo(tmp_path, data)

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "controlm_chain_admin",
            "validate",
            "--repo",
            str(root),
            "--strict",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None and process.stderr is not None
    process.stdout.read(100)
    process.stdout.close()  # like `| head -1`
    error = process.stderr.read()
    process.wait(timeout=60)

    assert b"Broken pipe" not in error and b"Traceback" not in error
