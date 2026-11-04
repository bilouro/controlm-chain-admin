"""distinct values and show on an XML document and on a repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.constants import Selector, define_constant
from controlm_chain_admin.core.errors import ModelError, UnknownEnvironment
from controlm_chain_admin.core.inspect import distinct_values, load_document, show_node
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.overrides import Override, write_overrides
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
    assert job["INCOND"][0]["link"] == "P77_INGEST_INIT-P77_INGEST_LOAD_OK"
    assert folder["FOLDER_NAME"] == "P77_INGEST_DAILY" and folder["jobs"] == [
        "P77_INGEST_INIT",
        "P77_INGEST_LOAD",
    ]
    assert folder["meta"] == {"JOBISN": "1"}


def test_show_leaves_out_the_own_order_of_a_job_written_another_way(tmp_path: Path) -> None:
    repo = _import(tmp_path)
    canonical = (
        b'RUN_AS="aup77proc" TASKTYPE="Command" NODEID="UP77_BATCH" CMDLINE="/opt/p77/bin/load'
    )
    written = (
        b'TASKTYPE="Command" RUN_AS="aup77proc" NODEID="UP77_BATCH" CMDLINE="/opt/p77/bin/load'
    )
    import_xml(repo, SAMPLE_EXPORT.replace(canonical, written), env="uat")

    assert show_node(repo, "P77_INGEST_DAILY/P77_INGEST_LOAD")["meta"] == {"JOBISN": "3"}


def test_show_unknown_node_raises_model_error(tmp_path: Path) -> None:
    repo = _import(tmp_path)

    with pytest.raises(ModelError):
        show_node(repo, "P77_INGEST_DAILY/NOPE")
    with pytest.raises(ModelError):
        show_node(repo, "NOPE/")


def test_show_resolves_the_values_of_an_environment(tmp_path: Path) -> None:
    repo = _import(tmp_path)
    repo = define_constant(repo, "node.batch", Selector("NODEID"),
                           {"uat": "UP77_BATCH", "prod": "PP77_BATCH"})  # fmt: skip
    repo = define_constant(repo, "user.proc", Selector("RUN_AS"), {"uat": "aup77proc"})
    import_xml(repo, SAMPLE_EXPORT, env="uat")  # binds the constants
    load = "P77_INGEST_DAILY/P77_INGEST_LOAD"
    write_overrides(repo, "prod", {load: Override(attributes={"TASKTYPE": "Dummy"})})

    base = show_node(repo, load)
    uat = show_node(repo, load, env="uat")
    prod = show_node(repo, load, env="prod")

    assert (base["NODEID"], base["RUN_AS"], base["TASKTYPE"]) == (
        "@{node.batch}", "@{user.proc}", "Command",
    )  # fmt: skip
    assert (uat["NODEID"], uat["RUN_AS"], uat["TASKTYPE"]) == (
        "UP77_BATCH",
        "aup77proc",
        "Command",
    )
    assert (prod["NODEID"], prod["RUN_AS"], prod["TASKTYPE"]) == (
        "PP77_BATCH", "@{user.proc}", "Dummy",  # no prod user yet; prod's exception applies
    )  # fmt: skip
    assert uat["meta"] == base["meta"]
    with pytest.raises(UnknownEnvironment, match="unknown environment 'nope'"):
        show_node(repo, load, env="nope")
