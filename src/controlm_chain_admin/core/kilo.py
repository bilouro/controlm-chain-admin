"""The files that set Kilo up to work on a chain repository.

Two ways, the same tools (:mod:`~controlm_chain_admin.tools`):

* by command (the default): ``.kilo/agents/controlm.md`` is an agent that may run
  ``python -m ctmadmin_service`` and nothing else, and is asked before each call that writes.
  It works wherever a command runs, also where a company policy blocks MCP servers;
* over MCP (``via="mcp"``): ``.kilo/kilo.json`` starts ``ctmchain mcp`` with this Python and this
  repository (paths of this machine: every person runs ``ctmchain kilo init``), the agent may
  use the ctmchain tools only, and ``.kilo/skills/ctmchain/`` tells any agent how to work.

Both keep ``vocabulary.md`` for the words of the team (written once, never overwritten). The
text comes from the capabilities file.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from controlm_chain_admin.core.capabilities import load_catalogue

AGENT = "controlm"
#: how the agent reaches the tools: a command (works everywhere) or an MCP server
VIA_SERVICE, VIA_MCP = "service", "mcp"
SERVICE_COMMAND = "python -m ctmadmin_service"
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
    "package", "refresh", "preview", "deliveries", "delivery_package", "resources",
)  # fmt: skip
#: the tools that write: Kilo asks the user first
ASKED = ("apply", "write_package", "keep_delivery", "remove_delivery", "write_delivery_package")

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


def kilo_files(
    repo_root: Path, python: str, *, via: str = VIA_SERVICE, project: Path | None = None
) -> dict[str, str]:
    """The content of every file, by its path in the Kilo project (``project``: where Kilo is
    opened, which runs the commands there)."""
    if via == VIA_SERVICE:
        return {AGENT_FILE: _service_agent(service_command(repo_root, project)),
                VOCABULARY_FILE: VOCABULARY}  # fmt: skip
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


def repair_command(target: Path, repo_root: Path, python: str) -> bool:
    """Point the MCP server of ``.kilo/kilo.json`` at this repository and this Python when it
    points elsewhere (the folder moved, the virtual environment was made again): Kilo would
    start a server that cannot run, and the assistant would have no tool. True when the file
    was rewritten; the rest of it, and a command that is not ours, stay as they are."""
    path = target / CONFIG
    try:
        config = json.loads(path.read_text("utf-8"))
        server = config["mcp"]["ctmchain"]
        current = server["command"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    wanted = [python, "-m", "controlm_chain_admin", "mcp", "--repo", str(repo_root.resolve())]
    ours = isinstance(current, list) and current[1:4] == wanted[1:4]
    if not ours or current == wanted:
        return False
    server["command"] = wanted
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", "utf-8", newline="\n")
    return True


def service_command(repo_root: Path, project: Path | None = None) -> str:
    """The command the agent runs, run in ``project``: with ``--repo`` when the chain
    repository is somewhere else below it."""
    root = Path(repo_root).resolve()
    if project is None or root == Path(project).resolve():
        return SERVICE_COMMAND
    try:
        where = root.relative_to(Path(project).resolve()).as_posix()
    except ValueError:
        where = root.as_posix()
    quoted = f'"{where}"' if " " in where else where
    return f"{SERVICE_COMMAND} --repo {quoted}"


def command_rules(command: str) -> list[str]:
    """How an assistant works with the tools as commands: how to call them, then the rules
    of the capabilities file, where they speak of apply and of steps, in command terms."""
    own = [
        f"Run {command} help at the start of a conversation: it says how to call each tool; "
        f"{command} help <tool> or help <capability> gives the parameters and a command to "
        "copy. Run no other command, and use no other tool to read the repository: everything "
        "is in this command (on some machines the other tools cannot run).",
        "A name with the letter of an environment (UP77_X, as Control-M shows it) is found "
        "without it: the names here carry no letter.",
        f"A change is {command} preview <capability> --param value ...: it prints each field "
        "before -> after, the warnings and a preview_id.",
    ]
    replaced = {
        "Then call apply": (
            f"Then run {command} apply <preview_id>: the user is asked to allow it before it "
            "runs, so do not ask for a yes in the text as well. Only preview when the user "
            "asked only to see the change."
        ),
        "Changes that belong together": (
            "Changes that belong together go in one change: preview the first, then each next "
            "one with --after <the preview_id before it>, in the order they must run, and "
            "apply the last preview_id."
        ),
    }
    rules = []
    for rule in load_catalogue().workflow:
        start = next((key for key in replaced if rule.startswith(key)), None)
        rules.append(replaced[start] if start else rule)
    return [rules[0], *own, *rules[1:]]


def _service_agent(command: str) -> str:
    asked = "".join(f'    "{command} {tool} *": ask\n' for tool in ASKED)
    rules = "\n".join(f"- {rule}" for rule in command_rules(command))
    tools = _wrapped([*QUESTIONS, "preview", *ASKED])
    return f"""---
description: Questions and changes on the Control-M chains, through {SERVICE_COMMAND} only
mode: primary
permission:
  edit: deny
  webfetch: deny
  websearch: deny
  bash:
    "*": deny
    "{command} *": allow
{asked}---
You answer questions about a Control-M chain repository and change it with one command:
{command} <tool> [value ...] [--name value ...]. Its tools:
{tools}.
Kilo asks the user before each of {", ".join(ASKED)}.

{rules}

The words of this team are in {VOCABULARY_FILE}: read that file when a word of the request is
not a Control-M name.
"""


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
   The names here carry no environment letter: a job the user calls UP77_LOAD (as Control-M
   shows it in uat) is P77_LOAD. Drop the letter before you look; ctmchain_find does it too
   and says so in read_as.
3. ctmchain_preview with steps [{{"do": "<capability>", "params": {{...}}}}] shows each field
   before -> after; tell the user.
4. ctmchain_apply with the same steps and the preview_id writes it once the user approves it
   (Kilo asks them). Nothing is committed: the user commits.
5. ctmchain_resources lists the CONTROL and QUANTITATIVE resources with the jobs that use
   each; the capabilities set-resource and remove-resource give one to several jobs at
   once, or take it off.

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
6. What the user wants to send later is kept as a delivery: ctmchain_keep_delivery with a
   name, the branch the items come from (head) and their ids, as ctmchain_takeable gives
   them or as the user names them (job:FOLDER/JOB, attr:FOLDER/JOB@NAME, folder:FOLDER).
   ctmchain_deliveries lists what is kept. ctmchain_delivery_package with the target branch
   and the names says what one import file with several of them would hold;
   ctmchain_write_delivery_package writes it and ctmchain_remove_delivery forgets one (Kilo
   asks the user before each of the three that write). A delivery is as its branch was on
   the day it was kept.

## Local words

vocabulary.md, next to this file, has the words of this team and what they mean in
Control-M. Read it when a word of the request is not a Control-M name.
"""
