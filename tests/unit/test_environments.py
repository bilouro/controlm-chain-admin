"""One branch per environment: which branch holds an environment, which environment a ref is."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.environments import (
    branch_of_env,
    env_branches,
    env_of_ref,
    held_env,
)
from controlm_chain_admin.core.errors import ModelError, UnknownEnvironment
from controlm_chain_admin.core.repo import ChainConfig, GitRules, load_repo, read_json, write_json
from tests.support.envexports import fresh_repo
from tests.support.gitrepo import commit_all, git


def test_the_git_rules_name_the_environment_branches_and_the_map_branch() -> None:
    rules = GitRules()

    assert (rules.env_prefix, rules.map_branch) == ("env/", "map")
    assert GitRules.from_json({"env_prefix": "environment/"}).env_prefix == "environment/"
    assert rules.to_json()["map_branch"] == "map"


def test_an_empty_environment_prefix_is_refused() -> None:
    with pytest.raises(ModelError, match="env_prefix"):
        GitRules.from_json({"env_prefix": ""})


def test_production_lives_on_the_trunk_and_the_others_on_their_branch(tmp_path: Path) -> None:
    config = fresh_repo(tmp_path).config

    assert branch_of_env(config, "prod") == "main"
    assert branch_of_env(config, "uat") == "env/uat"
    with pytest.raises(UnknownEnvironment):
        branch_of_env(config, "nowhere")


def test_the_rules_of_chain_json_rename_the_branches(tmp_path: Path) -> None:
    repo = fresh_repo(tmp_path)
    data = read_json(repo.chain_file)
    data["git"] = {"trunk": "trunk", "production": "uat", "env_prefix": "site/"}
    write_json(repo.chain_file, data)
    config = ChainConfig.from_json(read_json(repo.chain_file))

    assert branch_of_env(config, "uat") == "trunk"
    assert branch_of_env(config, "prod") == "site/prod"


def test_a_ref_tells_its_environment(tmp_path: Path) -> None:
    repo = fresh_repo(tmp_path)
    git(repo.root, "branch", "env/uat")
    git(repo.root, "branch", "release/26.1")
    git(repo.root, "tag", "v1")
    config = repo.config

    assert env_of_ref(repo.root, config, "main") == "prod"
    assert env_of_ref(repo.root, config, "env/uat") == "uat"
    assert env_of_ref(repo.root, config, "env/unknown") is None
    assert env_of_ref(repo.root, config, "release/26.1") is None
    assert env_of_ref(repo.root, config, "v1") is None


def test_the_working_tree_and_head_are_the_environment_of_the_branch_checked_out(
    tmp_path: Path,
) -> None:
    repo = fresh_repo(tmp_path)
    git(repo.root, "switch", "-q", "-c", "env/bench")

    assert env_of_ref(repo.root, repo.config, "WORKTREE") == "bench"
    assert env_of_ref(repo.root, repo.config, "HEAD") == "bench"

    git(repo.root, "switch", "-q", "--detach")
    assert env_of_ref(repo.root, repo.config, "HEAD") is None


def test_the_environment_branches_that_exist(tmp_path: Path) -> None:
    repo = fresh_repo(tmp_path)
    git(repo.root, "branch", "env/uat")
    (repo.root / "note.txt").write_text("x", "utf-8")
    commit_all(repo.root, "a note")

    assert env_branches(repo.root, load_repo(repo.root).config) == {
        "prod": "main",
        "uat": "env/uat",
    }


# ---------------------------------------------------------------- a branch of one's own


def _exported(root: Path, subject: str) -> None:
    """A commit as the tool writes one after an export went onto the branch."""
    git(root, "commit", "-q", "--allow-empty", "-m", subject)


def _with_uat_and_a_branch_of_it(tmp_path: Path) -> Path:
    """main refreshed from prod, env/uat from uat, and ``work/next`` started from env/uat."""
    root = fresh_repo(tmp_path).root
    _exported(root, "refresh(prod): prod.xml")
    git(root, "switch", "-q", "-c", "env/uat")
    _exported(root, "refresh(uat): uat.xml")
    git(root, "switch", "-q", "-c", "work/next")
    _exported(root, "fix: update job P77_A in P77_CHAIN")
    return root


def test_a_branch_of_one_s_own_holds_the_environment_of_the_branch_it_started_from(
    tmp_path: Path,
) -> None:
    root = _with_uat_and_a_branch_of_it(tmp_path)
    config = load_repo(root).config
    git(root, "branch", "work/prod-fix", "main")

    assert held_env(root, config, "work/next") == "uat"
    assert held_env(root, config, "work/prod-fix") == "prod"
    assert held_env(root, config, git(root, "rev-parse", "work/next")) == "uat"  # any commit
    # the branches of the environments are told by their names, as before
    assert held_env(root, config, "env/uat") == "uat"
    assert held_env(root, config, "main") == "prod"
    assert env_of_ref(root, config, "work/next") is None  # the name alone says nothing


def test_the_last_export_put_onto_the_branch_says_what_it_holds(tmp_path: Path) -> None:
    root = _with_uat_and_a_branch_of_it(tmp_path)
    config = load_repo(root).config
    git(root, "branch", "env/bench", "main")
    git(root, "switch", "-q", "-c", "work/prod-fix", "main")

    _exported(root, "import(uat): delivery.xml")
    assert held_env(root, config, "work/prod-fix") == "uat"
    _exported(root, "import(bench): bench.xml")
    _exported(root, "import(nowhere): not an environment of the repository")
    assert held_env(root, config, "work/prod-fix") == "bench"


def test_the_working_tree_and_head_of_a_branch_of_one_s_own(tmp_path: Path) -> None:
    root = _with_uat_and_a_branch_of_it(tmp_path)
    config = load_repo(root).config

    assert held_env(root, config, "WORKTREE") == "uat"
    assert held_env(root, config, "HEAD") == "uat"
    git(root, "switch", "-q", "--detach", "main")
    assert held_env(root, config, "HEAD") == "prod"  # a commit of the trunk's history


def test_only_the_branch_s_own_line_of_exports_counts(tmp_path: Path) -> None:
    root = _with_uat_and_a_branch_of_it(tmp_path)
    config = load_repo(root).config
    git(root, "switch", "-q", "-c", "work/prod-fix", "main")
    _exported(root, "docs: a note")

    git(root, "merge", "-q", "--no-ff", "-m", "merge uat's for a look", "env/uat")
    git(root, "commit", "-q", "--allow-empty", "-m", "docs: quoting\n\nimport(bench): b.xml")

    assert held_env(root, config, "work/prod-fix") == "prod"


def test_a_ref_without_an_export_in_its_history_holds_no_environment(tmp_path: Path) -> None:
    repo = fresh_repo(tmp_path)  # one commit, not written by a refresh
    git(repo.root, "branch", "release/26.1")

    assert held_env(repo.root, repo.config, "release/26.1") is None
    assert held_env(repo.root, repo.config, "no-such-ref") is None
    git(repo.root, "switch", "-q", "release/26.1")
    assert held_env(repo.root, repo.config, "WORKTREE") is None


def test_without_a_branch_for_the_environment_a_subject_that_names_it_says_nothing(
    tmp_path: Path,
) -> None:
    repo = fresh_repo(tmp_path)  # every environment in one tree: no env/uat
    git(repo.root, "switch", "-q", "-c", "release/26.1")
    _exported(repo.root, "import(uat): the export of this week")  # a message of one's own

    assert held_env(repo.root, repo.config, "release/26.1") is None
