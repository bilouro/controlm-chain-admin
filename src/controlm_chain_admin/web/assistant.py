"""The assistant of the web UI: a client of ``kilo serve`` and the shapes the UI reads.

Kilo runs the conversation (its model, the ``controlm`` agent, the ``ctmchain mcp`` tools); this
module only relays: it opens a session in the Kilo project, sends the prompt, reads the
messages back as text and tool calls, and lists what the assistant waits to be allowed to do.
An approval of ``ctmchain_apply`` carries this repository's own preview of its steps, so the
user sees the change as the core computes it before saying yes. Standard library only.
"""

from __future__ import annotations

import base64
import json
import shlex
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from controlm_chain_admin.core import previews
from controlm_chain_admin.core.capabilities import preview_steps
from controlm_chain_admin.core.errors import AssistantUnavailable, ChainError, ModelError
from controlm_chain_admin.core.repo import ChainRepo

TOOL_PREFIX = "ctmchain_"
#: the module an agent runs where an MCP server is not allowed
SERVICE = "ctmadmin_service"
OUTPUT_LIMIT = 2000
NO_ASSISTANT = (
    "no assistant: start the server with ctmchain serve --assistant (it runs Kilo), or set "
    "CTMCHAIN_ASSISTANT_URL to a running kilo serve"
)


class KiloClient:
    """The few calls of the ``kilo serve`` API a conversation needs, in one directory."""

    def __init__(
        self, url: str, directory: str, *, password: str | None = None, timeout: float = 30
    ) -> None:
        self.url = url.rstrip("/")
        self.directory = directory
        self.password = password
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        health: dict[str, Any] = self._call("GET", "/global/health")
        return health

    def create_session(self, agent: str, title: str = "ctmchain") -> str:
        session = self._call("POST", "/session", {"title": title, "agent": agent})
        return str(session["id"])

    def send(self, session: str, text: str, *, agent: str, model: str | None) -> None:
        body: dict[str, Any] = {"agent": agent, "parts": [{"type": "text", "text": text}]}
        if model:
            provider, _, name = model.partition("/")
            body["model"] = {"providerID": provider, "modelID": name}
        self._call("POST", f"/session/{_quoted(session)}/prompt_async", body)

    def busy(self, session: str) -> bool:
        status = self._call("GET", "/session/status") or {}
        state = status.get(session)
        return isinstance(state, Mapping) and state.get("type") != "idle"

    def messages(self, session: str) -> list[dict[str, Any]]:
        try:
            messages: list[dict[str, Any]] = self._call(
                "GET", f"/session/{_quoted(session)}/message"
            )
        except ModelError as exc:
            raise ModelError(f"unknown conversation {session}") from exc
        return messages

    def permissions(self, session: str) -> list[dict[str, Any]]:
        pending = self._call("GET", "/permission") or []
        return [p for p in pending if p.get("sessionID") == session]

    def reply(self, request: str, *, approve: bool) -> None:
        body = {"reply": "once" if approve else "reject"}
        self._call("POST", f"/permission/{_quoted(request)}/reply", body)

    def stop(self, session: str) -> None:
        self._call("POST", f"/session/{_quoted(session)}/abort")

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        query = urllib.parse.urlencode({"directory": self.directory})
        request = urllib.request.Request(
            f"{self.url}{path}?{query}",
            method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise _http_error(exc, method, path) from exc
        except (urllib.error.URLError, OSError, socket.timeout) as exc:
            raise AssistantUnavailable(
                f"Kilo does not answer at {self.url}: start it with ctmchain serve --assistant"
            ) from exc
        return json.loads(raw) if raw else None

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.password:
            token = base64.b64encode(f"kilo:{self.password}".encode()).decode()
            headers["authorization"] = f"Basic {token}"
        return headers


def _quoted(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def _http_error(exc: urllib.error.HTTPError, method: str, path: str) -> ChainError:
    if exc.code == 401:
        return AssistantUnavailable(
            "Kilo refused the password (CTMCHAIN_ASSISTANT_PASSWORD, KILO_SERVER_PASSWORD)"
        )
    if exc.code == 404:
        return ModelError(f"Kilo has nothing at {method} {path}")
    return AssistantUnavailable(f"Kilo answered {exc.code} to {method} {path}")


# ---------------------------------------------------------------- a kilo serve of our own


class KiloProcess:
    """A ``kilo serve`` started by ``ctmchain serve --assistant``, stopped with it."""

    def __init__(self, process: subprocess.Popen[bytes], url: str, password: str, log: Path):
        self.process, self.url, self.password, self.log = process, url, password, log

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        if sys.platform == "win32":  # pragma: no cover - the npm shim starts node under cmd
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.process.pid)], check=False,
                           capture_output=True)  # fmt: skip
        else:
            os.killpg(self.process.pid, signal.SIGTERM)
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - kilo ignored the signal
            self.process.kill()
            self.process.wait()


