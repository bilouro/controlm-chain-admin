---
description: "Control-M job chains as JSON in git: one branch per environment, real differences only, and the import file already written for the environment that receives it."
---

# controlm-chain-admin

[![PyPI version](https://img.shields.io/pypi/v/controlm-chain-admin)](https://pypi.org/project/controlm-chain-admin/)
[![Python versions](https://img.shields.io/pypi/pyversions/controlm-chain-admin)](https://pypi.org/project/controlm-chain-admin/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/bilouro/controlm-chain-admin/blob/main/LICENSE)

Keep the job chains of a Control-M application as JSON in git, **one branch per environment**,
and move changes between environments knowing exactly what differs.

!!! warning "Community tool"
    This is an independent open-source project, not affiliated with or endorsed by BMC.
    Control-M is a trademark of its owner.

## What it gives you

- **Each environment as it is.** A full export of an environment overwrites its branch
  (`refresh`), after showing what changed, attribute by attribute.
- **Real differences only.** What is expected to differ between environments (the letter of
  the names, machines, users, the datacenter, a word in a mail subject) lives in a map;
  a comparison shows what is left.
- **The import file, already written.** Choose an attribute, a job, a folder or a
  sub-application and get the XML for the environment that receives it, with its own letter,
  machines and users.
- **Deliveries kept for later.** Put items aside under a name, little by little, and make
  one import file from several when it is time.
- **Validation with fixes** the Control-M interface does not offer.
- **Three ways in:** the `ctmchain` command line, a local web UI, and tools for an
  assistant, as a command (`python -m ctmadmin_service`) or over MCP.

## Quickstart

```bash
pip install "controlm-chain-admin[web]"

mkdir chains && cd chains && git init -b main
ctmchain init --application P77_RISK_ENGINE --envs prod=P,uat=U,bench=B --prefixes P77,RQ_,RC_
git add -A && git commit -m "chore: the rules"

ctmchain refresh ../exports/prod.xml --apply     # main is production
ctmchain refresh ../exports/uat.xml --apply      # env/uat
ctmchain refresh ../exports/bench.xml --apply    # env/bench
ctmchain envmap derive --apply                   # what varies between them

ctmchain compare main env/uat                    # the real differences
ctmchain package main env/uat --take 'job:P77_CHAIN/P77_NEW' -o prod_import.xml
ctmchain serve                                   # the web UI
```

The names above (`P77`, the folders, the jobs) are of a fictional application: use your own.

## Where to go next

- [Installation & Quickstart](getting-started/index.md): from an empty directory to a
  repository with every environment.
- [Concepts](getting-started/concepts.md): the model in one page.
- The [guides](guide/refresh.md), one per thing you do.
- [Command reference](cli.md).
