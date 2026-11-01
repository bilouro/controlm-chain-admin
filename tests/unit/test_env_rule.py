"""Letter rule wired into the repository: neutral names on disk, letter chosen at export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.core.errors import EnvironmentRequired, ModelError, UnknownEnvironment
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.repo import init_repo
from tests.support.rawxml import filter_applications
from tests.support.samples import SAMPLE_EXPORT
from tests.unit.test_repo_ops import snapshot

APP = "P77_RISK_ENGINE"
ENVS = ("test", "uat", "bench", "prod")
PREFIXES = ("P77", "RQ_", "RC_")


def _repo(tmp_path: Path):  # type: ignore[no-untyped-def]
    return init_repo(tmp_path, APP, ENVS, prefixes=PREFIXES)


def test_init_records_the_rule_and_default_letters(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    chain = json.loads((tmp_path / "chain.json").read_text("utf-8"))
    assert chain["letter_rule"]["prefixes"] == list(PREFIXES)
    assert "JOBNAME" in chain["letter_rule"]["attributes"]
    assert repo.env_letters() == {"test": "T", "uat": "U", "bench": "B", "prod": "P"}
    assert repo.load_env("prod").display == "PROD"


def test_init_accepts_explicit_letters_and_rejects_duplicates(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "a", APP, ("uat", "prod"), letters={"uat": "X"})
    assert repo.env_letters() == {"uat": "X", "prod": "P"}

    with pytest.raises(ModelError):
        init_repo(tmp_path / "b", APP, ("prod", "preprod"))  # both default to P


def test_import_with_env_writes_environment_neutral_paths_and_names(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    report = import_xml(repo, SAMPLE_EXPORT, env="uat")

    assert report.environment == "uat"
    assert report.folders == ("P77_INGEST_DAILY",)
    folder = json.loads((tmp_path / "folders/P77_INGEST_DAILY/folder.json").read_text("utf-8"))
    job = json.loads(
        (tmp_path / "folders/P77_INGEST_DAILY/jobs/P77_INGEST_LOAD.json").read_text("utf-8")
    )
    assert folder["FOLDER_NAME"] == "P77_INGEST_DAILY"
    assert folder["jobs"] == ["P77_INGEST_INIT", "P77_INGEST_LOAD"]
    assert job["INCOND"][0]["NAME"] == "P77_INGEST_INIT-P77_INGEST_LOAD_OK"
    assert job["NODEID"] == "UP77_BATCH"  # not a name attribute: kept until constants exist
    assert report.literal_marks == () and report.suspicious_values == ()


def test_export_for_the_source_environment_is_byte_identical(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    import_xml(repo, SAMPLE_EXPORT, env="uat")

    assert export_xml(repo, env="uat") == filter_applications(SAMPLE_EXPORT, {APP})


def test_export_for_another_environment_rewrites_every_prefixed_name(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    import_xml(repo, SAMPLE_EXPORT, env="uat")

    prod = export_xml(repo, env="prod")

    assert b'FOLDER_NAME="PP77_INGEST_DAILY"' in prod
    assert b'NAME="PP77_INGEST_INIT-PP77_INGEST_LOAD_OK"' in prod
    assert b'NAME="PRQ_AM"' in prod
    assert b'NODEID="UP77_BATCH"' in prod  # untouched: not a name attribute
    assert b"UP77_" not in prod.replace(b'NODEID="UP77_BATCH"', b"")


def test_reimport_of_an_export_for_another_environment_changes_no_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    before = snapshot(tmp_path)

    import_xml(repo, export_xml(repo, env="prod"), env="prod")

    assert snapshot(tmp_path) == before


def test_import_and_export_require_the_environment_when_the_rule_is_enabled(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)

    with pytest.raises(EnvironmentRequired):
        import_xml(repo, SAMPLE_EXPORT)
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    with pytest.raises(EnvironmentRequired):
        export_xml(repo)


def test_unknown_environment_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    with pytest.raises(UnknownEnvironment):
        import_xml(repo, SAMPLE_EXPORT, env="staging")


def test_without_prefixes_the_rule_is_off_and_env_is_optional(tmp_path: Path) -> None:
    repo = init_repo(tmp_path, APP, ENVS)

    import_xml(repo, SAMPLE_EXPORT)

    assert (tmp_path / "folders/UP77_INGEST_DAILY/folder.json").is_file()
    assert export_xml(repo, env="prod") == filter_applications(SAMPLE_EXPORT, {APP})
