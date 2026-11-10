"""The full export of one environment through the API: what it changes on the branch of the
environment, then the branch overwritten with it. The export travels byte for byte."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.core.ops import export_xml
from controlm_chain_admin.core.repo import load_repo
from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.fourenvs import CHAIN, export_of, four_branches, own, uat_ahead
from tests.support.gitrepo import git, plain_git_identity

XML = {"X-Ctmchain-Token": "t", "Content-Type": "application/xml"}
NEWER = uat_ahead("uat", export_of("uat"))


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plain_git_identity(monkeypatch, tmp_path)
    return four_branches(tmp_path).root


@pytest.fixture
def api(root: Path) -> Iterator[TestClient]:
    settings = Settings(repo=root, open_browser=False, token="t", allowed_hosts=["testserver"])
    with TestClient(create_app(settings)) as client:
        yield client


def _sha(root: Path, ref: str) -> str:
    return str(git(root, "rev-parse", ref)).strip()


def test_the_preview_says_the_environment_and_what_differs_and_writes_nothing(
    api: TestClient, root: Path
) -> None:
    before = _sha(root, "env/uat")

    response = api.post(
        "/api/refresh/preview", content=NEWER, params={"source": "uat.xml"}, headers=XML
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["env"], body["branch"], body["source"]) == ("uat", "env/uat", "uat.xml")
    assert (body["applied"], body["unchanged"], body["new_branch"]) == (False, False, False)
    assert body["commit"] is None and body["files_changed"] == 12
    assert body["imported"]["folders"] == 3 and body["imported"]["jobs"] == 12
    assert "carry the letter U of uat" in body["evidence"][0]
    comparison = body["comparison"]
    assert comparison["summary"]["jobs"]["added"] == 3
    assert (comparison["base"]["name"], comparison["head"]["kind"]) == ("env/uat", "export")
    modified = [j for j in comparison["jobs"] if j["change"] == "modified"]
    assert [j["node"] for j in modified] == [f"{CHAIN}/P77_A"]
    assert _sha(root, "env/uat") == before
    assert git(root, "branch", "--show-current").strip() == "main"
    assert git(root, "status", "--porcelain").strip() == ""


def test_the_same_export_is_said_to_change_nothing(api: TestClient) -> None:
    body = api.post("/api/refresh/preview", content=export_of("egma"), headers=XML).json()

    assert (body["env"], body["unchanged"], body["files_changed"]) == ("egma", True, 0)
    assert body["source"] == "export.xml"


def test_the_export_is_not_read_without_the_token(api: TestClient) -> None:
    headers = {"Content-Type": "application/xml"}

    assert api.post("/api/refresh/preview", content=NEWER, headers=headers).status_code == 401
    assert api.post("/api/refresh/apply", content=NEWER, headers=headers).status_code == 401


def test_what_is_not_an_export_is_refused(api: TestClient) -> None:
    response = api.post("/api/refresh/preview", content=b"not an export", headers=XML)

    assert response.status_code == 422 and response.json()["error"] == "XmlFormatError"


def test_the_environment_given_must_be_the_one_the_export_shows(api: TestClient) -> None:
    response = api.post(
        "/api/refresh/preview", content=NEWER, params={"env": "bench"}, headers=XML
    )

    assert response.status_code == 400 and "uat" in response.json()["message"]


def test_apply_checks_the_branch_out_overwrites_it_and_commits(
    api: TestClient, root: Path
) -> None:
    before = _sha(root, "env/uat")

    response = api.post(
        "/api/refresh/apply", content=NEWER, params={"source": "uat.xml"}, headers=XML
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["applied"], body["env"], body["branch"]) == (True, "uat", "env/uat")
    assert body["commit"] == _sha(root, "env/uat") != before
    assert api.get("/api/git").json()["current"] == "env/uat"
    assert export_xml(load_repo(root), "uat") == own(NEWER)
    again = api.post("/api/refresh/apply", content=NEWER, headers=XML).json()
    assert (again["unchanged"], again["commit"]) == (True, None)
    assert _sha(root, "env/uat") == body["commit"]


def test_apply_can_leave_the_result_uncommitted(api: TestClient, root: Path) -> None:
    before = _sha(root, "env/uat")

    body = api.post(
        "/api/refresh/apply", content=NEWER, params={"commit": False}, headers=XML
    ).json()

    assert (body["applied"], body["commit"]) == (True, None)
    assert _sha(root, "env/uat") == before
    assert git(root, "status", "--porcelain").strip() != ""


def test_apply_is_refused_over_uncommitted_chain_changes(api: TestClient, root: Path) -> None:
    (root / "chain.json").write_text((root / "chain.json").read_text() + "\n", encoding="utf-8")

    response = api.post("/api/refresh/apply", content=NEWER, headers=XML)

    assert response.status_code == 409 and response.json()["error"] == "UncommittedChanges"
    assert git(root, "branch", "--show-current").strip() == "main"
