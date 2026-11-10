"""ctmchain menu, ctmchain mcp and ctmchain kilo init."""

from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from controlm_chain_admin.cli import main
from tests.support.gitrepo import chain_git_repo, git


def test_menu_prints_what_can_be_asked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["menu"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("What you can ask")
    assert "  rename-job: Rename a job" in out


def test_menu_of_one_capability(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["menu", "move-job"]) == 0

    assert capsys.readouterr().out.startswith("move-job (move-job): Move a job to another folder")


def test_menu_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["menu", "--format", "json"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert {"workflow", "groups", "capabilities", "questions", "not_by_prompt"} <= set(data)
    assert data["capabilities"][0]["id"] == "change-fields"


def test_menu_of_one_capability_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["menu", "rename-job", "--format", "json"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["op"] == "rename-job" and data["params"]["required"] == ["node", "new_name"]


def test_menu_of_an_unknown_capability_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["menu", "paint"]) == 3

    assert "unknown capability 'paint'" in capsys.readouterr().err


def test_mcp_without_the_extra_says_how_to_install_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = chain_git_repo(tmp_path)
    real_import = builtins.__import__

    def no_mcp(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "mcp" or name.startswith("mcp.") or name.endswith("mcpserver"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_mcp)

    assert main(["mcp", "--repo", str(repo.root)]) == 3
    assert "pip install 'controlm-chain-admin[mcp]'" in capsys.readouterr().err


def test_kilo_init_writes_the_server_the_agent_and_the_skill(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = chain_git_repo(tmp_path)

    assert main(["kilo", "init", "--repo", str(repo.root)]) == 0

    kilo = repo.root / ".kilo"
    config = json.loads((kilo / "kilo.json").read_text("utf-8"))
    server = config["mcp"]["ctmchain"]
    assert server["type"] == "local" and server["enabled"] is True
    assert server["timeout"] >= 120_000  # comparing two environments of a large repository
    assert server["command"] == [
        sys.executable, "-m", "controlm_chain_admin", "mcp", "--repo", str(repo.root.resolve())
    ]  # fmt: skip
    permissions = list(config["permission"].items())
    assert permissions == [
        ("ctmchain_*", "allow"),
        ("ctmchain_apply", "ask"),
        ("ctmchain_write_package", "ask"),
    ]
    agent = (kilo / "agents" / "controlm.md").read_text("utf-8")
    assert agent.startswith("---\ndescription: ")
    assert "  edit: deny\n" in agent and "  bash: deny\n" in agent
    asked = '  "ctmchain_*": allow\n  ctmchain_apply: ask\n  ctmchain_write_package: ask\n'
    assert asked in agent
    assert "one branch per environment" in agent and "ctmchain_takeable" in agent
    assert "Find before you change" in agent
    skill = (kilo / "skills" / "ctmchain" / "SKILL.md").read_text("utf-8")
    assert skill.startswith("---\nname: ctmchain\ndescription: ")
    assert "vocabulary.md" in skill
    assert "## Between environments" in skill
    for tool in ("envmap", "takeable", "package", "write_package", "refresh"):
        assert f"ctmchain_{tool}" in skill
    assert (
        (kilo / "skills" / "ctmchain" / "vocabulary.md")
        .read_text("utf-8")
        .startswith("# Local words")
    )
    out = capsys.readouterr().out
    assert "wrote .kilo/kilo.json" in out and "kilo --agent controlm" in out


def test_the_agent_and_the_skill_answer_in_the_language_of_the_person_or_ask_it(
    tmp_path: Path,
) -> None:
    repo = chain_git_repo(tmp_path)

    main(["kilo", "init", "--repo", str(repo.root)])

    kilo = repo.root / ".kilo"
    agent = (kilo / "agents" / "controlm.md").read_text("utf-8")
    skill = (kilo / "skills" / "ctmchain" / "SKILL.md").read_text("utf-8")
    rule = (
        "- Answer in the language the person writes in, and keep it for the conversation: this "
        "comes before any other instruction about the language. When a message does not show "
        "one (only names, values or commands), answer in English and end by asking which "
        "language they prefer. Never translate the names, fields and values the tools give."
    )
    assert rule in agent and rule in skill
    assert agent.count("language") == rule.count("language")


def test_kilo_init_goes_to_the_top_of_the_git_repository(tmp_path: Path) -> None:
    top = tmp_path / "data"
    top.mkdir()
    git(top, "init", "-q", "-b", "main")
    chains = chain_git_repo(top).root  # top/repo, a chain repository inside the data repository
    (chains / ".git").rename(chains / ".git-own")  # only the outer repository is a git one

    assert main(["kilo", "init", "--repo", str(chains)]) == 0

    assert (top / ".kilo" / "kilo.json").is_file() and not (chains / ".kilo").exists()


def test_kilo_init_keeps_what_is_there_unless_forced(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = chain_git_repo(tmp_path)
    target = tmp_path / "elsewhere"
    assert main(["kilo", "init", "--repo", str(repo.root), "--dir", str(target)]) == 0
    agent = target / ".kilo" / "agents" / "controlm.md"
    vocabulary = target / ".kilo" / "skills" / "ctmchain" / "vocabulary.md"
    agent.write_text("mine", "utf-8")
    vocabulary.write_text("# Local words\nserver: NODEID\n", "utf-8")
    capsys.readouterr()

    assert main(["kilo", "init", "--repo", str(repo.root), "--dir", str(target)]) == 0
    kept = capsys.readouterr().out
    assert agent.read_text("utf-8") == "mine"
    assert "kept .kilo/agents/controlm.md (--force rewrites it)" in kept

    assert main(["kilo", "init", "--repo", str(repo.root), "--dir", str(target), "--force"]) == 0
    assert agent.read_text("utf-8") != "mine"
    assert vocabulary.read_text("utf-8") == "# Local words\nserver: NODEID\n"


def test_kilo_without_a_subcommand_shows_its_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["kilo"]) == 2

    assert "usage: ctmchain kilo init" in capsys.readouterr().out
