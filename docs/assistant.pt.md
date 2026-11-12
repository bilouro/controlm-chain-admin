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

## O que podes pedir

- "O que é que uat tem que produção não tem?"
- "De que depende o P77_B? Quem espera por ele?"
- "Que itens de uat pode bench receber?" e depois "leva o job P77_NEW para este branch."
- "O ficheiro de import para produção com a pasta P77_WEEKLY_DAILY de uat."
- "Guarda o job novo de uat como entrega com o nome sexta." e "Que entregas tenho guardadas?"
- "O que mudaria o export ../exports/uat.xml?"
- "Há alguma coisa errada nas cadeias?"

## O que faz e o que nunca faz

| Lê, sem perguntar | Escreve, depois de aprovares |
|---|---|
| find, show, condition, validate, compare, envmap, takeable, package, refresh, deliveries, delivery_package | apply (uma alteração no branch aberto), write_package, keep_delivery, remove_delivery, write_delivery_package |

Nunca muda de branch, nunca faz commit nem push, e nunca aplica um export: pré-visualiza-o e
diz-te o comando que o aplica.

!!! warning "O modelo lê os teus dados"
    O modelo do assistente lê os nomes e os campos dos teus jobs. Usa um que a tua
    organização permita.

O `vocabulary.md`, ao lado do agente, guarda as palavras da tua equipa e o que significam
no Control-M: o assistente lê-o quando uma palavra do pedido não é um nome do Control-M.
