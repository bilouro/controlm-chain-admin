---
description: "Comparar dois ambientes Control-M pelas diferenças reais: o que o mapa e a letra explicam é lido através deles."
---

# Comparar dois ambientes

```bash
ctmchain compare main env/uat
ctmchain compare env/bench env/uat
ctmchain compare main env/uat --format md > uat-vs-prod.md
ctmchain compare main env/uat --raw
```

O primeiro argumento é quem recebe, o segundo é de onde as coisas vêm. O segundo é lido nos
termos do primeiro: a letra, e as máquinas, os utilizadores e as palavras que o mapa
conhece. O relatório começa pelo que foi lido assim e depois lista o que sobra:

```text
Compare main (prod) with env/uat (uat): real differences only
  expected between prod and uat, not shown: 28 values and 2 texts of the map,
  4 names with the letter, 1 condition called another name
```

`--raw` compara os dois branches tal como estão guardados, sem o mapa.

## Um valor com duas respostas

Quando um valor da origem corresponde a dois no destino (dois utilizadores lá para um cá),
nada é adivinhado: o valor fica como está e um aviso diz que itens do mapa o podiam
explicar. Repete com `--prefer`:

```bash
ctmchain compare env/bench env/uat --prefer run_as.1
```

## Uma condição com dois nomes

Uma condição que liga os mesmos jobs da mesma maneira com outro nome não é diferença, mas
é listada, com o item que leva o outro nome:

```text
  P77_A-P77_B_OK is P77_ALPHA-P77_B_OK in uat (link:… takes that name)
```

Cada ambiente pode manter o seu nome, ou um fica com o do outro
([Levar e empacotar](take-package.md)).

## Na página web

Na página *Compare*, escolhes *Base* e *Head* e carregas em **Compare**: nada corre até
carregares, e a comparação anterior fica visível enquanto a nova é calculada. Uma
comparação entre dois commits fica guardada, por isso pedi-la outra vez é imediato.
