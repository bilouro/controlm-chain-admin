"""Comparing only some commits of a branch: they are applied on the base, cherry-pick style."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.errors import GitError, SelectionConflict
from controlm_chain_admin.core.history import WORKTREE, commits_between
from controlm_chain_admin.core.refactor import apply, insert_job, set_attributes
from controlm_chain_admin.core.repo import ChainRepo
from tests.support.gitrepo import chain_git_repo, commit_all, git

C = "P77_CHAIN"


def _branch(tmp_path: Path) -> tuple[ChainRepo, str, str, str]:
    """main, then a feature with three commits: P77_B, P77_C, P77_B again (another line)."""
    repo = chain_git_repo(tmp_path)
    git(repo.root, "checkout", "-q", "-b", "feature")
    apply(repo, set_attributes(repo, f"{C}/P77_B", {"RUN_AS": "first"}))
    one = commit_all(repo.root, "feat: first on P77_B")
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "second"}))
    two = commit_all(repo.root, "feat: second on P77_C")
    apply(repo, set_attributes(repo, f"{C}/P77_B", {"CMDLINE": "/opt/p77/bin/third.ksh"}))
    three = commit_all(repo.root, "feat: third on P77_B")
    return repo, one, two, three


def _changes(result) -> dict[str, set[tuple[str, str | None]]]:  # type: ignore[no-untyped-def]
    return {j.node: {(a.name, a.after) for a in j.attributes} for j in result.jobs}


def test_only_the_selected_commits_are_compared(tmp_path: Path) -> None:
    repo, _one, two, _three = _branch(tmp_path)

    result = compare(repo.root, "main", "feature", commits=[two])

    assert _changes(result) == {f"{C}/P77_C": {("DESCRIPTION", "second")}}
    assert result.selected == (two,)
    assert len(result.commits) == 3  # every commit of the branch, to choose from


def test_left_out_commit_on_the_same_file_is_not_carried(tmp_path: Path) -> None:
    repo, _one, _two, three = _branch(tmp_path)

    result = compare(repo.root, "main", "feature", commits=[three[:10]])

    assert _changes(result) == {f"{C}/P77_B": {("CMDLINE", "/opt/p77/bin/third.ksh")}}
    assert result.selected == (three,)


def test_selecting_every_commit_is_the_branch_itself(tmp_path: Path) -> None:
    repo, one, two, three = _branch(tmp_path)

    result = compare(repo.root, "main", "feature", commits=[three, one, two])

    assert result.selected is None
    assert set(_changes(result)) == {f"{C}/P77_B", f"{C}/P77_C"}


def test_an_empty_selection_has_no_changes(tmp_path: Path) -> None:
    repo, *_ = _branch(tmp_path)

    result = compare(repo.root, "main", "feature", commits=[])

    assert result.jobs == () and result.selected == ()


def test_each_change_lists_the_commits_that_made_it(tmp_path: Path) -> None:
    repo, one, two, three = _branch(tmp_path)

    result = compare(repo.root, "main", "feature")

    commits = {j.node: j.commits for j in result.jobs}
    assert commits == {f"{C}/P77_B": (three, one), f"{C}/P77_C": (two,)}
    assert result.folders == ()  # only jobs changed: the folder itself is not listed


def test_a_commit_that_needs_a_left_out_one_names_it(tmp_path: Path) -> None:
    repo = chain_git_repo(tmp_path)
    git(repo.root, "checkout", "-q", "-b", "feature")
    apply(repo, insert_job(repo, f"{C}/P77_NEW", after=f"{C}/P77_A", before=f"{C}/P77_B"))
    created = commit_all(repo.root, "feat: insert P77_NEW")
    apply(repo, set_attributes(repo, f"{C}/P77_NEW", {"DESCRIPTION": "needs the insert"}))
    edited = commit_all(repo.root, "feat: describe P77_NEW")

    with pytest.raises(SelectionConflict) as caught:
        compare(repo.root, "main", "feature", commits=[edited])

    assert caught.value.commit == edited and caught.value.missing == (created,)
    assert "folders/P77_CHAIN/jobs/P77_NEW.json" in caught.value.paths
    assert caught.value.detail == {
        "commit": edited,
        "paths": list(caught.value.paths),
        "missing": [created],
    }


def test_commits_outside_the_branch_or_merges_cannot_be_selected(tmp_path: Path) -> None:
    repo, one, *_ = _branch(tmp_path)
    git(repo.root, "checkout", "-q", "main")
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "on main"}))
    on_main = commit_all(repo.root, "fix: on main")
    git(repo.root, "checkout", "-q", "feature")
    git(repo.root, "merge", "-q", "--no-edit", "main")
    merge = git(repo.root, "rev-parse", "HEAD")

    with pytest.raises(GitError, match="not one of the commits"):
        compare(repo.root, "main", "feature", commits=[on_main])
    with pytest.raises(GitError, match="merge commit"):
        compare(repo.root, "main", "feature", commits=[merge])
    with pytest.raises(GitError, match="unknown commit"):
        compare(repo.root, "main", "feature", commits=["nope"])
    assert next(c.merge for c in commits_between(repo.root, "main", "feature")) is True

    picked = compare(repo.root, "main", "feature", commits=[one])  # the merge is skipped
    assert _changes(picked) == {f"{C}/P77_B": {("RUN_AS", "first")}}


def test_the_working_tree_has_no_commits_to_select(tmp_path: Path) -> None:
    repo, one, *_ = _branch(tmp_path)

    with pytest.raises(GitError, match="working tree"):
        compare(repo.root, "main", WORKTREE, commits=[one])


def test_without_the_merge_base_the_commits_go_on_top_of_the_base_tip(tmp_path: Path) -> None:
    repo, _one, two, _three = _branch(tmp_path)
    git(repo.root, "checkout", "-q", "main")
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "on main"}))
    commit_all(repo.root, "fix: on main")

    result = compare(repo.root, "main", "feature", use_merge_base=False, commits=[two])

    assert _changes(result) == {f"{C}/P77_C": {("DESCRIPTION", "second")}}
