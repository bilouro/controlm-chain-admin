"""Releases through the API: where edits may go, start, switch, stash, install, close, push."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.core.refactor import apply, set_attributes
from controlm_chain_admin.core.repo import load_repo
from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.gitrepo import chain_git_repo, commit_all, git, plain_git_identity

C = "P77_CHAIN"
TOKEN = {"X-Ctmchain-Token": "t"}


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plain_git_identity(monkeypatch, tmp_path)
    return chain_git_repo(tmp_path).root


@pytest.fixture
def client(root: Path) -> Iterator[TestClient]:
    settings = Settings(repo=root, open_browser=False, token="t", allowed_hosts=["testserver"])
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def describe(root: Path, text: str) -> None:
    repo = load_repo(root)
    apply(repo, set_attributes(repo, f"{C}/P77_E", {"DESCRIPTION": text}))


def post(client: TestClient, path: str, body: dict[str, Any] | None = None) -> Any:
    response = client.post(f"/api/workspace/{path}", json=body or {}, headers=TOKEN)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_trunk_cannot_be_edited(client: TestClient) -> None:
    state = client.get("/api/workspace").json()

    assert state["branch"] == "main" and state["editable"] is False
    assert state["reason"].startswith("main is protected") and state["releases"] == []
    params = {"node": f"{C}/P77_E", "changes": {"DESCRIPTION": "x"}}
    preview = client.post(
        "/api/changes/preview", json={"op": "set-attributes", "params": params}, headers=TOKEN
    ).json()
    refused = client.post(
        "/api/changes/apply",
        json={"op": "set-attributes", "params": params, "fingerprint": preview["fingerprint"]},
        headers=TOKEN,
    )
    assert refused.status_code == 409 and refused.json()["error"] == "ProtectedBranch"


def test_the_branches_of_the_other_environments_are_listed_and_switched_to(
    client: TestClient, root: Path
) -> None:
    assert client.get("/api/workspace").json()["env_branches"] == []
    git(root, "branch", "env/uat")

    state = client.get("/api/workspace").json()
    assert state["env_branches"] == [
        {"env": "uat", "branch": "env/uat", "local": True, "remote": False}
    ]

    body = post(client, "switch", {"branch": "env/uat"})
    assert body["message"] == "Switched to env/uat"
    assert body["workspace"]["branch"] == "env/uat" and body["workspace"]["editable"] is True


def test_a_branch_from_the_checked_out_branch_is_started_and_listed(
    client: TestClient, root: Path
) -> None:
    git(root, "switch", "-q", "-c", "env/uat")
    assert client.get("/api/workspace").json()["branches"] == []
    assert client.post("/api/workspace/branch", json={"name": "work/next"}).status_code == 401

    body = post(client, "branch", {"name": "work/next"})

    assert body["message"] == "Started work/next from env/uat"
    state = body["workspace"]
    assert (state["branch"], state["editable"]) == ("work/next", True)
    assert state["branches"] == [{"branch": "work/next", "local": True, "remote": False}]
    refused = client.post("/api/workspace/branch", json={"name": "env/other"}, headers=TOKEN)
    assert refused.status_code == 422 and refused.json()["error"] == "GitError"
    assert "env/ holds the branches of the environments" in refused.json()["message"]


def test_start_a_release_then_edit_it(client: TestClient) -> None:
    assert client.post("/api/workspace/release", json={"name": "march"}).status_code == 401

    body = post(client, "release", {"name": "march"})

    assert body["message"] == "Started release/march from main"
    assert body["workspace"]["branch"] == "release/march" and body["workspace"]["editable"]
    params = {"node": f"{C}/P77_E", "changes": {"DESCRIPTION": "x"}}
    preview = client.post(
        "/api/changes/preview", json={"op": "set-attributes", "params": params}, headers=TOKEN
    ).json()
    applied = client.post(
        "/api/changes/apply",
        json={"op": "set-attributes", "params": params, "fingerprint": preview["fingerprint"]},
        headers=TOKEN,
    )
    assert applied.status_code == 200
    assert client.get("/api/workspace").json()["changes"] == 1


def test_switch_stash_pop_and_discard(client: TestClient, root: Path) -> None:
    post(client, "release", {"name": "march"})
    describe(root, "draft")

    blocked = client.post("/api/workspace/switch", json={"branch": "main"}, headers=TOKEN)
    assert blocked.status_code == 409 and blocked.json()["error"] == "UncommittedChanges"
    assert blocked.json()["detail"] == {"changes": 1}
    body = post(client, "switch", {"branch": "main", "stash": True})
    assert body["message"].endswith("Switched to main")
    [saved] = body["workspace"]["stashes"]
    assert saved == {
        "ref": "stash@{0}",
        "branch": "release/march",
        "message": "fix: update job P77_E in P77_CHAIN",
    }

    post(client, "switch", {"branch": "release/march"})
    body = post(client, "pop", {"ref": "stash@{0}"})
    assert body["message"].startswith("Restored stash@{0} on release/march")
    assert body["workspace"]["changes"] == 1

    pending = client.get("/api/git/pending").json()
    body = post(client, "discard", {"fingerprint": pending["fingerprint"]})
    assert body["message"] == "Discarded 1 chain file"
    assert body["workspace"]["changes"] == 0

    describe(root, "again")
    post(client, "stash")
    assert len(client.get("/api/workspace").json()["stashes"]) == 1


def test_install_update_and_close(client: TestClient, root: Path) -> None:
    post(client, "release", {"name": "march"})
    describe(root, "x")
    sha = commit_all(root, "fix: describe P77_E")

    body = post(client, "installed", {"env": "uat", "release": "march", "sha": sha})

    assert body["message"] == f"Tagged uat/march-1 on {sha[:7]}"
    [march] = body["workspace"]["releases"]
    assert march["installed"] == [{"env": "uat", "tag": "uat/march-1", "sha": sha, "behind": 0}]
    again = client.post(
        "/api/workspace/installed", json={"env": "uat", "release": "march"}, headers=TOKEN
    )
    assert again.status_code == 422 and "already has" in again.json()["message"]
    update = client.post("/api/workspace/update", headers=TOKEN)
    assert update.status_code == 422 and update.json()["error"] == "GitError"

    post(client, "installed", {"env": "prod"})
    body = post(client, "close")

    assert body["message"].startswith("Closed release/march: merged into main")
    assert body["workspace"]["branch"] == "main" and body["workspace"]["releases"] == []


def test_a_conflict_is_reported_with_the_files(client: TestClient, root: Path) -> None:
    post(client, "release", {"name": "march"})
    describe(root, "release")
    commit_all(root, "fix: release")
    git(root, "switch", "-q", "main")
    describe(root, "hotfix")
    commit_all(root, "fix: hotfix")
    git(root, "switch", "-q", "release/march")

    response = client.post("/api/workspace/update", headers=TOKEN)

    assert response.status_code == 409 and response.json()["error"] == "MergeConflict"
    assert response.json()["detail"] == {"paths": [f"folders/{C}/jobs/P77_E.json"]}


def test_push_and_pull(client: TestClient, root: Path, tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(root, "remote", "add", "origin", str(origin))
    post(client, "release", {"name": "march"})

    assert post(client, "push")["message"] == "Pushed release/march to origin"
    body = post(client, "pull")

    assert body["message"] == "Fetched origin. release/march: up to date"
    assert body["workspace"]["upstream"] == "origin/release/march"
