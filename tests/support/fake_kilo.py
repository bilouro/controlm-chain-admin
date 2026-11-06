"""A stand-in for ``kilo serve``: the endpoints ctmchain uses, with its state in memory."""

from __future__ import annotations

import base64
import json
import re
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


@dataclass
class FakeKilo:
    """Sessions, their messages and pending permissions; what was sent is recorded."""

    password: str | None = None
    port: int = 0
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    messages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    permissions: list[dict[str, Any]] = field(default_factory=list)
    busy: set[str] = field(default_factory=set)
    prompts: list[dict[str, Any]] = field(default_factory=list)
    replies: list[tuple[str, str]] = field(default_factory=list)
    aborted: list[str] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    def start(self) -> FakeKilo:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # quiet
                pass

            def do_GET(self) -> None:
                fake._handle(self, "GET")

            def do_POST(self) -> None:
                fake._handle(self, "POST")

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    # ------------------------------------------------------------ what a test arranges

    def say(
        self, session: str, *parts: dict[str, Any], error: dict[str, Any] | None = None
    ) -> None:
        """An assistant message with these parts."""
        number = len(self.messages[session]) + 1
        info: dict[str, Any] = {"id": f"msg_{number}", "role": "assistant", "sessionID": session}
        if error is not None:
            info["error"] = error
        self.messages[session].append({"info": info, "parts": list(parts)})

    def ask(self, session: str, permission: str, metadata: dict[str, Any]) -> str:
        """A pending permission request of the assistant."""
        request = f"per_{len(self.permissions) + 1}"
        self.permissions.append(
            {
                "id": request,
                "sessionID": session,
                "permission": permission,
                "patterns": ["*"],
                "metadata": metadata,
            }
        )
        return request

    # ------------------------------------------------------------ the HTTP side

    def _handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        if self.password is not None and not self._authorised(handler):
            self._send(handler, 401, {"name": "Unauthorized"})
            return
        url = urlparse(handler.path)
        directory = parse_qs(url.query).get("directory", [None])[0]
        length = int(handler.headers.get("content-length") or 0)
        body = json.loads(handler.rfile.read(length)) if length else None
        status, payload = self._route(method, url.path, body, directory)
        self._send(handler, status, payload)

    def _authorised(self, handler: BaseHTTPRequestHandler) -> bool:
        expected = base64.b64encode(f"kilo:{self.password}".encode()).decode()
        return handler.headers.get("authorization") == f"Basic {expected}"

    def _route(self, method: str, path: str, body: Any, directory: str | None) -> tuple[int, Any]:
        if (method, path) == ("GET", "/global/health"):
            return 200, {"healthy": True, "version": "fake"}
        if (method, path) == ("POST", "/session"):
            session = f"ses_{len(self.sessions) + 1}"
            self.sessions[session] = {"id": session, "directory": directory, **(body or {})}
            self.messages[session] = []
            self.directories.append(str(directory))
            return 200, self.sessions[session]
        if (method, path) == ("GET", "/session/status"):
            return 200, {s: {"type": "busy"} for s in self.busy}
        if (method, path) == ("GET", "/permission"):
            return 200, self.permissions
        found = re.fullmatch(r"/session/([^/]+)/(prompt_async|message|abort)", path)
        if found and found.group(1) in self.sessions:
            return self._session(method, found.group(1), found.group(2), body)
        found = re.fullmatch(r"/permission/([^/]+)/reply", path)
        if method == "POST" and found:
            self.replies.append((found.group(1), body["reply"]))
            self.permissions = [p for p in self.permissions if p["id"] != found.group(1)]
            return 200, True
        return 404, {"name": "NotFound", "data": {"message": f"{method} {path}"}}

    def _session(self, method: str, session: str, action: str, body: Any) -> tuple[int, Any]:
        if (method, action) == ("POST", "prompt_async"):
            self.prompts.append({"session": session, **body})
            text = body["parts"][0]["text"]
            self.messages[session].append(
                {
                    "info": {"id": f"msg_{len(self.messages[session]) + 1}", "role": "user"},
                    "parts": [{"type": "text", "text": text}],
                }
            )
            self.busy.add(session)
            return 204, None
        if (method, action) == ("GET", "message"):
            return 200, self.messages[session]
        if (method, action) == ("POST", "abort"):
            self.aborted.append(session)
            self.busy.discard(session)
            return 200, True
        return 404, {"name": "NotFound"}

    @staticmethod
    def _send(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
        raw = b"" if payload is None else json.dumps(payload).encode()
        handler.send_response(status)
        handler.send_header("content-type", "application/json")
        handler.send_header("content-length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)
