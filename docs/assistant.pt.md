---
description: "Perguntar pelas cadeias Control-M por palavras tuas: as ferramentas do controlm-chain-admin para um assistente como o Kilo, por comando ou por MCP."
---

# Assistente

Um assistente (o Kilo, ou qualquer assistente que corra comandos ou fale MCP) recebe o
repositório como ferramentas. Ele responde a perguntas e propõe alterações,
pré-visualizadas campo a campo, e só escreve quando concordas.

As mesmas ferramentas chegam-lhe de uma de duas formas:

| | Por comando (por omissão) | Por MCP |
|---|---|---|
| O que o agente corre | `python -m ctmadmin_service <ferramenta> ...` | as ferramentas do servidor MCP `ctmchain mcp` |
| Precisa de | nada além do pacote | o extra `[mcp]`, e servidores MCP permitidos |
| Funciona onde os servidores MCP estão bloqueados | sim | não |

```bash
pip install "controlm-chain-admin[web]"
ctmchain kilo init --repo .       # escreve .kilo/agents/controlm.md e o vocabulary.md
ctmchain serve --assistant        # a página web com o painel Assistant; ou: kilo --agent controlm
```

Arranca o `kilo` com o ambiente do pacote ativo, para que o `python` seja o que o tem; o
`ctmchain serve --assistant` trata disso sozinho. Onde os servidores MCP são permitidos, o
`ctmchain kilo init --repo . --via mcp` (com `pip install "controlm-chain-admin[mcp]"`)
prepara o agente por MCP.

Depois de uma atualização que traga ferramentas novas, corre
`ctmchain kilo init --repo . --force`: reescreve o agente e mantém o teu `vocabulary.md`.

## O comando

O `python -m ctmadmin_service help` diz como chamar cada ferramenta e como trabalhar;
`help <ferramenta>` e `help <capacidade>` dão os parâmetros e um comando para copiar. Cada
ferramenta escreve JSON (`menu`, `compare` e `refresh`: texto).

```bash
python -m ctmadmin_service find P77_LOAD
python -m ctmadmin_service show P77_CHAIN/P77_B
python -m ctmadmin_service preview set-resource --nodes P77_CHAIN/P77_A --nodes P77_CHAIN/P77_B --name RQ_AM
python -m ctmadmin_service apply <preview_id>
```

Os valores nunca vão como JSON na linha de comandos, que as shells estragam: uma lista
repete a opção, um mapa leva `CHAVE=VALOR` por entrada (`--changes MAXWAIT=3`), e `null`
quer dizer nenhum. O `preview` escreve o `preview_id`; o `apply` leva só esse id e é
recusado se o repositório mudou entretanto. Alterações que vão juntas: faz o `preview` da
seguinte com `--after <preview_id>` e aplica o último id.

O agente pode correr este comando e nenhum outro, e não pode editar ficheiros; o Kilo
pergunta-te antes de cada chamada que escreve (`apply`, `write_package`, `keep_delivery`,
`remove_delivery`, `write_delivery_package`). As regras estão em `.kilo/agents/controlm.md`.

## Quando o assistente não tem ferramentas

- **Por comando.** O agente diz `No module named ctmadmin_service`: o Kilo foi arrancado
  sem o ambiente do pacote. Ativa-o e arranca o Kilo de novo, ou usa o
  `ctmchain serve --assistant`.
- **Por MCP.** Uma política da empresa pode bloquear os servidores MCP: o `kilo mcp list`
  mostra então `ctmchain disabled`, e o `kilo mcp list --print-logs --log-level DEBUG` diz
  porquê. Prepara o agente por comando (`ctmchain kilo init --repo . --force`). O
  `.kilo/kilo.json` guarda também o caminho completo do repositório e do Python: o
  `ctmchain serve --assistant` corrige-os quando a pasta mudou de sítio.

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

O `vocabulary.md` (`.kilo/skills/ctmchain/`) guarda as palavras da tua equipa e o que
significam no Control-M: o assistente lê-o quando uma palavra do pedido não é um nome do
Control-M.
