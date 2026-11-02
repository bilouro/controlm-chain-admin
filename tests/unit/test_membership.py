"""Folders and jobs that exist in some environments only (``"envs"`` in their JSON)."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.membership import ENVS_KEY, belongs, with_envs
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.repo import ChainRepo, read_json, write_json
from tests.support.envexports import fresh_repo, prod_export

C = "P77_CHAIN"
ING = "P77_INGEST_DAILY"


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    return fresh_repo(tmp_path)


def _mark(path: Path, envs: list[str]) -> None:
    write_json(path, {**read_json(path), ENVS_KEY: envs})


def test_an_environment_leaves_out_what_it_does_not_have(repo: ChainRepo) -> None:
    _mark(repo.folder_file(ING), ["prod"])
    _mark(repo.job_file(C, "P77_E"), ["test", "prod"])

    uat, prod = export_xml(repo, "uat"), export_xml(repo, "prod")

    assert b"UP77_INGEST_DAILY" not in uat and b'JOBNAME="UP77_E"' not in uat
    assert b'JOBNAME="UP77_D"' in uat
    assert prod == export_xml_before(repo)  # every node of prod, and no "envs" in the XML
    assert b"envs" not in prod


def export_xml_before(repo: ChainRepo) -> bytes:
    from tests.support.gitrepo import APP
    from tests.support.rawxml import filter_applications

    return filter_applications(prod_export(), {APP})


def test_an_export_that_has_the_node_adds_its_environment(repo: ChainRepo) -> None:
    _mark(repo.folder_file(ING), ["uat"])
    _mark(repo.job_file(C, "P77_E"), ["uat"])

    import_xml(repo, prod_export(), env="prod")

    assert read_json(repo.folder_file(ING))[ENVS_KEY] == ["uat", "prod"]
    assert read_json(repo.job_file(C, "P77_E"))[ENVS_KEY] == ["uat", "prod"]
    assert ENVS_KEY not in read_json(repo.job_file(C, "P77_D"))  # everywhere stays everywhere


def test_membership_helpers() -> None:
    every = ("test", "uat", "bench", "prod")
    assert belongs({}, "uat") and belongs({ENVS_KEY: ["uat"]}, "uat")
    assert not belongs({ENVS_KEY: ["prod"]}, "uat")
    assert with_envs({"A": "1"}, ["prod", "uat"], every) == {"A": "1", ENVS_KEY: ["uat", "prod"]}
    assert with_envs({ENVS_KEY: ["uat"]}, every, every) == {}  # everywhere: no key
