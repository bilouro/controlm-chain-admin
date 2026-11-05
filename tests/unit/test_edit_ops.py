"""Editing operations used by the web UI: attributes, variables, raw JSON, links between nodes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.core.errors import InvalidChange
from controlm_chain_admin.core.graph import folder_graph
from controlm_chain_admin.core.links import load_links
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.refactor import (
    apply,
    fingerprint,
    link_nodes,
    rename_link,
    replace_node,
    set_attributes,
    set_variables,
    unlink_nodes,
    update_relation,
)
from controlm_chain_admin.core.repo import ChainRepo, init_repo, read_json, write_json
from tests.support.anomalies import ANOMALY_EXPORT

APP = "P77_RISK_ENGINE"
C = "P77_CHAIN"


def _repo(tmp_path: Path) -> ChainRepo:
    repo = init_repo(tmp_path, APP, ("uat", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    return repo


def _job(tmp_path: Path, job: str) -> dict:  # type: ignore[type-arg]
    return json.loads((tmp_path / f"folders/{C}/jobs/{job}.json").read_text("utf-8"))  # type: ignore[no-any-return]


def _edges(repo: ChainRepo) -> set[tuple[str, str]]:
    return {(e.source.split("/")[1], e.target.split("/")[1]) for e in folder_graph(repo, C).edges}


# ---------------------------------------------------------------- attributes / variables / raw


def test_set_attributes_adds_changes_and_removes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    apply(
        repo,
        set_attributes(
            repo, f"{C}/P77_B", {"DESCRIPTION": "Load", "RUN_AS": "svc", "CMDLINE": None}
        ),
    )

    job = _job(tmp_path, "P77_B")
    assert job["DESCRIPTION"] == "Load" and job["RUN_AS"] == "svc" and "CMDLINE" not in job
    assert list(job).index("DESCRIPTION") < list(job).index("INCOND")  # attributes before groups
    out = export_xml(repo, env="uat")
    assert b'DESCRIPTION="Load"' in out and b"/opt/p77/bin/b.ksh" not in out


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"JOBNAME": "X"}, "rename-job"),
        ({"PARENT_FOLDER": "X"}, "move-job"),
        ({"JOBISN": "9"}, "metadata"),
        ({"lower": "x"}, "attribute name"),
        ({}, "nothing"),
    ],
)
def test_set_attributes_refuses(tmp_path: Path, changes: dict, message: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(InvalidChange, match=message):
        set_attributes(_repo(tmp_path), f"{C}/P77_B", changes)


def test_set_variables_replaces_the_group_on_jobs_and_folders(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    apply(repo, set_variables(repo, f"{C}/P77_B", [{"NAME": "%%X", "VALUE": "1"}]))
    assert _job(tmp_path, "P77_B")["VARIABLE"] == [{"NAME": "%%X", "VALUE": "1"}]
    apply(repo, set_variables(repo, f"{C}/P77_B", []))
    assert "VARIABLE" not in _job(tmp_path, "P77_B")
    apply(repo, set_variables(repo, f"{C}/", [{"NAME": "%%ENV", "VALUE": "u"}]))
    assert b'<VARIABLE NAME="%%ENV" VALUE="u" />' in export_xml(repo, env="uat")

    with pytest.raises(InvalidChange, match="%%"):
        set_variables(repo, f"{C}/P77_B", [{"NAME": "X", "VALUE": "1"}])
    with pytest.raises(InvalidChange, match="twice"):
        set_variables(
            repo, f"{C}/P77_B", [{"NAME": "%%X", "VALUE": "1"}, {"NAME": "%%X", "VALUE": "2"}]
        )


def test_replace_node_with_raw_json(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    data = _job(tmp_path, "P77_B")
    data["CMDLINE"] = "/opt/p77/bin/b2.ksh"

    apply(repo, replace_node(repo, f"{C}/P77_B", data))

    assert _job(tmp_path, "P77_B")["CMDLINE"] == "/opt/p77/bin/b2.ksh"
    with pytest.raises(InvalidChange, match="rename-job"):
        replace_node(repo, f"{C}/P77_B", {**data, "JOBNAME": "P77_Z"})
    with pytest.raises(InvalidChange):
        replace_node(repo, f"{C}/P77_B", {**data, "CMDLINE": 3})


# ---------------------------------------------------------------- predecessors / successors


def test_link_nodes_creates_a_new_link_with_plus_wait_and_cleanup(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    change = link_nodes(repo, f"{C}/P77_E", producer=f"{C}/P77_C")
    apply(repo, change)

    assert {"link": "P77_C-P77_E_OK", "ODATE": "ODAT", "SIGN": "+"} in _job(tmp_path, "P77_C")[
        "OUTCOND"
    ]
    e = _job(tmp_path, "P77_E")
    assert {"link": "P77_C-P77_E_OK", "ODATE": "ODAT", "AND_OR": "A"} in e["INCOND"]
    assert {"link": "P77_C-P77_E_OK", "ODATE": "ODAT", "SIGN": "-"} in e["OUTCOND"]
    assert ("P77_C", "P77_E") in _edges(repo)
    assert "P77_C-P77_E_OK" in change.summary


def test_link_nodes_options_and_refusals(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    apply(
        repo,
        link_nodes(
            repo,
            f"{C}/P77_F~2",
            producer=f"{C}/P77_D",
            and_or="O",
            cleanup=False,
            name="P77_D_DONE",
        ),
    )
    f2 = json.loads((tmp_path / f"folders/{C}/jobs/P77_F~2.json").read_text("utf-8"))
    assert (
        f2["INCOND"] == [{"link": "P77_D_DONE", "ODATE": "ODAT", "AND_OR": "O"}]
        and "OUTCOND" not in f2
    )

    with pytest.raises(InvalidChange, match="already waits"):
        link_nodes(repo, f"{C}/P77_B", producer=f"{C}/P77_A")
    with pytest.raises(InvalidChange, match="itself"):
        link_nodes(repo, f"{C}/P77_B", producer=f"{C}/P77_B")
    with pytest.raises(InvalidChange, match="producer or an existing link"):
        link_nodes(repo, f"{C}/P77_B")
    with pytest.raises(InvalidChange, match="already used"):
        link_nodes(repo, f"{C}/P77_E", producer=f"{C}/P77_C", name="P77_A-P77_B_OK")


def test_link_nodes_can_wait_for_an_existing_condition(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    apply(repo, link_nodes(repo, f"{C}/P77_F", link="P77_A-P77_C_OK"))

    assert [str(n) for n in load_links(repo)["P77_A-P77_C_OK"].consumers] == [f"{C}/P77_F"]
    assert ("P77_A", "P77_F") in _edges(repo)


def test_unlink_removes_the_wait_and_the_orphaned_emission(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    change = unlink_nodes(repo, "P77_A-P77_B_OK", f"{C}/P77_B")
    apply(repo, change)

    assert "INCOND" not in _job(tmp_path, "P77_B")
    assert all(o["link"] != "P77_A-P77_B_OK" for o in _job(tmp_path, "P77_A")["OUTCOND"])
    assert "P77_A-P77_B_OK" not in load_links(repo)
    assert "no consumer left" in change.summary


def test_unlink_keeps_the_emission_while_other_consumers_wait(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    apply(repo, link_nodes(repo, f"{C}/P77_F~2", link="P77_A-P77_B_OK"))

    apply(repo, unlink_nodes(repo, "P77_A-P77_B_OK", f"{C}/P77_B"))

    assert {"link": "P77_A-P77_B_OK", "ODATE": "ODAT", "SIGN": "+"} in _job(tmp_path, "P77_A")[
        "OUTCOND"
    ]
    with pytest.raises(InvalidChange, match="does not wait"):
        unlink_nodes(repo, "P77_A-P77_B_OK", f"{C}/P77_B")


def test_update_relation_changes_and_or_cleanup_and_odate_everywhere(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    apply(
        repo,
        update_relation(
            repo, "P77_A-P77_B_OK", f"{C}/P77_B", and_or="O", cleanup=False, odate="PREV"
        ),
    )

    b = _job(tmp_path, "P77_B")
    assert b["INCOND"] == [{"link": "P77_A-P77_B_OK", "ODATE": "PREV", "AND_OR": "O"}]
    assert all(o["link"] != "P77_A-P77_B_OK" for o in b["OUTCOND"])
    assert {"link": "P77_A-P77_B_OK", "ODATE": "PREV", "SIGN": "+"} in _job(tmp_path, "P77_A")[
        "OUTCOND"
    ]

    apply(repo, update_relation(repo, "P77_A-P77_B_OK", f"{C}/P77_B", cleanup=True))
    assert {"link": "P77_A-P77_B_OK", "ODATE": "PREV", "SIGN": "-"} in _job(tmp_path, "P77_B")[
        "OUTCOND"
    ]
    with pytest.raises(InvalidChange, match="AND_OR"):
        update_relation(repo, "P77_A-P77_B_OK", f"{C}/P77_B", and_or="X")


def test_rename_link_and_its_refusals(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    apply(repo, rename_link(repo, "P77_A-P77_B_OK", "P77_A-P77_B_DONE"))

    assert load_links(repo)["P77_A-P77_B_OK"].name == "P77_A-P77_B_DONE"
    assert b'NAME="UP77_A-UP77_B_DONE"' in export_xml(repo, env="uat")
    with pytest.raises(InvalidChange, match="already"):
        rename_link(repo, "P77_A-P77_B_OK", "P77_B-P77_C_OK")
    with pytest.raises(InvalidChange, match="unknown link"):
        rename_link(repo, "NOPE", "X")


def test_fingerprint_identifies_a_change_until_the_repository_moves(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = set_attributes(repo, f"{C}/P77_B", {"DESCRIPTION": "x"})

    assert fingerprint(first) == fingerprint(
        set_attributes(repo, f"{C}/P77_B", {"DESCRIPTION": "x"})
    )
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "y"}))
    assert fingerprint(first) == fingerprint(
        set_attributes(repo, f"{C}/P77_B", {"DESCRIPTION": "x"})
    )
    apply(repo, set_attributes(repo, f"{C}/P77_B", {"RUN_AS": "z"}))
    assert fingerprint(first) != fingerprint(
        set_attributes(repo, f"{C}/P77_B", {"DESCRIPTION": "x"})
    )


@pytest.mark.parametrize("node", [f"{C}/../folder", "../meta/", f"{C}/P77_B/x"])
def test_node_names_cannot_escape_their_folder(tmp_path: Path, node: str) -> None:
    from controlm_chain_admin.core.errors import UnsafeName

    with pytest.raises((UnsafeName, InvalidChange)):
        set_attributes(_repo(tmp_path), node, {"DESCRIPTION": "x"})


def test_numbered_job_ids_are_valid_nodes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert set_attributes(repo, f"{C}/P77_F~2", {"DESCRIPTION": "x"}).edits


def test_the_whole_json_of_a_node_of_some_environments_can_be_replaced(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = repo.job_file("P77_CHAIN", "P77_B")
    data = read_json(path)
    data["envs"] = ["uat"]
    write_json(path, data)
    data = {**read_json(path), "MAXWAIT": "7"}

    apply(repo, replace_node(repo, "P77_CHAIN/P77_B", data))

    assert read_json(path)["MAXWAIT"] == "7" and read_json(path)["envs"] == ["uat"]
    with pytest.raises(InvalidChange, match="INCOND"):
        replace_node(repo, "P77_CHAIN/P77_B", {**data, "INCOND": ["not an element"]})