def kilo_executable() -> str | None:
    """The ``kilo`` to start: ``CTMCHAIN_KILO``, else the one on the PATH. On Windows npm puts
    a shell script ``kilo`` beside ``kilo.cmd``, and only the ``.cmd`` (or an ``.exe``) runs."""
    names = ("kilo.cmd", "kilo.exe", "kilo") if sys.platform == "win32" else ("kilo",)
    found = (shutil.which(name) for name in names)
    return os.environ.get("CTMCHAIN_KILO") or next((path for path in found if path), None)


def start_kilo(
    directory: Path, repo_root: Path | None = None, *, timeout: float = 60
) -> KiloProcess:
    """Start ``kilo serve`` in the Kilo project ``directory``, on a free port of 127.0.0.1 with
    a password of its own, and wait until it answers. The commands of its agent find this
    Python first on the PATH and the chain repository in ``CTMCHAIN_REPO``."""
    executable = kilo_executable()
    if not executable:
        raise AssistantUnavailable(
            "kilo is not installed: npm install -g @kilocode/cli (or set CTMCHAIN_KILO to it)"
        )
    port, password = _free_port(), secrets.token_urlsafe(18)
    log = Path(tempfile.gettempdir()) / f"ctmchain-kilo-serve-{port}.log"
    with log.open("wb") as out:
        process = subprocess.Popen(
            [executable, "serve", "--port", str(port), "--hostname", "127.0.0.1"],
            cwd=directory,
            # ~/.claude/CLAUDE.md is what a person wants of Claude Code (a language, say), not
            # the rules of this assistant; KILO_DISABLE_CLAUDE_CODE_PROMPT=0 reads it again
            env={
                "KILO_DISABLE_CLAUDE_CODE_PROMPT": "1",
                **os.environ,
                "KILO_SERVER_PASSWORD": password,
                "PATH": os.pathsep.join([str(Path(sys.executable).parent), os.environ["PATH"]]),
                **({"CTMCHAIN_REPO": str(repo_root.resolve())} if repo_root else {}),
            },
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=sys.platform != "win32",
        )
    started = KiloProcess(process, f"http://127.0.0.1:{port}", password, log)
    client = KiloClient(started.url, str(directory), password=password, timeout=2)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssistantUnavailable(
                f"kilo serve stopped (exit {process.returncode}): see {log}"
            )
        try:
            client.health()
            return started
        except AssistantUnavailable:
            time.sleep(0.3)
    started.stop()  # pragma: no cover - a kilo that never answers
    raise AssistantUnavailable(f"kilo serve did not answer in {timeout:.0f}s: see {log}")  # pragma: no cover


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


# ---------------------------------------------------------------- what the UI reads


