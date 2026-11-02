"""Dirty names: another environment's letter, a letter in place of the P, a replaced first
letter, resources of another environment; each with its fix."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.fixes import fixes_for
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.refactor import apply, run_operation
from controlm_chain_admin.core.repo import ChainRepo, init_repo, load_repo, read_json
from controlm_chain_admin.core.validate import Finding, validate
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"
C = "P77_CHAIN"
ING = "P77_INGEST_DAILY"


def dirty() -> tuple[bytes, bytes]:
    """The synthetic exports (uat) with the dirty names found in real ones."""
    anomaly = (
        ANOMALY_EXPORT.replace(b"UP77_A-UP77_B_OK", b"UP77_A-PP77_B_OK")  # prod letter
        .replace(b"UP77_D-UP77_NOBODY_OK", b"U77_D-UP77_NOBODY_OK")  # U in place of the P
        .replace(b'MEMNAME="UP77_E"', b'MEMNAME="U77_E"')
        .replace(
            b'<INCOND NAME="UP77_A-PP77_B_OK" ODATE="ODAT" AND_OR="A" />',
            b'<QUANTITATIVE NAME="TRQ_AM" QUANT="1" ONFAIL="R" ONOK="R" />\n'
            b'            <INCOND NAME="UP77_A-PP77_B_OK" ODATE="ODAT" AND_OR="A" />',
        )  # the test environment's resource
    )
    sample = SAMPLE_EXPORT.replace(
        b"UP77_INGEST_INIT-UP77_INGEST_LOAD_OK", b"UP77_INGEST_INIT-UP77_INGEST_POAD_OK"
    )  # LOAD with its first letter replaced by the prod letter
    return sample, anomaly


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    repo = init_repo(
        tmp_path, APP, ("test", "uat", "bench", "prod"), prefixes=("P77", "RQ_", "RC_")
    )
    for data in dirty():
        import_xml(repo, data, env="uat")
    return load_repo(tmp_path)


def _findings(repo: ChainRepo, code: str) -> list[Finding]:
    return [f for f in validate(repo, write_index=False).findings if f.code == code]


def _fix(repo: ChainRepo, finding: Finding) -> object:
    report = validate(repo, write_index=False)
    [offered] = [
        o
        for f, o in zip(report.findings, fixes_for(repo, report.findings), strict=True)
        if f == finding
    ]
    [fix] = offered
    return fix


def test_a_condition_with_another_environments_letter(repo: ChainRepo) -> None:
    [finding] = _findings(repo, "foreign-letter")

    assert (finding.severity, finding.name) == ("warning", "P77_A-PP77_B_OK")
    assert "letter P of prod" in finding.message
    fix = _fix(repo, finding)
    assert (fix.kind, fix.params["name"]) == ("remove-letter", "P77_A-P77_B_OK")  # type: ignore[attr-defined]
    apply(repo, run_operation(repo, fix.op, fix.params))  # type: ignore[attr-defined]
    assert _findings(repo, "foreign-letter") == []


def test_a_resource_of_another_environment_is_an_error(repo: ChainRepo) -> None:
    [finding] = _findings(repo, "foreign-resource")

    assert (finding.severity, finding.node, finding.name) == ("error", f"{C}/P77_B", "TRQ_AM")
    assert "resource TRQ_AM of test" in finding.message
    fix = _fix(repo, finding)
    assert fix.kind == "remove-letter"  # type: ignore[attr-defined]
    apply(repo, run_operation(repo, fix.op, fix.params))  # type: ignore[attr-defined]
    names = [q["NAME"] for q in read_json(repo.job_file(C, "P77_B"))["QUANTITATIVE"]]
    assert names == ["RQ_AM"] and _findings(repo, "foreign-resource") == []


def test_a_letter_in_place_of_the_p(repo: ChainRepo) -> None:
    found = {f.name: f for f in _findings(repo, "letter-for-p")}

    assert set(found) == {"U77_D-P77_NOBODY_OK", "U77_E"}
    assert found["U77_E"].node == f"{C}/P77_E" and "MEMNAME" in found["U77_E"].message
    condition = _fix(repo, found["U77_D-P77_NOBODY_OK"])
    assert condition.params["name"] == "P77_D-P77_NOBODY_OK"  # type: ignore[attr-defined]
    memname = _fix(repo, found["U77_E"])
    assert (memname.op, memname.params) == (  # type: ignore[attr-defined]
        "set-attributes", {"node": f"{C}/P77_E", "changes": {"MEMNAME": "P77_E"}},
    )  # fmt: skip
    assert "script" in memname.explanation  # type: ignore[attr-defined]


def test_a_word_with_its_first_letter_replaced(repo: ChainRepo) -> None:
    [finding] = _findings(repo, "replaced-first-letter")

    assert finding.name == "P77_INGEST_INIT-P77_INGEST_POAD_OK"
    assert "POAD looks like LOAD" in finding.message
    fix = _fix(repo, finding)
    assert fix.params["name"] == "P77_INGEST_INIT-P77_INGEST_LOAD_OK"  # type: ignore[attr-defined]


def test_clean_names_have_no_such_finding(tmp_path: Path) -> None:
    repo = init_repo(
        tmp_path, APP, ("test", "uat", "bench", "prod"), prefixes=("P77", "RQ_", "RC_")
    )
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    import_xml(repo, ANOMALY_EXPORT, env="uat")

    codes = {f.code for f in validate(load_repo(tmp_path), write_index=False).findings}

    assert not codes & {
        "foreign-letter",
        "foreign-resource",
        "letter-for-p",
        "replaced-first-letter",
    }


def test_a_resource_with_an_inner_prefix_needs_the_leading_only_rule(tmp_path: Path) -> None:
    repo = init_repo(
        tmp_path, APP, ("test", "uat", "bench", "prod"), prefixes=("P77", "RQ_", "RC_")
    )
    data = ANOMALY_EXPORT.replace(
        b'<INCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" AND_OR="A" />',
        b'<QUANTITATIVE NAME="URQ_P77_AGG" QUANT="1" ONFAIL="R" ONOK="R" />\n'
        b'            <INCOND NAME="UP77_A-UP77_B_OK" ODATE="ODAT" AND_OR="A" />',
    )
    import_xml(repo, data, env="uat")  # kept literally: no leading-only rule yet
    repo = load_repo(tmp_path)

    [finding] = _findings(repo, "foreign-resource")
    report = validate(repo, write_index=False)
    offered = dict(zip(report.findings, fixes_for(repo, report.findings), strict=True))

    assert finding.name == "URQ_P77_AGG" and offered[finding] == ()
