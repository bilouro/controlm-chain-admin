"""Predecessors and successors of every node, and the folder/job table built from them."""

from __future__ import annotations

from pathlib import Path

from controlm_chain_admin.core.constants import Selector, define_constant
from controlm_chain_admin.core.membership import with_envs
from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.relations import all_relations, chain_table
from controlm_chain_admin.core.repo import ChainRepo, init_repo, load_repo, read_json, write_json
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"
C = "P77_CHAIN"


def _repo(tmp_path: Path) -> ChainRepo:
    repo = init_repo(tmp_path, APP, ("uat", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    return repo


def test_predecessor_details_keep_and_or_odate_and_cleanup(tmp_path: Path) -> None:
    relations = all_relations(_repo(tmp_path))

    (pred,) = relations[f"{C}/P77_B"].predecessors
    assert pred.link == "P77_A-P77_B_OK" and pred.name == "P77_A-P77_B_OK"
    assert [p.node for p in pred.peers] == [f"{C}/P77_A"]
    assert (pred.and_or, pred.odate, pred.cleanup) == ("A", "ODAT", True)
    assert pred.kind == "edge" and not pred.external


def test_successor_details_describe_each_consumer(tmp_path: Path) -> None:
    relations = all_relations(_repo(tmp_path))

    successors = {s.link: s for s in relations[f"{C}/P77_A"].successors}
    to_b = successors["P77_A-P77_B_OK"]
    assert to_b.sign == "+" and [(p.node, p.and_or, p.cleanup) for p in to_b.peers] == [
        (f"{C}/P77_B", "A", True)
    ]
    assert successors["P77_A-P77_C_OK"].peers == () and successors["P77_A-P77_C_OK"].external
    (to_c,) = relations[f"{C}/P77_B"].successors  # static + and DOCOND + on the same link: once
    assert to_c.sign == "+" and to_c.peers[0].cleanup is False


def test_conditional_producers_and_external_predecessors(tmp_path: Path) -> None:
    relations = all_relations(_repo(tmp_path))

    e_preds = {p.link: p for p in relations[f"{C}/P77_E"].predecessors}
    assert e_preds["P77_GHOST-P77_E_OK"].peers == () and e_preds["P77_GHOST-P77_E_OK"].external
    folder = relations[f"{C}/"]
    assert [p.link for p in folder.predecessors] == ["P77_OTHER-P77_CHAIN_OK"]
    assert [s.link for s in folder.successors] == ["P77_CHAIN-P77_NEXT_OK"]
    assert relations[f"{C}/P77_F~2"].predecessors == ()


def test_chain_table_lists_folders_in_order_with_their_jobs_and_neighbours(
    tmp_path: Path,
) -> None:
    table = chain_table(_repo(tmp_path))

    assert [f["name"] for f in table] == ["P77_INGEST_DAILY", C]
    chain = table[1]
    assert chain["application"] == APP and chain["sub_application"] == "P77_BATCH"
    assert chain["predecessors"] == [
        {
            "node": None,
            "link": "P77_OTHER-P77_CHAIN_OK",
            "name": "P77_OTHER-P77_CHAIN_OK",
            "external": True,
        }
    ]
    jobs = {j["id"]: j for j in chain["jobs"]}
    assert list(jobs)[:2] == ["P77_A", "P77_B"]
    b = jobs["P77_B"]
    assert (b["name"], b["task_type"], b["sub_application"]) == ("P77_B", "Command", "P77_BATCH")
    assert [p["node"] for p in b["predecessors"]] == [f"{C}/P77_A"]
    assert [s["node"] for s in b["successors"]] == [f"{C}/P77_C"]
    assert [s["node"] for s in jobs["P77_A"]["successors"]] == [f"{C}/P77_B", None]


def test_chain_table_of_an_environment_has_its_nodes_with_its_values(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo = define_constant(repo, "node.batch", Selector("NODEID"),
                           {"uat": "UP77_BATCH", "prod": "PP77_BATCH"})  # fmt: skip
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    path = repo.job_file(C, "P77_E")
    write_json(path, with_envs(read_json(path), ["uat"], ("uat", "prod")))

    uat = {f["name"]: f for f in chain_table(load_repo(repo.root), "uat")}
    prod = {f["name"]: f for f in chain_table(load_repo(repo.root), "prod")}

    assert "P77_E" in [j["id"] for j in uat[C]["jobs"]]
    assert "P77_E" not in [j["id"] for j in prod[C]["jobs"]]
    assert {j["node_id"] for j in uat["P77_INGEST_DAILY"]["jobs"]} == {"UP77_BATCH"}
    assert {j["node_id"] for j in prod["P77_INGEST_DAILY"]["jobs"]} == {"PP77_BATCH"}
    base = chain_table(load_repo(repo.root))
    assert {j["node_id"] for j in base[0]["jobs"]} == {"@{node.batch}"}
