"""Taking changes of another branch through /api/changes, and what the comparison shows."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.core.refactor import apply, set_attributes, set_exception
from controlm_chain_admin.core.repo import load_repo
from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.gitrepo import chain_git_repo, commit_all, git, plain_git_identity

C = "P77_CHAIN"
TOKEN = {"X-Ctmchain-Token": "t"}
ITEM = f"attr:{C}/P77_A@TIMEFROM"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plain_git_identity(monkeypatch, tmp_path)
    repo = chain_git_repo(tmp_path)
    git(repo.root, "switch", "-q", "-c", "release/other")
    apply(repo, set_attributes(repo, f"{C}/P77_A", {"TIMEFROM": "0800"}))
    apply(repo, set_exception(repo, "prod", f"{C}/P77_E", {"TASKTYPE": "Dummy"}))
    commit_all(repo.root, "feat: other")
    git(repo.root, "switch", "-q", "-c", "release/mine", "main")
    return repo.root


@pytest.fixture
def client(root: Path) -> Iterator[TestClient]:
    settings = Settings(repo=root, open_browser=False, token="t", allowed_hosts=["testserver"])
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _request(**params: object) -> dict[str, object]:
    return {"op": "take", "params": {"base": "release/mine", "head": "release/other", **params}}


def test_an_item_is_previewed_and_applied(client: TestClient) -> None:
    request = _request(items=[ITEM])

    preview = client.post("/api/changes/preview", json=request, headers=TOKEN).json()
    applied = client.post(
        "/api/changes/apply", json={**request, "fingerprint": preview["fingerprint"]}, headers=TOKEN
    )

    assert preview["summary"] == f"take 1 change from release/other: {ITEM}"
    assert applied.status_code == 200


def test_a_conflict_is_409_with_each_value(client: TestClient, root: Path) -> None:
    mine = load_repo(root)
    apply(mine, set_attributes(mine, f"{C}/P77_A", {"TIMEFROM": "0900"}))

    response = client.post("/api/changes/preview", json=_request(items=[ITEM]), headers=TOKEN)

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "TakeConflict"
    assert body["detail"]["conflicts"] == [
        {"item": ITEM, "mine": "0900", "before": None, "theirs": "0800"}
    ]
    forced = _request(items=[ITEM], theirs=[ITEM])
    assert client.post("/api/changes/preview", json=forced, headers=TOKEN).status_code == 200


def test_the_comparison_shows_exceptions(client: TestClient) -> None:
    body = client.get("/api/compare", params={"base": "release/mine", "head": "release/other"})

    assert body.json()["exceptions"] == [
        {
            "env": "prod",
            "node": f"{C}/P77_E",
            "before": None,
            "after": {"set": {"TASKTYPE": "Dummy"}, "variables": {}, "elements": {}},
        }
    ]
