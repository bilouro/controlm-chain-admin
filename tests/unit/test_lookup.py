"""Read-only answers for an assistant: find nodes, describe one, a condition by its name."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.constants import Selector, define_constant
from controlm_chain_admin.core.errors import InvalidChange, ModelError, UnknownEnvironment
from controlm_chain_admin.core.lookup import describe_node, find_condition, find_nodes
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.overrides import Override, write_overrides
from controlm_chain_admin.core.repo import ChainRepo, init_repo, load_repo, read_json, write_json
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    root = tmp_path / "repo"
    repo = init_repo(root, APP, ("uat", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    repo = define_constant(repo, "node.batch", Selector("NODEID"),
                           {"uat": "UP77_BATCH", "prod": "PP77_BATCH"})  # fmt: skip
    import_xml(repo, SAMPLE_EXPORT, env="uat")  # the values become the constant
    write_overrides(repo, "prod", {"P77_CHAIN/P77_B": Override(attributes={"TASKTYPE": "Dummy"})})
    return load_repo(root)


def test_find_by_part_of_a_name_ignores_case(repo: ChainRepo) -> None:
    found = find_nodes(repo, text="ingest_l")

    assert found["total"] == 1
    (match,) = found["matches"]
    assert match == {
        "node": "P77_INGEST_DAILY/P77_INGEST_LOAD",
        "kind": "job",
        "name": "P77_INGEST_LOAD",
        "matched": {"JOBNAME": "P77_INGEST_LOAD"},
    }


def test_find_a_folder_by_its_name(repo: ChainRepo) -> None:
    found = find_nodes(repo, text="P77_INGEST_DAILY")

    assert found["matches"][0] == {"node": "P77_INGEST_DAILY/", "kind": "folder",
                                   "name": "P77_INGEST_DAILY",
                                   "matched": {"FOLDER_NAME": "P77_INGEST_DAILY"}}  # fmt: skip


def test_find_by_an_attribute_and_part_of_its_value(repo: ChainRepo) -> None:
    found = find_nodes(repo, attribute="cmdline", value="load.ksh")

    assert [m["node"] for m in found["matches"]] == ["P77_INGEST_DAILY/P77_INGEST_LOAD"]
    assert found["matches"][0]["matched"] == {"CMDLINE": "/opt/p77/bin/load.ksh -d %%ODATE"}


def test_find_by_a_value_in_any_attribute(repo: ChainRepo) -> None:
    found = find_nodes(repo, value="/opt/p77/bin/load")

    assert found["matches"][0]["matched"] == {"CMDLINE": "/opt/p77/bin/load.ksh -d %%ODATE"}


def test_find_who_has_an_attribute(repo: ChainRepo) -> None:
    found = find_nodes(repo, attribute="NODEID")

    assert {m["node"] for m in found["matches"]} >= {"P77_INGEST_DAILY/P77_INGEST_LOAD"}
    assert all(set(m["matched"]) == {"NODEID"} for m in found["matches"])


def test_find_in_one_environment_sees_its_values(repo: ChainRepo) -> None:
    in_prod = find_nodes(repo, attribute="NODEID", value="PP77_BATCH", env="prod")
    in_the_base = find_nodes(repo, attribute="NODEID", value="PP77_BATCH")
    dummies = find_nodes(repo, attribute="TASKTYPE", value="Dummy", env="prod")

    assert in_prod["total"] >= 1 and in_the_base["total"] == 0
    assert "P77_CHAIN/P77_B" in [m["node"] for m in dummies["matches"]]


def test_find_says_when_it_shows_only_the_first(repo: ChainRepo) -> None:
    found = find_nodes(repo, text="P77", limit=2)

    assert len(found["matches"]) == 2 and found["total"] > 2 and found["truncated"] is True


def test_find_needs_something_to_look_for(repo: ChainRepo) -> None:
    with pytest.raises(InvalidChange, match="give a text, an attribute or a value"):
        find_nodes(repo)


def test_find_in_an_unknown_environment_is_refused(repo: ChainRepo) -> None:
    with pytest.raises(UnknownEnvironment):
        find_nodes(repo, text="P77", env="nope")


def test_describe_a_job_with_its_neighbours_and_its_exceptions(repo: ChainRepo) -> None:
    job = describe_node(repo, "P77_CHAIN/P77_B")

    assert job["node"] == "P77_CHAIN/P77_B" and job["kind"] == "job"
    assert job["attributes"]["JOBNAME"] == "P77_B"
    assert job["waits_for"] == [{"condition": "P77_A-P77_B_OK", "from": ["P77_CHAIN/P77_A"]}]
    assert job["releases"] == [{"condition": "P77_B-P77_C_OK", "to": ["P77_CHAIN/P77_C"]}]
    assert job["exceptions"] == {"prod": {"attributes": {"TASKTYPE": "Dummy"}}}


def test_describe_a_job_as_one_environment_has_it(repo: ChainRepo) -> None:
    job = describe_node(repo, "P77_CHAIN/P77_B", env="prod")
    load = describe_node(repo, "P77_INGEST_DAILY/P77_INGEST_LOAD", env="prod")

    assert job["env"] == "prod" and job["attributes"]["TASKTYPE"] == "Dummy"
    assert load["attributes"]["NODEID"] == "PP77_BATCH"
    assert load["variables"] == {}


def test_describe_a_folder(repo: ChainRepo) -> None:
    folder = describe_node(repo, "P77_INGEST_DAILY/")

    assert folder["kind"] == "folder" and folder["attributes"]["FOLDER_NAME"] == "P77_INGEST_DAILY"
    assert folder["jobs"] == ["P77_INGEST_INIT", "P77_INGEST_LOAD"]


def test_describe_an_unknown_job_is_refused(repo: ChainRepo) -> None:
    with pytest.raises(ModelError, match="unknown job"):
        describe_node(repo, "P77_CHAIN/P77_NOPE")


def test_a_condition_by_its_name(repo: ChainRepo) -> None:
    condition = find_condition(repo, "P77_B-P77_C_OK")

    assert condition["name"] == "P77_B-P77_C_OK"
    assert condition["from"] == ["P77_CHAIN/P77_B"] and condition["to"] == ["P77_CHAIN/P77_C"]


def test_an_unknown_condition_is_refused(repo: ChainRepo) -> None:
    with pytest.raises(ModelError, match="no condition is called P77_NOPE"):
        find_condition(repo, "P77_NOPE")


def test_a_variable_without_a_value_is_described_as_such(repo: ChainRepo) -> None:
    path = repo.job_file("P77_CHAIN", "P77_B")
    write_json(path, {**read_json(path), "VARIABLE": [{"NAME": "%%BARE"}]})

    job = describe_node(repo, "P77_CHAIN/P77_B")

    assert job["variables"] == {"%%BARE": None}
