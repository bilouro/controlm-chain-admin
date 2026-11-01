"""Run the local server with uvicorn and open the browser."""

from __future__ import annotations

import threading
import webbrowser

from controlm_chain_admin.web.app import create_app
from controlm_chain_admin.web.settings import Settings


def run(settings: Settings) -> None:
    """Serve ``settings.repo`` on ``settings.host:port`` until interrupted."""
    import uvicorn  # heavy import kept local; only needed when actually serving

    app = create_app(settings)
    if settings.open_browser:
        threading.Timer(0.8, webbrowser.open, args=(settings.url,)).start()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
