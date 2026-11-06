"""``ctmchain serve``: builds the app for a repository; ``--check`` stops before listening."""

from __future__ import annotations

import json
import os
import signal
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from controlm_chain_admin.cli import main
from tests.support.samples import SAMPLE_EXPORT

APP = "P77_RISK_ENGINE"


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    assert main(["init", "--repo", str(root), "--application", APP, "--envs", "uat"]) == 0
    xml = tmp_path / "export.xml"
    xml.write_bytes(SAMPLE_EXPORT)
    assert main(["import", str(xml), "--repo", str(root)]) == 0
    return root


def test_serve_check_prints_the_url_without_listening(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    capsys.readouterr()

    code = main(["serve", "--repo", str(root), "--port", "9999", "--no-browser", "--check"])

    out = capsys.readouterr().out
    assert code == 0
    assert "http://127.0.0.1:9999/" in out and "1 folder" in out


def test_serve_check_fails_cleanly_without_a_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["serve", "--repo", str(tmp_path), "--check"])

    assert code == 3
    assert "chain.json" in capsys.readouterr().err


def test_serve_keeps_the_token_given_in_the_environment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    capsys.readouterr()
    monkeypatch.setenv("CTMCHAIN_TOKEN", "kept-across-restarts")

    assert main(["serve", "--repo", str(root), "--no-browser", "--check"]) == 0

    assert "?token=kept-across-restarts" in capsys.readouterr().out


def _fake_kilo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A ``kilo`` on the PATH that is FakeKilo; returns the file it records its start in."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = Path(__file__).resolve().parents[1] / "support" / "fake_kilo_cli.py"
    kilo = bin_dir / "kilo"
    kilo.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', "utf-8")
    kilo.chmod(kilo.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    record = tmp_path / "kilo-start.json"
    monkeypatch.setenv("FAKE_KILO_RECORD", str(record))
    return record


def _answers(url: str) -> bool:
    host, port = url.removeprefix("http://").split(":")
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex((host, int(port))) == 0


@pytest.mark.skipif(sys.platform == "win32", reason="the fake kilo is a shell script")
def test_serve_with_the_assistant_starts_kilo_in_the_project_and_stops_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    record = _fake_kilo(tmp_path, monkeypatch)
    capsys.readouterr()

    code = main(["serve", "--repo", str(root), "--no-browser", "--check", "--assistant",
                 "--assistant-model", "openai/gpt-5-mini"])  # fmt: skip

    out = capsys.readouterr().out
    assert code == 0, out
    started = json.loads(record.read_text("utf-8"))
    assert started["args"][:1] == ["serve"] and "--hostname" in started["args"]
    assert started["args"][started["args"].index("--hostname") + 1] == "127.0.0.1"
    assert started["cwd"] == str(root.resolve()) and started["password"] is True
    assert (root / ".kilo" / "kilo.json").is_file() and "wrote .kilo/kilo.json" in out
    line = next(row for row in out.splitlines() if row.startswith("Assistant:"))
    assert line.startswith("Assistant: Kilo (agent controlm, model openai/gpt-5-mini) at http")
    assert not _answers(line.rsplit(" at ", 1)[1])  # stopped with the server


@pytest.mark.skipif(sys.platform == "win32", reason="the fake kilo is a shell script")
def test_serve_with_the_assistant_keeps_the_kilo_files_there(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _fake_kilo(tmp_path, monkeypatch)
    assert main(["kilo", "init", "--repo", str(root)]) == 0
    capsys.readouterr()

    assert main(["serve", "--repo", str(root), "--no-browser", "--check", "--assistant"]) == 0

    out = capsys.readouterr().out
    assert "wrote .kilo" not in out and "model Kilo's own" in out


@pytest.mark.skipif(sys.platform == "win32", reason="the fake kilo is a shell script")
def test_serve_with_an_assistant_that_cannot_start_says_where_its_log_is(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    _fake_kilo(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_KILO_FAIL", "1")

    code = main(["serve", "--repo", str(root), "--no-browser", "--check", "--assistant"])

    err = capsys.readouterr().err
    assert code == 3 and "kilo serve stopped" in err and "kilo-serve" in err


def test_serve_with_the_assistant_without_kilo_says_how_to_install_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))  # no kilo there

    code = main(["serve", "--repo", str(root), "--no-browser", "--check", "--assistant"])

    assert code == 3 and "npm install -g @kilocode/cli" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.parametrize("stop", [signal.SIGTERM, signal.SIGHUP])
def test_a_server_stopped_by_a_signal_stops_its_kilo_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop: signal.Signals
) -> None:
    root = _repo(tmp_path)
    _fake_kilo(tmp_path, monkeypatch)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = subprocess.Popen(
        [sys.executable, "-m", "controlm_chain_admin", "serve", "--repo", str(root),
         "--port", str(port), "--no-browser", "--assistant"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )  # fmt: skip
    try:
        assert server.stdout is not None
        line = ""
        deadline = time.monotonic() + 60
        while not line.startswith("Assistant:") and time.monotonic() < deadline:
            line = server.stdout.readline()
        kilo = line.rsplit(" at ", 1)[1].strip()
        while not _answers(f"http://127.0.0.1:{port}") and time.monotonic() < deadline:
            time.sleep(0.1)
        assert _answers(kilo)

        server.send_signal(stop)
        server.wait(timeout=30)

        assert not _answers(kilo)
    finally:
        if server.poll() is None:
            server.kill()
