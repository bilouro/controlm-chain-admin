"""Run the local server with uvicorn and open the browser."""

from __future__ import annotations

import secrets
import signal
import threading
import webbrowser
from types import FrameType

from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings


def _stop(signum: int, frame: FrameType | None) -> None:
    raise SystemExit(0)


def run(settings: Settings) -> None:
    """Serve ``settings.repo`` on ``settings.host:port`` until interrupted.

    A terminate or hang-up signal ends it like Ctrl+C: what the caller cleans up afterwards
    (the Kilo of ``--assistant``) is cleaned up. uvicorn stops gracefully on SIGTERM, then
    raises it again, which by default would end the process before any ``finally``.
    """
    import uvicorn  # heavy import kept local; only needed when actually serving

    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _stop)

    if settings.token is None:
        settings = settings.model_copy(update={"token": secrets.token_urlsafe(18)})
    assert settings.token is not None
    app = create_app(settings)
    if settings.open_browser:
        threading.Timer(0.8, webbrowser.open, args=(settings.editor_url(settings.token),)).start()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
