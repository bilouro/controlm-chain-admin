"""The resources of a job (CONTROL, QUANTITATIVE): seen by resource, added to one job or to
several, changed and removed."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.capabilities import preview_steps
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.refactor import apply, run_operation
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from controlm_chain_admin.core.resources import remove_resource, set_resource, usage
from tests.support.gitrepo import chain_git_repo, git

ING, CHAIN = "P77_INGEST_DAILY", "P77_CHAIN"
INIT, LOAD = f"{ING}/P77_INGEST_INIT", f"{ING}/P77_INGEST_LOAD"
A, B = f"{CHAIN}/P77_A", f"{CHAIN}/P77_B"


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    built = chain_git_repo(tmp_path)
    git(built.root, "checkout", "-q", "-b", "release/26.1")  # main is protected
    return load_repo(built.root)


def _of(repo: ChainRepo, node: str, tag: str) -> list[dict[str, str]]:
    folder, _, job = node.partition("/")
    path = repo.job_file(folder, job) if job else repo.folder_file(folder)
    return list(read_json(path).get(tag, []))


def test_who_uses_each_resource(repo: ChainRepo) -> None:
    (only,) = usage(repo)

    assert (only.tag, only.name, only.nodes) == ("QUANTITATIVE", "RQ_AM", (INIT,))
    assert only.attributes == {"QUANT": "1", "ONFAIL": "R", "ONOK": "R"}
    assert only.to_json() == {
        "tag": "QUANTITATIVE", "name": "RQ_AM", "nodes": [INIT], "count": 1,
        "attributes": {"QUANT": "1", "ONFAIL": "R", "ONOK": "R"},
    }  # fmt: skip


def test_a_resource_another_job_has_comes_with_what_it_has_there(repo: ChainRepo) -> None:
    change = set_resource(repo, LOAD, "RQ_AM")
    apply(repo, change)
    repo = load_repo(repo.root)

    assert change.summary == f"add QUANTITATIVE RQ_AM to {LOAD}"
    assert _of(repo, LOAD, "QUANTITATIVE") == _of(repo, INIT, "QUANTITATIVE")
    assert usage(repo)[0].nodes == (INIT, LOAD)
    assert (
        b'<QUANTITATIVE NAME="URQ_AM" QUANT="1" ONFAIL="R" ONOK="R" />'
        in export_xml(repo, "uat").split(b"P77_INGEST_LOAD", 1)[1]
    )


def test_a_new_resource_says_its_kind_and_gets_the_usual_attributes(repo: ChainRepo) -> None:
    with pytest.raises(ChainError, match="CONTROL or a QUANTITATIVE"):
        set_resource(repo, A, "RC_SHARED")

    apply(repo, set_resource(repo, A, "RC_SHARED", tag="control"))
    apply(load_repo(repo.root), set_resource(load_repo(repo.root), B, "RC_SHARED",
                                             attributes={"TYPE": "S"}))  # fmt: skip
    repo = load_repo(repo.root)

    assert _of(repo, A, "CONTROL") == [{"NAME": "RC_SHARED", "TYPE": "E", "ONFAIL": "R"}]
    assert _of(repo, B, "CONTROL") == [{"NAME": "RC_SHARED", "TYPE": "S", "ONFAIL": "R"}]
    by_name = {use.name: use for use in usage(repo)}
    assert by_name["RC_SHARED"].nodes == (A, B)
    assert b'<CONTROL NAME="URC_SHARED" TYPE="E" ONFAIL="R" />' in export_xml(repo, "uat")


def test_what_a_job_has_already_is_changed_not_added_again(repo: ChainRepo) -> None:
    change = set_resource(repo, INIT, "RQ_AM", attributes={"QUANT": "2"})
    apply(repo, change)
    same = set_resource(load_repo(repo.root), INIT, "RQ_AM", attributes={"QUANT": "2"})

    assert change.summary == f"change QUANTITATIVE RQ_AM on {INIT}: QUANT 1 -> 2"
    assert _of(load_repo(repo.root), INIT, "QUANTITATIVE") == [
        {"NAME": "RQ_AM", "QUANT": "2", "ONFAIL": "R", "ONOK": "R"}
    ]
    assert same.edits == () and "already has" in same.summary


def test_a_resource_is_removed_from_a_job(repo: ChainRepo) -> None:
    apply(repo, remove_resource(repo, INIT, "RQ_AM"))
    repo = load_repo(repo.root)

    assert "QUANTITATIVE" not in read_json(repo.job_file(ING, "P77_INGEST_INIT"))
    assert usage(repo) == ()
    with pytest.raises(ChainError, match="has no resource RQ_AM"):
        remove_resource(repo, INIT, "RQ_AM")


def test_bad_requests_are_refused(repo: ChainRepo) -> None:
    with pytest.raises(ChainError, match="unknown job"):
        set_resource(repo, f"{ING}/P77_NOWHERE", "RQ_AM")
    with pytest.raises(ChainError, match="CONTROL or QUANTITATIVE"):
        set_resource(repo, A, "RQ_AM", tag="condition")
    with pytest.raises(ChainError, match="a name is needed"):
        set_resource(repo, A, "  ")
    with pytest.raises(ChainError, match="is a QUANTITATIVE resource"):
        set_resource(repo, A, "RQ_AM", tag="control")


def test_one_resource_for_several_jobs_is_one_change(repo: ChainRepo) -> None:
    steps = [{"do": "set-resource", "params": {"nodes": [A, B, LOAD], "name": "RQ_AM"}}]

    preview = preview_steps(repo, steps)
    apply(repo, run_operation(repo, "batch", {"changes": [
        {"op": "set-resource", "params": {"node": node, "name": "RQ_AM"}} for node in (A, B, LOAD)
    ]}))  # fmt: skip

    assert {row["where"] for row in preview["changes"]} == {A, B, LOAD}
    assert usage(load_repo(repo.root))[0].nodes == (A, B, INIT, LOAD)


def test_the_commands_list_add_rename_and_remove(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    root = str(repo.root)

    assert main(["resources", "--repo", root]) == 0
    listed = capsys.readouterr().out
    assert main(["set-resource", "RQ_AM", A, B, "--repo", root, "--apply"]) == 0
    assert main(["rename-resource", A, "RQ_AM", "RQ_PM", "--repo", root, "--apply"]) == 0
    assert main(["remove-resource", "RQ_AM", B, "--repo", root, "--apply"]) == 0
    assert main(["resources", "--name", "RQ_PM", "--repo", root]) == 0
    one = capsys.readouterr().out

    assert "QUANTITATIVE  RQ_AM  1 job" in listed and INIT in listed
    by_name = {use.name: use.nodes for use in usage(load_repo(repo.root))}
    assert by_name == {"RQ_AM": (INIT,), "RQ_PM": (A,)}
    assert "RQ_PM  1 job" in one and "RQ_AM" not in one.split("Applied")[-1]
