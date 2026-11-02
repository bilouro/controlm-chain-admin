"""ctmchain resolve: list the fixes per kind of finding, then preview or apply a choice."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.repo import load_repo
from controlm_chain_admin.core.validate import validate
from tests.support.gitrepo import chain_git_repo, git


def test_without_a_choice_it_lists_the_fixes_per_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = chain_git_repo(tmp_path).root

    assert main(["resolve", "--repo", str(root)]) == 0

    out = capsys.readouterr().out
    assert "never-cleaned (1 finding)" in out
    assert "  add-cleanup: Delete it after use (1)" in out
    assert "  emit: Make the named producer emit it (1)" in out
    assert "non-standard-name (1 finding): no fix" in out


def test_a_choice_is_previewed_then_applied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = chain_git_repo(tmp_path).root
    choice = ["never-cleaned=add-cleanup", "stale-name=standard-name"]

    assert main(["resolve", *choice, "--repo", str(root), "--stat"]) == 0
    preview = capsys.readouterr().out
    assert preview.startswith("2 changes:") and "Preview only" in preview

    assert main(["resolve", *choice, "--repo", str(root), "--apply"]) == 3
    assert "main is protected" in capsys.readouterr().err  # never written on the trunk
    git(root, "switch", "-q", "-c", "release/march")

    assert main(["resolve", *choice, "--repo", str(root), "--apply"]) == 0
    assert "Applied" in capsys.readouterr().out
    codes = {f.code for f in validate(load_repo(root)).findings}
    assert "never-cleaned" not in codes and "stale-name" not in codes


def test_findings_without_that_fix_are_skipped_and_bad_choices_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = chain_git_repo(tmp_path).root

    assert main(["resolve", "dangling-external=stop-waiting", "unconsumed=emit",
                 "--repo", str(root), "--stat"]) == 0  # fmt: skip
    out = capsys.readouterr().out
    assert "skipped: unconsumed P77_A-P77_C_OK (no single emit fix)" in out

    assert main(["resolve", "never-cleaned", "--repo", str(root)]) == 2
    assert "CODE=KIND" in capsys.readouterr().err
