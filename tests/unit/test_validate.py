"""validate: one finding per anomaly of the synthetic chain, with the right severity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.repo import ChainRepo, init_repo
from controlm_chain_admin.core.validate import (
    parse_condition_name,
    render_markdown,
    render_text,
    validate,
)
from tests.support.anomalies import ANOMALY_EXPORT, EXPECTED_FINDINGS
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"
PREFIXES = ("P77", "RQ_", "RC_")

SEVERITY_OF = {
    "dangling": "error",
    "dangling-external": "info",
    "dangling-unknown": "warning",
    "unconsumed": "warning",
    "unconsumed-external": "info",
    "never-cleaned": "warning",
    "stale-name": "warning",
    "duplicate-jobname": "warning",
    "non-standard-name": "info",
}


def _import(tmp_path: Path, data: bytes) -> ChainRepo:
    repo = init_repo(tmp_path, APP, ("uat", "prod"), prefixes=PREFIXES)
    import_xml(repo, data, env="uat")
    return repo


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("P77_A-P77_B_OK", ("P77_A", "P77_B")),
        ("P77_A-TO-P77_B", ("P77_A", "P77_B")),
        ("P77_A-P77_B_Ok", ("P77_A", "P77_B")),
        ("P77_A_P77_B_OK", None),
        ("WEIRD_NAME", None),
        ("P77_A-P77_B_OK-U26", None),
    ],
)
def test_parse_condition_name(name: str, expected: tuple[str, str] | None) -> None:
    assert parse_condition_name(name) == expected


def test_every_anomaly_is_found_exactly_once_with_its_severity(tmp_path: Path) -> None:
    repo = _import(tmp_path, ANOMALY_EXPORT)

    report = validate(repo)

    found: dict[str, set[str]] = {}
    for finding in report.findings:
        found.setdefault(finding.code, set()).add(finding.name)
        assert finding.severity == SEVERITY_OF[finding.code], finding
    assert found == EXPECTED_FINDINGS
    assert report.links == 10 and report.nodes == 8  # folder + 7 jobs
    assert report.worst == "error"
    assert report.count("error") == 1


def test_clean_chain_yields_only_external_information(tmp_path: Path) -> None:
    repo = _import(tmp_path, SAMPLE_EXPORT)

    report = validate(repo)

    assert [f.code for f in report.findings] == ["dangling-external"]
    assert report.worst == "info"


def test_findings_carry_the_node_they_belong_to(tmp_path: Path) -> None:
    repo = _import(tmp_path, ANOMALY_EXPORT)

    by_code = {f.code: f for f in validate(repo).findings}

    assert by_code["never-cleaned"].node == "P77_CHAIN/P77_C"
    assert by_code["duplicate-jobname"].node == "P77_CHAIN/"
    assert by_code["dangling"].node == "P77_CHAIN/P77_E"
    assert "P77_A" in by_code["dangling"].message


def test_text_and_markdown_renderings_mention_counts_and_findings(tmp_path: Path) -> None:
    report = validate(_import(tmp_path, ANOMALY_EXPORT))

    text = render_text(report)
    md = render_markdown(report)

    assert "1 error" in text and "P77_A-P77_E_OK" in text
    assert md.startswith("# Validation report") and "| error |" in md


def test_cli_validate_exit_codes_and_formats(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _import(tmp_path / "bad", ANOMALY_EXPORT)
    _import(tmp_path / "ok", SAMPLE_EXPORT)

    assert main(["validate", "--repo", str(tmp_path / "bad")]) == 1
    assert "error" in capsys.readouterr().out
    assert main(["validate", "--repo", str(tmp_path / "ok")]) == 0
    assert main(["validate", "--repo", str(tmp_path / "ok"), "--strict"]) == 1
    capsys.readouterr()
    assert main(["validate", "--repo", str(tmp_path / "bad"), "--format", "json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["counts"]["error"] == 1 and len(data["findings"]) == sum(
        len(v) for v in EXPECTED_FINDINGS.values()
    )
