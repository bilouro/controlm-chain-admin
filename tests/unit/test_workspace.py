"""Release branches from the trunk, installations as tags, stash, discard, close, push and pull."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from controlm_chain_admin.core import workspace as ws
from controlm_chain_admin.core.commit import discard, pending
from controlm_chain_admin.core.errors import (
    ChangeConflict,
    GitError,
    MergeConflict,
    ModelError,
    NothingToCommit,
    ProtectedBranch,
    UncommittedChanges,
    UnknownEnvironment,
)
from controlm_chain_admin.core.refactor import apply, set_attributes
from controlm_chain_admin.core.repo import (
    ChainRepo,
    GitRules,
    init_repo,
    load_repo,
    read_json,
    write_json,
)
from tests.support.gitrepo import chain_git_repo, commit_all, git, plain_git_identity

C = "P77_CHAIN"
E = f"{C}/P77_E"
E_FILE = f"folders/{C}/jobs/P77_E.json"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ChainRepo:
    plain_git_identity(monkeypatch, tmp_path)
    return chain_git_repo(tmp_path)


def describe(repo: ChainRepo, text: str, job: str = E) -> None:
    apply(repo, set_attributes(repo, job, {"DESCRIPTION": text}))


def release_with_commit(repo: ChainRepo, name: str = "march", text: str = "x") -> str:
    ws.start_release(repo, name)
    describe(repo, text)
    return commit_all(repo.root, f"fix: describe P77_E as {text}")


def add_remote(repo: ChainRepo, tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(repo.root, "remote", "add", "origin", str(origin))
    git(repo.root, "push", "-q", "-u", "origin", "main")
    return origin


def clone(origin: Path, tmp_path: Path) -> ChainRepo:
    target = tmp_path / "teammate"
    git(tmp_path, "clone", "-q", str(origin), str(target))
    return load_repo(target)


# ---------------------------------------------------------------- rules


def test_git_rules_have_defaults_and_can_be_set_in_chain_json(repo: ChainRepo) -> None:
    rules = repo.config.git_rules

    assert repo.config.git is None and rules == GitRules()
    assert (rules.trunk, rules.protected, rules.release_prefix) == ("main", ("main", "master"),
                                                                     "release/")  # fmt: skip
    assert (rules.tag_format, rules.production, rules.remote) == (
        "{env}/{release}-{n}", "prod", "origin",
    )  # fmt: skip
    assert "git" not in read_json(repo.chain_file)  # defaults are not written

    data = read_json(repo.chain_file)
    data["git"] = {"trunk": "trunk", "protected": ["stable"], "release_prefix": "rel/"}
    write_json(repo.chain_file, data)
    config = load_repo(repo.root).config

    assert config.git_rules.trunk == "trunk" and config.git_rules.protected == ("stable",)
    assert config.git_rules.tag_format == "{env}/{release}-{n}"  # the default is kept
    assert config.to_json()["git"]["release_prefix"] == "rel/"  # survives a save


@pytest.mark.parametrize(
    "bad",
    [
        {"tag_format": "{env}-{n}"},
        {"protected": "main"},
        {"release_prefix": ""},
        {"trunk": 3},
        {"unknown": 1},
    ],
)
def test_bad_git_rules_are_reported(bad: dict[str, object]) -> None:
    with pytest.raises(ModelError, match=r"chain\.json: git"):
        GitRules.from_json(bad)


# ---------------------------------------------------------------- where edits may go


def test_the_trunk_is_read_only_and_a_release_is_not(repo: ChainRepo) -> None:
    state = ws.workspace(repo)

    assert state.branch == "main" and state.trunk == "main" and not state.editable
    assert state.reason is not None and state.reason.startswith("main is protected")
    assert state.release is None and state.releases == () and state.changes == 0
    with pytest.raises(ProtectedBranch, match="main is protected"):
        ws.ensure_editable(repo)

    assert ws.start_release(repo, "march") == "Started release/march from main"

    state = ws.workspace(repo)
    assert state.branch == "release/march" and state.release == "march" and state.editable
    ws.ensure_editable(repo)
    [march] = state.releases
    assert (march.name, march.branch, march.local, march.remote) == (
        "march", "release/march", True, False,
    )  # fmt: skip
    assert (march.ahead, march.trunk_behind, march.installed, march.closable) == (0, 0, (), False)


def test_detached_head_and_other_protected_branches_are_read_only(repo: ChainRepo) -> None:
    git(repo.root, "switch", "-q", "-c", "master")
    with pytest.raises(ProtectedBranch, match="master is protected"):
        ws.ensure_editable(repo)
    git(repo.root, "switch", "-q", "--detach", "main")
    with pytest.raises(ProtectedBranch, match="detached"):
        ws.ensure_editable(repo)
    git(repo.root, "switch", "-q", "-c", "spike")
    ws.ensure_editable(repo)  # any other branch may be edited


def test_a_repository_outside_git_is_always_editable(tmp_path: Path) -> None:
    ws.ensure_editable(init_repo(tmp_path / "plain", "P77_RISK_ENGINE", ("uat",)))


def test_a_release_always_starts_from_the_trunk(repo: ChainRepo) -> None:
    release_with_commit(repo, "march")

    ws.start_release(repo, "april")

    assert git(repo.root, "rev-parse", "HEAD") == git(repo.root, "rev-parse", "main")


@pytest.mark.parametrize("name", ["", "two words", "a/b", "-x", "a..b", "x.lock"])
def test_bad_release_names(repo: ChainRepo, name: str) -> None:
    with pytest.raises(GitError, match="invalid release name"):
        ws.start_release(repo, name)


def test_an_existing_release_or_a_missing_trunk(repo: ChainRepo) -> None:
    ws.start_release(repo, "march")
    with pytest.raises(GitError, match="release/march already exists"):
        ws.start_release(repo, "march")
    git(repo.root, "branch", "-q", "-m", "main", "old")
    with pytest.raises(GitError, match="the trunk branch main does not exist"):
        ws.start_release(repo, "april")


# ---------------------------------------------------------------- uncommitted changes


def test_uncommitted_changes_block_leaving_unless_stashed(repo: ChainRepo) -> None:
    ws.start_release(repo, "march")
    describe(repo, "draft")
    with pytest.raises(UncommittedChanges, match="1 uncommitted chain file on release/march"):
        ws.switch(repo, "main")
    with pytest.raises(UncommittedChanges) as caught:
        ws.start_release(repo, "april")
    assert caught.value.detail == {"changes": 1}

    message = ws.switch(repo, "main", stash=True)

    assert message == (
        "Stashed 1 chain file of release/march (fix: update job P77_E in P77_CHAIN). "
        "Switched to main"
    )
    state = ws.workspace(repo)
    assert state.branch == "main" and state.changes == 0
    [saved] = state.stashes
    assert (saved.ref, saved.branch) == ("stash@{0}", "release/march")
    assert saved.message == "fix: update job P77_E in P77_CHAIN"


def test_switch_errors(repo: ChainRepo) -> None:
    with pytest.raises(GitError, match="already on main"):
        ws.switch(repo, "main")
    with pytest.raises(GitError, match="unknown branch 'nope'"):
        ws.switch(repo, "nope")
    with pytest.raises(NothingToCommit, match="nothing to stash"):
        ws.stash(repo)


def test_a_stash_is_restored_on_an_editable_branch_only(repo: ChainRepo) -> None:
    ws.start_release(repo, "march")
    describe(repo, "draft")
    ws.switch(repo, "main", stash=True)
    with pytest.raises(ProtectedBranch, match="main is protected"):
        ws.pop(repo, "stash@{0}")
    ws.switch(repo, "release/march")

    message = ws.pop(repo, "stash@{0}")

    assert message == "Restored stash@{0} on release/march (fix: update job P77_E in P77_CHAIN)"
    state = ws.workspace(repo)
    assert state.changes == 1 and state.stashes == ()
    with pytest.raises(GitError, match="unknown stash"):
        ws.pop(repo, "stash@{3}")


def test_a_stash_that_conflicts_changes_nothing_and_is_kept(repo: ChainRepo) -> None:
    ws.start_release(repo, "march")
    describe(repo, "draft")
    ws.stash(repo)
    describe(repo, "other")
    with pytest.raises(UncommittedChanges):
        ws.pop(repo, "stash@{0}")
    commit_all(repo.root, "fix: another description")

    with pytest.raises(MergeConflict, match=r"stash@\{0\} does not apply") as caught:
        ws.pop(repo, "stash@{0}")

    assert caught.value.detail == {"paths": [E_FILE]}
    assert git(repo.root, "status", "--porcelain") == ""
    assert len(ws.workspace(repo).stashes) == 1


def test_discard_restores_the_last_commit(repo: ChainRepo) -> None:
    ws.start_release(repo, "march")
    describe(repo, "draft")
    new = repo.root / "folders" / C / "README.txt"
    new.write_text("draft\n", encoding="utf-8")
    (repo.root / "notes.txt").write_text("not a chain file\n", encoding="utf-8")
    state = pending(repo.root)
    with pytest.raises(ChangeConflict):
        discard(repo.root, "stale")

    assert discard(repo.root, state.fingerprint) == 2

    assert git(repo.root, "status", "--porcelain") == "?? notes.txt" and not new.exists()
    with pytest.raises(NothingToCommit, match="nothing to discard"):
        discard(repo.root, pending(repo.root).fingerprint)


# ---------------------------------------------------------------- installations


def test_installations_are_tags_numbered_per_environment(repo: ChainRepo) -> None:
    first = release_with_commit(repo, "march", "one")

    installed = ws.mark_installed(repo, "uat")

    assert (installed.env, installed.tag, installed.sha, installed.behind) == (
        "uat", "uat/march-1", first, 0,
    )  # fmt: skip
    assert git(repo.root, "cat-file", "-t", "uat/march-1") == "tag"  # annotated
    subject = git(repo.root, "tag", "-l", "--format=%(contents:subject)", "uat/march-1")
    assert subject == "Installed release/march in uat"
    with pytest.raises(GitError, match="uat already has release/march at"):
        ws.mark_installed(repo, "uat")

    describe(repo, "two")
    second = commit_all(repo.root, "fix: two")
    [march] = ws.workspace(repo).releases
    assert [(i.env, i.tag, i.behind) for i in march.installed] == [("uat", "uat/march-1", 1)]

    assert ws.mark_installed(repo, "uat", "march", second).tag == "uat/march-2"
    assert ws.mark_installed(repo, "prod", sha=first).tag == "prod/march-1"
    [march] = ws.workspace(repo).releases
    assert [(i.env, i.tag, i.behind) for i in march.installed] == [
        ("uat", "uat/march-2", 0), ("prod", "prod/march-1", 1),
    ]  # fmt: skip


def test_installation_errors(repo: ChainRepo) -> None:
    ws.start_release(repo, "empty")
    with pytest.raises(GitError, match="release/empty has no commit of its own"):
        ws.mark_installed(repo, "uat")
    release_with_commit(repo, "march")
    with pytest.raises(UnknownEnvironment):
        ws.mark_installed(repo, "bench")
    with pytest.raises(GitError, match="unknown release 'april'"):
        ws.mark_installed(repo, "uat", "april")
    with pytest.raises(GitError, match="is not a commit of release/march"):
        ws.mark_installed(repo, "uat", sha=git(repo.root, "rev-parse", "main"))
    ws.switch(repo, "main")
    with pytest.raises(GitError, match="not on a release"):
        ws.mark_installed(repo, "uat")


# ---------------------------------------------------------------- closing a release


def test_close_merges_a_release_installed_in_production(repo: ChainRepo) -> None:
    tip = release_with_commit(repo, "march")
    with pytest.raises(GitError, match="not installed in prod"):
        ws.close_release(repo)
    ws.mark_installed(repo, "uat")
    ws.mark_installed(repo, "prod")
    assert ws.workspace(repo).releases[0].closable

    message = ws.close_release(repo)

    merge = git(repo.root, "rev-parse", "main")
    assert message == f"Closed release/march: merged into main ({merge[:7]})"
    assert git(repo.root, "rev-parse", "main^2") == tip
    assert git(repo.root, "log", "-1", "--format=%s", "main") == "Merge release/march into main"
    assert "Installed: uat/march-1, prod/march-1" in git(repo.root, "log", "-1", "--format=%b")
    state = ws.workspace(repo)
    assert state.branch == "main" and state.releases == ()
    assert git(repo.root, "branch", "--list", "release/march") == ""
    assert git(repo.root, "status", "--porcelain") == ""
    with pytest.raises(GitError, match="not on a release"):
        ws.close_release(repo)


def test_a_release_behind_the_trunk_is_updated_before_closing(repo: ChainRepo) -> None:
    release_with_commit(repo, "march")
    ws.mark_installed(repo, "prod")
    git(repo.root, "switch", "-q", "main")
    describe(repo, "hotfix", f"{C}/P77_A")
    commit_all(repo.root, "fix: hotfix")
    git(repo.root, "switch", "-q", "release/march")
    [march] = ws.workspace(repo).releases
    assert march.trunk_behind == 1 and not march.closable
    with pytest.raises(GitError, match="main has 1 commit that release/march does not have"):
        ws.close_release(repo)

    assert ws.update_from_trunk(repo) == "Merged 1 commit of main into release/march"

    assert git(repo.root, "log", "-1", "--format=%s") == "Merge main into release/march"
    with pytest.raises(GitError, match="already has every commit of main"):
        ws.update_from_trunk(repo)
    with pytest.raises(GitError, match="not installed in prod"):
        ws.close_release(repo)  # what was merged must be installed again
    ws.mark_installed(repo, "prod")
    ws.close_release(repo)
    assert git(repo.root, "rev-list", "--count", "main") == "5"


def test_an_update_that_conflicts_changes_nothing(repo: ChainRepo) -> None:
    release_with_commit(repo, "march", "release")
    git(repo.root, "switch", "-q", "main")
    describe(repo, "hotfix")
    commit_all(repo.root, "fix: hotfix")
    git(repo.root, "switch", "-q", "release/march")

    with pytest.raises(MergeConflict, match="main does not merge into release/march") as caught:
        ws.update_from_trunk(repo)

    assert caught.value.detail == {"paths": [E_FILE]}
    assert git(repo.root, "status", "--porcelain") == ""
    assert not (repo.root / ".git" / "MERGE_HEAD").exists()


def test_update_and_close_refuse_uncommitted_changes(repo: ChainRepo) -> None:
    release_with_commit(repo, "march")
    describe(repo, "draft")
    with pytest.raises(UncommittedChanges):
        ws.update_from_trunk(repo)
    with pytest.raises(UncommittedChanges):
        ws.close_release(repo)
    ws.switch(repo, "main", stash=True)
    with pytest.raises(ProtectedBranch):
        ws.update_from_trunk(repo)


# ---------------------------------------------------------------- remote


def test_push_and_pull_need_the_remote(repo: ChainRepo) -> None:
    with pytest.raises(GitError, match="no remote 'origin'"):
        ws.push(repo)
    with pytest.raises(GitError, match="no remote 'origin'"):
        ws.pull(repo)


def test_push_and_pull_a_release(repo: ChainRepo, tmp_path: Path) -> None:
    origin = add_remote(repo, tmp_path)
    release_with_commit(repo, "march")
    ws.mark_installed(repo, "uat")
    state = ws.workspace(repo)
    assert state.remote == "origin" and state.upstream is None

    assert ws.push(repo) == "Pushed release/march to origin"

    assert git(origin, "rev-parse", "release/march") == git(repo.root, "rev-parse", "HEAD")
    assert git(origin, "tag", "-l") == "uat/march-1"
    state = ws.workspace(repo)
    assert state.upstream == "origin/release/march" and (state.ahead, state.behind) == (0, 0)

    teammate = clone(origin, tmp_path)
    git(teammate.root, "switch", "-q", "release/march")
    describe(teammate, "teammate", f"{C}/P77_A")
    commit_all(teammate.root, "fix: teammate")
    git(teammate.root, "push", "-q", "origin", "release/march")

    assert ws.pull(repo) == "Fetched origin. release/march: fast-forwarded 1 commit"
    assert git(repo.root, "rev-parse", "HEAD") == git(teammate.root, "rev-parse", "HEAD")
    assert ws.pull(repo) == "Fetched origin. release/march: up to date"

    describe(repo, "mine")
    commit_all(repo.root, "fix: mine")
    describe(teammate, "theirs", f"{C}/P77_B")
    commit_all(teammate.root, "fix: theirs")
    git(teammate.root, "push", "-q", "origin", "release/march")
    with pytest.raises(GitError, match="release/march and origin/release/march have diverged"):
        ws.pull(repo)


def test_pull_brings_new_releases_and_moves_the_trunk(repo: ChainRepo, tmp_path: Path) -> None:
    origin = add_remote(repo, tmp_path)
    ws.start_release(repo, "march")
    teammate = clone(origin, tmp_path)
    git(teammate.root, "switch", "-q", "-c", "release/april")
    describe(teammate, "april")
    commit_all(teammate.root, "fix: april")
    git(teammate.root, "push", "-q", "origin", "release/april")
    git(teammate.root, "switch", "-q", "main")
    describe(teammate, "main moved", f"{C}/P77_A")
    commit_all(teammate.root, "fix: main moved")
    git(teammate.root, "push", "-q", "origin", "main")

    message = ws.pull(repo)

    assert message == "Fetched origin. main: fast-forwarded 1 commit"
    assert git(repo.root, "rev-parse", "main") == git(teammate.root, "rev-parse", "main")
    april = next(r for r in ws.workspace(repo).releases if r.name == "april")
    assert (april.local, april.remote, april.ahead) == (False, True, 1)
    ws.switch(repo, "release/april")
    assert git(repo.root, "rev-parse", "--abbrev-ref", "@{u}") == "origin/release/april"


def test_pushing_the_trunk_after_closing_removes_the_remote_release(
    repo: ChainRepo, tmp_path: Path
) -> None:
    origin = add_remote(repo, tmp_path)
    release_with_commit(repo, "march")
    ws.mark_installed(repo, "prod")
    ws.push(repo)
    ws.close_release(repo)
    assert ws.workspace(repo).releases == ()  # closed, though still on the remote

    assert ws.push(repo) == "Pushed main to origin; deleted the closed release/march on origin"

    assert git(origin, "branch", "--list", "release/march") == ""
    assert git(origin, "rev-parse", "main") == git(repo.root, "rev-parse", "main")


def test_the_workspace_lists_the_branches_of_the_other_environments(
    repo: ChainRepo, tmp_path: Path
) -> None:
    assert ws.workspace(repo).env_branches == ()

    git(repo.root, "branch", "env/uat")
    git(repo.root, "branch", "env/elsewhere")
    here = ws.workspace(repo)

    assert here.env_branches == (ws.EnvBranch("uat", "env/uat", True, False),)
    assert here.to_json()["env_branches"] == [
        {"env": "uat", "branch": "env/uat", "local": True, "remote": False}
    ]

    origin = add_remote(repo, tmp_path)
    git(repo.root, "push", "-q", "origin", "env/uat")
    assert ws.workspace(repo).env_branches == (ws.EnvBranch("uat", "env/uat", True, True),)
    teammate = clone(origin, tmp_path)
    assert ws.workspace(teammate).env_branches == (ws.EnvBranch("uat", "env/uat", False, True),)

    assert ws.switch(teammate, "env/uat") == "Switched to env/uat"
    there = ws.workspace(teammate)
    assert (there.branch, there.editable) == ("env/uat", True)
    assert there.env_branches == (ws.EnvBranch("uat", "env/uat", True, True),)


# ---------------------------------------------------------------- a branch from the one here


def test_a_branch_starts_from_the_checked_out_branch(repo: ChainRepo) -> None:
    git(repo.root, "switch", "-q", "-c", "env/uat")
    describe(repo, "as uat has it")
    tip = commit_all(repo.root, "fix: what uat has")

    assert ws.start_branch(repo, "work/uat-next") == "Started work/uat-next from env/uat"

    state = ws.workspace(repo)
    assert (state.branch, state.editable, state.head) == ("work/uat-next", True, tip)
    assert git(repo.root, "rev-parse", "main") != tip  # not from the trunk
    assert state.branches == (ws.Branch("work/uat-next", True, False),)


def test_uncommitted_changes_follow_into_the_new_branch_and_are_said(repo: ChainRepo) -> None:
    ws.start_release(repo, "march")
    describe(repo, "draft")

    message = ws.start_branch(repo, "spike")

    assert message == "Started spike from release/march, with its 1 uncommitted chain file"
    state = ws.workspace(repo)
    assert (state.branch, state.changes) == ("spike", 1)


def test_a_branch_starts_from_a_detached_head_too(repo: ChainRepo) -> None:
    git(repo.root, "switch", "-q", "--detach", "main")
    short = git(repo.root, "rev-parse", "--short", "HEAD")

    assert ws.start_branch(repo, "spike") == f"Started spike from {short}"


@pytest.mark.parametrize(
    ("name", "why"),
    [
        ("", "invalid branch name ''"),
        ("two words", "invalid branch name"),
        ("-x", "invalid branch name"),
        ("a..b", "invalid branch name"),
        ("x.lock", "invalid branch name"),
        ("work/", "invalid branch name"),
        ("@{-1}", "invalid branch name"),
        ("main", "main already exists: switch to it"),
        ("release/march", "release/march already exists: switch to it"),
        ("master", "master is a protected branch"),
        ("map", "map is the branch of the map"),
        ("env/uat-next", "env/ holds the branches of the environments"),
        ("release/april", "a release starts from main"),
    ],
)
def test_names_a_new_branch_cannot_have(repo: ChainRepo, name: str, why: str) -> None:
    ws.start_release(repo, "march")

    with pytest.raises(GitError, match=re.escape(why)):
        ws.start_branch(repo, name)

    assert ws.workspace(repo).branch == "release/march"


def test_the_workspace_lists_the_other_branches(repo: ChainRepo, tmp_path: Path) -> None:
    assert ws.workspace(repo).branches == ()

    ws.start_release(repo, "march")
    for name in ("env/uat", "map", "work/uat-next", "spike"):
        git(repo.root, "branch", name)
    here = ws.workspace(repo)

    # not the trunk, an environment's, a release or the map
    assert here.branches == (
        ws.Branch("spike", True, False),
        ws.Branch("work/uat-next", True, False),
    )
    assert here.to_json()["branches"][0] == {"branch": "spike", "local": True, "remote": False}

    origin = add_remote(repo, tmp_path)
    git(repo.root, "push", "-q", "origin", "work/uat-next")
    teammate = clone(origin, tmp_path)

    assert ws.workspace(teammate).branches == (ws.Branch("work/uat-next", False, True),)
    with pytest.raises(GitError, match="work/uat-next already exists on origin: switch to it"):
        ws.start_branch(teammate, "work/uat-next")
    assert ws.switch(teammate, "work/uat-next") == "Switched to work/uat-next"
    assert ws.workspace(teammate).branches == (ws.Branch("work/uat-next", True, True),)


def test_workspace_as_json(repo: ChainRepo) -> None:
    sha = release_with_commit(repo, "march")
    ws.mark_installed(repo, "uat")

    data = ws.workspace(repo).to_json()

    assert data["branch"] == "release/march" and data["editable"] is True
    assert data["reason"] is None and data["release"] == "march" and data["trunk"] == "main"
    assert data["environments"] == ["uat", "prod"] and data["production"] == "prod"
    assert data["prefix"] == "release/" and data["stashes"] == []
    assert data["releases"][0]["installed"] == [
        {"env": "uat", "tag": "uat/march-1", "sha": sha, "behind": 0}
    ]
