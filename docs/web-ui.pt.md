---
description: "A página web local do controlm-chain-admin: cadeias, validação, comparação, refresh, mapa e entregas num browser."
---

# Página web

```bash
pip install "controlm-chain-admin[web]"
ctmchain serve                 # imprime o endereço, com um token de sessão
ctmchain serve --port 8770     # outra porta
ctmchain serve --assistant     # com o painel Assistant (precisa do Kilo)
```

O servidor só escuta em `127.0.0.1`. Ler não precisa de nada; tudo o que escreve precisa do
token de sessão que o comando imprimiu (abre o endereço que ele dá, com o token).

| Página | O que lá fazes |
|---|---|
| **Chains** | as pastas e os jobs, com predecessores e sucessores; uma pasta abre o grafo, um job os atributos por grupo |
| **Validate** | os problemas, por gravidade e tipo; escolhes um tipo para ler o que significa; *Resolve* num problema ou numa seleção |
| **Compare** | dois branches ou ambientes; marcas itens para os levar, empacotar ou guardar numa entrega |
| **Refresh** | o export de um ambiente para o branch dele, ou para um branch teu; completo, ou só algumas pastas |
| **Map** | a letra e o branch de cada ambiente, os itens, quem segue cada um, *Follow…*, o que os branches mostram e o mapa não tem, e os atributos técnicos |
| **Deliveries** | o que ficou guardado e os commits que cada uma leva; um ficheiro de import com uma ou várias |
| **Resources** | cada recurso CONTROL e QUANTITATIVE com os jobs que o usam; dar um a vários jobs |

Cada alteração é pré-visualizada primeiro, campo a campo, e só é escrita quando confirmas.
Nenhum commit é feito por ti: o botão *Commit* propõe uma mensagem a partir do que mudou.

O diálogo dos branches (o botão com o nome do branch) muda para o branch de um ambiente,
cria um branch teu, e faz push ou pull. Enquanto uma destas corre, o botão diz-o
(*Switching…*, *Pushing…*) e os outros esperam.
