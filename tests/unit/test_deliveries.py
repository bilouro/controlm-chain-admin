"""Deliveries kept for later: items put aside under a name, little by little, and one import
file made afterwards from one or several of them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.deliveries import (
    build_delivery,
    listed,
    read_deliveries,
    remove_delivery,
    save_delivery,
)
from controlm_chain_admin.core.envmap import read_map
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.package import build_package
from controlm_chain_admin.core.refactor import apply, set_attributes
from controlm_chain_admin.core.repo import ChainRepo, load_repo
from tests.support.fourenvs import (
    CHAIN,
    INGEST,
    USERS,
    WEEKLY,
    four_branches,
    uat_ahead,
    with_map,
)
from tests.support.gitrepo import commit_all, git, plain_git_identity

BENCH, UAT = "env/bench", "env/uat"
TODAY = "2026-11-12"
NEW, CMD = f"job:{CHAIN}/P77_NEW", f"attr:{CHAIN}/P77_A@CMDLINE"


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


@pytest.fixture
def repo(tmp_path: Path) -> ChainRepo:
    built = four_branches(tmp_path, change=uat_ahead)
    with_map(built)
    return load_repo(built.root)


def test_a_selection_is_kept_under_a_name_with_where_it_comes_from(repo: ChainRepo) -> None:
    kept = save_delivery(repo, "new job", UAT, [NEW, NEW], base=BENCH, note="for Friday",
                         today=TODAY)  # fmt: skip
    save_delivery(repo, "command of A", UAT, [CMD], base=BENCH, today=TODAY)

    again = read_deliveries(repo.root, repo.config)

    assert [d.name for d in again] == ["new job", "command of A"] and again[0] == kept
    assert (kept.head, kept.base, kept.items, kept.note, kept.saved) == (
        UAT, BENCH, (NEW,), "for Friday", TODAY,
    )  # fmt: skip
    assert kept.sha == git(repo.root, "rev-parse", UAT)
    assert git(repo.root, "status", "--porcelain") == ""  # on the branch of the map, by plumbing
    assert git(repo.root, "branch", "--show-current") == "main"
    assert read_map(repo.root, repo.config).entries  # the map is still there, beside them


def test_a_name_is_used_once_and_an_entry_needs_items_of_a_known_ref(repo: ChainRepo) -> None:
    save_delivery(repo, "one", UAT, [NEW], today=TODAY)

    with pytest.raises(ChainError, match="there is a delivery called 'one' already"):
        save_delivery(repo, "one", UAT, [CMD], today=TODAY)
    with pytest.raises(ChainError, match="nothing to keep"):
        save_delivery(repo, "empty", UAT, [], today=TODAY)
    with pytest.raises(ChainError, match="unknown item"):
        save_delivery(repo, "odd", UAT, ["thing:whatever"], today=TODAY)
    with pytest.raises(ChainError, match="unknown git ref"):
        save_delivery(repo, "lost", "env/nowhere", [NEW], today=TODAY)
    with pytest.raises(ChainError, match="a name is needed"):
        save_delivery(repo, "  ", UAT, [NEW], today=TODAY)


def test_one_file_from_several_deliveries_for_the_environment_that_receives(
    repo: ChainRepo,
) -> None:
    save_delivery(repo, "new job", UAT, [NEW], base=BENCH, today=TODAY)
    save_delivery(repo, "weekly", UAT, [f"folder:{WEEKLY}"], base=BENCH, today=TODAY)
    save_delivery(repo, "command of A", UAT, [CMD], base=BENCH, today=TODAY)

    two = build_delivery(repo.root, BENCH, ["new job", "weekly"], today=TODAY)
    one = build_delivery(repo.root, "main", ["command of A"], today=TODAY)

    assert two.env == "bench" and [f.name for f in two.folders] == [CHAIN, WEEKLY]
    xml = two.require_xml()
    assert b'JOBNAME="BP77_NEW"' in xml and b'FOLDER_NAME="BP77_WEEKLY_DAILY"' in xml
    assert USERS["bench"].encode() in xml and b"UP77" not in xml
    assert two.filename == f"deploy_bench_new-job+weekly_{TODAY}.xml"
    assert two.taken == (NEW, f"folder:{WEEKLY}")
    alone = build_package(repo.root, BENCH, UAT, take=[NEW, f"folder:{WEEKLY}"], today=TODAY)
    assert xml == alone.require_xml()  # the same file as taking the same items at once
    assert one.env == "prod" and b"a2.ksh -x" in one.require_xml()
    assert b'JOBNAME="PP77_NEW"' not in one.require_xml()  # the new job is another delivery
    assert git(repo.root, "status", "--porcelain") == ""


def test_something_picked_from_the_chain_is_packaged_even_when_the_target_has_it(
    repo: ChainRepo,
) -> None:
    save_delivery(repo, "ingest as uat has it", UAT, [f"folder:{INGEST}"], today=TODAY)
    save_delivery(repo, "a job of the chain", UAT, [f"job:{CHAIN}/P77_B"], today=TODAY)

    package = build_delivery(
        repo.root, BENCH, ["ingest as uat has it", "a job of the chain"], today=TODAY
    )

    assert sorted(f.name for f in package.folders) == sorted([CHAIN, INGEST])
    assert all("already as env/bench has it" in f.reasons[-1] for f in package.folders)
    assert b'FOLDER_NAME="BP77_INGEST_DAILY"' in package.require_xml()


def test_two_deliveries_that_give_one_attribute_two_values_are_refused(repo: ChainRepo) -> None:
    git(repo.root, "switch", "-q", "-c", "work/other", UAT)
    work = load_repo(repo.root)
    apply(work, set_attributes(work, f"{CHAIN}/P77_A", {"CMDLINE": "/opt/p77/bin/other.ksh"}))
    commit_all(repo.root, "feat: another command")
    git(repo.root, "switch", "-q", "main")
    save_delivery(repo, "uat", UAT, [CMD], today=TODAY)
    save_delivery(repo, "mine", "work/other", [CMD], today=TODAY)

    with pytest.raises(ChainError, match=r"'mine' and what was put before it disagree"):
        build_delivery(repo.root, BENCH, ["uat", "mine"], today=TODAY)
    with pytest.raises(ChainError, match="no delivery called 'nothing'"):
        build_delivery(repo.root, BENCH, ["nothing"], today=TODAY)
    with pytest.raises(ChainError, match="choose one delivery at least"):
        build_delivery(repo.root, BENCH, [], today=TODAY)


def test_a_delivery_is_tied_to_the_commit_it_was_made_from(repo: ChainRepo) -> None:
    save_delivery(repo, "command of A", UAT, [CMD], base=BENCH, today=TODAY)
    git(repo.root, "switch", "-q", UAT)
    uat = load_repo(repo.root)
    apply(uat, set_attributes(uat, f"{CHAIN}/P77_A", {"CMDLINE": "/opt/p77/bin/later.ksh"}))
    commit_all(repo.root, "feat: uat moved on")
    git(repo.root, "switch", "-q", "main")

    (row,) = listed(repo)
    package = build_delivery(repo.root, BENCH, ["command of A"], today=TODAY)

    assert row["moved"] is True and row["environment"] == "uat" and row["count"] == 1
    assert b"a2.ksh -x" in package.require_xml() and b"later.ksh" not in package.require_xml()
    assert any("env/uat moved since 'command of A' was kept" in w for w in package.warnings)


def _change(repo: ChainRepo, node: str, attributes: dict[str, str], message: str) -> None:
    uat = load_repo(repo.root)
    apply(uat, set_attributes(uat, node, attributes))
    commit_all(repo.root, message)


def test_a_delivery_lists_the_commits_that_changed_what_it_holds(repo: ChainRepo) -> None:
    """The work in it: the commits of its branch since the last export, on its items only;
    and, apart, what touched them after it was kept."""
    git(repo.root, "switch", "-q", UAT)
    _change(repo, f"{CHAIN}/P77_A", {"MAXWAIT": "3"}, "feat: wait longer on A")
    _change(repo, f"{INGEST}/P77_INGEST_LOAD", {"MAXWAIT": "4"}, "feat: another folder")
    save_delivery(repo, "job A", UAT, [f"job:{CHAIN}/P77_A"], base=BENCH, today=TODAY)
    save_delivery(repo, "attribute", UAT, [CMD], base=BENCH, today=TODAY)
    save_delivery(repo, "the folder", UAT, [f"folder:{CHAIN}"], today=TODAY)
    save_delivery(repo, "a link", UAT, ["link:nope"], today=TODAY)
    _change(repo, f"{CHAIN}/P77_A", {"MAXRERUN": "2"}, "feat: after it was kept")
    git(repo.root, "switch", "-q", "main")

    rows = {row["name"]: row for row in listed(repo)}

    def subjects(name: str, key: str = "commits") -> list[str]:
        return [commit["subject"] for commit in rows[name][key]]

    assert subjects("job A") == ["feat: wait longer on A"]  # not the export, not elsewhere
    assert subjects("attribute") == ["feat: wait longer on A"]  # the file of the job
    assert subjects("the folder") == ["feat: wait longer on A"]
    assert subjects("job A", "commits_after") == ["feat: after it was kept"]
    assert rows["a link"]["commits"] == [] and rows["a link"]["commits_after"] == []
    commit = rows["job A"]["commits"][0]
    assert len(commit["sha"]) == 40 and commit["author"] and commit["date"].startswith("20")


def test_the_list_says_the_commits_of_each_delivery(
    repo: ChainRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    git(repo.root, "switch", "-q", UAT)
    _change(repo, f"{CHAIN}/P77_A", {"MAXWAIT": "3"}, "feat: wait longer on A")
    save_delivery(repo, "job A", UAT, [f"job:{CHAIN}/P77_A"], today=TODAY)
    _change(repo, f"{CHAIN}/P77_A", {"MAXRERUN": "2"}, "feat: after it was kept")
    capsys.readouterr()

    assert main(["delivery", "list", "--repo", str(repo.root)]) == 0

    out = capsys.readouterr().out
    first = git(repo.root, "rev-parse", "--short=7", f"{UAT}~1")
    assert f"      commit {first} feat: wait longer on A (" in out
    assert "      after it was kept, not in it: " in out and "feat: after it was kept" in out


def test_a_delivery_of_a_branch_of_ones_own_starts_at_the_export_it_holds(
    repo: ChainRepo,
) -> None:
    git(repo.root, "switch", "-q", "-c", "work/mine", UAT)
    _change(repo, f"{CHAIN}/P77_A", {"MAXWAIT": "3"}, "feat: mine")
    save_delivery(repo, "mine", "work/mine", [f"job:{CHAIN}/P77_A"], today=TODAY)
    git(repo.root, "switch", "-q", "main")

    (row,) = [row for row in listed(repo) if row["name"] == "mine"]

    # the branch started from uat's: the export of uat in its history is where it begins
    assert [c["subject"] for c in row["commits"]] == ["feat: mine"]
    assert row["commits_after"] == []


def test_a_delivery_is_removed_by_its_name(repo: ChainRepo) -> None:
    save_delivery(repo, "one", UAT, [NEW], today=TODAY)
    save_delivery(repo, "two", UAT, [CMD], today=TODAY)

    remove_delivery(repo, "one")

    assert [d.name for d in read_deliveries(repo.root, repo.config)] == ["two"]
    with pytest.raises(ChainError, match="no delivery called 'one'"):
        remove_delivery(repo, "one")


def test_the_commands_keep_list_package_and_remove(
    repo: ChainRepo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, out = str(repo.root), tmp_path / "bench.xml"

    assert main(["delivery", "save", "new job", UAT, "--item", NEW, "--base", BENCH,
                 "--repo", root]) == 0  # fmt: skip
    assert "Kept 'new job': 1 item(s) of env/uat" in capsys.readouterr().out
    assert main(["delivery", "list", "--repo", root, "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)["deliveries"]
    assert main(["delivery", "package", BENCH, "new job", "-o", str(out), "--repo", root]) == 0
    assert main(["delivery", "remove", "new job", "--repo", root]) == 0
    assert main(["delivery", "list", "--repo", root]) == 0

    assert [(r["name"], r["head"], r["items"]) for r in rows] == [("new job", UAT, [NEW])]
    assert b'JOBNAME="BP77_NEW"' in out.read_bytes()
    assert "No delivery is kept." in capsys.readouterr().out
