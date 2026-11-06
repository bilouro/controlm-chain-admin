"""The files that set Kilo up to work on a chain repository through ``ctmchain mcp``.

``.kilo/kilo.json`` starts the MCP server with this Python and this repository (paths of this
machine: every person runs ``ctmchain kilo init``); ``.kilo/agents/controlm.md`` is an agent
that may use the ctmchain tools and may not edit files or run commands;
``.kilo/skills/ctmchain/`` tells any agent how to work, with ``vocabulary.md`` for the words of
the team (written once, never overwritten). The text comes from the capabilities file.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from controlm_chain_admin.core.capabilities import load_catalogue

AGENT = "controlm"
SKILL = "ctmchain"
CONFIG = ".kilo/kilo.json"
AGENT_FILE = f".kilo/agents/{AGENT}.md"
SKILL_FILE = f".kilo/skills/{SKILL}/SKILL.md"
VOCABULARY_FILE = f".kilo/skills/{SKILL}/vocabulary.md"
SERVER_TIMEOUT_MS = 30000  # a large repository takes seconds to load
SKILL_DESCRIPTION = (
    "Answer questions about the Control-M chains and change them (fields, variables, "
    "exceptions of one environment, conditions, renames, moves) with the ctmchain MCP tools: "
    "find, show, preview, apply."
)

VOCABULARY = """# Local words

The words of this team and what they mean in Control-M, one per line, for example:

- agent: NODEID
- the morning chain: the folder P77_INGEST_DAILY
"""


@dataclass(frozen=True)
class Written:
    """What ``write_files`` did with one file: ``wrote`` or ``kept``."""

    path: str
    action: str


def project_dir(repo_root: Path) -> Path:
    """Where Kilo is opened: the top of the git repository holding the chains, else the
    chain repository itself."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:  # no git on this machine
        return repo_root.resolve()
    top = result.stdout.strip()
    return Path(top).resolve() if result.returncode == 0 and top else repo_root.resolve()


def kilo_files(repo_root: Path, python: str) -> dict[str, str]:
    """The content of every file, by its path in the Kilo project."""
    command = [python, "-m", "controlm_chain_admin", "mcp", "--repo", str(repo_root.resolve())]
    config = {
        "mcp": {
            "ctmchain": {
                "type": "local",
                "command": command,
                "enabled": True,
                "timeout": SERVER_TIMEOUT_MS,
            }
        },
        "permission": {"ctmchain_*": "allow", "ctmchain_apply": "ask"},
    }
    return {
        CONFIG: json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        AGENT_FILE: _agent(),
        SKILL_FILE: _skill(),
        VOCABULARY_FILE: VOCABULARY,
    }


def write_files(target: Path, files: dict[str, str], *, force: bool = False) -> list[Written]:
    """Write the files under ``target``; one there already is kept unless ``force`` (the
    vocabulary always is: it is the team's)."""
    report = []
    for relative, text in files.items():
        path = target / relative
        keep = path.exists() and (not force or relative == VOCABULARY_FILE)
        if not keep:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        report.append(Written(relative, "kept" if keep else "wrote"))
    return report


def _workflow() -> str:
    return "\n".join(f"- {rule}" for rule in load_catalogue().workflow)


def _agent() -> str:
    return f"""---
description: Questions and changes on the Control-M chains, through the ctmchain tools only
mode: primary
permission:
  edit: deny
  bash: deny
  webfetch: deny
  websearch: deny
  "ctmchain_*": allow
  ctmchain_apply: ask
---
You answer questions about a Control-M chain repository and change it, with the ctmchain
tools only (ctmchain_menu, ctmchain_find, ctmchain_show, ctmchain_condition,
ctmchain_validate, ctmchain_compare, ctmchain_preview, ctmchain_apply).

{_workflow()}

Start with ctmchain_menu when you do not know which capability fits. The skill {SKILL} has
the words of this team (vocabulary.md): read it when a word of the request is not a
Control-M name. Answer in the language of the user.
"""


def _skill() -> str:
    return f"""---
name: {SKILL}
description: {SKILL_DESCRIPTION}
---
# Working on the Control-M chains with ctmchain

{_workflow()}

## How

1. ctmchain_menu lists what can be asked; ctmchain_menu with capability=<id> gives its
   parameters, rules and an example.
2. ctmchain_find and ctmchain_show give the exact nodes (FOLDER/JOB, FOLDER/) and values.
3. ctmchain_preview with steps [{{"do": "<capability>", "params": {{...}}}}] shows each field
   before -> after; tell the user.
4. ctmchain_apply with the same steps and the preview_id writes it once the user approves it
   (Kilo asks them). Nothing is committed: the user commits.

## Local words

vocabulary.md, next to this file, has the words of this team and what they mean in
Control-M. Read it when a word of the request is not a Control-M name.
"""
