---
description: "Ver os recursos CONTROL e QUANTITATIVE dos jobs Control-M por recurso, e dar um a vários jobs de uma vez."
---

# Recursos

Um job pode **segurar** um recurso enquanto corre (`CONTROL`: em exclusivo, `E`, ou
partilhado, `S`) ou **tomar** um número de unidades de um (`QUANTITATIVE`). O Control-M
mostra-os job a job; aqui também se veem por recurso.

```bash
ctmchain resources                    # cada recurso, quem o usa e como
ctmchain resources --name RQ_         # só os que têm este texto no nome
```

```text
QUANTITATIVE  RQ_AM  1 job  QUANT=1 ONFAIL=R ONOK=R
    P77_INGEST_DAILY/P77_INGEST_INIT
```

Os nomes guardam-se sem a letra do ambiente: `URQ_AM` em UAT e `PRQ_AM` em produção são
ambos `RQ_AM` aqui, e o export volta a pôr a letra.

## Dar um recurso a um job, ou a vários

```bash
ctmchain set-resource RQ_AM P77_CHAIN/P77_A P77_CHAIN/P77_B            # pré-visualiza
ctmchain set-resource RQ_AM P77_CHAIN/P77_A P77_CHAIN/P77_B --apply
```

Um recurso que outro job usa vem **com os atributos que lá tem**, para todos os jobs
pedirem o mesmo. Um que ninguém usa ainda precisa do tipo:

```bash
ctmchain set-resource RC_SHARED P77_CHAIN/P77_A --kind control --apply
```

Um `CONTROL` novo é seguro em exclusivo e um `QUANTITATIVE` novo toma uma unidade; ambos
são libertados no fim. Para mudar isso, ou o que um job já tem:

```bash
ctmchain set-resource RC_SHARED P77_CHAIN/P77_B --set TYPE=S --apply
ctmchain set-resource RQ_AM P77_INGEST_DAILY/P77_INGEST_INIT --set QUANT=2 --apply
```

## Renomear e remover

```bash
ctmchain rename-resource P77_CHAIN/P77_A RQ_AM RQ_PM --apply
ctmchain remove-resource RQ_AM P77_CHAIN/P77_B --apply
```

## Na página web

- A página de um job, e de uma pasta, tem um separador **Resources**: o que segura e o que
  toma, com *Add* (os nomes em uso são sugeridos), como é seguro ou quantas unidades,
  *Rename* e *Remove*.
- A página **Resources** lista cada recurso com os jobs que o usam, e *Add to jobs…* dá-o
  a vários de uma vez.

Cada alteração é pré-visualizada e revista como qualquer outra. Depois viaja como qualquer
alteração: `compare`, `take`, `package`, ou uma entrega.
