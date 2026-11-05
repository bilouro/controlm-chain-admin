"""POST /api/intake, then the receive change through /api/changes."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.envexports import both, constants_repo, fresh_repo, job, to_prod
from tests.support.gitrepo import git, plain_git_identity

C = "P77_CHAIN"
TOKEN = {"X-Ctmchain-Token": "t"}


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plain_git_identity(monkeypatch, tmp_path)
    return constants_repo(tmp_path).root


@pytest.fixture
def client(root: Path) -> Iterator[TestClient]:
    settings = Settings(repo=root, open_browser=False, token="t", allowed_hosts=["testserver"])
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def xml() -> str:
    return job(to_prod(both()), b"PP77_E", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"').decode()


def test_intake_tells_the_environment_and_the_decisions(client: TestClient) -> None:
    assert client.post("/api/intake", json={"xml": xml()}).status_code == 401

    body = client.post("/api/intake", json={"xml": xml()}, headers=TOKEN).json()

    assert body["env"] == "prod" and body["partial"] is False
    ids = {d["id"]: d for d in body["decisions"]}
    assert ids["learn:user.proc"]["incoming"] == "app77proc"
    assert ids[f"{C}/P77_E@TASKTYPE"]["options"] == ["change", "exception", "ignore"]
    bad = client.post("/api/intake", json={"xml": "<nope"}, headers=TOKEN)
    assert bad.status_code == 422


def test_the_receive_change_is_previewed_and_applied(client: TestClient, root: Path) -> None:
    git(root, "switch", "-q", "-c", "release/march")
    request = {
        "op": "receive",
        "params": {"xml": xml(), "choices": {f"{C}/P77_E@TASKTYPE": "exception"}},
    }

    preview = client.post("/api/changes/preview", json=request, headers=TOKEN).json()
    applied = client.post(
        "/api/changes/apply", json={**request, "fingerprint": preview["fingerprint"]}, headers=TOKEN
    )

    assert preview["summary"].startswith("receive a prod export: 2 folders")
    assert applied.status_code == 200, applied.text
    assert (root / "envs/prod/overrides.json").is_file()


def test_a_group_carries_the_values_its_constant_would_have(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain_git_identity(monkeypatch, tmp_path)
    repo = fresh_repo(tmp_path)
    settings = Settings(repo=repo.root, open_browser=False, token="t", allowed_hosts=["testserver"])
    with TestClient(create_app(settings)) as fresh:
        body = fresh.post("/api/intake", json={"xml": both().decode()}, headers=TOKEN).json()

    groups = {d["field"]: d for d in body["decisions"] if d["kind"] == "group"}
    assert groups["NODEID"]["values"]["bench"] == "BP77_BATCH"
    assert (groups["NODEID"]["inline"], groups["DOMAIL/@SUBJECT"]["inline"]) == (False, True)
    members = groups["RUN_AS"]["members"]  # each job's own decision, to take apart
    assert len(members) == groups["RUN_AS"]["count"]
    assert "P77_CHAIN/P77_A@RUN_AS" in [m["id"] for m in members]
    assert members[0]["options"] == ["change", "exception", "ignore"]
    assert members[0]["members"] == [] and members[0]["nodes"] == []


def test_the_export_can_be_told_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain_git_identity(monkeypatch, tmp_path)
    repo = fresh_repo(tmp_path)
    git(repo.root, "switch", "-q", "-c", "release/baseline")
    settings = Settings(repo=repo.root, open_browser=False, token="t", allowed_hosts=["testserver"])
    chain = ANOMALY_EXPORT.decode()
    with TestClient(create_app(settings)) as fresh:
        delivery = fresh.post("/api/intake", json={"xml": chain}, headers=TOKEN).json()
        full = fresh.post("/api/intake", json={"xml": chain, "full": True}, headers=TOKEN).json()
        request = {"op": "receive", "params": {"xml": chain, "full": True}}
        preview = fresh.post("/api/changes/preview", json=request, headers=TOKEN).json()

    assert (delivery["full"], full["full"]) == (False, True)
    assert [d["id"] for d in full["decisions"] if d["kind"] == "absent"] == [
        "P77_INGEST_DAILY/#absent"
    ]
    assert any(f["path"] == "folders/P77_INGEST_DAILY/folder.json" for f in preview["files"])


def test_a_full_export_of_another_environment_makes_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain_git_identity(monkeypatch, tmp_path)
    repo = fresh_repo(tmp_path)
    git(repo.root, "switch", "-q", "-c", "release/environments")
    settings = Settings(repo=repo.root, open_browser=False, token="t", allowed_hosts=["testserver"])
    uat = job(both(), b"UP77_D", b'TASKTYPE="Command"', b'TASKTYPE="Dummy"').decode()
    with TestClient(create_app(settings)) as fresh:
        body = {"xml": uat}
        intake = fresh.post("/api/intake", json=body, headers=TOKEN).json()
        request = {"op": "receive", "params": body}
        preview = fresh.post("/api/changes/preview", json=request, headers=TOKEN).json()

    assert intake["full"] is True and "values_only" not in intake
    decisions = {d["id"]: d for d in intake["decisions"]}
    assert decisions[f"{C}/P77_D@TASKTYPE"]["default"] == "exception"
    assert "1 exception(s)" in preview["summary"]
