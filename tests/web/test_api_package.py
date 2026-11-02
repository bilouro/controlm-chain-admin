"""Commit selection in the comparison, and the Control-M import package, through the API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.core.refactor import apply, set_attributes
from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.gitrepo import chain_git_repo, commit_all, git

C, ING = "P77_CHAIN", "P77_INGEST_DAILY"


@pytest.fixture
def shas(tmp_path: Path) -> dict[str, str]:
    repo = chain_git_repo(tmp_path)
    git(repo.root, "branch", "develop")
    git(repo.root, "checkout", "-q", "-b", "feature/x")
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded"}))
    chain = commit_all(repo.root, "feat: describe P77_C")
    apply(repo, set_attributes(repo, f"{ING}/P77_INGEST_LOAD", {"DESCRIPTION": "Ingest"}))
    ingest = commit_all(repo.root, "feat: describe the load")
    apply(repo, set_attributes(repo, f"{C}/P77_C", {"DESCRIPTION": "Loaded twice"}))
    again = commit_all(repo.root, "feat: describe P77_C again")
    return {"root": str(repo.root), "chain": chain, "ingest": ingest, "again": again}


@pytest.fixture
def client(shas: dict[str, str]) -> Iterator[TestClient]:
    settings = Settings(
        repo=Path(shas["root"]), open_browser=False, token="t", allowed_hosts=["testserver"]
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


BASE = {"base": "develop", "head": "feature/x"}


def test_compare_only_the_selected_commits(client: TestClient, shas: dict[str, str]) -> None:
    body = client.get("/api/compare", params={**BASE, "commits": shas["ingest"]}).json()

    assert body["selected"] == [shas["ingest"]]
    assert [j["node"] for j in body["jobs"]] == [f"{ING}/P77_INGEST_LOAD"]
    assert body["jobs"][0]["commits"] == [shas["ingest"]]
    assert len(body["commits"]) == 3 and body["commits"][0]["merge"] is False


def test_an_empty_selection_and_every_commit(client: TestClient) -> None:
    empty = client.get("/api/compare", params={**BASE, "commits": ""}).json()
    every = client.get("/api/compare", params=BASE).json()

    assert empty["selected"] == [] and empty["jobs"] == []
    assert every["selected"] is None and len(every["jobs"]) == 2


def test_a_selection_that_needs_a_left_out_commit_is_a_conflict(
    client: TestClient, shas: dict[str, str]
) -> None:
    response = client.get("/api/compare", params={**BASE, "commits": shas["again"]})

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "SelectionConflict"
    assert body["detail"]["missing"] == [shas["chain"]]
    assert body["detail"]["commit"] == shas["again"]


def test_package_preview_lists_the_folders_and_the_file(client: TestClient) -> None:
    body = client.get("/api/package", params={**BASE, "env": "uat"}).json()

    assert {f["name"] for f in body["folders"]} == {C, ING}
    assert body["filename"].startswith("deploy_uat_feature-x_") and body["size"] > 0
    assert body["env"] == "uat" and "xml" not in body


def test_package_xml_is_a_download(client: TestClient, shas: dict[str, str]) -> None:
    params = {**BASE, "env": "uat", "commits": shas["ingest"]}
    preview = client.get("/api/package", params=params).json()

    response = client.get("/api/package/xml", params=params)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{preview["filename"]}"'
    )
    assert response.content.startswith(b"<?xml") and len(response.content) == preview["size"]
    assert b"UP77_INGEST_DAILY" in response.content and b"UP77_CHAIN" not in response.content


def test_package_errors(client: TestClient) -> None:
    nothing = client.get("/api/package/xml", params={**BASE, "commits": "", "env": "uat"})
    unknown = client.get("/api/package", params={**BASE, "env": "staging"})
    empty = client.get("/api/package", params={**BASE, "commits": "", "env": "uat"})

    assert nothing.status_code == 422 and nothing.json()["error"] == "NothingToPackage"
    assert unknown.status_code == 404 and unknown.json()["error"] == "UnknownEnvironment"
    assert empty.status_code == 200 and empty.json()["folders"] == []
