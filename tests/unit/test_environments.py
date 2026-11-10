"""One branch per environment: which branch holds an environment, which environment a ref is."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.core.environments import (
    branch_of_env,
    env_branches,
    env_of_ref,
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
