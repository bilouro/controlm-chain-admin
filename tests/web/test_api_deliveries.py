"""Deliveries kept for later through the API: kept, listed, packaged for a target, removed."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.fourenvs import CHAIN, WEEKLY, four_branches, uat_ahead, with_map
from tests.support.gitrepo import git, plain_git_identity

TOKEN = {"X-Ctmchain-Token": "t"}
BENCH, UAT = "env/bench", "env/uat"
NEW = f"job:{CHAIN}/P77_NEW"


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    plain_git_identity(monkeypatch, tmp_path)
    repo = four_branches(tmp_path, change=uat_ahead)
    with_map(repo)
    settings = Settings(repo=repo.root, open_browser=False, token="t",
                        allowed_hosts=["testserver"])  # fmt: skip
    with TestClient(create_app(settings)) as client:
        yield client


def _keep(api: TestClient, name: str, items: list[str], **more: object) -> object:
    body = {"name": name, "head": UAT, "items": items, **more}
    return api.post("/api/deliveries", json=body, headers=TOKEN)


def test_nothing_is_kept_at_first(api: TestClient) -> None:
    assert api.get("/api/deliveries").json() == {"deliveries": []}


def test_a_delivery_is_kept_listed_and_removed(api: TestClient) -> None:
    kept = _keep(api, "new job", [NEW], base=BENCH, note="for Friday")
    (row,) = api.get("/api/deliveries").json()["deliveries"]
    gone = api.delete("/api/deliveries/new%20job", headers=TOKEN)

    assert kept.status_code == 200  # type: ignore[attr-defined]
    assert (row["name"], row["head"], row["base"], row["items"]) == ("new job", UAT, BENCH, [NEW])
    assert (row["count"], row["environment"], row["moved"], row["note"]) == (
        1, "uat", False, "for Friday",
    )  # fmt: skip
    assert gone.status_code == 200 and gone.json() == {"deliveries": []}


def test_keeping_and_removing_need_the_token_and_a_good_request(api: TestClient) -> None:
    refused = api.post("/api/deliveries", json={"name": "x", "head": UAT, "items": [NEW]})
    _keep(api, "one", [NEW])
    twice = _keep(api, "one", [NEW])
    unknown = api.delete("/api/deliveries/nothing", headers=TOKEN)

    assert refused.status_code == 401
    assert twice.status_code == 422 and "already" in twice.json()["message"]  # type: ignore[attr-defined]
    assert unknown.status_code in (400, 404, 422) and "no delivery called" in (
        unknown.json()["message"]
    )


def test_one_file_for_a_target_from_the_deliveries_chosen(api: TestClient) -> None:
    _keep(api, "new job", [NEW], base=BENCH)
    _keep(api, "weekly", [f"folder:{WEEKLY}"], base=BENCH)
    chosen = {"target": BENCH, "name": ["new job", "weekly"]}

    preview = api.get("/api/deliveries/package", params=chosen)
    xml = api.get("/api/deliveries/package/xml", params=chosen)
    none = api.get("/api/deliveries/package", params={"target": BENCH})

    body = preview.json()
    assert preview.status_code == 200 and body["env"] == "bench"
    assert [f["name"] for f in body["folders"]] == [CHAIN, WEEKLY]
    assert body["filename"].startswith("deploy_bench_new-job+weekly_")
    assert xml.status_code == 200 and b'JOBNAME="BP77_NEW"' in xml.content
    assert body["filename"] in xml.headers["content-disposition"]
    assert none.status_code == 422
    assert git(Path(api.app.state.settings.repo), "status", "--porcelain") == ""  # type: ignore[attr-defined]
