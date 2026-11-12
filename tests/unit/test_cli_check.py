"""ctmchain check: an environment's export against the repository's export of it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from tests.support.envexports import fresh_repo, prod_export, uat_full

UAT = uat_full()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return fresh_repo(tmp_path).root


def _write(tmp_path: Path, name: str, data: bytes) -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_production_byte_for_byte_exits_0(
    root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    xml = _write(tmp_path, "prod.xml", prod_export())

    assert main(["check", xml, "--repo", str(root)]) == 0

    out = capsys.readouterr().out
    assert "The repository's export of prod is the same byte for byte" in out
    assert "Folders and jobs: 11 in the export, 11 in both, 0 only in the export" in out
    assert "No field differs." in out


def test_an_environment_shows_counts_and_never_values(
    root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    xml = _write(tmp_path, "uat.xml", UAT)

    assert main(["check", xml, "--env", "uat", "--repo", str(root)]) == 1

    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].startswith("uat export: ")
    assert "not the same byte for byte" in out
    assert "1 only in the export, 1 only in the repository" in out
    header = next(i for i, line in enumerate(lines) if line.startswith("field"))
    assert lines[header].split() == ["field", "uat", "vs", "prod", "repository", "vs", "uat"]
    assert lines[header + 1].split() == ["RUN_AS", "10", "10"]
    assert "TASKTYPE" in out
    for value in ("aup77proc", "app77proc", "PP77_BATCH", "UP77_BATCH", "P77_D", "ops@"):
        assert value not in out


def test_json_names_the_nodes(
    root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    xml = _write(tmp_path, "uat.xml", UAT)

    assert main(["check", xml, "--repo", str(root), "--format", "json"]) == 1

    body = json.loads(capsys.readouterr().out)
    assert {f["field"]: f["differs"] for f in body["fields"]}["TASKTYPE"] == ["P77_CHAIN/P77_D"]
