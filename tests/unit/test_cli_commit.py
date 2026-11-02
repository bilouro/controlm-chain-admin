"""ctmchain commit: the suggested message, or a given one, for the chain files only."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from controlm_chain_admin.core.refactor import apply, set_attributes
from tests.support.gitrepo import chain_git_repo, git, plain_git_identity

C = "P77_CHAIN"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plain_git_identity(monkeypatch, tmp_path)
    repo = chain_git_repo(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "x"}))
    return repo.root


def test_dry_run_prints_the_suggested_message(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["commit", "--repo", str(root), "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "fix: update job P77_E in P77_CHAIN" in out
    assert f"folders/{C}/jobs/P77_E.json" in out and "Nothing committed" in out
    assert git(root, "status", "--porcelain") != ""


def test_commit_with_the_suggested_or_a_given_message(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["commit", "--repo", str(root), "--branch", "fix/e"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Committed ") and "on fix/e: fix: update job P77_E" in out

    repo_root = root
    (repo_root / "folders" / C / "jobs" / "P77_E.json").write_text("{}\n", encoding="utf-8")
    assert main(["commit", "--repo", str(root), "-m", "chore: by hand"]) == 0
    assert git(root, "log", "-1", "--format=%s") == "chore: by hand"


def test_nothing_to_commit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = chain_git_repo(tmp_path)

    assert main(["commit", "--repo", str(repo.root)]) == 0

    assert "Nothing to commit" in capsys.readouterr().out
