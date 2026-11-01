"""Allow ``python -m controlm_chain_admin``."""

from __future__ import annotations

import sys

from controlm_chain_admin.cli import main

if __name__ == "__main__":
    sys.exit(main())
