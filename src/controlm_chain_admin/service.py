"""``python -m ctmadmin_service``: the assistant's tools as commands, one per call.

Where an MCP server is not allowed (a company policy may block them) an assistant can still run
commands: this is the same :class:`~controlm_chain_admin.tools.ChainTools` as ``ctmchain mcp``,
called as ``python -m ctmadmin_service <tool> [value ...] [--name value ...]``, printing JSON
(text for ``menu``, ``compare`` and ``refresh``). ``help`` says how to call and how to work,
``help <tool>`` or ``help <capability>`` the parameters and a command to copy.

A change is ``preview <capability> --param value ...``, which prints the ``preview_id`` and
keeps its steps (:mod:`~controlm_chain_admin.core.previews`), then ``apply <preview_id>``,
which an assistant is configured to ask the user for. Values never travel as JSON on the command
line, which shells mangle (PowerShell above all): lists repeat their flag, a map takes
``KEY=VALUE`` per entry, ``null`` is null. The standard library only, like the core.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import types
import typing
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from controlm_chain_admin import __version__
from controlm_chain_admin.core import previews
from controlm_chain_admin.core.capabilities import Capability, load_catalogue, render_menu
from controlm_chain_admin.core.errors import ChainError
from controlm_chain_admin.core.kilo import command_rules
from controlm_chain_admin.tools import WRITERS, ChainTools, error_message

COMMAND = "python -m ctmadmin_service"
REPO_VARIABLE = "CTMCHAIN_REPO"
#: tools that print text, not JSON
TEXT = frozenset({"menu", "compare", "refresh"})
#: a command to copy, by tool
EXAMPLES = {
    "menu": "menu --capability change-fields",
    "find": "find P77_LOAD",
    "show": "show P77_CHAIN/P77_B",
    "condition": "condition P77_A-P77_B_OK",
    "validate": "validate --limit 10",
    "compare": "compare main env/uat --real_only",
    "envmap": "envmap",
    "takeable": "takeable env/uat",
    "package": "package main --take job:FOLDER/JOB",
    "write_package": "write_package main --take job:FOLDER/JOB",
    "resources": "resources --name RQ_",
    "deliveries": "deliveries",
    "keep_delivery": 'keep_delivery "next release" env/uat --items job:FOLDER/JOB',
    "remove_delivery": 'remove_delivery "next release"',
    "delivery_package": 'delivery_package main --names "next release"',
    "write_delivery_package": 'write_delivery_package main --names "next release"',
    "refresh": "refresh exports/uat.xml",
    "preview": "preview change-fields --nodes P77_CHAIN/P77_B --changes MAXWAIT=3",
    "apply": "apply <preview_id>",
}
EXIT_OK, EXIT_USAGE, EXIT_ERROR = 0, 2, 3
_TRUE, _FALSE = {"true", "yes", "1"}, {"false", "no", "0"}


class UsageError(Exception):
    """A call this module cannot run as written: what to correct, and which help to read."""

    def __init__(self, message: str, topic: str | None = None) -> None:
        super().__init__(message)
        self.topic = topic


@dataclass(frozen=True)
class Param:
    """One parameter of a tool or a capability, as a flag."""

    name: str
    kind: str  # text, number, flag, list, map
    required: bool
    nullable: bool = False
    description: str = ""

    def words(self) -> str:
        said = {
            "text": "text",
            "number": "a whole number",
            "flag": "true or false (the flag alone: true)",
            "list": "text, repeat it for several",
            "map": "KEY=VALUE, repeat it for several",
        }[self.kind]
        return said + (" (null: none)" if self.nullable else "")


# ---------------------------------------------------------------- parameters


def _kind(annotation: Any) -> tuple[str, bool]:
    """The kind of a Python annotation, and whether it takes None."""
    args = typing.get_args(annotation)
    nullable = type(None) in args
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        annotation = next(a for a in args if a is not type(None))
    if typing.get_origin(annotation) is list:
        return "list", nullable
    return {bool: "flag", int: "number"}.get(annotation, "text"), nullable


def tool_params(method: Callable[..., Any]) -> list[Param]:
    """The parameters of one method of :class:`ChainTools`, in their order."""
    hints = typing.get_type_hints(method)
    found = []
    for name, parameter in inspect.signature(method).parameters.items():
        if name == "self":
            continue
        kind, nullable = _kind(hints[name])
        required = parameter.default is inspect.Parameter.empty
        found.append(Param(name, kind, required, nullable))
    return found


def capability_params(capability: Capability) -> list[Param]:
    """The parameters of a capability, from its JSON Schema."""
    required = set(capability.params.get("required", []))
    found = []
    for name, schema in capability.params.get("properties", {}).items():
        types_ = schema.get("type")
        types_ = types_ if isinstance(types_, list) else [types_]
        kind = {"array": "list", "object": "map", "boolean": "flag", "integer": "number"}.get(
            next(t for t in types_ if t != "null"), "text"
        )
        nullable = "null" in types_
        if kind == "map":
            values = schema.get("additionalProperties", {}).get("type")
            nullable = isinstance(values, list) and "null" in values
        description = schema.get("description", "")
        found.append(Param(name, kind, name in required, nullable, description))
    return found


def _flag(token: str) -> str:
    return token[2:].replace("-", "_")


def _value(param: Param, text: str, where: str) -> Any:
    if param.nullable and text == "null":
        return None
    if param.kind == "number":
        try:
            return int(text)
        except ValueError:
            raise UsageError(f"--{param.name} takes a whole number, not {text!r}", where) from None
    if param.kind == "flag":
        if text.lower() not in _TRUE | _FALSE:
            raise UsageError(f"--{param.name} takes true or false, not {text!r}", where)
        return text.lower() in _TRUE
    return text


def _entry(param: Param, text: str, where: str) -> tuple[str, Any]:
    key, equals, value = text.partition("=")
    if not equals or not key:
        raise UsageError(f"--{param.name} takes KEY=VALUE (KEY=null: none), not {text!r}", where)
    return key, None if param.nullable and value == "null" else value


def parse(params: Sequence[Param], tokens: Sequence[str], where: str) -> dict[str, Any]:
    """The arguments of ``tokens``: ``--name value`` (or ``--name=value``), a flag alone is
    true, a list or a map repeats its flag; plain values fill the other parameters in order."""
    by_name = {p.name: p for p in params}
    given: dict[str, Any] = {}
    plain: list[str] = []
    rest = list(tokens)
    while rest:
        token = rest.pop(0)
        if not token.startswith("--") or token == "--":
            plain.append(token)
            continue
        name, equals, inline = _flag(token).partition("=")
        param = by_name.get(name)
        if param is None:
            known = ", ".join(f"--{p.name}" for p in params) or "no parameter"
            raise UsageError(f"{where} has no --{name}; it takes {known}", where)
        if param.kind == "flag" and not equals:
            given[name] = _value(param, rest.pop(0), where) if rest and rest[0].lower() in (
                _TRUE | _FALSE) else True  # fmt: skip
            continue
        if not equals:
            if not rest:
                raise UsageError(f"--{name} needs a value", where)
            inline = rest.pop(0)
        if param.kind == "list":
            given.setdefault(name, []).append(inline)
        elif param.kind == "map":
            key, value = _entry(param, inline, where)
            given.setdefault(name, {})[key] = value
        else:
            given[name] = _value(param, inline, where)
    open_ = [p for p in params if p.name not in given and p.kind in ("text", "number")]
    if len(plain) > len(open_):
        raise UsageError(f"too many values for {where}: {' '.join(plain)}", where)
    for param, text in zip(open_, plain, strict=False):
        given[param.name] = _value(param, text, where)
    missing = [p.name for p in params if p.required and p.name not in given]
    if missing:
        raise UsageError(f"{where} needs " + ", ".join(f"--{m}" for m in missing), where)
    return given


# ---------------------------------------------------------------- help


def _quoted(value: Any) -> str:
    text = "null" if value is None else str(value)
    return f'"{text}"' if not text or any(c in text for c in ' "&|<>^') else text


def command_of(capability: Capability) -> str:
    """The example of a capability as a preview command."""
    parts = [COMMAND, "preview", capability.id]
    kinds = {p.name: p.kind for p in capability_params(capability)}
    for name, value in capability.example.items():
        if kinds.get(name) == "list":
            parts += [item for v in value for item in (f"--{name}", _quoted(v))]
        elif kinds.get(name) == "map":
            parts += [i for k, v in value.items() for i in (f"--{name}", _quoted(f"{k}={v}"))]
        elif kinds.get(name) == "flag":
            parts += [f"--{name}", "true" if value else "false"]
        else:
            parts += [f"--{name}", _quoted(value)]
    return " ".join(parts)


def overview(catalogue_tools: Mapping[str, str]) -> str:
    """How to call, how to work, every tool and every capability."""
    catalogue = load_catalogue()
    lines = [
        f"ctmadmin_service {__version__}: tools over a Control-M chain repository (ctmchain), "
        "for an assistant that runs commands.",
        "",
        "How to call",
        f"  {COMMAND} <tool> [value ...] [--name value ...]",
        "  Plain values fill the parameters in order; --name value (or --name=value) any of them.",
        "  A list repeats its flag (--nodes A --nodes B); a map takes KEY=VALUE per entry",
        "  (--changes MAXWAIT=3 --changes MAXRERUN=2); null means none (--value null: remove it).",
        "  Quote a value with spaces in double quotes. Every tool prints JSON (menu, compare",
        "  and refresh: text). The repository: --repo DIR before the tool, else",
        f"  {REPO_VARIABLE}, else the current directory.",
        "",
        "How to work",
        *(f"- {rule}" for rule in command_rules(COMMAND)),
        "",
        "Tools (help <tool>: its parameters and a command to copy)",
    ]
    for name, description in catalogue_tools.items():
        first = description.split(". ")[0].rstrip(".")
        mark = " [asks the user]" if name in WRITERS else ""
        lines += [f"  {name}{mark}", f"      {first}."]
    lines += ["", "Capabilities, for preview (help <capability>: parameters, rules, example)"]
    lines += [f"  {c.signature}: {c.title}" for c in catalogue.capabilities]
    return "\n".join(lines) + "\n"


def tool_help(name: str, description: str, params: Sequence[Param]) -> str:
    lines = [f"{COMMAND} {name}", "", description, "", "Parameters:"]
    for param in params:
        flag = " (required)" if param.required else ""
        lines.append(f"  --{param.name}{flag}: {param.words()}")
    if name == "preview":
        lines += [
            "  <capability> first, then its parameters as flags (help <capability> lists them)",
            "  --after <preview_id>: this change comes after that preview, as one change",
            "  --steps-file FILE, or --steps - with the JSON on the input: steps "
            '[{"do": <capability>, "params": {...}}] as they are',
        ]
    lines += ["", "Example:", f"  {COMMAND} {EXAMPLES[name]}"]
    return "\n".join(lines) + "\n"


def capability_help(capability: Capability) -> str:
    flags = [f"  --{p.name}{' (required)' if p.required else ''}: {p.words()} - "
             f"{p.description}" for p in capability_params(capability)]  # fmt: skip
    return (
        render_menu(load_catalogue(), capability.id)
        + "\nAs flags of preview:\n" + "\n".join(flags)
        + f"\n\nAs a command:\n  {command_of(capability)}\n"
    )  # fmt: skip


# ---------------------------------------------------------------- tools


@dataclass(frozen=True)
class Service:
    """The tools of one repository, called by name with the tokens of a command line."""

    tools: ChainTools
    stdin: TextIO

    @property
    def root(self) -> Path:
        return self.tools.root

    def call(self, name: str, tokens: Sequence[str]) -> Any:
        if name == "preview":
            return self.preview(tokens)
        method = getattr(self.tools, name)
        params = tool_params(method)
        if name == "apply":
            params = [p for p in params if p.name != "steps"]
            preview_id = parse(params, tokens, name)["preview_id"]
            return method(previews.recall(self.root, preview_id), preview_id)
        return method(**parse(params, tokens, name))

    def preview(self, tokens: Sequence[str]) -> dict[str, Any]:
        rest = list(tokens)
        own = [Param("after", "text", False), Param("steps_file", "text", False),
               Param("steps", "text", False), Param("diff_lines", "number", False)]  # fmt: skip
        capability = None
        if rest and not rest[0].startswith("--"):
            capability = load_catalogue().get(rest.pop(0))
        mine, theirs = _split(rest, {p.name for p in own})
        options = parse(own, mine, "preview")
        steps = self._steps(options)
        if capability is not None:
            given = parse(capability_params(capability), theirs, capability.id)
            steps.append({"do": capability.id, "params": given})
        elif theirs:
            raise UsageError(f"preview has no {theirs[0]} without a capability", "preview")
        if not steps:
            raise UsageError("preview needs a capability (or --steps-file)", "preview")
        if options.get("after"):
            steps = previews.recall(self.root, options["after"]) + steps
        result = self.tools.preview(steps, diff_lines=options.get("diff_lines", 400))
        if result["preview_id"]:
            previews.remember(self.root, result["preview_id"], steps)
            result["apply"] = f"{COMMAND} apply {result['preview_id']}"
        return result

    def _steps(self, options: Mapping[str, Any]) -> list[dict[str, Any]]:
        if options.get("steps_file"):
            try:
                text = Path(options["steps_file"]).read_text("utf-8-sig")
            except OSError as exc:
                raise UsageError(f"cannot read the steps: {exc.strerror}", "preview") from exc
        elif options.get("steps") == "-":
            text = self.stdin.read().lstrip("﻿")
        elif options.get("steps"):
            text = options["steps"]
        else:
            return []
        try:
            data = json.loads(text)
        except ValueError:
            raise UsageError("the steps are not JSON: [{\"do\": ..., \"params\": {...}}]",
                             "preview") from None  # fmt: skip
        return list(data) if isinstance(data, list) else [data]


def _split(tokens: Sequence[str], names: set[str]) -> tuple[list[str], list[str]]:
    """The tokens of the flags ``names`` (with their values), and the others."""
    mine: list[str] = []
    theirs: list[str] = []
    rest = list(tokens)
    while rest:
        token = rest.pop(0)
        name = _flag(token).partition("=")[0] if token.startswith("--") else None
        target = mine if name in names else theirs
        target.append(token)
        if name and "=" not in token and rest and not rest[0].startswith("--"):
            target.append(rest.pop(0))
    return mine, theirs


# ---------------------------------------------------------------- main


def _utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


def _print(name: str, result: Any) -> None:
    if name in TEXT or isinstance(result, str):
        sys.stdout.write(result if str(result).endswith("\n") else f"{result}\n")
    else:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n")


def _usage(message: str, topic: str | None) -> int:
    where = f"{COMMAND} help {topic}" if topic else f"{COMMAND} help"
    sys.stderr.write(f"usage error: {message}\nsee: {where}\n")
    return EXIT_USAGE


def _help(tokens: Sequence[str], descriptions: Mapping[str, str]) -> str:
    if not tokens:
        return overview(descriptions)
    snake = tokens[0].replace("-", "_")
    topic = snake if snake in descriptions else tokens[0]
    if topic in descriptions:
        params = tool_params(getattr(ChainTools, topic))
        if topic == "apply":
            params = [p for p in params if p.name != "steps"]
        if topic == "preview":
            params = [p for p in params if p.name == "diff_lines"]
        return tool_help(topic, descriptions[topic], params)
    return capability_help(load_catalogue().get(topic))


#: where a tool is called otherwise than over MCP
AS_COMMANDS = {
    "menu": "What can be asked and how: every capability with an example; --capability <id> "
            "gives its parameters and rules.",
    "preview": "Preview a change without writing: preview <capability> --param value ... "
               "Prints each field before -> after, the warnings, the preview_id and the apply "
               "command; --after <preview_id> adds it to that change.",
    "apply": "Write a change previewed before, once the user agreed: apply <preview_id>. "
             "Refused when the repository changed since; nothing is committed.",
}  # fmt: skip


def _descriptions() -> dict[str, str]:
    """What each tool does, without a repository (help works anywhere)."""
    described = ChainTools.descriptions(_Bare())  # type: ignore[arg-type]
    return {name: AS_COMMANDS.get(name, text) for name, text in described.items()}


class _Bare:
    catalogue = load_catalogue()


def main(argv: Sequence[str] | None = None, *, stdin: TextIO | None = None) -> int:
    """Run one tool; 0 when it answered, 2 for a call to correct, 3 for an error."""
    args = list(sys.argv[1:] if argv is None else argv)
    if argv is None:
        _utf8(sys.stdout)
        _utf8(sys.stderr)
    root = os.environ.get(REPO_VARIABLE) or "."
    if args[:1] == ["--repo"] and len(args) > 1:
        root, args = args[1], args[2:]
    elif args[:1] and args[0].startswith("--repo="):
        root, args = args[0].partition("=")[2], args[1:]
    if args[:1] in (["--version"], ["-V"]):
        sys.stdout.write(f"ctmadmin_service {__version__}\n")
        return EXIT_OK
    if not args:
        return _usage(f"give a tool: {COMMAND} <tool> ...", None)
    name, tokens = args[0].replace("-", "_"), args[1:]
    descriptions = _descriptions()
    try:
        if name in ("help", "__help", "_h"):
            sys.stdout.write(_help(tokens, descriptions))
            return EXIT_OK
        if name not in descriptions:
            raise UsageError(f"unknown tool {args[0]!r}; the tools: {', '.join(descriptions)}")
        try:
            tools = ChainTools(Path(root))
        except ChainError as exc:
            sys.stderr.write(f"error: {exc} (give the repository with --repo DIR)\n")
            return EXIT_ERROR
        result = Service(tools, stdin or sys.stdin).call(name, tokens)
    except UsageError as exc:
        return _usage(str(exc), exc.topic)
    except ChainError as exc:
        if name == "preview" and "unknown capability" in str(exc):
            return _usage(str(exc), None)
        sys.stderr.write(f"error: {error_message(exc)}\n")
        return EXIT_ERROR
    _print(name, result)
    return EXIT_OK
