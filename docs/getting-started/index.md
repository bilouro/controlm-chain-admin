---
description: "Install controlm-chain-admin and build a chain repository from the full exports of each environment."
---

# Installation & Quickstart

## Requirements

- Python 3.11 or newer.
- git.
- One **full export** of each environment (Control-M *Export* of the folders, as XML).

## Install

```bash
pip install "controlm-chain-admin[web,mcp]"
ctmchain --version
```

The core has no dependency outside the standard library. `[web]` adds the local web UI
(`ctmchain serve`), `[mcp]` the tools for an assistant (`ctmchain mcp`).

## From zero

The repository holds the chains of **one** Control-M application. Four things describe it:
its `APPLICATION`, the letter of each environment, the prefixes that carry that letter, and
which of them carry it only at the start of a name.

```bash
mkdir chains && cd chains
git init -b main
ctmchain init --application P77_RISK_ENGINE \
    --envs prod=P,uat=U,bench=B \
    --prefixes P77,RQ_,RC_ --leading-only RQ_,RC_
git add -A && git commit -m "chore: the rules"
```

Each environment gets its branch from its export. `main` is production; every other
environment is `env/<name>`:

```bash
ctmchain refresh ../exports/prod.xml --apply
ctmchain refresh ../exports/uat.xml --apply
ctmchain refresh ../exports/bench.xml --apply
git switch main
```

Without `--apply`, `refresh` only shows what the export would change.

Prove that each branch gives its export back, byte for byte:

```bash
ctmchain check ../exports/prod.xml --env prod
```

Then the map of what varies between the environments:

```bash
ctmchain envmap derive            # what the branches show
ctmchain envmap derive --apply    # into the map
ctmchain envmap show
```

Now the environments can be compared:

```bash
ctmchain compare main env/uat
```

## The web UI

```bash
ctmchain serve
```

It prints a local address with a session token; open it in a browser. Nothing leaves your
machine: the server listens on `127.0.0.1` only.

## Upgrading

```bash
pip install --upgrade "controlm-chain-admin[web,mcp]"
```

A new version reads the repository of an earlier one as it is. Restart `ctmchain serve`
after an upgrade, and run `ctmchain kilo init --force` when the release notes say the
assistant got new tools.
