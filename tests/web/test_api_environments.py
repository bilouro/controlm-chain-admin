"""GET /api/environments."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.envexports import constants_repo


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = constants_repo(tmp_path).root
    settings = Settings(repo=root, open_browser=False, token="t", allowed_hosts=["testserver"])
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_the_constants_of_every_environment(client: TestClient) -> None:
    body = client.get("/api/environments").json()

    assert [(e["name"], e["letter"]) for e in body["environments"]] == [("uat", "U"), ("prod", "P")]
    proc = next(c for c in body["constants"] if c["name"] == "user.proc")
    assert proc["values"] == {"uat": "aup77proc", "prod": None} and proc["missing"] == ["prod"]
    assert proc["uses"] == 11 and proc["nodes"][0] == "P77_CHAIN/"
