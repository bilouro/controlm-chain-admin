"""Reading the chain repository at any git ref."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.core.errors import GitError
from controlm_chain_admin.core.history import (
    WORKTREE,
    commits_between,
    git_state,
    merge_base,
    resolve,
    snapshot,
)
from tests.support.gitrepo import chain_git_repo, commit_all, git, remove_tree

FOLDER = "folders/P77_CHAIN/folder.json"


def test_git_state_lists_branches_and_the_current_one(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    git(repo.root, "branch", "develop")

    state = git_state(repo.root)

    assert state.current == "main" and not state.dirty
    assert {r.name for r in state.refs if r.kind == "branch"} == {"main", "develop"}
    assert len(state.head) == 40


def test_dirty_working_tree_is_reported(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    (repo.root / FOLDER).write_text("{}\n", encoding="utf-8")

    assert git_state(repo.root).dirty


def test_snapshot_of_a_ref_holds_the_files_as_committed(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    original = (repo.root / FOLDER).read_text("utf-8")
    git(repo.root, "checkout", "-q", "-b", "feature")
    (repo.root / FOLDER).write_text(
        original.replace('"P77_BATCH"', '"P77_CORE"'), encoding="utf-8"
    )
    commit_all(repo.root, "change the sub-application")

    with snapshot(repo.root, "main") as main_root, snapshot(repo.root, "feature") as feature_root:
        assert (main_root / FOLDER).read_text("utf-8") == original
        assert '"P77_CORE"' in (feature_root / FOLDER).read_text("utf-8")
        assert (main_root / "chain.json").is_file()
        assert not (main_root / ".git").exists()


def test_worktree_snapshot_is_the_repository_itself(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)

    with snapshot(repo.root, WORKTREE) as root:
        assert root == repo.root
    assert resolve(repo.root, WORKTREE).kind == "worktree"


def test_merge_base_and_commits_between(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    base = git(repo.root, "rev-parse", "HEAD")
    git(repo.root, "checkout", "-q", "-b", "feature")
    (repo.root / "folders/P77_CHAIN/notes.txt").write_text("x\n", encoding="utf-8")
    first = commit_all(repo.root, "feat: first change")
    (repo.root / "folders/P77_CHAIN/notes.txt").write_text("y\n", encoding="utf-8")
    second = commit_all(repo.root, "feat: second change")
    git(repo.root, "checkout", "-q", "main")
    (repo.root / "folders/P77_INGEST_DAILY/notes.txt").write_text("z\n", encoding="utf-8")
    commit_all(repo.root, "fix: on main meanwhile")

    main, feature = resolve(repo.root, "main"), resolve(repo.root, "feature")
    assert merge_base(repo.root, main.sha or "", feature.sha or "") == base
    commits = commits_between(repo.root, base, second)
    assert [c.sha for c in commits] == [second, first]
    assert commits[0].subject == "feat: second change" and commits[0].author == "Test"


def test_unknown_refs_and_missing_git_repositories_raise(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)

    with pytest.raises(GitError, match="nope"):
        resolve(repo.root, "nope")
    (tmp_path / "plain").mkdir()
    with pytest.raises(GitError):
        git_state(tmp_path / "plain")


def test_snapshot_of_a_chain_repository_in_a_subdirectory(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-q", "-b", "main")
    repo = chain_git_repo(outer)  # creates outer/repo inside the outer git repository
    remove_tree(repo.root / ".git")  # read-only objects on Windows
    commit_all(outer, "chain in a subdirectory")

    with snapshot(repo.root, "main") as root:
        assert (
            json.loads((root / "chain.json").read_text("utf-8"))["application"]
            == "P77_RISK_ENGINE"
        )
