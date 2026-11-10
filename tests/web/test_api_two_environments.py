"""Two environments' branches through the API: the real differences, the items taken into the
checked-out one, the import file of chosen items for the target."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.fourenvs import (
    CHAIN,
    USERS,
    WEEKLY,
    administrator,
    four_branches,
    two_users_in,
    uat_ahead,
    with_map,
)
from tests.support.gitrepo import git, plain_git_identity

BENCH, UAT = "env/bench", "env/uat"


@pytest.fixture
def api(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    plain_git_identity(monkeypatch, tmp_path)
    repo = four_branches(tmp_path, change=getattr(request, "param", uat_ahead))
    with_map(repo)
    git(repo.root, "switch", "-q", BENCH)
    settings = Settings(repo=repo.root, open_browser=False, token="t", allowed_hosts=["testserver"])
    with TestClient(create_app(settings)) as client:
        yield client


def test_compare_says_which_environments_and_what_was_explained(api: TestClient) -> None:
    body = api.get("/api/compare", params={"base": BENCH, "head": UAT}).json()

    assert body["environments"] == ["bench", "uat"]
    assert body["translation"]["target"] == "bench" and body["translation"]["source"] == "uat"
    assert body["translation"]["values"] > 0 and body["translation"]["warnings"] == []
    assert body["summary"]["folders"]["added"] == 1 and body["summary"]["jobs"]["added"] == 3
    assert body["commits"] == [] and body["merge_base"] is None
    modified = [j for j in body["jobs"] if j["change"] == "modified"]
    assert [a["name"] for j in modified for a in j["attributes"]] == ["CMDLINE"]


def test_compare_raw_is_the_two_branches_as_stored(api: TestClient) -> None:
    body = api.get("/api/compare", params={"base": BENCH, "head": UAT, "raw": True}).json()

    assert body["environments"] == ["bench", "uat"] and body["translation"] is None
    changed = {a["name"] for j in body["jobs"] for a in j["attributes"]}
    assert {"RUN_AS", "NODEID"} <= changed


def test_one_environment_has_no_translation(api: TestClient) -> None:
    body = api.get("/api/compare", params={"base": BENCH, "head": "WORKTREE"}).json()

    assert body["environments"] is None and body["translation"] is None


def test_the_package_of_chosen_items_needs_no_environment(api: TestClient) -> None:
    params = [("base", BENCH), ("head", UAT), ("take", f"folder:{WEEKLY}"),
              ("take", f"job:{CHAIN}/P77_NEW")]  # fmt: skip

    body = api.get("/api/package", params=params).json()

    assert (body["env"], body["source"]) == ("bench", "uat")
    assert body["taken"] == [f"folder:{WEEKLY}", f"job:{CHAIN}/P77_NEW"]
    assert [f["name"] for f in body["folders"]] == [CHAIN, WEEKLY]

    xml = api.get("/api/package/xml", params=params)
    assert xml.status_code == 200
    assert b'FOLDER_NAME="BP77_WEEKLY_DAILY"' in xml.content and b"UP77" not in xml.content
    assert USERS["uat"].encode() not in xml.content
    assert "deploy_bench_env-uat_2-items_" in xml.headers["content-disposition"]


def test_the_package_for_another_environment_than_the_base_is_refused(api: TestClient) -> None:
    response = api.get("/api/package", params={"base": BENCH, "head": UAT, "env": "prod"})

    assert response.status_code == 422 and "env/bench holds bench" in response.json()["message"]


def test_a_package_of_one_environment_still_asks_which(api: TestClient) -> None:
    response = api.get("/api/package", params={"base": BENCH, "head": "WORKTREE"})

    assert response.status_code == 422 and "which environment" in response.json()["message"]


@pytest.mark.parametrize("api", [two_users_in("bench")], indirect=True)
def test_a_preferred_entry_settles_a_value_the_map_gives_two_answers_for(api: TestClient) -> None:
    params: dict[str, str | list[str]] = {
        "base": BENCH, "head": UAT, "take": [f"job:{CHAIN}/P77_NEW"],
    }  # fmt: skip

    unsure = api.get("/api/package", params=params).json()
    assert [w for w in unsure["warnings"] if "kept as it is" in w and "run_as.2" in w]
    assert api.get("/api/compare", params=params).json()["translation"]["warnings"]

    settled = {**params, "prefer": ["run_as.2"]}
    assert not [
        w for w in api.get("/api/package", params=settled).json()["warnings"] if "kept" in w
    ]
    xml = api.get("/api/package/xml", params=settled).content
    assert xml.count(f'RUN_AS="{administrator("bench")}"'.encode()) == 2
    assert api.get("/api/compare", params=settled).json()["translation"]["warnings"] == []
    unknown = api.get("/api/compare", params={**params, "prefer": ["run_as.9"]})
    assert unknown.status_code == 400 and "run_as.9" in unknown.json()["message"]
