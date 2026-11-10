"""``ctmchain refresh``: the full export of an environment onto its branch, preview first."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from tests.support.fourenvs import empty_repo, export_of, four_branches, write_export
from tests.support.gitrepo import git, plain_git_identity


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plain_git_identity(monkeypatch, tmp_path)


def test_the_branches_of_two_environments_from_their_exports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = empty_repo(tmp_path).root
    prod, uat = write_export(tmp_path, "prod"), write_export(tmp_path, "uat")

    assert main(["refresh", str(prod), "--repo", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Refresh main (prod) from prod.xml: 2 folders, 9 jobs in the export")
    assert "folders: 2 added" in out and "jobs: 9 added" in out
    assert "main holds no folder yet: the whole export is new" in out
    assert "added    job" not in out and "condition added" not in out  # counts, not 9 jobs
    assert "Nothing written: --apply overwrites main with this export." in out
    assert git(root, "status", "--porcelain") == ""

    assert main(["refresh", str(prod), "--repo", str(root), "--apply"]) == 0
    assert "Committed on main: refresh(prod): prod.xml" in capsys.readouterr().out

    assert main(["refresh", str(uat), "--repo", str(root), "--apply"]) == 0
    out = capsys.readouterr().out
    assert "Refresh env/uat (uat) from uat.xml" in out and "env/uat is a new branch" in out
    assert "Committed on env/uat: refresh(uat): uat.xml" in out
    assert git(root, "branch", "--show-current") == "env/uat"


def test_a_second_export_lists_what_differs_before_it_is_applied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = four_branches(tmp_path).root
    changed = export_of("bench").replace(b"/opt/p77/bin/c.ksh", b"/opt/p77/bin/c2.ksh")
    xml = write_export(tmp_path, "bench", changed)

    assert main(["refresh", str(xml), "--repo", str(root)]) == 0

    out = capsys.readouterr().out
    assert "modified job P77_CHAIN/P77_C" in out
    assert "CMDLINE: /opt/p77/bin/c.ksh -> /opt/p77/bin/c2.ksh" in out
    assert "jobs: 1 modified" in out

    assert main(["refresh", str(xml), "--repo", str(root), "--stat"]) == 0
    out = capsys.readouterr().out
    assert "jobs: 1 modified" in out and "CMDLINE" not in out

    assert main(["refresh", str(xml), "--repo", str(root), "--apply", "--no-commit"]) == 0
    out = capsys.readouterr().out
    assert "Written on env/bench, not committed" in out
    assert "P77_C.json" in git(root, "status", "--porcelain")


def test_the_same_export_says_there_is_nothing_to_do(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = four_branches(tmp_path).root
    xml = write_export(tmp_path, "egma")

    assert main(["refresh", str(xml), "--repo", str(root), "--apply"]) == 0

    assert "env/egma already holds this export: nothing to do." in capsys.readouterr().out


def test_json_and_a_wrong_environment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = four_branches(tmp_path).root
    xml = write_export(tmp_path, "uat")

    assert main(["refresh", str(xml), "--repo", str(root), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert (data["env"], data["branch"], data["unchanged"]) == ("uat", "env/uat", True)
    assert data["imported"] == {"folders": 2, "jobs": 9, "links": data["imported"]["links"],
                                "skipped": 1, "literal_marks": 0,
                                "suspicious_values": 0}  # fmt: skip

    assert main(["refresh", str(xml), "--repo", str(root), "--env", "bench"]) == 3
    assert "looks like uat" in capsys.readouterr().err
