"""Editing through the API: table view, relations, preview and apply with a session token."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.web.conftest import TOKEN

AUTH = {"X-Ctmchain-Token": TOKEN}
C = "P77_CHAIN"


def test_table_lists_folders_with_jobs_and_neighbours(client: TestClient) -> None:
    body = client.get("/api/table").json()

    assert [f["name"] for f in body["folders"]] == ["P77_INGEST_DAILY", C]
    jobs = {j["id"]: j for j in body["folders"][1]["jobs"]}
    assert [p["node"] for p in jobs["P77_B"]["predecessors"]] == [f"{C}/P77_A"]
    assert body["folders"][1]["application"] == "P77_RISK_ENGINE"


def test_job_and_folder_detail_carry_detailed_relations(client: TestClient) -> None:
    job = client.get(f"/api/jobs/{C}/P77_B").json()
    folder = client.get(f"/api/folders/{C}").json()

    (pred,) = job["predecessors"]
    assert pred["link"] == "P77_A-P77_B_OK" and pred["cleanup"] is True and pred["and_or"] == "A"
    assert pred["peers"] == [{"node": f"{C}/P77_A", "and_or": None, "cleanup": False, "conditional": None}]
    assert job["successors"][0]["peers"][0]["node"] == f"{C}/P77_C"
    assert [p["link"] for p in folder["predecessors"]] == ["P77_OTHER-P77_CHAIN_OK"]


def test_changes_need_the_session_token(client: TestClient) -> None:
    request = {"op": "set-attributes", "params": {"node": f"{C}/P77_B", "changes": {"DESCRIPTION": "x"}}}

    assert client.post("/api/changes/preview", json=request).status_code == 401
    assert client.post("/api/changes/preview", json=request, headers={"X-Ctmchain-Token": "bad"}).status_code == 401


def test_preview_then_apply_writes_the_change(client: TestClient, repo_root: Path) -> None:
    request = {"op": "set-attributes", "params": {"node": f"{C}/P77_B", "changes": {"DESCRIPTION": "Loaded"}}}

    preview = client.post("/api/changes/preview", json=request, headers=AUTH)
    assert preview.status_code == 200
    body = preview.json()
    assert body["files"] == [{"path": f"folders/{C}/jobs/P77_B.json", "change": "modify"}]
    assert '+  "DESCRIPTION": "Loaded",' in body["diff"] and body["fingerprint"]

    applied = client.post("/api/changes/apply", json={**request, "fingerprint": body["fingerprint"]}, headers=AUTH)
    assert applied.status_code == 200 and applied.json() == {"written": 1, "deleted": 0}
    job = json.loads((repo_root / f"folders/{C}/jobs/P77_B.json").read_text("utf-8"))
    assert job["DESCRIPTION"] == "Loaded"


def test_apply_refuses_a_stale_preview(client: TestClient) -> None:
    request = {"op": "set-attributes", "params": {"node": f"{C}/P77_B", "changes": {"DESCRIPTION": "A"}}}
    fp = client.post("/api/changes/preview", json=request, headers=AUTH).json()["fingerprint"]
    other = {"op": "set-attributes", "params": {"node": f"{C}/P77_B", "changes": {"RUN_AS": "z"}}}
    client.post("/api/changes/apply", json={**other, "fingerprint": client.post("/api/changes/preview", json=other, headers=AUTH).json()["fingerprint"]}, headers=AUTH)

    response = client.post("/api/changes/apply", json={**request, "fingerprint": fp}, headers=AUTH)

    assert response.status_code == 409 and response.json()["error"] == "ChangeConflict"


def test_relation_operations_through_the_api(client: TestClient) -> None:
    def run(op: str, **params: object) -> dict:  # type: ignore[type-arg]
        preview = client.post("/api/changes/preview", json={"op": op, "params": params}, headers=AUTH)
        assert preview.status_code == 200, preview.text
        body = {"op": op, "params": params, "fingerprint": preview.json()["fingerprint"]}
        applied = client.post("/api/changes/apply", json=body, headers=AUTH)
        assert applied.status_code == 200, applied.text
        return preview.json()  # type: ignore[no-any-return]

    run("link", consumer=f"{C}/P77_E", producer=f"{C}/P77_C")
    run("update-relation", link="P77_C-P77_E_OK", consumer=f"{C}/P77_E", and_or="O")
    run("rename-link", link="P77_C-P77_E_OK", name="P77_C-P77_E_DONE")
    preds = {p["link"]: p for p in client.get(f"/api/jobs/{C}/P77_E").json()["predecessors"]}
    assert preds["P77_C-P77_E_OK"]["name"] == "P77_C-P77_E_DONE" and preds["P77_C-P77_E_OK"]["and_or"] == "O"
    run("unlink", link="P77_C-P77_E_OK", consumer=f"{C}/P77_E")
    assert "P77_C-P77_E_OK" not in {p["link"] for p in client.get(f"/api/jobs/{C}/P77_E").json()["predecessors"]}


def test_invalid_changes_are_422(client: TestClient) -> None:
    bad_op = client.post("/api/changes/preview", json={"op": "explode", "params": {}}, headers=AUTH)
    bad_params = client.post(
        "/api/changes/preview",
        json={"op": "set-attributes", "params": {"node": f"{C}/P77_B", "changes": {"JOBNAME": "X"}}},
        headers=AUTH,
    )

    assert bad_op.status_code == 422
    assert bad_params.status_code == 422 and bad_params.json()["error"] == "InvalidChange"


def test_requests_for_another_host_are_rejected(client: TestClient) -> None:
    assert client.get("/api/repo", headers={"Host": "evil.example"}).status_code == 400


def test_folder_detail_groups_its_attributes_like_a_job(client: TestClient) -> None:
    groups = client.get(f"/api/folders/{C}").json()["groups"]

    assert groups["identity"]["FOLDER_NAME"] == C
    assert "tag" not in {k for g in groups.values() for k in g}
