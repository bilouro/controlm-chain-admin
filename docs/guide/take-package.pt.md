---
description: "Levar um atributo, um job, uma pasta ou uma sub-aplicação de um ambiente Control-M para outro: para um branch, ou como ficheiro de import."
---

# Levar e empacotar

O que viaja é um **item**:

| Item | Significa |
|---|---|
| `attr:PASTA/JOB@NOME` | um atributo de um job (`attr:PASTA/@NOME` para uma pasta) |
| `var:PASTA/JOB@%%NOME` | uma variável |
| `job:PASTA/JOB` | um job inteiro |
| `folder:PASTA` | uma pasta inteira |
| `subapp:NOME` | todas as pastas e jobs de uma sub-aplicação |
| `link:ID` | o nome de uma condição |

```bash
ctmchain take env/uat --list --base env/bench     # o que bench pode receber de uat, com ids
```

## O ficheiro de import (nenhum branch muda)

```bash
ctmchain package env/bench env/uat \
    --take 'job:P77_CHAIN/P77_NEW' --take 'attr:P77_CHAIN/P77_A@CMDLINE' \
    -o bench_import.xml
```

O ficheiro é o que o `env/bench` tem com esses itens por cima e mais nada, escrito com a
letra, as máquinas, os utilizadores e o datacenter de bench. Importa-o no Control-M; o
export seguinte de bench, depois do refresh, mostra exatamente o que lá entrou.

Sem `--take`, todas as pastas que diferem vão inteiras. `--dry-run` diz o que o ficheiro
levaria e não escreve nenhum.

Para produção é sempre assim, com `main` a receber:

```bash
ctmchain package main env/uat --take 'folder:P77_WEEKLY_DAILY' -o prod_import.xml
```

O `main` nunca se edita: só muda quando entra o export seguinte de produção.

!!! note "Pastas inteiras"
    O Control-M importa pastas inteiras. O ficheiro traz inteira cada pasta em que um item
    está: tal como o ambiente que recebe a tem, exceto no que escolheste.

## Para um branch

Para registar a escolha no branch de um ambiente que não é produção:

```bash
git switch env/bench
ctmchain take env/uat --item 'folder:P77_WEEKLY_DAILY'           # pré-visualiza
ctmchain take env/uat --item 'folder:P77_WEEKLY_DAILY' --apply
ctmchain commit -m "take the weekly folder from uat"
```

Quando o branch mudou o mesmo sítio também, o take pára e diz o item com os três valores
(o teu, o de partida, o deles): deixa-o de fora, ou leva-o com `--theirs`.

## O nome de uma condição

O `ctmchain compare` lista as condições a que os dois ambientes dão nomes diferentes. Para
a produção passar a usar o nome que UAT usa:

```bash
ctmchain package main env/uat --take 'link:ID' -o prod_import.xml
```
