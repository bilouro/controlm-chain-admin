"""A chain repository built from the synthetic exports, served by the FastAPI app in-process."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.repo import init_repo
from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    repo = init_repo(root, APP, ("test", "uat", "bench", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    return root


@pytest.fixture
def client(repo_root: Path) -> Iterator[TestClient]:
    app = create_app(Settings(repo=repo_root, open_browser=False))
    with TestClient(app) as test_client:
        yield test_client
