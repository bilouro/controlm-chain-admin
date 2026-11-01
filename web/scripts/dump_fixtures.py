"""Dump API responses for the synthetic repository into web/src/test/fixtures (MSW handlers).

Run from the repository root with the dev extras installed:

    .venv/bin/python web/scripts/dump_fixtures.py

Only synthetic data (application P77) is involved, so the output is safe to commit.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from controlm_chain_admin.core.ops import import_xml  # noqa: E402
from controlm_chain_admin.core.repo import init_repo  # noqa: E402
from controlm_chain_admin.web.app import create_app  # noqa: E402
from controlm_chain_admin.web.settings import Settings  # noqa: E402
from tests.support.anomalies import ANOMALY_EXPORT  # noqa: E402
from tests.support.samples import SAMPLE_EXPORT  # noqa: E402

FIXTURES = ROOT / "web" / "src" / "test" / "fixtures"
ENDPOINTS = {
    "repo.json": "/api/repo",
    "folders.json": "/api/folders",
    "folder-P77_CHAIN.json": "/api/folders/P77_CHAIN",
    "folder-P77_INGEST_DAILY.json": "/api/folders/P77_INGEST_DAILY",
    "job-P77_INGEST_DAILY-P77_INGEST_LOAD.json": "/api/jobs/P77_INGEST_DAILY/P77_INGEST_LOAD",
    "job-P77_CHAIN-P77_B.json": "/api/jobs/P77_CHAIN/P77_B",
    "validate.json": "/api/validate",
}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        repo = init_repo(
            root, "P77_RISK_ENGINE", ("test", "uat", "bench", "prod"), prefixes=("P77", "RQ_", "RC_")
        )
        import_xml(repo, SAMPLE_EXPORT, env="uat")
        import_xml(repo, ANOMALY_EXPORT, env="uat")
        FIXTURES.mkdir(parents=True, exist_ok=True)
        with TestClient(create_app(Settings(repo=root, open_browser=False))) as client:
            for filename, path in ENDPOINTS.items():
                response = client.get(path)
                response.raise_for_status()
                body = response.json()
                if filename == "repo.json":
                    body["root"] = "/tmp/repo"  # not deterministic otherwise
                (FIXTURES / filename).write_text(
                    json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                print(f"wrote {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
