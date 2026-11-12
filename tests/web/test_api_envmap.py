"""The map of what varies per environment through the API: shown, derived from the branches,
suggested, and edited one entry at a time. It lives on its own branch: no checkout changes."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.fourenvs import GEIENV, HOSTS, SUBJECT, USERS, administrator, four_branches
from tests.support.gitrepo import git, plain_git_identity

TOKEN = {"X-Ctmchain-Token": "t"}
DERIVED = ["nodeid.1", "run_as.1", "datacenter.1"]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plain_git_identity(monkeypatch, tmp_path)
    return four_branches(tmp_path).root


@pytest.fixture
def api(root: Path) -> Iterator[TestClient]:
    settings = Settings(repo=root, open_browser=False, token="t", allowed_hosts=["testserver"])
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def derived(api: TestClient) -> TestClient:
    assert api.post("/api/envmap/derive", json={}, headers=TOKEN).status_code == 200
    return api


def _names(api: TestClient) -> list[str]:
    return [entry["name"] for entry in api.get("/api/envmap").json()["entries"]]


def test_an_empty_map_still_says_its_branch_and_the_letter_and_branch_of_each_environment(
    api: TestClient,
) -> None:
    body = api.get("/api/envmap").json()

    assert (body["branch"], body["entries"]) == ("map", [])
    assert body["letters"] == {"prod": "P", "uat": "U", "egma": "E", "bench": "B"}
    assert body["branches"]["prod"] == "main" and body["branches"]["uat"] == "env/uat"


def test_derive_shows_what_the_branches_say_and_writes_nothing(api: TestClient) -> None:
    body = api.get("/api/envmap/derive").json()

    assert [entry["name"] for entry in body["entries"]] == DERIVED
    assert body["entries"][1]["values"] == USERS and body["entries"][1]["nodes"] == 11
    assert body["environments"] == ["prod", "uat", "egma", "bench"]
    assert (body["applied"], body["known"], body["left_out"]) == (False, [], [])
    assert _names(api) == []


def test_derive_looks_at_the_keys_and_the_texts_asked_for(api: TestClient) -> None:
    params = {"key": GEIENV, "text": SUBJECT, "min_nodes": 1}

    body = api.get("/api/envmap/derive", params=params).json()

    by_key = {entry["key"]: entry for entry in body["entries"]}
    assert by_key[GEIENV]["values"]["bench"] == "b" and not by_key[GEIENV].get("inline")
    assert by_key[SUBJECT]["inline"] is True and by_key[SUBJECT]["values"]["uat"] == "UAT"


def test_values_too_few_nodes_show_are_left_out_and_said(api: TestClient) -> None:
    body = api.get("/api/envmap/derive", params={"key": GEIENV}).json()

    assert GEIENV not in {entry["key"] for entry in body["entries"]}
    assert [(item["key"], item["nodes"]) for item in body["left_out"]] == [(GEIENV, 1)]


def test_applying_the_derived_entries_needs_the_token_and_touches_no_checkout(
    api: TestClient, root: Path
) -> None:
    assert api.post("/api/envmap/derive", json={}).status_code == 401
    assert _names(api) == []

    body = api.post("/api/envmap/derive", json={"min_nodes": 2}, headers=TOKEN).json()

    assert body["applied"] is True and [e["name"] for e in body["entries"]] == DERIVED
    assert _names(api) == DERIVED
    assert git(root, "status", "--porcelain").strip() == ""
    assert git(root, "branch", "--show-current").strip() == "main"
    again = api.post("/api/envmap/derive", json={}, headers=TOKEN).json()
    assert (again["applied"], again["entries"]) == (False, [])
    assert [item["name"] for item in again["known"]] == DERIVED


def test_a_key_that_cannot_be_read_is_refused(api: TestClient) -> None:
    response = api.get("/api/envmap/derive", params={"key": "[bad"})

    assert response.status_code == 422
    assert "invalid attribute spec '[bad'" in response.json()["message"]


def test_suggest_lists_what_else_varies_a_page_at_a_time(derived: TestClient) -> None:
    body = derived.get("/api/envmap/suggest").json()

    assert body["total"] == 2  # the machines and the users are in the map now
    by_key = {item["key"]: item for item in body["suggestions"]}
    assert set(by_key) == {SUBJECT, GEIENV}
    assert by_key[SUBJECT]["text"] is True and by_key[SUBJECT]["example"]["bench"] == "BENCH"
    assert by_key[GEIENV]["text"] is False and by_key[GEIENV]["nodes"] == 1
    page = derived.get("/api/envmap/suggest", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and page["suggestions"] == body["suggestions"][1:]


def test_an_entry_is_added_by_hand_with_the_name_given(derived: TestClient) -> None:
    entry = {
        "key": "RUN_AS",
        "values": {"uat": administrator("uat"), "bench": administrator("bench")},
        "name": "administrators",
    }

    assert derived.post("/api/envmap/entries", json=entry).status_code == 401
    response = derived.post("/api/envmap/entries", json=entry, headers=TOKEN)

    assert response.status_code == 200
    added = response.json()["entries"][-1]
    assert (added["name"], added["values"]["bench"]) == ("administrators", administrator("bench"))
    assert _names(derived) == [*DERIVED, "administrators"]


def test_an_entry_without_a_name_gets_the_next_one_of_its_key(derived: TestClient) -> None:
    entry = {"key": "NODEID", "values": {"uat": "srvu-web1", "prod": "srvp-web1"}, "inline": False}

    body = derived.post("/api/envmap/entries", json=entry, headers=TOKEN).json()

    assert body["entries"][-1]["name"] == "nodeid.2"


def test_an_entry_for_an_environment_nobody_knows_is_refused(derived: TestClient) -> None:
    entry = {"key": "RUN_AS", "values": {"mars": "x"}}

    response = derived.post("/api/envmap/entries", json=entry, headers=TOKEN)

    assert response.status_code == 400
    assert "unknown environment 'mars'" in response.json()["message"]
    assert _names(derived) == DERIVED


def test_an_entry_is_renamed_to_say_what_it_is(derived: TestClient) -> None:
    assert derived.patch("/api/envmap/entries/run_as.1", json={"name": "batch"}).status_code == 401

    body = derived.patch(
        "/api/envmap/entries/run_as.1", json={"name": "batch"}, headers=TOKEN
    ).json()

    assert [entry["name"] for entry in body["entries"]] == ["nodeid.1", "batch", "datacenter.1"]
    taken = derived.patch(
        "/api/envmap/entries/batch", json={"name": "nodeid.1"}, headers=TOKEN
    )
    assert taken.status_code == 400 and "'nodeid.1' already" in taken.json()["message"]


def test_an_entry_is_removed(derived: TestClient) -> None:
    assert derived.delete("/api/envmap/entries/nodeid.1").status_code == 401

    body = derived.delete("/api/envmap/entries/nodeid.1", headers=TOKEN).json()

    assert [entry["name"] for entry in body["entries"]] == ["run_as.1", "datacenter.1"]
    assert HOSTS["uat"] not in str(body)
    missing = derived.delete("/api/envmap/entries/nodeid.1", headers=TOKEN)
    assert missing.status_code == 400 and "no entry called 'nodeid.1'" in missing.json()["message"]


def test_how_many_places_follow_each_entry(derived: TestClient) -> None:
    body = derived.get("/api/envmap/followers").json()

    assert body["environments"] == ["prod", "uat", "egma", "bench"]
    assert set(body["followers"]) == set(DERIVED)
    assert all(count > 0 for count in body["followers"].values()) and body["unmapped"] == 0


def test_following_another_entry_is_a_change_previewed_like_any_other(
    derived: TestClient, root: Path
) -> None:
    git(root, "switch", "-q", "env/bench")
    added = derived.post(
        "/api/envmap/entries",
        json={"key": "RUN_AS", "name": "run_as.9",
              "values": {"prod": USERS["prod"], "bench": administrator("bench")}},
        headers=TOKEN,
    )  # fmt: skip
    preview = derived.post(
        "/api/changes/preview",
        json={"op": "follow-entry", "params": {"entry": "run_as.1", "other": "run_as.9"}},
        headers=TOKEN,
    )

    assert added.status_code == 200 and preview.status_code == 200
    assert "of bench follow run_as.9 instead of run_as.1" in preview.json()["summary"]
    assert preview.json()["files"]
