---
description: "Cadeias de jobs do Control-M como JSON em git: um branch por ambiente, só as diferenças reais, e o ficheiro de import já escrito para o ambiente que recebe."
---

# controlm-chain-admin

[![Versão no PyPI](https://img.shields.io/pypi/v/controlm-chain-admin)](https://pypi.org/project/controlm-chain-admin/)
[![Versões de Python](https://img.shields.io/pypi/pyversions/controlm-chain-admin)](https://pypi.org/project/controlm-chain-admin/)
[![Licença: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/bilouro/controlm-chain-admin/blob/main/LICENSE)

Guarda as cadeias de jobs de uma aplicação Control-M como JSON em git, **um branch por
ambiente**, e leva alterações de um ambiente para outro sabendo exatamente o que difere.

!!! warning "Ferramenta da comunidade"
    É um projeto open source independente, sem ligação à BMC nem aprovado por ela.
    Control-M é uma marca do seu proprietário.

## O que te dá

- **Cada ambiente tal como está.** O export completo de um ambiente substitui o branch
  dele (`refresh`), depois de mostrar o que mudou, atributo a atributo.
- **Só as diferenças reais.** O que se espera que difira entre ambientes (a letra dos nomes,
  máquinas, utilizadores, o datacenter, uma palavra no assunto de um e-mail) fica num mapa;
  a comparação mostra o que sobra.
- **O ficheiro de import, já escrito.** Escolhes um atributo, um job, uma pasta ou uma
  sub-aplicação e sai o XML para o ambiente que recebe, com a letra, as máquinas e os
  utilizadores dele.
- **Entregas guardadas.** Guardas itens com um nome, aos poucos, e geras um único ficheiro
  de import com várias quando for altura.
- **Validação com correções** que a interface do Control-M não oferece.
- **Três entradas:** a linha de comandos `ctmchain`, uma página web local e ferramentas para
  um assistente, por comando (`python -m ctmadmin_service`) ou por MCP.

## Quickstart

```bash
pip install "controlm-chain-admin[web]"

mkdir chains && cd chains && git init -b main
ctmchain init --application P77_RISK_ENGINE --envs prod=P,uat=U,bench=B --prefixes P77,RQ_,RC_
git add -A && git commit -m "chore: the rules"

ctmchain refresh ../exports/prod.xml --apply     # main é a produção
ctmchain refresh ../exports/uat.xml --apply      # env/uat
ctmchain refresh ../exports/bench.xml --apply    # env/bench
ctmchain envmap derive --apply                   # o que varia entre eles

ctmchain compare main env/uat                    # as diferenças reais
ctmchain package main env/uat --take 'job:P77_CHAIN/P77_NEW' -o prod_import.xml
ctmchain serve                                   # a página web
```

Os nomes acima (`P77`, as pastas, os jobs) são de uma aplicação fictícia: usa os teus.

## Para onde ir a seguir

- [Instalação e Quickstart](getting-started/index.md): de uma pasta vazia a um repositório
  com todos os ambientes.
- [Conceitos](getting-started/concepts.md): o modelo numa página.
- Os [guias](guide/refresh.md), um por cada coisa que fazes.
- [Referência dos comandos](cli.md).
