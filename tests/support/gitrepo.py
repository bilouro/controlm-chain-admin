"""Helpers to build throw-away git repositories holding a synthetic chain repository."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

from controlm_chain_admin.core.ops import import_xml
from controlm_chain_admin.core.repo import ChainRepo, init_repo
from tests.support.anomalies import ANOMALY_EXPORT
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"
IDENTITY = (
    "-c",
    "user.name=Test",
    "-c",
    "user.email=test@example.com",
    "-c",
    "commit.gpgsign=false",
)


def git(root: Path, *args: str) -> str:
    """Run git in ``root`` with a fixed identity; returns stdout."""
    result = subprocess.run(
        ["git", "-C", str(root), *IDENTITY, *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def commit_all(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def chain_git_repo(tmp_path: Path) -> ChainRepo:
    """A git repository (branch main, one commit) with the synthetic chain imported."""
    root = tmp_path / "repo"
    repo = init_repo(root, APP, ("uat", "prod"), prefixes=("P77", "RQ_", "RC_"))
    import_xml(repo, SAMPLE_EXPORT, env="uat")
    import_xml(repo, ANOMALY_EXPORT, env="uat")
    git(root, "init", "-q", "-b", "main")
    commit_all(root, "import the synthetic chain")
    return repo


def remove_tree(path: Path) -> None:
    """``shutil.rmtree`` that also removes read-only files (git objects on Windows)."""
    for item in path.rglob("*"):
        if item.is_file():
            os.chmod(item, stat.S_IREAD | stat.S_IWRITE)
    shutil.rmtree(path)
