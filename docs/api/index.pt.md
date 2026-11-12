---
description: "O núcleo Python do controlm-chain-admin: as funções que a linha de comandos, a API web e o servidor MCP chamam."
---

# Referência API

Toda a lógica está em `controlm_chain_admin.core`, que só depende da biblioteca padrão. A
linha de comandos, a API web e o servidor MCP traduzem entrada e saída, e mais nada: o que
eles fazem, um script também faz.

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

A descrição de cada função abaixo está em inglês, como no código.

## O repositório

::: controlm_chain_admin.core.repo.load_repo

## Refresh

::: controlm_chain_admin.core.refresh.refresh

## Comparar

::: controlm_chain_admin.core.compare.compare

## Levar

::: controlm_chain_admin.core.take.takeable

::: controlm_chain_admin.core.take.take

## Empacotar

::: controlm_chain_admin.core.package.build_package

::: controlm_chain_admin.core.package.save

## Entregas

::: controlm_chain_admin.core.deliveries.save_delivery

::: controlm_chain_admin.core.deliveries.build_delivery

## O mapa

::: controlm_chain_admin.core.mapcheck.survey

::: controlm_chain_admin.core.mapcheck.follow_entry

## Validar

::: controlm_chain_admin.core.validate.validate

## Aplicar uma alteração

As funções que alteram o repositório devolvem um `ChangeSet`: os ficheiros que escreveria,
com o conteúdo antes e depois. Nada é escrito até ser aplicado.

::: controlm_chain_admin.core.refactor.apply