def conversation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The messages as the UI shows them: text, tool calls and errors; the rest is left out."""
    shown = []
    for message in messages:
        info = message.get("info", {})
        parts = [p for p in (_part(raw) for raw in message.get("parts", [])) if p is not None]
        error = info.get("error")
        if error:
            parts.append({"kind": "error", "text": _error_text(error)})
        shown.append({"id": info.get("id", ""), "role": info.get("role", "assistant"),
                      "parts": parts})  # fmt: skip
    return shown


def _part(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    if raw.get("type") == "text" and not raw.get("synthetic"):
        return {"kind": "text", "text": raw.get("text", "")}
    if raw.get("type") != "tool":
        return None
    state = raw.get("state", {})
    output = state.get("error") if state.get("status") == "error" else state.get("output")
    tool, data = str(raw.get("tool", "")).removeprefix(TOOL_PREFIX), state.get("input")
    called = _service_call(data) if tool == "bash" else None
    if called is not None:
        tool, data = called[0], {"args": " ".join(called[1])}
    return {
        "kind": "tool",
        "tool": tool,
        "status": state.get("status"),
        "input": data,
        "output": _short(output),
    }


def _service_call(data: Any) -> tuple[str, list[str]] | None:
    """The tool and the values of a command that runs the service; None for any other."""
    command = data.get("command") if isinstance(data, Mapping) else None
    if not isinstance(command, str) or SERVICE not in command:
        return None
    try:
        words = shlex.split(command.split(SERVICE, 1)[1])
    except ValueError:
        return None
    if words[:1] == ["--repo"]:
        words = words[2:]
    elif words[:1] and words[0].startswith("--repo="):
        words = words[1:]
    return (words[0].replace("-", "_"), words[1:]) if words else None


def _short(output: Any) -> str | None:
    if output is None:
        return None
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    if len(text) <= OUTPUT_LIMIT:
        return text
    return f"{text[:OUTPUT_LIMIT]}... ({len(text) - OUTPUT_LIMIT} more characters)"


def _error_text(error: Mapping[str, Any]) -> str:
    message = (error.get("data") or {}).get("message")
    name = error.get("name", "error")
    return f"{name}: {message}" if message else str(name)


def approvals(repo: ChainRepo, pending: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the assistant waits to be allowed to do; an apply with this repository's preview."""
    return [_approval(repo, request) for request in pending]


def _approval(repo: ChainRepo, request: Mapping[str, Any]) -> dict[str, Any]:
    metadata = request.get("metadata") or {}
    data = metadata.get("mcpInput", metadata)
    tool = str(request.get("permission", "")).removeprefix(TOOL_PREFIX)
    called = _service_call(data) if tool == "bash" else None
    if called is not None:
        tool, data = called[0], {"args": " ".join(called[1])}
        if tool == "apply" and called[1]:
            return _command_apply(repo, request, called[1][0])
    approval: dict[str, Any] = {"id": request.get("id"), "tool": tool, "input": data,
                                "preview": None, "problem": None}  # fmt: skip
    steps = data.get("steps") if isinstance(data, Mapping) else None
    if tool != "apply" or not isinstance(steps, list):
        return approval
    try:
        approval["preview"] = preview_steps(repo, steps)
    except ChainError as exc:
        approval["problem"] = str(exc)
        return approval
    asked = data.get("preview_id")
    if asked and asked != approval["preview"]["preview_id"]:
        approval["problem"] = (
            "this is not the change the assistant previewed: the repository changed since; "
            "reject it and ask again"
        )
    return approval


def _command_apply(repo: ChainRepo, request: Mapping[str, Any], preview_id: str) -> dict[str, Any]:
    """An apply by command names its preview only: the steps kept for it, previewed again."""
    approval: dict[str, Any] = {"id": request.get("id"), "tool": "apply",
                                "input": {"preview_id": preview_id},
                                "preview": None, "problem": None}  # fmt: skip
    try:
        steps = previews.recall(repo.root, preview_id)
        approval["preview"] = preview_steps(repo, steps)
    except ChainError as exc:
        approval["problem"] = str(exc)
        return approval
    if approval["preview"]["preview_id"] != preview_id:
        approval["problem"] = (
            "this is not the change the assistant previewed: the repository changed since; "
            "reject it and ask again"
        )
    return approval
