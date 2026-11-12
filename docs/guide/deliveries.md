---
description: "Keep items for later under a name, little by little, and make one Control-M import file from one or several of them."
---

# Deliveries kept for later

A change seldom travels alone or at once. A **delivery** is a choice kept: a name, the
branch and the commit the items come from, and the items.

```bash
ctmchain delivery save 'new job' env/uat --item 'job:P77_CHAIN/P77_NEW' --base env/bench
ctmchain delivery save 'weekly folder' env/uat --item 'folder:P77_WEEKLY_DAILY'
ctmchain delivery list
ctmchain delivery package env/bench 'new job' 'weekly folder' -o bench_import.xml
ctmchain delivery remove 'new job'
```

## Three ways to keep one

- **From a comparison.** On the *Compare* page, check the items and press *Keep N items…*
  instead of packaging at once.
- **A change of your own.** Make it on a branch of your own, commit, compare your branch
  with the environment's and keep the items.
- **From the chain, with nothing changed.** On the page of a job, *Keep for a delivery…*
  keeps the whole job, or one attribute of it, as the branch checked out has it. On the
  page of a folder, the folder.

## One file from several

On the *Deliveries* page, check one or several, choose in *For* the branch that receives
and press *Generate XML*. One file comes out with their sum, written as that environment
writes it. It is the same file as taking the same items at once.

## Good to know

- A delivery is **tied to the commit** it was made from: the file it gives is the same
  whenever it is made. The list says *its branch moved since* when it did.
- An item the target **already has** is packaged all the same, with its folder: what you
  chose goes in the file.
- Two deliveries that give one place **two values** are refused, naming the second. Nothing
  is guessed: leave one out.
- They are kept on the branch `map`, beside the map. For the team to see them:
  `git push origin map`.
