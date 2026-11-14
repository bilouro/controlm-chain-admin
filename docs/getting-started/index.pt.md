---
description: "Instalar o controlm-chain-admin e montar um repositório de cadeias a partir dos exports completos de cada ambiente."
---

# Instalação e Quickstart

## Requisitos

- Python 3.11 ou mais recente.
- git.
- Um **export completo** de cada ambiente (o *Export* das pastas no Control-M, em XML).

## Instalar

```bash
pip install "controlm-chain-admin[web]"
ctmchain --version
```

O núcleo não depende de nada fora da biblioteca padrão. `[web]` junta a página web local
(`ctmchain serve`). As ferramentas do assistente vêm com o pacote (`python -m
ctmadmin_service`); o `[mcp]` junta as mesmas ferramentas por MCP (`ctmchain mcp`), para
onde os servidores MCP forem permitidos.

## Do zero

O repositório guarda as cadeias de **uma** aplicação Control-M. Quatro coisas descrevem-na:
o `APPLICATION`, a letra de cada ambiente, os prefixos que levam essa letra, e quais deles
só a levam no início do nome.

```bash
mkdir chains && cd chains
git init -b main
ctmchain init --application P77_RISK_ENGINE \
    --envs prod=P,uat=U,bench=B \
    --prefixes P77,RQ_,RC_ --leading-only RQ_,RC_
git add -A && git commit -m "chore: the rules"
```

Cada ambiente ganha o seu branch a partir do seu export. `main` é a produção; cada outro
ambiente é `env/<nome>`:

```bash
ctmchain refresh ../exports/prod.xml --apply
ctmchain refresh ../exports/uat.xml --apply
ctmchain refresh ../exports/bench.xml --apply
git switch main
```

Sem `--apply`, o `refresh` só mostra o que o export mudaria.

Prova que cada branch devolve o seu export, byte a byte:

```bash
ctmchain check ../exports/prod.xml --env prod
```

Depois, o mapa do que varia entre os ambientes:

```bash
ctmchain envmap derive            # o que os branches mostram
ctmchain envmap derive --apply    # para o mapa
ctmchain envmap show
```

Agora os ambientes podem ser comparados:

```bash
ctmchain compare main env/uat
```

## A página web

```bash
ctmchain serve
```

Imprime um endereço local com um token de sessão; abre-o num browser. Nada sai da tua
máquina: o servidor só escuta em `127.0.0.1`.

## Atualizar

```bash
pip install --upgrade "controlm-chain-admin[web]"
```

Uma versão nova lê o repositório de uma anterior tal como está. Reinicia o `ctmchain serve`
depois de atualizar, e corre `ctmchain kilo init --repo . --force` quando as notas da versão
disserem que o assistente mudou (a 0.7.0 passou-o do MCP para o comando `python -m
ctmadmin_service`).
