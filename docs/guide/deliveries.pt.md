---
description: "Guardar itens com um nome, aos poucos, e gerar um único ficheiro de import Control-M com uma ou várias entregas."
---

# Entregas guardadas

Uma alteração raramente viaja sozinha ou de uma vez. Uma **entrega** é uma escolha
guardada: um nome, o branch e o commit de onde vêm os itens, e os itens.

```bash
ctmchain delivery save 'job novo' env/uat --item 'job:P77_CHAIN/P77_NEW' --base env/bench
ctmchain delivery save 'pasta semanal' env/uat --item 'folder:P77_WEEKLY_DAILY'
ctmchain delivery list
ctmchain delivery package env/bench 'job novo' 'pasta semanal' -o bench_import.xml
ctmchain delivery remove 'job novo'
```

## Três maneiras de guardar

- **De uma comparação.** Na página *Compare*, marcas os itens e carregas em *Keep N items…*
  em vez de gerar logo o XML.
- **Uma alteração tua.** Fazes a alteração num branch teu, fazes commit, comparas o teu
  branch com o do ambiente e guardas os itens.
- **A partir da cadeia, sem alterar nada.** Na página de um job, *Keep for a delivery…*
  guarda o job inteiro, ou um atributo dele, tal como o branch aberto o tem. Na página de
  uma pasta, a pasta.

## Um ficheiro com várias

Na página *Deliveries*, marcas uma ou várias, escolhes em *For* o branch que recebe e
carregas em *Generate XML*. Sai um único ficheiro com a soma, escrito como esse ambiente o
escreve. É o mesmo ficheiro que levar os mesmos itens de uma vez.

## Convém saber

- Uma entrega fica **presa ao commit** de onde foi feita: gera sempre o mesmo ficheiro. A
  lista diz *its branch moved since* quando o branch mudou depois.
- A lista diz **os commits que ela leva**: os do seu branch desde o último export, até ao
  commit em que foi guardada, que mudaram os seus itens (uma pasta conta com todos os seus
  jobs). Os commits que lhes mexeram depois de guardada vêm à parte, marcados *not in it*.
- Um item que o destino **já tem** igual vai no ficheiro na mesma, com a pasta dele: o que
  escolheste sai.
- Duas entregas que dão **dois valores** ao mesmo sítio são recusadas, com o nome da
  segunda. Nada é adivinhado: tira uma.
- Ficam guardadas no branch `map`, ao lado do mapa. Para a equipa as ver:
  `git push origin map`.
