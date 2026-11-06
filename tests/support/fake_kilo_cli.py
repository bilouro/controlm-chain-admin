"""``kilo serve --port P --hostname H`` played by FakeKilo, for ``ctmchain serve --assistant``.

Records how it was started (``FAKE_KILO_RECORD``: a JSON file) and serves until stopped.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support.fake_kilo import FakeKilo


def main(argv: list[str]) -> int:
    if os.environ.get("FAKE_KILO_FAIL"):
        print("kilo: cannot start", file=sys.stderr)
        return 1
    port = int(argv[argv.index("--port") + 1])
    record = os.environ.get("FAKE_KILO_RECORD")
    if record:
        Path(record).write_text(
            json.dumps({"args": argv, "cwd": os.getcwd(),
                        "password": bool(os.environ.get("KILO_SERVER_PASSWORD"))}),
            "utf-8",
        )  # fmt: skip
    FakeKilo(password=os.environ.get("KILO_SERVER_PASSWORD"), port=port).start()
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    stopped.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
