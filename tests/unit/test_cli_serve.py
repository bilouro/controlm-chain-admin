"""``ctmchain serve``: builds the app for a repository; ``--check`` stops before listening."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    assert main(["init", "--repo", str(root), "--application", APP, "--envs", "uat"]) == 0
    xml = tmp_path / "export.xml"
    xml.write_bytes(SAMPLE_EXPORT)
    assert main(["import", str(xml), "--repo", str(root)]) == 0
    return root


def test_serve_check_prints_the_url_without_listening(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    capsys.readouterr()

    code = main(["serve", "--repo", str(root), "--port", "9999", "--no-browser", "--check"])

    out = capsys.readouterr().out
    assert code == 0
    assert "http://127.0.0.1:9999/" in out and "1 folder" in out


def test_serve_check_fails_cleanly_without_a_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["serve", "--repo", str(tmp_path), "--check"])

    assert code == 3
    assert "chain.json" in capsys.readouterr().err
