"""distinct values and show on an XML document and on a repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.errors import ModelError
from controlm_chain_admin.core.inspect import distinct_values, load_document, show_node
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.repo import ChainRepo, init_repo
from controlm_chain_admin.core.xmlio import parse_xml
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"


def _import(tmp_path: Path) -> ChainRepo:
    repo = init_repo(tmp_path, APP, ("uat", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    return repo


def test_distinct_on_a_document_counts_values_and_samples_nodes() -> None:
    result = distinct_values(parse_xml(SAMPLE_EXPORT), ["NODEID", "RUN_AS"])

    nodeid = [(v.value, v.count) for v in result["NODEID"]]
    assert nodeid == [("UP77_BATCH", 2), ("srvu-oth-bat1", 1)]
    assert result["NODEID"][0].samples == (
        "UP77_INGEST_DAILY/UP77_INGEST_INIT",
        "UP77_INGEST_DAILY/UP77_INGEST_LOAD",
    )
    run_as = {v.value: v.count for v in result["RUN_AS"]}
    assert run_as == {"aup77proc": 3, "root": 1}  # folder-level RUN_AS counts too


def test_distinct_with_tag_qualified_spec_restricts_the_element() -> None:
    result = distinct_values(parse_xml(SAMPLE_EXPORT), ["DOMAIL/@DEST", "VARIABLE/@VALUE"])

    assert [(v.value, v.count) for v in result["DOMAIL/@DEST"]] == [("ops@example.com", 1)]
    assert result["DOMAIL/@DEST"][0].samples == ("UP77_INGEST_DAILY/UP77_INGEST_LOAD",)
    assert {v.value for v in result["VARIABLE/@VALUE"]} == {"u"}
    assert result["VARIABLE/@VALUE"][0].samples == ("UP77_INGEST_DAILY/",)


def test_distinct_on_the_repository_sees_neutral_names(tmp_path: Path) -> None:
    repo = _import(tmp_path)

    result = distinct_values(load_document(repo), ["JOBNAME", "NODEID"])

    assert [v.value for v in result["JOBNAME"]] == [
        "P77_INGEST_DAILY",
        "P77_INGEST_INIT",
        "P77_INGEST_LOAD",
    ]
    assert [(v.value, v.count) for v in result["NODEID"]] == [("UP77_BATCH", 2)]


def test_show_returns_job_json_with_its_metadata(tmp_path: Path) -> None:
    repo = _import(tmp_path)

    job = show_node(repo, "P77_INGEST_DAILY/P77_INGEST_LOAD")
    folder = show_node(repo, "P77_INGEST_DAILY/")

    assert job["JOBNAME"] == "P77_INGEST_LOAD"
    assert job["meta"] == {"JOBISN": "3"}
    assert job["INCOND"][0]["NAME"] == "P77_INGEST_INIT-P77_INGEST_LOAD_OK"
    assert folder["FOLDER_NAME"] == "P77_INGEST_DAILY" and folder["jobs"] == [
        "P77_INGEST_INIT",
        "P77_INGEST_LOAD",
    ]
    assert folder["meta"] == {"JOBISN": "1"}


def test_show_unknown_node_raises_model_error(tmp_path: Path) -> None:
    repo = _import(tmp_path)

    with pytest.raises(ModelError):
        show_node(repo, "P77_INGEST_DAILY/NOPE")
    with pytest.raises(ModelError):
        show_node(repo, "NOPE/")
