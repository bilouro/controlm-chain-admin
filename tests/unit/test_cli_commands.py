"""``ctmchain init``, ``import`` and ``export`` through the CLI adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from tests.support.rawxml import filter_applications
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"


def _init(tmp_path: Path) -> None:
    code = main(["init", "--repo", str(tmp_path), "--application", APP, "--envs", "uat,prod"])
    assert code == 0


def test_init_creates_the_repo_and_reports_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(tmp_path)

    out = capsys.readouterr().out
    assert (tmp_path / "chain.json").is_file()
    assert "Initialized chain repository" in out and APP in out


def test_init_takes_the_whole_letter_rule(tmp_path: Path) -> None:
    code = main(
        [
            "init", "--repo", str(tmp_path), "--application", APP, "--envs", "uat,prod",
            "--prefixes", "P77,RQ_,RC_", "--leading-only", "RQ_,RC_",
        ]
    )  # fmt: skip

    rule = json.loads((tmp_path / "chain.json").read_text(encoding="utf-8"))["letter_rule"]
    assert code == 0
    assert (rule["prefixes"], rule["leading_only"]) == (["P77", "RQ_", "RC_"], ["RQ_", "RC_"])


def test_init_leaves_a_guide_for_claude_in_the_new_repository(tmp_path: Path) -> None:
    args = ["init", "--repo", str(tmp_path), "--application", APP, "--envs", "uat=U,prod=P"]
    assert main([*args, "--prefixes", "P77"]) == 0

    guide = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert guide.startswith(f"# {APP} — chain repository")
    assert "uat (U), prod (P)" in guide and "Production is prod" in guide
    assert "never edit `main`" in guide and "ctmchain receive" in guide
    assert "ctmchain check exports/uat/full.xml --env uat" in guide


def test_init_keeps_a_guide_that_is_already_there(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("# mine\n", encoding="utf-8")

    _init(tmp_path)

    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "# mine\n"


def test_init_twice_fails_with_error_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(tmp_path)

    code = main(["init", "--repo", str(tmp_path), "--application", APP, "--envs", "uat"])

    assert code == 3
    assert "already" in capsys.readouterr().err


def test_import_reports_folders_jobs_and_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(tmp_path)
    xml = tmp_path / "export.xml"
    xml.write_bytes(SAMPLE_EXPORT)

    code = main(["import", str(xml), "--repo", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "1 folder" in out and "2 jobs" in out
    assert "UOTH_HOUSEKEEPING" in out and "OTHER_APP" in out


def test_import_json_format_prints_the_report_as_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(tmp_path)
    capsys.readouterr()  # drop the init message
    xml = tmp_path / "export.xml"
    xml.write_bytes(SAMPLE_EXPORT)

    code = main(["import", str(xml), "--repo", str(tmp_path), "--format", "json"])

    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["folders"] == ["UP77_INGEST_DAILY"]
    assert report["skipped"] == [{"folder": "UOTH_HOUSEKEEPING", "application": "OTHER_APP"}]


def test_export_writes_the_filtered_original(tmp_path: Path) -> None:
    _init(tmp_path)
    xml = tmp_path / "export.xml"
    xml.write_bytes(SAMPLE_EXPORT)
    main(["import", str(xml), "--repo", str(tmp_path)])
    out = tmp_path / "out.xml"

    code = main(["export", "--repo", str(tmp_path), "-o", str(out)])

    assert code == 0
    assert out.read_bytes() == filter_applications(SAMPLE_EXPORT, {APP})


def test_commands_on_a_directory_without_chain_json_fail_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["export", "--repo", str(tmp_path), "-o", str(tmp_path / "x.xml")])

    assert code == 3
    assert "chain.json" in capsys.readouterr().err


def test_import_of_malformed_xml_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init(tmp_path)
    bad = tmp_path / "bad.xml"
    bad.write_bytes(b"<nope")

    code = main(["import", str(bad), "--repo", str(tmp_path)])

    assert code == 3
    assert "malformed" in capsys.readouterr().err.lower()
