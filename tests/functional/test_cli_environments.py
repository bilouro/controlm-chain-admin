"""The commands a person types to work with one branch per environment, each through
``main(argv)``: compare two environments, list and take items, write the import file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.repo import read_json
from tests.support.fourenvs import (
    CHAIN,
    INGEST,
    USERS,
    WEEKLY,
    administrator,
    four_branches,
    two_users_in,
    uat_ahead,
    with_map,
)
from tests.support.gitrepo import git, plain_git_identity

BENCH, UAT = "env/bench", "env/uat"


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Four environments with their map; uat is ahead of the others; main is checked out."""
    repo = four_branches(tmp_path, change=uat_ahead)
    with_map(repo)
    return repo.root


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------- compare


def test_compare_shows_the_real_differences_of_two_environments(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(capsys, "compare", BENCH, UAT, "--repo", str(root))

    assert code == 0
    assert out.startswith("Compare env/bench (bench) with env/uat (uat): real differences only")
    assert "expected between bench and uat, not shown:" in out
    assert f"added    folder {WEEKLY}/" in out and f"added    job {CHAIN}/P77_NEW" in out
    assert "CMDLINE: /opt/p77/bin/a.ksh -> /opt/p77/bin/a2.ksh -x" in out
    assert USERS["uat"] not in out and "srvu-bat1" not in out


def test_compare_raw_shows_the_two_branches_as_they_are_stored(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(capsys, "compare", BENCH, UAT, "--raw", "--repo", str(root))

    assert code == 0
    assert out.startswith("Compare env/bench (bench) with env/uat (uat): as stored")
    assert f"RUN_AS: {USERS['bench']} -> {USERS['uat']}" in out
    assert "real differences only" not in out


def test_compare_in_json_says_what_was_explained(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(capsys, "compare", "main", UAT, "--format", "json", "--repo", str(root))

    translation = json.loads(out)["translation"]
    assert code == 0 and (translation["target"], translation["source"]) == ("prod", "uat")
    assert translation["values"] > 0 and translation["warnings"] == []


# ---------------------------------------------------------------- take


def test_the_list_names_the_base_it_was_given_not_the_branch_checked_out(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(root, "switch", "-q", "main")

    code, out, _ = _run(capsys, "take", UAT, "--list", "--base", BENCH, "--repo", str(root))

    assert code == 0
    assert "Items env/uat (uat) has that can be taken into env/bench (bench):" in out


def test_take_lists_what_can_be_taken_from_the_smallest_to_the_largest(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(root, "switch", "-q", BENCH)

    code, out, _ = _run(capsys, "take", UAT, "--list", "--repo", str(root))

    assert code == 0
    assert "Items env/uat (uat) has that can be taken into env/bench (bench):" in out
    listed = {line.split()[0] for line in out.splitlines()[1:]}
    assert {
        "subapp:P77_BATCH", f"folder:{WEEKLY}", f"job:{CHAIN}/P77_NEW",
        f"attr:{CHAIN}/P77_A@CMDLINE", f"var:{INGEST}/@%%RETRY",
    } <= listed  # fmt: skip
    assert "subapp:P77_BATCH  3 folders that differ" in out


def test_take_lists_the_items_in_json_for_a_program(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(root, "switch", "-q", BENCH)

    code, out, _ = _run(capsys, "take", UAT, "--list", "--format", "json", "--repo", str(root))

    listed = json.loads(out)
    assert code == 0
    assert (listed["into"], listed["from"], listed["environments"]) == (
        BENCH, UAT, ["bench", "uat"]
    )  # fmt: skip
    assert listed["items"][0] == {"id": "subapp:P77_BATCH", "label": "3 folders that differ"}
    assert {"id": f"folder:{WEEKLY}", "label": "the whole folder, added"} in listed["items"]


def test_take_previews_then_applies_a_folder(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(root, "switch", "-q", BENCH)
    item = ("--item", f"folder:{WEEKLY}", "--repo", str(root))

    code, out, _ = _run(capsys, "take", UAT, *item)
    assert code == 0 and f"folders/{WEEKLY}/folder.json" in out
    assert git(root, "status", "-s") == ""  # a preview writes nothing

    code, out, _ = _run(capsys, "take", UAT, *item, "--apply")
    assert code == 0
    taken = read_json(root / "folders" / WEEKLY / "jobs" / "P77_WEEKLY_INIT.json")
    assert taken["RUN_AS"] == USERS["bench"]


def test_take_is_refused_on_the_branch_of_production(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _run(
        capsys, "take", UAT, "--item", f"folder:{WEEKLY}", "--apply", "--repo", str(root)
    )

    assert code == 3 and "main" in err
    assert git(root, "status", "-s") == ""


# ---------------------------------------------------------------- package


def test_package_writes_the_file_of_the_chosen_items_for_the_target(
    root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "bench.xml"

    code, out, _ = _run(
        capsys, "package", BENCH, UAT, "--take", f"folder:{WEEKLY}",
        "--take", f"job:{CHAIN}/P77_NEW", "-o", str(out_file), "--repo", str(root),
    )  # fmt: skip

    assert code == 0
    assert out.startswith("Package env/uat (uat) for bench (env/bench): 2 folders, 2 items taken")
    assert f"  {WEEKLY} (" in out and f"  {CHAIN} (" in out
    xml = out_file.read_bytes()
    assert b'FOLDER_NAME="BP77_WEEKLY_DAILY"' in xml and b'JOBNAME="BP77_NEW"' in xml
    assert b"UP77" not in xml and USERS["uat"].encode() not in xml
    assert git(root, "status", "-s") == ""


def test_package_of_everything_that_differs_for_production(
    root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(
        capsys, "package", "main", UAT, "--dry-run", "--format", "json", "--repo", str(root)
    )

    package = json.loads(out)
    assert code == 0 and package["env"] == "prod" and package["taken"] is None
    assert {f["name"] for f in package["folders"]} == {CHAIN, INGEST, WEEKLY}

    code, out, _ = _run(capsys, "package", "main", UAT, "--dry-run", "--repo", str(root))
    assert out.startswith(
        "Package env/uat (uat) for prod (main): 3 folders, everything that differs"
    )


def test_package_for_another_environment_than_the_base_is_refused(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _run(capsys, "package", BENCH, UAT, "--env", "prod", "--repo", str(root))

    assert code == 3 and "env/bench holds bench" in err


def test_package_of_one_environment_is_for_it(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(capsys, "package", "main", "--worktree", "--repo", str(root))

    assert code == 0 and "for prod" in out


# ---------------------------------------------------------------- a value the map cannot settle


def test_a_preferred_entry_of_the_map_settles_a_value_with_two_answers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = four_branches(tmp_path, change=two_users_in("bench"))
    with_map(repo)
    args = ("package", BENCH, UAT, "--take", f"job:{CHAIN}/P77_NEW", "--repo", str(repo.root))

    code, out, _ = _run(capsys, *args, "--dry-run")
    assert code == 0 and "kept as it is" in out and "run_as.2" in out

    out_file = tmp_path / "new.xml"
    code, out, _ = _run(capsys, *args, "--prefer", "run_as.2", "-o", str(out_file))
    assert code == 0 and "kept as it is" not in out
    assert out_file.read_bytes().count(f'RUN_AS="{administrator("bench")}"'.encode()) == 2

    code, out, _ = _run(capsys, "compare", BENCH, UAT, "--prefer", "run_as.1", "--repo",
                        str(repo.root))  # fmt: skip
    assert code == 0 and "warning:" not in out
    git(repo.root, "switch", "-q", BENCH)
    code, out, _ = _run(capsys, "take", UAT, "--item", f"job:{CHAIN}/P77_NEW", "--prefer",
                        "run_as.1", "--repo", str(repo.root))  # fmt: skip
    assert code == 0 and "kept as it is" not in out


def test_the_list_of_what_can_be_taken_follows_the_entry_preferred(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = four_branches(tmp_path, change=two_users_in("bench"))
    with_map(repo)
    args = ("take", UAT, "--list", "--base", BENCH, "--repo", str(repo.root))

    code, out, _ = _run(capsys, *args, "--prefer", "run_as.2")
    assert code == 0 and f"job:{CHAIN}/P77_NEW" in out

    code, _, err = _run(capsys, *args, "--prefer", "run_as.9")
    assert code != 0 and "no entry called 'run_as.9'" in err
