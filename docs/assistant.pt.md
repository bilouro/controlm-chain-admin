---
description: "Perguntar pelas cadeias Control-M por palavras tuas: as ferramentas MCP do controlm-chain-admin para um assistente como o Kilo ou o Claude."
---

# Assistente

O `ctmchain mcp` dá a um assistente (Kilo, Claude, qualquer cliente MCP) o repositório como
ferramentas. Ele responde a perguntas e propõe alterações, pré-visualizadas campo a campo,
e só escreve quando concordas.

```bash
pip install "controlm-chain-admin[mcp]"
ctmchain kilo init --repo .       # escreve .kilo/: o servidor, o agente controlm, a skill
kilo --agent controlm             # ou: ctmchain serve --assistant
```

Depois de uma atualização que traga ferramentas novas, corre
`ctmchain kilo init --repo . --force`: reescreve o agente e mantém o teu `vocabulary.md`.

## Quando o assistente não tem ferramentas

O `.kilo/kilo.json` arranca o servidor com o caminho completo do repositório e do Python.
Uma pasta que mudou de sítio, ou um ambiente virtual refeito, deixa-o a apontar para lado
nenhum: o assistente diz então que as ferramentas ctmchain não estão disponíveis e procura
nos ficheiros à mão. O `ctmchain serve --assistant` corrige o caminho sozinho ao arrancar;
só com o `kilo`, corre `ctmchain kilo init --repo . --force`. Para ver o erro, arranca o
servidor à mão: tem de ficar à espera, em silêncio.

```bash
python -m controlm_chain_admin mcp --repo .
```

Pede "chama ctmchain_menu e diz-me o que devolve": a lista de capacidades quer dizer que as
ferramentas estão lá.

Um job pode ser dito como o Control-M o mostra, com a letra do ambiente (`UP77_LOAD`): é
encontrado como `P77_LOAD`, o nome guardado aqui.

## O que podes pedir

- "O que é que uat tem que produção não tem?"
- "De que depende o P77_B? Quem espera por ele?"
- "Que itens de uat pode bench receber?" e depois "leva o job P77_NEW para este branch."
- "O ficheiro de import para produção com a pasta P77_WEEKLY_DAILY de uat."
- "Guarda o job novo de uat como entrega com o nome sexta." e "Que entregas tenho guardadas?"
- "O que mudaria o export ../exports/uat.xml?"
- "Que jobs usam o recurso RQ_AM?" e "o P77_A e o P77_B também o devem tomar."
- "Há alguma coisa errada nas cadeias?"

## O que faz e o que nunca faz

| Lê, sem perguntar | Escreve, depois de aprovares |
|---|---|
| find, show, condition, validate, compare, envmap, takeable, package, refresh, deliveries, delivery_package, resources | apply (uma alteração no branch aberto), write_package, keep_delivery, remove_delivery, write_delivery_package |

Nunca muda de branch, nunca faz commit nem push, e nunca aplica um export: pré-visualiza-o e
diz-te o comando que o aplica.

!!! warning "O modelo lê os teus dados"
    O modelo do assistente lê os nomes e os campos dos teus jobs. Usa um que a tua
    organização permita.

O `vocabulary.md`, ao lado do agente, guarda as palavras da tua equipa e o que significam
no Control-M: o assistente lê-o quando uma palavra do pedido não é um nome do Control-M.
