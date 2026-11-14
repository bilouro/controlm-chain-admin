---
description: "Ask about your Control-M chains in plain words: the MCP tools of controlm-chain-admin for an assistant such as Kilo or Claude."
---

# Assistant

`ctmchain mcp` gives an assistant (Kilo, Claude, any MCP client) the repository as tools.
It answers questions and proposes changes, previewed field by field, and writes only when
you agree.

```bash
pip install "controlm-chain-admin[mcp]"
ctmchain kilo init --repo .       # writes .kilo/: the server, the controlm agent, the skill
kilo --agent controlm             # or: ctmchain serve --assistant
```

After an upgrade that brings new tools, run `ctmchain kilo init --repo . --force`: it
rewrites the agent and keeps your `vocabulary.md`.

## When the assistant has no tools

`.kilo/kilo.json` starts the server with the full path of the repository and of Python. A
folder that moved, or a virtual environment made again, leaves it pointing nowhere: the
assistant then says the ctmchain tools are not available and searches the files by hand.
`ctmchain serve --assistant` repairs the path by itself when it starts; with `kilo` alone,
run `ctmchain kilo init --repo . --force`. To see the error, start the server by hand: it
must wait in silence.

```bash
python -m controlm_chain_admin mcp --repo .
```

Ask "call ctmchain_menu and tell me what it returns": the list of capabilities means the
tools are there.

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

`vocabulary.md`, next to the agent, holds the words of your team and what they mean in
Control-M: the assistant reads it when a word of the request is not a Control-M name.
