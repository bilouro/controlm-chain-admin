"""Serve a synthetic chain repository for the Playwright tests (web/tests/e2e).

A git repository of the synthetic chain (application P77) on a release branch, in a temporary
directory, served by ``ctmchain serve`` on the port and token the tests use. With
``CTMCHAIN_E2E_ASSISTANT=1`` the server starts Kilo too (``--assistant``, the model of
``CTMCHAIN_E2E_MODEL``).

With ``--environments`` the repository has one branch per environment instead (prod, uat, egma
and bench, the map derived, the branch of bench checked out), on the port of
``CTMCHAIN_E2E_ENVS_PORT``; a newer export of uat is left in the file ``CTMCHAIN_E2E_EXPORT``
names, for the refresh to be tried with.

Only synthetic data is involved. Run by ``npm run test:e2e``.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.support.fourenvs import (  # noqa: E402
    export_of,
    four_branches,
    two_users_in,
    uat_ahead,
    with_map,
)
from tests.support.gitrepo import chain_git_repo, git  # noqa: E402


def _release(work: Path) -> list[str]:
    """The chain on a release branch; the repository and the options of its server."""
    repo = chain_git_repo(work)
    git(repo.root, "checkout", "-q", "-b", "release/e2e")
    options = [str(repo.root), "--port", os.environ.get("CTMCHAIN_E2E_PORT", "8799")]
    if os.environ.get("CTMCHAIN_E2E_ASSISTANT") == "1":
        model = os.environ.get("CTMCHAIN_E2E_MODEL", "openai/gpt-5-mini")
        options += ["--assistant", "--assistant-model", model]
    return options


def _environments(work: Path) -> list[str]:
    """One branch per environment, uat ahead and two users in bench, the map derived."""
    repo = four_branches(work, change=two_users_in("bench"))
    with_map(repo)
    git(repo.root, "switch", "-q", "env/bench")
    newer = os.environ.get("CTMCHAIN_E2E_EXPORT")
    if newer:
        export = uat_ahead("uat", export_of("uat")).replace(b"a2.ksh -x", b"a3.ksh")
        Path(newer).write_bytes(export)
    return [str(repo.root), "--port", os.environ.get("CTMCHAIN_E2E_ENVS_PORT", "8798")]


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="ctmchain-e2e-"))
    build = _environments if "--environments" in sys.argv[1:] else _release
    command = [sys.executable, "-m", "controlm_chain_admin", "serve", "--repo", *build(work),
               "--no-browser"]  # fmt: skip
    env = {**os.environ, "CTMCHAIN_TOKEN": os.environ.get("CTMCHAIN_E2E_TOKEN", "e2e-token")}
    process = subprocess.Popen(command, env=env)
    signal.signal(signal.SIGTERM, lambda *_: process.terminate())
    signal.signal(signal.SIGINT, lambda *_: process.terminate())
    try:
        return process.wait()
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
