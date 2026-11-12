---
description: "Trazer um export completo novo de um ambiente Control-M para o branch dele: ver o que mudou e depois substituir."
---

# Atualizar um ambiente

Um branch é o que o último export completo do seu ambiente disse, e mais nada. Um export
novo substitui-o, depois de mostrar o que mudou.

```bash
ctmchain refresh ../exports/uat.xml            # o que mudaria; nada é escrito
ctmchain refresh ../exports/uat.xml --apply    # substitui o env/uat e faz commit
git push origin env/uat
```

O primeiro comando lista o que entrou, o que saiu e o que mudou, atributo a atributo. O
segundo abre o branch, substitui os ficheiros das cadeias e faz o commit
(`refresh(uat): uat.xml`). As pastas e os jobs que o export já não tem saem.

O ambiente é dito pela letra dos nomes. Quando não dá para saber, indica-o:

```bash
ctmchain refresh ../exports/uat.xml --env uat
```

## Convém saber

- Com ficheiros de cadeias por commitar o refresh recusa: faz commit ou descarta primeiro.
- O mesmo export outra vez não muda nada (`already holds this export`).
- `--stat` dá só as contagens; `--no-commit` deixa o resultado por commitar.
- Um ficheiro só com algumas pastas (uma entrega) não é um export completo: vai para um
  [branch teu](own-branch.md) com `--here --partial`.
- Na página web: *Refresh*.
