---
description: "The local web UI of controlm-chain-admin: chains, validation, compare, refresh, map and deliveries in a browser."
---

# Web UI

```bash
pip install "controlm-chain-admin[web]"
ctmchain serve                 # prints the address, with a session token
ctmchain serve --port 8770     # another port
ctmchain serve --assistant     # with the Assistant panel (needs Kilo)
```

The server listens on `127.0.0.1` only. Reading needs nothing; anything that writes needs
the session token the command printed (open the address it gives, token included).

| Page | What you do there |
|---|---|
| **Chains** | the folders and jobs, with predecessors and successors; a folder opens its graph, a job its attributes by group |
| **Validate** | the findings, by severity and type; choose a type to read what it means; *Resolve* a finding or a selection |
| **Compare** | two branches or environments; check items to take them, package them, or keep them for a delivery |
| **Refresh** | the export of an environment onto its branch, or onto a branch of your own |
| **Map** | the entries, who follows each, *Follow…*, and what the branches show that the map lacks |
| **Deliveries** | what was kept for later; one import file from one or several |
| **Environments** | the letter of each environment and its constants |

Every change is previewed first, field by field, and written only when you confirm. Nothing
is committed for you: the *Commit* button proposes a message from what changed.

The branch dialog (the button with the branch name) switches to the branch of an
environment, starts a branch of your own, and pushes or pulls.
