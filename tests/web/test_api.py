"""Read-only API over the chain repository."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from controlm_chain_admin.core.overrides import Override, write_overrides
from controlm_chain_admin.core.repo import load_repo
from tests.web.conftest import TOKEN

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
    assert body["raw"]["INCOND"][0]["link"] == "P77_INGEST_INIT-P77_INGEST_LOAD_OK"
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


def test_validate_findings_carry_their_link_and_fixes(client: TestClient) -> None:
    findings = client.get("/api/validate").json()["findings"]

    cleaned = next(f for f in findings if f["code"] == "never-cleaned")
    assert cleaned["link"] == "P77_B-P77_C_OK"
    (fix,) = cleaned["fixes"]
    assert fix["kind"] == "add-cleanup" and fix["op"] == "update-relation"
    assert fix["params"] == {
        "link": "P77_B-P77_C_OK",
        "consumer": "P77_CHAIN/P77_C",
        "cleanup": True,
    }
    assert fix["title"] == "Delete it after use" and fix["explanation"]


def test_a_batch_of_fixes_is_previewed_as_one_change(client: TestClient) -> None:
    findings = client.get("/api/validate").json()["findings"]
    changes = [
        {"op": fix["op"], "params": fix["params"]}
        for f in findings
        for fix in f["fixes"]
        if fix["kind"] in ("add-cleanup", "standard-name")
    ]

    response = client.post(
        "/api/changes/preview",
        json={"op": "batch", "params": {"changes": changes}},
        headers={"X-Ctmchain-Token": TOKEN},
    )

    assert response.status_code == 200, response.text
    assert response.json()["summary"].startswith("2 changes:")


def test_link_by_name(client: TestClient) -> None:
    response = client.get("/api/links/P77_OLDNAME-P77_D_OK")

    assert response.status_code == 200
    assert response.json()["from"] == ["P77_CHAIN/P77_C"]
    assert client.get("/api/links/NOPE").status_code == 404


def test_spa_root_is_served_or_explains_how_to_build_it(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "ctmchain" in response.text


def test_job_and_folder_details_list_their_exceptions(client: TestClient, repo_root: Path) -> None:
    repo = load_repo(repo_root)
    load = Override(attributes={"TASKTYPE": "Dummy", "CMDLINE": None})
    folder_override = Override(variables={"%%GEIENV": "x"})
    write_overrides(
        repo, "prod", {"P77_INGEST_DAILY/P77_INGEST_LOAD": load, "P77_INGEST_DAILY/": folder_override}
    )
    write_overrides(
        repo, "bench", {"P77_INGEST_DAILY/P77_INGEST_LOAD": Override(attributes={"MAXWAIT": "3"})}
    )

    job = client.get("/api/jobs/P77_INGEST_DAILY/P77_INGEST_LOAD").json()
    folder = client.get("/api/folders/P77_INGEST_DAILY").json()

    assert job["exceptions"] == {
        "bench": {"attributes": {"MAXWAIT": "3"}, "variables": {}},
        "prod": {"attributes": {"CMDLINE": None, "TASKTYPE": "Dummy"}, "variables": {}},
    }
    assert folder["exceptions"] == {"prod": {"attributes": {}, "variables": {"%%GEIENV": "x"}}}
    assert client.get("/api/jobs/P77_INGEST_DAILY/P77_INGEST_INIT").json()["exceptions"] == {}
