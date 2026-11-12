---
description: "Validar cadeias de jobs Control-M: condições soltas, nomes que enganam, nomes de job repetidos, valores de outro ambiente, com correção para a maioria."
---

# Validar e corrigir

```bash
ctmchain validate                 # os problemas; sai com 1 quando há algum
ctmchain resolve                  # cada tipo de problema, o que significa e as correções
ctmchain resolve never-cleaned=add-cleanup            # pré-visualiza essa correção em todos
ctmchain resolve never-cleaned=add-cleanup --apply
```

Cada tipo de problema diz o que procura, porque importa e o que a correção faz: no
`ctmchain resolve`, e na página *Validation* quando escolhes um tipo de problema.

## Os tipos de problema

| Código | O que procura | A correção |
|---|---|---|
| `dangling` | um job espera por uma condição que ninguém emite, com o nome de um job que existe | o job nomeado passa a emiti-la, ou o job deixa de esperar |
| `dangling-unknown` | o mesmo, e o nome não diz quem a devia emitir | o job deixa de esperar |
| `dangling-external` | o mesmo, com o nome de um job de outra aplicação | normalmente não é precisa |
| `unconsumed` | um job emite uma condição por que ninguém espera | o job nomeado passa a esperar, ou o job deixa de emitir |
| `unconsumed-external` | o mesmo, para um job de outra aplicação | normalmente não é precisa |
| `never-cleaned` | um job espera por uma condição e nunca a apaga | o job apaga-a depois de usar |
| `stale-name` | o nome de uma condição fala de dois jobs e ela liga outros dois | renomeada pelos jobs que liga |
| `non-standard-name` | um nome que não é feito dos dois jobs que liga | renomeada para o nome padrão |
| `similar-names` | condições que só diferem por um sufixo de cópia ou por maiúsculas | cada uma fica com um número |
| `duplicate-jobname` | dois jobs de uma pasta com o mesmo JOBNAME, sem numeração | os seguintes ficam com um número |
| `repeated-jobname` | um JOBNAME partilhado por vários jobs, em qualquer pasta | o nome numerado passa a ser o verdadeiro |
| `foreign-letter`, `letter-for-p`, `replaced-first-letter`, `foreign-resource` | um nome que leva a letra de um ambiente | a letra é tirada |
| `foreign-value` | um job com o valor que outro ambiente tem no mapa | o valor deste ambiente |
| `unmapped-difference` | um atributo do mapa que difere sem nenhum item o dizer | nenhuma: junta um item, ou corrige o job |
| `ambiguous-map` | um valor daqui, várias respostas noutro ambiente | nenhuma: prefere um item |
| `suspect-map-entry` | um item que é outro com um ambiente configurado como um terceiro | os jobs dele seguem o outro item |

## Um JOBNAME partilhado por vários jobs

Com `--dedupe-jobnames` o import numera os jobs seguintes de um JOBNAME repetido (`X2`,
`X3`) dentro do repositório; no Control-M continuam todos com o mesmo nome. Para tornar o
nome numerado o verdadeiro, com as condições que levam o nome antigo a seguir:

```bash
git switch -c work/names env/uat
ctmchain adopt-jobname 'P77_CHAIN/P77_A2'           # pré-visualiza
ctmchain adopt-jobname 'P77_CHAIN/P77_A2' --apply
ctmchain commit -m "adopt P77_A2"
ctmchain compare env/uat work/names                 # JOBNAME: P77_A -> P77_A2
ctmchain package env/uat work/names -o uat_import.xml
```

O JOBNAME muda no Control-M quando o ficheiro for importado: o que aparece na monitorização
e no histórico muda com ele.

## Os problemas que vêm do mapa

Os últimos quatro códigos da tabela precisam de um branch por ambiente e de um mapa; são
calculados para o ambiente que o branch aberto contém. Vê [O mapa](map.md).
