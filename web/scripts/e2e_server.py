"""Serve a synthetic chain repository for the Playwright tests (web/tests/e2e).

A git repository of the synthetic chain (application P77) on a release branch, in a temporary
directory, served by ``ctmchain serve`` on the port and token the tests use. With
``CTMCHAIN_E2E_ASSISTANT=1`` the server starts Kilo too (``--assistant``, the model of
``CTMCHAIN_E2E_MODEL``). Only synthetic data is involved. Run by ``npm run test:e2e``.
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

from tests.support.gitrepo import chain_git_repo, git  # noqa: E402


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="ctmchain-e2e-"))
    repo = chain_git_repo(work)
    git(repo.root, "checkout", "-q", "-b", "release/e2e")
    command = [sys.executable, "-m", "controlm_chain_admin", "serve", "--repo", str(repo.root),
               "--port", os.environ.get("CTMCHAIN_E2E_PORT", "8799"), "--no-browser"]  # fmt: skip
    if os.environ.get("CTMCHAIN_E2E_ASSISTANT") == "1":
        model = os.environ.get("CTMCHAIN_E2E_MODEL", "openai/gpt-5-mini")
        command += ["--assistant", "--assistant-model", model]
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
