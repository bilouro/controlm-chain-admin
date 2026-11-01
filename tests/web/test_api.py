"""Read-only API over the chain repository."""

from __future__ import annotations

from fastapi.testclient import TestClient

ERROR_KEYS = {"error", "message", "detail"}


def test_repo_summary(client: TestClient) -> None:
    response = client.get("/api/repo")

    assert response.status_code == 200
    body = response.json()
    assert body["application"] == "P77_RISK_ENGINE"
    assert body["environments"] == ["test", "uat", "bench", "prod"]
    assert body["folders"] == 2 and body["jobs"] == 9
    assert body["letter_rule"]["prefixes"] == ["P77", "RQ_", "RC_"]


def test_folder_list_with_counts_search_and_pagination(client: TestClient) -> None:
    response = client.get("/api/folders")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    names = [f["name"] for f in body["items"]]
    assert names == ["P77_CHAIN", "P77_INGEST_DAILY"]
    chain = body["items"][0]
    assert chain["jobs"] == 7 and chain["links"] == 10
    assert chain["sub_application"] == "P77_BATCH"

    assert [f["name"] for f in client.get("/api/folders?q=ingest").json()["items"]] == [
        "P77_INGEST_DAILY"
    ]
    page = client.get("/api/folders?limit=1&offset=1").json()
    assert page["total"] == 2 and [f["name"] for f in page["items"]] == ["P77_INGEST_DAILY"]


def test_folder_detail_has_folder_json_jobs_links_and_graph(client: TestClient) -> None:
    response = client.get("/api/folders/P77_CHAIN")

    assert response.status_code == 200
    body = response.json()
    assert body["folder"]["FOLDER_NAME"] == "P77_CHAIN"
    assert body["folder"]["meta"] == {"JOBISN": "1"}
    assert [j["id"] for j in body["jobs"]][:2] == ["P77_A", "P77_B"]
    assert body["jobs"][0]["name"] == "P77_A" and body["jobs"][0]["task_type"] == "Command"
    assert body["jobs"][-1] == {"id": "P77_F~2", "name": "P77_F", "task_type": "Dummy"}
    assert len(body["graph"]["edges"]) == 3
    assert len(body["links"]) == 10
    assert body["graph"]["dangling"] and body["graph"]["unconsumed"]


def test_unknown_folder_is_404_with_the_common_error_shape(client: TestClient) -> None:
    response = client.get("/api/folders/P77_NOPE")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == ERROR_KEYS and body["error"] == "ModelError"


def test_job_detail_groups_attributes_and_keeps_the_raw_json(client: TestClient) -> None:
    response = client.get("/api/jobs/P77_INGEST_DAILY/P77_INGEST_LOAD")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "P77_INGEST_LOAD" and body["folder"] == "P77_INGEST_DAILY"
    groups = body["groups"]
    assert groups["identity"]["JOBNAME"] == "P77_INGEST_LOAD"
    assert groups["execution"]["CMDLINE"] == "/opt/p77/bin/load.ksh -d %%ODATE"
    assert groups["execution"]["NODEID"] == "UP77_BATCH"
    assert body["meta"] == {"JOBISN": "3"}
    assert body["raw"]["INCOND"][0]["NAME"] == "P77_INGEST_INIT-P77_INGEST_LOAD_OK"
    assert [link["name"] for link in body["links"]] == ["P77_INGEST_INIT-P77_INGEST_LOAD_OK"]
    assert body["on"][0]["CODE"] == "NOTOK"


def test_unknown_job_is_404(client: TestClient) -> None:
    assert client.get("/api/jobs/P77_INGEST_DAILY/NOPE").status_code == 404


def test_validate_report(client: TestClient) -> None:
    response = client.get("/api/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["counts"]["error"] == 1
    assert {f["code"] for f in body["findings"]} >= {"dangling", "stale-name", "never-cleaned"}
    assert body["links"] == 12 and body["nodes"] == 11


def test_link_by_name(client: TestClient) -> None:
    response = client.get("/api/links/P77_OLDNAME-P77_D_OK")

    assert response.status_code == 200
    assert response.json()["from"] == ["P77_CHAIN/P77_C"]
    assert client.get("/api/links/NOPE").status_code == 404


def test_spa_root_is_served_or_explains_how_to_build_it(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "ctmchain" in response.text
