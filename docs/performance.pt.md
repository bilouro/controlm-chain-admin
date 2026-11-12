---
description: "Porque o controlm-chain-admin se mantém rápido onde os ficheiros pequenos são lentos, e como medir uma máquina com o ctmchain diagnose."
---

# Desempenho

Em algumas máquinas cada ficheiro pequeno custa caro: um antivírus inspeciona cada um, ou a
pasta está numa unidade de rede ou numa pasta sincronizada. Uma ferramenta que trabalha com
milhares de ficheiros pequenos gasta aí quase todo o tempo.

Desde a 0.3.4 a ferramenta não usa o disco como memória de trabalho:

- **As cópias de trabalho vivem em memória.** Um branch sai do git de uma só vez, para a
  memória: a fotografia de um ref, a cópia que uma comparação reescreve, a que recebe uma
  seleção, a que prepara uma alteração.
- **Cada ficheiro do repositório é aberto uma vez.** O texto é lembrado até o ficheiro
  mudar, e a primeira leitura de uma árvore limpa vem do git de uma só vez.
- **Uma comparação entre dois commits fica guardada.** A mesma pergunta outra vez é
  respondida logo. `CTMCHAIN_NO_CACHE=1` desliga isso.

## Medir uma máquina

```bash
ctmchain diagnose
ctmchain diagnose -o diagnose.txt
```

Mede a máquina (um ficheiro pequeno na pasta temporária e ao lado do repositório, uma
chamada ao git, cálculo puro) e uma comparação real, fase a fase, com os ficheiros que abriu
e escreveu. O relatório tem números e os dois refs comparados: nenhum nome de job, de pasta
ou de diretório, por isso pode ser passado a outra pessoa.

## Se ainda estiver lento

- Mantém o repositório num disco local, fora de qualquer pasta sincronizada ou de rede.
- Em Windows: `git config core.fscache true` e `git config core.untrackedCache true`.
- Reinicia o `ctmchain serve` depois de atualizar: um servidor a correr fica com a versão
  antiga.
