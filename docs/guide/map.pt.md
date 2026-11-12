---
description: "O mapa do que se espera que difira entre ambientes Control-M: derivá-lo dos branches, ver quem segue cada item, e corrigir um ambiente."
---

# O mapa

O mapa diz que valor de um ambiente corresponde a que valor de outro: a máquina, o
utilizador, o datacenter, uma palavra no assunto de um e-mail. Com ele, uma comparação
mostra só as diferenças reais, e o que levas chega com os valores certos.

```bash
ctmchain envmap derive                         # o que os branches mostram e o mapa não tem
ctmchain envmap derive --apply                 # junta
ctmchain envmap derive --text 'DOMAIL/@SUBJECT' --apply   # uma palavra de um texto
ctmchain envmap show
ctmchain envmap suggest                        # o que mais varia, com contagens
```

O `derive` olha para `NODEID`, `RUN_AS` e `DATACENTER`; `--key` junta um atributo cujo valor
inteiro varia, `--text` um cujos textos diferem numa só palavra. Os valores que menos de
dois sítios mostram ficam de fora (`--min-nodes`): são o que um job tem, não o que o
ambiente tem.

Um item também se junta, renomeia ou remove à mão:

```bash
ctmchain envmap add RUN_AS prod=app77proc uat=aup77proc bench=abp77proc
ctmchain envmap rename run_as.1 the_batch_user
ctmchain envmap remove run_as.2
```

O mapa vive num branch próprio (`map`) e é escrito lá diretamente: nenhum checkout muda.
Faz push dele como de qualquer branch.

## Quem segue cada item

```bash
ctmchain envmap followers
```

Um *sítio* (um atributo de um job, ou de um elemento dentro dele) segue um item quando os
valores dele em todos os ambientes são exatamente os do item. A página *Map* mostra o mesmo
na coluna *Followed by*.

## Um ambiente configurado com o valor de outro

Dois itens do mesmo campo que diferem num único ambiente são, quase sempre, uma só regra e
um ambiente mal configurado. Renomear um item muda o nome e nenhum job. Isto muda:

```bash
git switch -c work/fix-bench env/bench
ctmchain envmap follow run_as.2 run_as.1           # pré-visualiza
ctmchain envmap follow run_as.2 run_as.1 --apply
ctmchain commit -m "run_as.2 follows run_as.1"
ctmchain package env/bench work/fix-bench -o bench_import.xml
```

No branch aberto, que tem de conter o ambiente onde os dois itens diferem, os jobs que
seguem o primeiro item ficam com o valor do segundo. O mapa não é alterado: depois de o
ficheiro de import estar no Control-M e de entrar o export seguinte desse ambiente, nada
segue o item errado e ele pode ser removido.

O `ctmchain validate` aponta estes casos: vê [Validar e corrigir](validate.md).
