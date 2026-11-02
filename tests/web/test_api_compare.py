"""Git refs and branch comparison through the API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.core.refactor import apply, rename_job, set_attributes
from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.gitrepo import chain_git_repo, commit_all, git

C = "P77_CHAIN"


@pytest.fixture
def git_client(tmp_path: Path) -> Iterator[TestClient]:
    repo = chain_git_repo(tmp_path)
    git(repo.root, "branch", "develop")
    git(repo.root, "checkout", "-q", "-b", "feature/x")
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded"}))
    apply(repo, rename_job(repo, f"{C}/P77_D", "P77_DELTA"))
    commit_all(repo.root, "feat: demo")
    settings = Settings(repo=repo.root, open_browser=False, token="t", allowed_hosts=["testserver"])
    with TestClient(create_app(settings)) as client:
        yield client


def test_git_state_lists_the_refs(git_client: TestClient) -> None:
    body = git_client.get("/api/git").json()

    assert body["current"] == "feature/x" and body["dirty"] is False
    assert {r["name"] for r in body["refs"]} >= {"main", "develop", "feature/x"}


def test_compare_two_branches(git_client: TestClient) -> None:
    response = git_client.get("/api/compare", params={"base": "develop", "head": "feature/x"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["jobs"] == {"added": 0, "removed": 0, "modified": 1, "renamed": 1, "moved": 0}
    renamed = next(j for j in body["jobs"] if j["change"] == "renamed")
    assert renamed["previous"] == f"{C}/P77_D" and renamed["node"] == f"{C}/P77_DELTA"
    modified = next(j for j in body["jobs"] if j["change"] == "modified")
    assert modified["attributes"] == [{"name": "DESCRIPTION", "before": None, "after": "Loaded"}]
    assert [c["subject"] for c in body["commits"]] == ["feat: demo"]
    assert body["base"]["name"] == "develop" and body["head"]["name"] == "feature/x"


def test_compare_with_the_working_tree_and_errors(git_client: TestClient) -> None:
    same = git_client.get("/api/compare", params={"base": "feature/x", "head": "WORKTREE"}).json()
    assert same["jobs"] == [] and same["head"]["kind"] == "worktree"

    bad = git_client.get("/api/compare", params={"base": "develop", "head": "nope"})
    assert bad.status_code == 422 and bad.json()["error"] == "GitError"


def test_git_endpoints_on_a_directory_that_is_not_a_git_repository(client: TestClient) -> None:
    response = client.get("/api/git")

    assert response.status_code == 422 and response.json()["error"] == "GitError"
