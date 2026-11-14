"""The Kilo project files: the MCP server's command follows the repository when it moves."""

from __future__ import annotations

import json
from pathlib import Path

from controlm_chain_admin.core.kilo import CONFIG, kilo_files, repair_command, write_files


def _command(target: Path) -> list[str]:
    config = json.loads((target / CONFIG).read_text("utf-8"))
    return list(config["mcp"]["ctmchain"]["command"])


def test_the_command_follows_a_repository_that_moved(tmp_path: Path) -> None:
    """The folder was written from elsewhere (moved, or copied from another machine): the
    server would be started on a repository that is not there."""
    old, new = tmp_path / "old" / "chains", tmp_path / "new" / "chains"
    new.mkdir(parents=True)
    write_files(new, kilo_files(old, "/old/venv/python"))
    config = json.loads((new / CONFIG).read_text("utf-8"))
    config["permission"]["ctmchain_find"] = "ask"  # somebody's own choice: it stays
    (new / CONFIG).write_text(json.dumps(config), "utf-8")

    assert repair_command(new, new, "/new/venv/python") is True

    assert _command(new) == [
        "/new/venv/python", "-m", "controlm_chain_admin", "mcp", "--repo", str(new.resolve()),
    ]  # fmt: skip
    kept = json.loads((new / CONFIG).read_text("utf-8"))
    assert kept["permission"]["ctmchain_find"] == "ask"
    assert kept["mcp"]["ctmchain"]["enabled"] is True


def test_a_command_that_is_right_is_left_alone(tmp_path: Path) -> None:
    write_files(tmp_path, kilo_files(tmp_path, "/venv/python"))
    before = (tmp_path / CONFIG).read_bytes()

    assert repair_command(tmp_path, tmp_path, "/venv/python") is False
    assert (tmp_path / CONFIG).read_bytes() == before


def test_a_configuration_that_cannot_be_read_or_has_no_server_is_left_alone(
    tmp_path: Path,
) -> None:
    assert repair_command(tmp_path, tmp_path, "/venv/python") is False  # no file
    (tmp_path / ".kilo").mkdir()
    for text in ("not json", '{"mcp": {}}', '{"mcp": {"ctmchain": {"command": "own"}}}'):
        (tmp_path / CONFIG).write_text(text, "utf-8")
        assert repair_command(tmp_path, tmp_path, "/venv/python") is False
        assert (tmp_path / CONFIG).read_text("utf-8") == text
