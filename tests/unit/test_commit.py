"""Committing the edits: what is pending, a message written from it, and the commit itself."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.commit import commit, pending
from controlm_chain_admin.core.errors import (
    ChangeConflict,
    GitError,
    NothingToCommit,
    ProtectedBranch,
)
from controlm_chain_admin.core.history import git_state
from controlm_chain_admin.core.refactor import (
    apply,
    insert_job,
    rename_link,
    run_operation,
    set_attributes,
    update_relation,
)
from controlm_chain_admin.core.repo import ChainRepo
from tests.support.gitrepo import chain_git_repo, git, plain_git_identity

C = "P77_CHAIN"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ChainRepo:
    plain_git_identity(monkeypatch, tmp_path)
    return chain_git_repo(tmp_path)


def test_nothing_pending_on_a_clean_repository(repo: ChainRepo) -> None:
    state = pending(repo.root)

    assert state.files == () and state.message == "" and state.branch == "main"
    assert state.protected  # main: the dialog offers a new branch
    with pytest.raises(NothingToCommit):
        commit(repo.root, "fix: nothing", state.fingerprint)


def test_one_job_changed_gives_a_message_naming_it(repo: ChainRepo) -> None:
    apply(repo, update_relation(repo, "P77_B-P77_C_OK", f"{C}/P77_C", cleanup=True))

    state = pending(repo.root)

    subject, _, body = state.message.partition("\n\n")
    assert subject == "fix: update job P77_C in P77_CHAIN"
    assert f"- modified job {C}/P77_C" in body
    assert "predecessor P77_B-P77_C_OK modified: cleanup no -> yes" in body
    assert f"folders/{C}/jobs/P77_C.json" in state.files
    assert all(not f.endswith("index.json") for f in state.files)  # derived, committed silently


def test_several_kinds_of_change_are_summed_up(repo: ChainRepo) -> None:
    apply(repo, insert_job(repo, f"{C}/P77_NEW", after=f"{C}/P77_A", before=f"{C}/P77_B"))
    apply(repo, rename_link(repo, "P77_D-P77_NOBODY_OK", "P77_D_DONE"))
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "x"}))

    subject = pending(repo.root).message.splitlines()[0]

    assert subject.startswith("feat: add 1 job, rename ")
    assert "condition" in subject and "update " in subject


def test_only_renames_are_a_refactoring(repo: ChainRepo) -> None:
    apply(repo, rename_link(repo, "P77_D-P77_NOBODY_OK", "P77_D_DONE"))

    assert pending(repo.root).message.startswith("refactor: rename 1 condition")


def test_a_batch_is_committed_as_one_commit_with_the_given_message(repo: ChainRepo) -> None:
    changes = [
        {"op": "update-relation", "params": {
            "link": "P77_B-P77_C_OK", "consumer": f"{C}/P77_C", "cleanup": True,
        }},
        {"op": "rename-link", "params": {"link": "P77_D-P77_NOBODY_OK", "name": "P77_D_DONE"}},
    ]  # fmt: skip
    git(repo.root, "switch", "-q", "-c", "release/march")
    apply(repo, run_operation(repo, "batch", {"changes": changes}))
    state = pending(repo.root)
    before = git(repo.root, "rev-list", "--count", "HEAD")

    done = commit(repo.root, "fix: two fixes\n\nedited by hand", state.fingerprint)

    assert not state.protected
    assert git(repo.root, "rev-list", "--count", "HEAD") == str(int(before) + 1)
    assert git(repo.root, "log", "-1", "--format=%B") == "fix: two fixes\n\nedited by hand"
    assert done.branch == "release/march" and done.subject == "fix: two fixes"
    assert len(done.sha) == 40
    assert not git_state(repo.root).dirty
    assert git(repo.root, "status", "--porcelain") == ""  # index.json committed too


def test_commit_on_a_new_branch(repo: ChainRepo) -> None:
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "x"}))
    state = pending(repo.root)

    done = commit(repo.root, state.message, state.fingerprint, branch="fix/describe-e")

    assert done.branch == "fix/describe-e"
    assert git(repo.root, "rev-parse", "--abbrev-ref", "HEAD") == "fix/describe-e"
    assert git(repo.root, "rev-list", "--count", "main..fix/describe-e") == "1"


def test_a_protected_branch_is_never_committed_on(repo: ChainRepo) -> None:
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "x"}))
    state = pending(repo.root)

    with pytest.raises(ProtectedBranch, match="main is protected"):
        commit(repo.root, state.message, state.fingerprint)
    with pytest.raises(ProtectedBranch, match="master is protected"):
        commit(repo.root, state.message, state.fingerprint, branch="master")
    assert git(repo.root, "rev-list", "--count", "HEAD") == "1"


def test_files_outside_the_chain_are_left_alone(repo: ChainRepo) -> None:
    git(repo.root, "switch", "-q", "-c", "release/march")
    (repo.root / "notes.txt").write_text("not mine\n", encoding="utf-8")
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "x"}))
    state = pending(repo.root)

    commit(repo.root, state.message, state.fingerprint)

    assert git(repo.root, "status", "--porcelain") == "?? notes.txt"


def test_a_change_after_the_dialog_opened_is_refused(repo: ChainRepo) -> None:
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "x"}))
    state = pending(repo.root)
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "y"}))

    with pytest.raises(ChangeConflict, match="changed since"):
        commit(repo.root, state.message, state.fingerprint)


def test_bad_message_or_branch(repo: ChainRepo) -> None:
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "x"}))
    state = pending(repo.root)

    with pytest.raises(GitError, match="empty"):
        commit(repo.root, "   ", state.fingerprint)
    with pytest.raises(GitError, match="branch name"):
        commit(repo.root, "fix: x", state.fingerprint, branch="bad..name")
    git(repo.root, "branch", "taken")
    with pytest.raises(GitError, match="already exists"):
        commit(repo.root, "fix: x", state.fingerprint, branch="taken")
