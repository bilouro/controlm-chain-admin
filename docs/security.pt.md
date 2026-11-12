---
description: "Como o controlm-chain-admin mantém os teus dados Control-M na tua máquina, e como reportar uma vulnerabilidade."
---

# Segurança

## Os teus dados ficam onde estão

- **Nada é enviado para lado nenhum.** A linha de comandos e a página web trabalham sobre um
  repositório git local. O servidor web só escuta em `127.0.0.1`.
- **Escrever precisa de um token.** Cada pedido que altera alguma coisa precisa do token de
  sessão que o `ctmchain serve` imprime ao arrancar; ler não precisa.
- **O assistente é a exceção que tu escolhes.** Com `ctmchain mcp` ou
  `ctmchain serve --assistant`, o modelo do teu assistente lê os nomes e os campos dos teus
  jobs. Usa um modelo que a tua organização permita; sem o assistente, nenhum modelo entra.
- **Relatórios só com números.** O `ctmchain diagnose` tem tempos, contagens e versões:
  nenhum nome de job, de pasta ou de diretório.

## Os teus exports são confidenciais

Um export do Control-M tem os nomes das tuas máquinas, utilizadores e jobs. Mantém o
repositório de cadeias privado, e nunca ponhas um export real, ou um valor de um, num issue,
num pull request ou num teste deste projeto: os exemplos aqui usam uma aplicação fictícia
(`P77`).

## Reportar uma vulnerabilidade

Não abras um issue público. Usa o canal privado do repositório
([Security advisories](https://github.com/bilouro/controlm-chain-admin/security/advisories/new))
e vê o [`SECURITY.md`](https://github.com/bilouro/controlm-chain-admin/blob/main/SECURITY.md)
para as versões suportadas.
