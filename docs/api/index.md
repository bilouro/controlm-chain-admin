---
description: "The Python core of controlm-chain-admin: the functions the command line, the web API and the MCP server all call."
---

# API Reference

All the logic is in `controlm_chain_admin.core`, which depends on the standard library
only. The command line, the web API and the MCP server translate input and output, and
nothing else: what they do, a script can do.

```python
from pathlib import Path

from controlm_chain_admin.core.compare import compare
from controlm_chain_admin.core.package import build_package, save

root = Path("chains")
result = compare(root, "main", "env/uat")
print(result.summary())

package = build_package(root, "main", "env/uat", take=["job:P77_CHAIN/P77_NEW"])
save(package, Path("prod_import.xml"))
```

## The repository

::: controlm_chain_admin.core.repo.load_repo

## Refresh

::: controlm_chain_admin.core.refresh.refresh

## Compare

::: controlm_chain_admin.core.compare.compare

## Take

::: controlm_chain_admin.core.take.takeable

::: controlm_chain_admin.core.take.take

## Package

::: controlm_chain_admin.core.package.build_package

::: controlm_chain_admin.core.package.save

## Deliveries

::: controlm_chain_admin.core.deliveries.save_delivery

::: controlm_chain_admin.core.deliveries.build_delivery

## The map

::: controlm_chain_admin.core.mapcheck.survey

::: controlm_chain_admin.core.mapcheck.follow_entry

## Validate

::: controlm_chain_admin.core.validate.validate

## Applying a change

Functions that change the repository return a `ChangeSet`: the files it would write, with
their content before and after. Nothing is written until it is applied.

::: controlm_chain_admin.core.refactor.apply
