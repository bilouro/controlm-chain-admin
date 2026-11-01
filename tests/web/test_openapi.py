"""The OpenAPI schema is the frontend contract: changing it is a deliberate, visible commit."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

SNAPSHOT = Path(__file__).with_name("openapi.snapshot.json")


def test_openapi_matches_the_committed_snapshot(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    schema["info"]["version"] = "<version>"  # the package version is not part of the contract

    if not SNAPSHOT.exists():  # first run: write it, then fail so the author commits it knowingly
        SNAPSHOT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise AssertionError(f"wrote {SNAPSHOT.name}; review and commit it, then re-run")

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert schema == expected, "OpenAPI changed: regenerate the snapshot on purpose (delete it)"


def test_every_endpoint_has_a_summary_and_a_tag(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            assert operation.get("summary"), f"{method.upper()} {path} has no summary"
            assert operation.get("tags"), f"{method.upper()} {path} has no tag"
