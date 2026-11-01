"""``python -m controlm_chain_admin`` behaves like the ``ctmchain`` script."""

from __future__ import annotations

import subprocess
import sys

from controlm_chain_admin import __version__


def test_python_dash_m_reports_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "controlm_chain_admin", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == f"ctmchain {__version__}"
