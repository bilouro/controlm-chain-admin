"""Taking changes of another branch into the checked-out one, item by item."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.constants import Selector, define_constant
from controlm_chain_admin.core.errors import InvalidChange, TakeConflict
from controlm_chain_admin.core.ops import export_xml, import_xml
from controlm_chain_admin.core.overrides import Override, load_overrides
from controlm_chain_admin.core.refactor import (
    apply,
    insert_job,
    link_nodes,
    set_attributes,
    set_exception,
    set_variables,
)
from controlm_chain_admin.core.repo import ChainRepo, load_repo, read_json
from controlm_chain_admin.core.take import take
from tests.support.gitrepo import chain_git_repo, commit_all, git, plain_git_identity
from tests.support.samples import SAMPLE_EXPORT

C = "P77_CHAIN"
OTHER = "release/other"
MINE = "release/mine"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ChainRepo:
    """main, then release/other with changes of every kind, then release/mine checked out."""
    plain_git_identity(monkeypatch, tmp_path)
    repo = chain_git_repo(tmp_path)
    root = repo.root
    git(root, "switch", "-q", "-c", OTHER)
    apply(repo, set_attributes(repo, f"{C}/P77_A", {"TIMEFROM": "0800", "CMDLINE": "/a2.ksh"}))
    apply(repo, set_variables(repo, f"{C}/P77_B", [{"NAME": "%%X", "VALUE": "1"}]))
    apply(repo, insert_job(repo, f"{C}/P77_N", after=f"{C}/P77_A", before=f"{C}/P77_B"))
    apply(repo, link_nodes(repo, f"{C}/P77_D", producer=f"{C}/P77_A"))
    apply(repo, set_exception(repo, "prod", f"{C}/P77_E", {"TASKTYPE": "Dummy"}))
    define_constant(
        repo, "node.batch", Selector("NODEID"), {"uat": "UP77_BATCH", "prod": "PP77_BATCH"}
    )
    weekly = SAMPLE_EXPORT.replace(b"INGEST", b"WEEKLY")  # a new folder
    import_xml(repo, weekly, env="uat")
    commit_all(root, "feat: the other release")
    git(root, "switch", "-q", "-c", MINE, "main")
    return load_repo(root)


def _job(repo: ChainRepo, name: str) -> dict:  # type: ignore[type-arg]
    return read_json(repo.job_file(C, name))  # type: ignore[no-any-return]


def _take(repo: ChainRepo, *items: str, **kwargs: object) -> None:
    apply(repo, take(repo, MINE, OTHER, items, **kwargs))  # type: ignore[arg-type]


def test_one_attribute_of_a_job_and_nothing_else(repo: ChainRepo) -> None:
    change = take(repo, MINE, OTHER, [f"attr:{C}/P77_A@TIMEFROM"])

    assert change.summary == f"take 1 change from {OTHER}: attr:{C}/P77_A@TIMEFROM"
    apply(repo, change)
    job_a = _job(load_repo(repo.root), "P77_A")
    assert (job_a["TIMEFROM"], job_a["CMDLINE"]) == ("0800", "/opt/p77/bin/a.ksh")
    assert not load_repo(repo.root).job_file(C, "P77_N").exists()


def test_a_variable(repo: ChainRepo) -> None:
    _take(repo, f"var:{C}/P77_B@%%X")

    assert _job(load_repo(repo.root), "P77_B")["VARIABLE"] == [{"NAME": "%%X", "VALUE": "1"}]


def test_a_whole_job_without_its_folder(repo: ChainRepo) -> None:
    change = take(repo, MINE, OTHER, [f"job:{C}/P77_N"])
    apply(repo, change)

    mine = load_repo(repo.root)
    assert read_json(mine.folder_file(C))["jobs"][:3] == ["P77_A", "P77_N", "P77_B"]
    assert "TIMEFROM" not in _job(mine, "P77_A")  # the rest of the folder stays
    assert any("P77_N-P77_B_OK" in w and "waits" in w for w in change.warnings)
    assert b'JOBNAME="UP77_N"' in export_xml(mine, "uat")  # its new condition has a name


def test_a_relation_comes_with_both_of_its_ends(repo: ChainRepo) -> None:
    result = compare(repo.root, MINE, OTHER)
    [link] = [
        r.link for j in result.jobs if j.node == f"{C}/P77_D" for r in j.relations
        if r.change == "added"
    ]  # fmt: skip

    _take(repo, f"rel:{C}/P77_D@{link}")

    mine = load_repo(repo.root)
    assert any(e["link"] == link for e in _job(mine, "P77_A")["OUTCOND"])
    assert any(e["link"] == link for e in _job(mine, "P77_D")["INCOND"])
    assert export_xml(mine, "uat")  # the condition has its name


def test_a_whole_folder(repo: ChainRepo) -> None:
    _take(repo, "folder:P77_WEEKLY_DAILY")

    mine = load_repo(repo.root)
    assert read_json(mine.folder_file("P77_WEEKLY_DAILY"))["jobs"] == [
        "P77_WEEKLY_INIT", "P77_WEEKLY_LOAD",
    ]  # fmt: skip
    assert b"UP77_WEEKLY_DAILY" in export_xml(mine, "uat")


def test_a_constant_comes_with_its_definition_and_an_exception(repo: ChainRepo) -> None:
    _take(repo, "const:prod@node.batch", f"exception:prod@{C}/P77_E")

    mine = load_repo(repo.root)
    assert mine.config.constants["node.batch"] == Selector("NODEID")
    assert mine.load_env("prod").constants["node.batch"] == "PP77_BATCH"
    assert load_overrides(mine, "prod") == {f"{C}/P77_E": Override({"TASKTYPE": "Dummy"})}


def test_a_value_the_checkout_changed_too_is_a_conflict(repo: ChainRepo) -> None:
    apply(repo, set_attributes(repo, f"{C}/P77_A", {"TIMEFROM": "0900"}))
    item = f"attr:{C}/P77_A@TIMEFROM"

    with pytest.raises(TakeConflict) as raised:
        take(repo, MINE, OTHER, [item])

    assert raised.value.detail == {
        "conflicts": [{"item": item, "mine": "0900", "before": None, "theirs": "0800"}]
    }
    _take(repo, item, theirs=[item])
    assert _job(load_repo(repo.root), "P77_A")["TIMEFROM"] == "0800"


def test_a_change_already_there_changes_nothing(repo: ChainRepo) -> None:
    apply(repo, set_attributes(repo, f"{C}/P77_A", {"TIMEFROM": "0800"}))

    assert take(repo, MINE, OTHER, [f"attr:{C}/P77_A@TIMEFROM"]).edits == ()


def test_changes_go_into_the_checked_out_branch_only(repo: ChainRepo) -> None:
    with pytest.raises(InvalidChange, match="checked-out branch"):
        take(repo, OTHER, MINE, [f"attr:{C}/P77_A@TIMEFROM"])
    with pytest.raises(InvalidChange, match="unknown item"):
        take(repo, MINE, OTHER, ["nope:x"])


def test_the_cli_lists_the_items_and_takes_some(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    from controlm_chain_admin.cli import main

    root = str(repo.root)
    assert main(["take", OTHER, "--repo", root, "--list"]) == 0
    listed = capsys.readouterr().out
    for item in (
        f"attr:{C}/P77_A@TIMEFROM", f"job:{C}/P77_N", f"var:{C}/P77_B@%%X",
        "folder:P77_WEEKLY_DAILY", "const:prod@node.batch", f"exception:prod@{C}/P77_E",
    ):  # fmt: skip
        assert f"  {item}  " in listed

    assert main(["take", OTHER, "--repo", root, "--item", f"attr:{C}/P77_A@TIMEFROM",
                 "--apply", "--stat"]) == 0  # fmt: skip
    assert _job(load_repo(repo.root), "P77_A")["TIMEFROM"] == "0800"


def test_the_cli_shows_each_conflict(repo: ChainRepo, capsys: pytest.CaptureFixture[str]) -> None:
    from controlm_chain_admin.cli import main

    apply(repo, set_attributes(repo, f"{C}/P77_A", {"CMDLINE": "/mine.ksh"}))
    item = f"attr:{C}/P77_A@CMDLINE"

    assert main(["take", OTHER, "--repo", str(repo.root), "--item", item]) != 0

    err = capsys.readouterr().err
    assert f"conflict {item}: mine /mine.ksh, before /opt/p77/bin/a.ksh, theirs /a2.ksh" in err
    assert f"--theirs {item}" in err
