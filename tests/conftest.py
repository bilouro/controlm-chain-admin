"""Shared pytest fixtures.

Real-data tests (marker ``realdata``) run only when ``CTMCHAIN_DATA_REPO`` points to a clone of
the private data repository; they are skipped everywhere else, including CI.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

DATA_REPO_ENV = "CTMCHAIN_DATA_REPO"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip ``realdata`` tests unless the private data repository is available."""
    if os.environ.get(DATA_REPO_ENV):
        return
    skip = pytest.mark.skip(reason=f"{DATA_REPO_ENV} is not set; real-data tests skipped")
    for item in items:
        if "realdata" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def data_repo() -> Path:
    """Path of the private data repository (real exports). Only for ``realdata`` tests."""
    value = os.environ.get(DATA_REPO_ENV)
    if not value:
        pytest.skip(f"{DATA_REPO_ENV} is not set")
    path = Path(value).expanduser()
    if not path.is_dir():
        pytest.fail(f"{DATA_REPO_ENV}={value} is not a directory")
    return path


@pytest.fixture
def uat_export(data_repo: Path) -> Path:
    """The UAT export file inside the private data repository (``exports/uat/*.xml``)."""
    candidates = sorted((data_repo / "exports" / "uat").glob("*.xml"))
    if not candidates:
        pytest.fail(f"no XML export under {data_repo / 'exports' / 'uat'}")
    return candidates[0]
