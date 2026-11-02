"""Pending changes and the commit through the API (the commit needs the session token)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.core.refactor import apply, set_attributes
from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.gitrepo import chain_git_repo, git, plain_git_identity

C = "P77_CHAIN"
TOKEN = {"X-Ctmchain-Token": "t"}


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plain_git_identity(monkeypatch, tmp_path)
    repo = chain_git_repo(tmp_path)
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": "x"}))
    return repo.root


@pytest.fixture
def client(root: Path) -> Iterator[TestClient]:
    settings = Settings(repo=root, open_browser=False, token="t", allowed_hosts=["testserver"])
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_pending_changes_with_a_suggested_message(client: TestClient) -> None:
    assert client.get("/api/git").json()["changes"] == 1

    body = client.get("/api/git/pending").json()

    assert body["files"] == [f"folders/{C}/jobs/P77_E.json"]
    assert body["message"].startswith("fix: update job P77_E in P77_CHAIN\n\n- modified job")
    assert body["branch"] == "main" and body["protected"] is True and body["fingerprint"]
    assert body["summary"]["jobs"]["modified"] == 1


def test_commit_needs_the_token_then_commits(client: TestClient, root: Path) -> None:
    state = client.get("/api/git/pending").json()
    request = {"message": "fix: describe P77_E", "fingerprint": state["fingerprint"]}

    assert client.post("/api/git/commit", json=request).status_code == 401
    response = client.post("/api/git/commit", json={**request, "branch": "fix/e"}, headers=TOKEN)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["branch"] == "fix/e" and body["subject"] == "fix: describe P77_E"
    assert git(root, "log", "-1", "--format=%s") == "fix: describe P77_E"
    assert client.get("/api/git").json()["changes"] == 0


def test_commit_errors(client: TestClient, root: Path) -> None:
    stale = client.post(
        "/api/git/commit", json={"message": "fix: x", "fingerprint": "old"}, headers=TOKEN
    )
    state = client.get("/api/git/pending").json()
    git(root, "stash", "-q")
    nothing = client.post(
        "/api/git/commit",
        json={"message": "fix: x", "fingerprint": state["fingerprint"]},
        headers=TOKEN,
    )

    assert stale.status_code == 409 and stale.json()["error"] == "ChangeConflict"
    assert nothing.status_code == 422 and nothing.json()["error"] == "NothingToCommit"
