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
# A large repository takes seconds to load, and comparing two of its environments several
# times that on a slow disk: 30 s (the value up to 0.2.0) left little room on Windows.
SERVER_TIMEOUT_MS = 120_000
SKILL_DESCRIPTION = (
    "Answer questions about the Control-M chains and change them (fields, variables, "
    "exceptions of one environment, conditions, renames, moves), compare two environments, "
    "take what one has into another and build the import file for production, with the "
    "ctmchain MCP tools: find, show, compare, takeable, package, preview, apply."
)
QUESTIONS = (
    "menu", "find", "show", "condition", "validate", "compare", "envmap", "takeable",
    "package", "refresh", "preview",
)  # fmt: skip
ASKED = ("apply", "write_package")  # the tools that write: Kilo asks the user first

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
        "permission": {"ctmchain_*": "allow"} | {f"ctmchain_{tool}": "ask" for tool in ASKED},
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


def _wrapped(words: list[str], width: int = 92) -> str:
    """The words separated by commas, in lines no longer than ``width``."""
    lines = [""]
    for word in words:
        if lines[-1] and len(lines[-1]) + len(word) + 2 > width:
            lines.append("")
        lines[-1] += f"{word}, "
    return "\n".join(line.rstrip() for line in lines).rstrip(",")


def _agent() -> str:
    asked = "\n".join(f"  ctmchain_{tool}: ask" for tool in ASKED)
    tools = _wrapped([f"ctmchain_{tool}" for tool in (*QUESTIONS, *ASKED)])
    return f"""---
description: Questions and changes on the Control-M chains, through the ctmchain tools only
mode: primary
permission:
  edit: deny
  bash: deny
  webfetch: deny
  websearch: deny
  "ctmchain_*": allow
{asked}
---
You answer questions about a Control-M chain repository and change it, with the ctmchain
tools only:
{tools}.

{_workflow()}

Start with ctmchain_menu when you do not know which capability fits. The skill {SKILL} has
the words of this team (vocabulary.md): read it when a word of the request is not a
Control-M name.
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

## Between environments

With one branch per environment (ctmchain_envmap says so: production on the trunk, env/<name>
for every other one), the names, users and machines differ by rule and the tools read through
them: what is left is what really differs.

1. ctmchain_compare with base and head (main, env/uat, ...) gives the real differences; a
   warning "kept as it is" names the entries that explain one value: pass prefer=[entry].
2. ctmchain_takeable with head gives the items the branch checked out can take, with their
   ids. Take them with the capability take: ctmchain_preview with
   [{{"do": "take", "params": {{"head": "env/uat", "items": ["<id>", ...]}}}}], then
   ctmchain_apply. A conflict names the item and its three values: leave it out, or name it
   in theirs once the user chose.
3. Production is never changed here: ctmchain_package with base main, the head and
   take=[ids] says what its import file would hold; ctmchain_write_package writes that file
   once the user agrees (Kilo asks them). The user imports it in Control-M.
4. ctmchain_refresh with the path of a full export says what it would change in the branch
   of its environment. The user applies it (ctmchain refresh FILE --apply): it switches the
   branch and commits, which these tools never do.
5. Any other branch is the user's own work. It holds the environment of the last export put
   onto it, else of the branch it started from, and the tools above read it like that
   environment's branch. ctmchain_refresh with here=true says what an export would change in
   the branch checked out, and the branch of the environment stays as it is; add
   partial=true when the export holds some folders only (the others stay). The user applies
   it: ctmchain refresh FILE --here --apply, with --partial for some folders only.

## Local words

vocabulary.md, next to this file, has the words of this team and what they mean in
Control-M. Read it when a word of the request is not a Control-M name.
"""
