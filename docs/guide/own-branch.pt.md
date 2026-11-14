---
description: "Experimentar um export Control-M num branch teu sem tocar no branch do ambiente, e levar o que ele tem para outro lado."
---

# Um branch teu

Para ver o que um export traz, guardado, antes de substituir o branch do ambiente: cria um
branch a partir do do ambiente e importa o export sobre ele.

```bash
git switch -c work/uat-next env/uat
ctmchain refresh ../exports/uat-next.xml --here            # o que mudaria
ctmchain refresh ../exports/uat-next.xml --here --apply
ctmchain compare env/uat work/uat-next                     # UAT de hoje contra o que chegou
```

Para um ficheiro só com algumas pastas (uma entrega), junta `--partial`: as pastas que o
ficheiro não tem ficam como estão.

```bash
ctmchain refresh ../exports/delivery.xml --here --partial --apply
```

Sem `--here` o refresh vai para o branch do ambiente, esteja o que estiver aberto; o
`--partial` também funciona aí, para um pacote importado no ambiente ([Refresh](refresh.md)).
Sem `--partial` um ficheiro só com algumas pastas é lido como export completo e removia as
outras: a pré-visualização diz quando um ficheiro parece assim, e avisa antes de remover
mais de metade do branch.

## O que um branch assim contém

Um branch teu é lido como o ambiente que contém: o do branch de onde partiu, até o export
completo de outro ambiente ir para cima dele. Por isso serve de origem tal como o branch
do ambiente:

```bash
ctmchain compare main work/uat-next
ctmchain take work/uat-next --list --base env/bench
ctmchain package env/bench work/uat-next --take 'folder:P77_WEEKLY_DAILY' -o bench_import.xml
ctmchain package env/uat work/uat-next -o uat_import.xml
```

A ferramenta sabe o ambiente pelo assunto do último commit de export na história do branch
(`refresh(uat): …` ou `import(uat): …`). Com `--no-commit` o comando imprime o assunto a
usar no commit.

Quando o export passa a ser o estado oficial do ambiente, fazes o [refresh](refresh.md)
normal e apagas o teu branch.
