"""--dedupe-jobnames: repeated JOBNAMEs get a numeric suffix; originals restorable on export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.ops import dedupe_jobnames, export_xml, import_xml
from controlm_chain_admin.core.repo import ChainRepo, init_repo
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.rawxml import split_folders
from tests.support.samples import SAMPLE_EXPORT
from tests.unit.test_repo_ops import snapshot

APP = "P77_RISK_ENGINE"
PREFIXES = ("P77", "RQ_", "RC_")


def _double(second_suffix: bytes = b"") -> bytes:
    """ANOMALY_EXPORT plus a copy of its folder named UP77_CHAIN2 (same job names)."""
    raw = split_folders(ANOMALY_EXPORT)
    chunk = ANOMALY_EXPORT[raw.folders[0].start : raw.folders[0].end].replace(
        b"UP77_CHAIN", b"UP77_CHAIN2"
    )
    if second_suffix:
        chunk = chunk.replace(b'_OK"', second_suffix + b'"')
    return ANOMALY_EXPORT.replace(b"</DEFTABLE>\n", chunk + b"</DEFTABLE>\n")


def _repo(tmp_path: Path) -> ChainRepo:
    return init_repo(tmp_path, APP, ("uat", "prod"), prefixes=PREFIXES)


def _read(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(path.read_text("utf-8"))  # type: ignore[no-any-return]


def _jobnames(xml: bytes) -> list[str]:
    return [
        j.get("JOBNAME") or "" for f in parse_xml(xml).root.elements() for j in f.find_all("JOB")
    ]


# ---------------------------------------------------------------- pure function


def test_dedupe_renames_later_occurrences_in_document_order_and_skips_taken_names() -> None:
    xml = (
        b'<?xml version="1.0" encoding="utf-8"?>\n<DEFTABLE>\n'
        b'    <SMART_FOLDER FOLDER_NAME="F1">\n'
        b'        <JOB JOBNAME="X" />\n        <JOB JOBNAME="X" />\n'
        b'        <JOB JOBNAME="X2" />\n    </SMART_FOLDER>\n'
        b'    <SMART_FOLDER FOLDER_NAME="F2">\n        <JOB JOBNAME="X" />\n    </SMART_FOLDER>\n'
        b"</DEFTABLE>\n"
    )

    document, renames = dedupe_jobnames(parse_xml(xml))

    names = [j.get("JOBNAME") for f in document.root.elements() for j in f.find_all("JOB")]
    assert names == ["X", "X3", "X2", "X4"]
    assert renames == (("F1", "X", "X3"), ("F2", "X", "X4"))


def test_dedupe_of_unique_names_changes_nothing() -> None:
    document = parse_xml(SAMPLE_EXPORT)  # every JOBNAME is unique

    deduped, renames = dedupe_jobnames(document)

    assert renames == () and deduped == document


# ---------------------------------------------------------------- repository


def test_import_with_dedupe_renames_across_and_inside_folders(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    report = import_xml(repo, _double(), env="uat", dedupe_jobnames=True)

    assert _read(tmp_path / "chain.json")["dedupe_jobnames"] is True
    assert report.duplicate_job_names == ()
    assert "P77_CHAIN/P77_F -> P77_F2" in report.jobnames_deduped
    assert "P77_CHAIN2/P77_A -> P77_A2" in report.jobnames_deduped
    assert len(report.jobnames_deduped) == 8  # F (2nd) in CHAIN, then all 7 jobs of CHAIN2
    assert _read(tmp_path / "folders/P77_CHAIN2/folder.json")["jobs"][0] == "P77_A2"
    job = _read(tmp_path / "folders/P77_CHAIN2/jobs/P77_A2.json")
    assert job["JOBNAME"] == "P77_A2" and job["MEMNAME"] == "P77_A"  # MEMNAME is never renamed
    meta = _read(tmp_path / "meta/folders/P77_CHAIN2.json")
    assert meta["original_jobnames"]["P77_A2"] == "P77_A"
    assert "original_jobnames" in _read(tmp_path / "meta/folders/P77_CHAIN.json")


def test_export_writes_deduped_names_by_default_and_restores_originals_on_request(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    data = _double()
    import_xml(repo, data, env="uat", dedupe_jobnames=True)

    deduped = export_xml(repo, env="uat")
    original = export_xml(repo, env="uat", jobnames="original")

    assert "UP77_A2" in _jobnames(deduped) and "UP77_F4" in _jobnames(deduped)
    assert original == data  # byte-identical with the original names


def test_standard_names_become_unique_once_jobnames_are_deduped(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    import_xml(repo, _double(second_suffix=b"_DONE"), env="uat", dedupe_jobnames=True)

    out = export_xml(repo, env="uat", names="standard")

    assert b'NAME="UP77_A2-UP77_B2_OK"' in out
    assert b'NAME="UP77_A-UP77_B_OK"' in out
    assert b"UP77_CHAIN2_UP77_A" not in out  # no folder prefix needed any more


def test_dedupe_policy_persists_and_reimport_is_idempotent(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    data = _double()
    import_xml(repo, data, env="uat", dedupe_jobnames=True)
    before = snapshot(tmp_path)

    import_xml(
        repo, export_xml(repo, env="uat"), env="uat"
    )  # deduped export, policy from chain.json
    assert snapshot(tmp_path) == before
    import_xml(repo, data, env="uat")  # a fresh original export again
    assert snapshot(tmp_path) == before


def test_cli_dedupe_and_jobnames_flags(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
    xml = tmp_path / "export.xml"
    data = _double()
    xml.write_bytes(data)
    capsys.readouterr()

    assert (
        main(["import", str(xml), "--repo", str(root), "--env", "uat", "--dedupe-jobnames"]) == 0
    )
    out = capsys.readouterr().out
    assert "Deduplicated JOBNAMEs: 8" in out and "P77_CHAIN2/P77_A -> P77_A2" in out

    target = tmp_path / "original.xml"
    assert (
        main(
            [
                "export",
                "--repo",
                str(root),
                "--env",
                "uat",
                "--jobnames",
                "original",
                "-o",
                str(target),
            ]
        )
        == 0
    )
    assert target.read_bytes() == data


def test_a_partial_export_keeps_the_names_the_full_one_gave(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    import_xml(repo, _double(), env="uat", dedupe_jobnames=True)
    folder_file = tmp_path / "folders/P77_CHAIN2/folder.json"
    before = _read(folder_file)["jobs"]
    raw = split_folders(_double())
    second = raw.header + _double()[raw.folders[1].start : raw.folders[1].end] + raw.footer

    import_xml(repo, second, env="uat")  # only the second folder, as a team delivers it

    assert before[0] == "P77_A2" and _read(folder_file)["jobs"] == before
    originals = _read(tmp_path / "meta/folders/P77_CHAIN2.json")["original_jobnames"]
    assert originals["P77_A2"] == "P77_A"
