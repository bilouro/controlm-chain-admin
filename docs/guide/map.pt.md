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
na coluna *Followed by*. É contado nos branches dos ambientes **tal como estão commitados**:
uma alteração por commitar ainda não o mexe. Um sítio com os valores de um item em alguns
ambientes e os de outro nos restantes, depois de um follow feito só em parte, está *a meio
caminho* entre os dois.

## Valores novos depois de um refresh

Um refresh pode trazer um valor que o mapa não conhece: um utilizador renomeado no
Control-M, uma máquina substituída. Enquanto não estiver no mapa, comparar esse ambiente com
outro mostra como diferente cada job que o tem.

```bash
ctmchain envmap new-values                                   # no branch de um ambiente
ctmchain envmap adopt RUN_AS aup77svc --entry run_as.1       # para o item sugerido
ctmchain envmap adopt RUN_AS aup77svc --new                  # ou para um item novo
ctmchain envmap set run_as.4 egma aep77svc                   # preencher um ambiente
ctmchain envmap set run_as.4 egma --clear                    # deixá-lo por preencher
```

O `new-values` lista, para o ambiente do branch aberto, os valores que nenhum item diz para
esses sítios, com quantos sítios têm cada um e o item sugerido: aquele cujos valores os
outros ambientes têm ali. Corre sozinho depois de cada refresh do branch de um ambiente (o
`ctmchain refresh … --apply` diz o que encontrou, a página *Refresh* lista-os), e a qualquer
momento na página *Map*, secção *New values*.

- Para um item: o item fica com o valor novo para esse ambiente. Quando o valor antigo já
  não é usado em lado nenhum do ambiente (renomeado em todo o lado), todos os itens que o
  tinham ficam com o novo; senão só o escolhido, e és avisado de quantos sítios ficam com o
  antigo.
- Um item novo fica com o que os seus sítios têm nos outros ambientes, onde concordam todos;
  o resto fica *por preencher*, e um item não traduz nada num ambiente sem valor até ser
  preenchido.
- Uma *combinação nova* é um valor que o mapa conhece com outros valores noutros ambientes:
  onde dois ambientes tinham o mesmo valor antes de um ser renomeado. Fica com um item seu.

## Seguir outro item, em todos os ambientes

Dois itens do mesmo campo são muitas vezes uma só regra e alguns ambientes mal configurados.
Renomear um item muda o nome e nenhum job. Isto muda:

```bash
ctmchain envmap follow run_as.2 run_as.1           # pré-visualiza, por ambiente
ctmchain envmap follow run_as.2 run_as.1 --apply   # um commit no branch de cada um
```

Em cada ambiente onde os dois itens diferem, os sítios que seguem o primeiro ficam com o
valor do segundo: um commit no branch desse ambiente, `follow(<ambiente>): run_as.2 ->
run_as.1`, sem mudar de branch (o branch aberto não pode ter ficheiros de cadeias por
commitar). Produção nunca é editada aqui: a pré-visualização diz quando também difere, e
produção recebe a alteração por um ficheiro de import (Compare, package). As contagens mexem
logo. O Control-M de cada ambiente recebe a alteração pelo seu ficheiro de import; até lá, o
export seguinte traz o valor antigo de volta.

O `--here` faz só no branch aberto, para rever e commitar: faz o commit com o assunto que o
comando diz (`follow(<ambiente>): …`), para os sítios ainda a meio caminho serem
reconhecidos. Na página *Map*: *Follow…*, depois *Preview* e *Follow in N environments*.

O `ctmchain validate` aponta estes casos: vê [Validar e corrigir](validate.md).
