---
description: "Ask about your Control-M chains in plain words: the tools of controlm-chain-admin for an assistant such as Kilo, as a command or over MCP."
---

# Assistant

An assistant (Kilo, or any assistant that runs commands or speaks MCP) gets the repository
as tools. It answers questions and proposes changes, previewed field by field, and writes
only when you agree.

The same tools reach it in one of two ways:

| | By command (the default) | Over MCP |
|---|---|---|
| What the agent runs | `python -m ctmadmin_service <tool> ...` | the tools of the MCP server `ctmchain mcp` |
| Needs | nothing more than the package | the `[mcp]` extra, and MCP servers allowed |
| Works where MCP servers are blocked | yes | no |

```bash
pip install "controlm-chain-admin[web]"
ctmchain kilo init --repo .       # writes .kilo/agents/controlm.md and vocabulary.md
ctmchain serve --assistant        # the web UI with its Assistant panel; or: kilo --agent controlm
```

Start `kilo` yourself with the package's environment active, so that `python` is the one
that has it; `ctmchain serve --assistant` sees to that by itself. Where MCP servers are
allowed, `ctmchain kilo init --repo . --via mcp` (with `pip install
"controlm-chain-admin[mcp]"`) sets the agent up over MCP instead.

After an upgrade that brings new tools, run `ctmchain kilo init --repo . --force`: it
rewrites the agent and keeps your `vocabulary.md`.

## The command

`python -m ctmadmin_service help` says how to call every tool and how to work;
`help <tool>` and `help <capability>` give the parameters and a command to copy. Every tool
prints JSON (`menu`, `compare` and `refresh`: text).

```bash
python -m ctmadmin_service find P77_LOAD
python -m ctmadmin_service show P77_CHAIN/P77_B
python -m ctmadmin_service preview set-resource --nodes P77_CHAIN/P77_A --nodes P77_CHAIN/P77_B --name RQ_AM
python -m ctmadmin_service apply <preview_id>
```

Values never travel as JSON on the command line, which shells mangle: a list repeats its
flag, a map takes `KEY=VALUE` per entry (`--changes MAXWAIT=3`), and `null` means none.
`preview` prints the `preview_id`; `apply` takes that id alone and is refused when the
repository changed since. Changes that belong together: `preview` the next one with
`--after <preview_id>` and apply the last id.

The agent may run this command and no other, and may not edit files; Kilo asks you before
each call that writes (`apply`, `write_package`, `keep_delivery`, `remove_delivery`,
`write_delivery_package`). The rules are in `.kilo/agents/controlm.md`.

## When the assistant has no tools

- **By command.** The agent says `No module named ctmadmin_service`: Kilo was started
  without the package's environment. Activate it and start Kilo again, or use
  `ctmchain serve --assistant`.
- **Over MCP.** A company policy may block MCP servers: `kilo mcp list` then shows
  `ctmchain disabled`, and `kilo mcp list --print-logs --log-level DEBUG` says why. Set the
  agent up by command instead (`ctmchain kilo init --repo . --force`). `.kilo/kilo.json`
  also holds the full paths of the repository and of Python: `ctmchain serve --assistant`
  repairs them when the folder moved.

A job can be named as Control-M shows it, with the letter of its environment (`UP77_LOAD`):
it is found as `P77_LOAD`, the name kept here.

## What you can ask

- "What does uat have that production has not?"
- "What does P77_B wait for? Who waits for it?"
- "Which items of uat can bench take?" and then "take the job P77_NEW into this branch."
- "The import file for production with the folder P77_WEEKLY_DAILY of uat."
- "Keep the new job of uat as a delivery called friday." and "Which deliveries are kept?"
- "What would the export ../exports/uat.xml change?"
- "Which jobs use the resource RQ_AM?" and "P77_A and P77_B should take it too."
- "Is anything wrong with the chains?"

## What it does and never does

| Reads, without asking | Writes, after you approve |
|---|---|
| find, show, condition, validate, compare, envmap, takeable, package, refresh, deliveries, delivery_package, resources | apply (a change to the checked-out branch), write_package, keep_delivery, remove_delivery, write_delivery_package |

It never switches a branch, never commits or pushes, and never applies an export: it
previews one and tells you the command that applies it.

!!! warning "The model reads your data"
    The assistant's model reads the names and fields of your jobs. Use one your organisation
    allows.

`vocabulary.md` (`.kilo/skills/ctmchain/`) holds the words of your team and what they mean
in Control-M: the assistant reads it when a word of the request is not a Control-M name.
