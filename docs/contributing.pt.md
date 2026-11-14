---
description: "Como preparar o controlm-chain-admin para desenvolvimento, correr os testes e enviar uma alteração."
---

# Contribuir

```bash
git clone https://github.com/bilouro/controlm-chain-admin
cd controlm-chain-admin
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,web,mcp]"

pytest                                   # os testes de Python, com dados sintéticos
ruff check . && ruff format --check . && mypy src
cd web && npm ci && npm run lint && npm run typecheck && npm test && npm run build
```

## As regras da casa

- **Primeiro um teste que falha.** Nenhum código de produção sem um teste que falhe pela
  razão certa; o teste e o código vão no mesmo commit.
- **Nunca dados reais.** Nenhum export, nome de job, máquina, utilizador ou endereço real,
  nem sequer num teste. Os dados de teste são de uma aplicação fictícia, `P77`.
- **O núcleo só depende da biblioteca padrão.** O FastAPI está no extra `[web]`, o servidor
  MCP no `[mcp]`; o comando do assistente (`ctmadmin_service`) não precisa de mais nada.
- **Um núcleo, adaptadores finos.** A lógica, incluindo as alterações, está em
  `controlm_chain_admin.core`; a linha de comandos, a API, o servidor MCP e o comando do
  assistente só traduzem (as ferramentas do assistente são uma classe, `tools.ChainTools`).
- **Conventional Commits**, um changelog no formato Keep a Changelog, SemVer.

## Antes de uma versão

Os dados de teste sintéticos são regulares; as cadeias reais não. Antes de uma versão, o
autor ensaia os fluxos que a versão mexe numa cópia temporária do repositório de dados
privado (nunca no próprio repositório), só com contagens:

```bash
CTMCHAIN_DATA_REPO=~/dev/controlm-chain-data pytest -m realdata tests/realdata/test_rehearsal.py -s
```

Um fluxo que uma versão muda ganha lá um cenário primeiro.

## A documentação

```bash
pip install -e ".[docs]"
mkdocs serve          # http://127.0.0.1:8000
mkdocs build --strict
```

Cada página tem uma gémea em português (`pagina.pt.md`) com os mesmos títulos.

O guia completo está em
[`CONTRIBUTING.md`](https://github.com/bilouro/controlm-chain-admin/blob/main/CONTRIBUTING.md).
