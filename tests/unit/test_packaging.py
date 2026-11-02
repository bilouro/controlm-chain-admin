"""The source distribution carries the whole project, so it can be developed where only PyPI is."""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

sdist = pytest.importorskip("hatchling.builders.sdist")

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def members(tmp_path_factory: pytest.TempPathFactory) -> set[str]:
    out = tmp_path_factory.mktemp("dist")
    [built] = sdist.SdistBuilder(str(ROOT)).build(directory=str(out), versions=["standard"])
    with tarfile.open(built) as archive:
        return {name.split("/", 1)[1] for name in archive.getnames() if "/" in name}


def test_the_rules_skills_and_frontend_travel_with_the_code(members: set[str]) -> None:
    expected = {
        "CLAUDE.md",
        "DESIGN.md",
        "BACKLOG.md",
        "CHANGELOG.md",
        "pyproject.toml",
        ".gitignore",
        ".claude/skills/verify/verify.sh",
        ".claude/skills/python-core-tdd/SKILL.md",
        ".github/workflows/ci.yml",
        "web/package.json",
        "web/package-lock.json",
        "web/src/main.tsx",
        "tests/unit/test_packaging.py",
        "src/controlm_chain_admin/cli.py",
    }
    assert expected <= members
    if (ROOT / "src/controlm_chain_admin/web/static/index.html").is_file():
        assert "src/controlm_chain_admin/web/static/index.html" in members  # serve without npm


def test_nothing_local_or_generated_travels(members: set[str]) -> None:
    local = (".venv/", "node_modules/", "web/dist/", "__pycache__/", ".mypy_cache/", ".git/")
    assert not [m for m in members if any(part in f"/{m}" for part in (f"/{p}" for p in local))]
    assert not [m for m in members if m.endswith(".xml") or m.endswith("no-real-data.patterns")]
