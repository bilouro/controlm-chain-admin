---
description: "How controlm-chain-admin keeps your Control-M data on your machine, and how to report a vulnerability."
---

# Security

## Your data stays where it is

- **Nothing is sent anywhere.** The command line and the web UI work on a local git
  repository. The web server listens on `127.0.0.1` only.
- **Writing needs a token.** Every request that changes something needs the session token
  `ctmchain serve` prints at start; reading does not.
- **The assistant is the exception you choose.** With the assistant
  (`ctmchain serve --assistant`, `python -m ctmadmin_service`, `ctmchain mcp`), the model of
  your assistant reads the names and fields of your jobs. Use a model your organisation allows; without the assistant, no model is
  involved.
- **Reports with numbers only.** `ctmchain diagnose` holds timings, counts and versions: no
  name of a job, of a folder or of a directory.

## Your exports are confidential

A Control-M export names your hosts, users and jobs. Keep the chain repository private, and
never put a real export, or a value from one, in an issue, a pull request or a test of this
project: the examples here use a fictional application (`P77`).

## Reporting a vulnerability

Please do not open a public issue. Use the private reporting of the repository
([Security advisories](https://github.com/bilouro/controlm-chain-admin/security/advisories/new))
and see [`SECURITY.md`](https://github.com/bilouro/controlm-chain-admin/blob/main/SECURITY.md)
for the supported versions.
