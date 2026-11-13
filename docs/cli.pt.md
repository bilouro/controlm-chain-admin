---
description: "Todos os comandos do ctmchain, pelo que servem."
---

# Referência dos comandos

Todos os comandos aceitam `--repo DIR` (por omissão, a pasta atual) e mostram a sua ajuda
com `--help`. Os comandos que alteram alguma coisa pré-visualizam primeiro e só escrevem com
`--apply`. Códigos de saída: `0` ok, `1` problemas encontrados, `2` uso, `3` erro.

## O repositório

| Comando | O que faz |
|---|---|
| `ctmchain init --application APP --envs prod=P,uat=U [--prefixes ...] [--leading-only ...] [--dedupe-jobnames]` | transforma uma pasta num repositório de cadeias |
| `ctmchain refresh XML [--env ENV] [--apply] [--here] [--partial] [--no-commit] [--stat]` | o export de um ambiente para o branch dele (ou para o branch aberto) |
| `ctmchain check XML [--env ENV]` | um export contra o que o repositório devolve para esse ambiente |
| `ctmchain export [--env ENV] -o FICHEIRO` | regenera o XML do branch aberto |
| `ctmchain commit [-m MENSAGEM]` | faz commit das cadeias, com uma mensagem escrita a partir do que mudou |

## Entre ambientes

| Comando | O que faz |
|---|---|
| `ctmchain envmap show\|derive\|suggest\|add\|rename\|remove` | o mapa do que varia |
| `ctmchain envmap followers`, `ctmchain envmap follow ITEM OUTRO [--apply]` | quem segue cada item; fazer os jobs de um seguirem outro |
| `ctmchain compare BASE [HEAD] [--raw] [--prefer ITEM] [--format text\|md\|json]` | o que difere |
| `ctmchain take HEAD [--list] [--base BASE] [--item ID ...] [--theirs ID ...] [--apply]` | itens de outro branch para o que está aberto |
| `ctmchain package BASE [HEAD] [--take ID ...] [--env ENV] [-o FICHEIRO] [--dry-run]` | o ficheiro de import |
| `ctmchain delivery save\|list\|remove\|package` | itens guardados, e um ficheiro com vários |

## Ver

| Comando | O que faz |
|---|---|
| `ctmchain show NÓ`, `ctmchain graph PASTA`, `ctmchain links NÓ` | um nó, o grafo de uma pasta, as ligações de um nó |
| `ctmchain distinct ATRIBUTO ...` | os valores distintos de atributos, com contagens |
| `ctmchain validate`, `ctmchain resolve [CÓDIGO=TIPO ...] [--apply]` | problemas, e as suas correções |
| `ctmchain diagnose [BASE HEAD] [-o FICHEIRO]` | porque algo está lento aqui (só números) |

## Alterar

| Comando | O que faz |
|---|---|
| `ctmchain rename-job NÓ NOVO`, `rename-folder`, `rename-subapp`, `move-job`, `insert-job` | refatorações; os nomes das condições seguem |
| `ctmchain adopt-jobname NÓ` | o nome numerado de um job passa a ser o JOBNAME |
| `ctmchain resources [--name TEXTO]`, `set-resource NOME NÓ... [--kind ...] [--set ATRIBUTO=VALOR]`, `remove-resource NOME NÓ...`, `rename-resource NÓ ANTIGO NOVO` | os recursos CONTROL e QUANTITATIVE: quem usa cada um, dar um a vários jobs, tirar, renomear |
| `ctmchain extract-variable`, `ctmchain technical` | um literal para uma variável; os atributos técnicos |
| `ctmchain set-exception`, `promote-exception`, `map`, `rename-constant` | para um repositório que guarda todos os ambientes numa só árvore |

## Interfaces

| Comando | O que faz |
|---|---|
| `ctmchain serve [--port N] [--assistant]` | a página web local e a API (`[web]`) |
| `ctmchain mcp`, `ctmchain menu`, `ctmchain kilo init [--force]` | as ferramentas para um assistente (`[mcp]`) |
