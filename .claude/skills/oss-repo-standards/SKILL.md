---
name: oss-repo-standards
description: Open-source repository standards for controlm-chain-admin — README structure, community health files, Conventional Commits, Keep a Changelog, SemVer, issue/PR templates, Trusted Publishing release, naming conventions, bilingual mkdocs. Use when creating or editing README, CONTRIBUTING, CHANGELOG, docs, pyproject metadata, GitHub workflows or templates, when naming a module, command or JSON key, or when someone asks whether the repo «segue os padrões open source».
---

# oss-repo-standards

Adapted from Everything Claude Code `opensource-packager`, `opensource-sanitizer` and
`rules/common` (MIT, see `.claude/ATTRIBUTION.md`), and from the author's `xmldiffreport`.

## Files every release must have

| File | Standard |
|---|---|
| `README.md` | See structure below |
| `LICENSE` | MIT, copyright line with year and author |
| `CONTRIBUTING.md` | how to set up, run tests, TDD rule, commit format, PR checklist, where to ask |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1 with a contact address |
| `SECURITY.md` | supported versions, private reporting channel, response time |
| `CHANGELOG.md` | Keep a Changelog 1.1: `## [Unreleased]` on top, sections Added/Changed/Fixed/Removed, compare links |
| `.github/ISSUE_TEMPLATE/bug_report.md`, `feature_request.md`, `.github/PULL_REQUEST_TEMPLATE.md` | PR template includes the `verify` report and the TDD checkbox |
| `.github/workflows/ci.yml`, `release.yml`, `docs.yml` | CI on push/PR (lint + test matrix 3.11–3.13, macOS/Windows), release on `v*` tags with PyPI Trusted Publishing (OIDC, environment `pypi`), docs to GitHub Pages |
| `.editorconfig`, `.pre-commit-config.yaml` | ruff, ruff-format, end-of-file, trailing whitespace |
| `pyproject.toml` | name, version (single source), description, readme, `requires-python`, license, authors, keywords, classifiers (Development Status, Intended Audience, License, OS, Python versions, Topic, Typing :: Typed), `[project.urls]` Homepage/Documentation/Repository/Issues/Changelog, `[project.scripts] ctmchain` |
| `mkdocs.yml` | mkdocs-material, `mkdocs-static-i18n` with `en` default and `pt`, every page has a `.pt.md` twin |

## README structure (in this order)

1. Title, one-line tagline, badges: Docs, CI, PyPI version, Python versions, License.
2. Documentation links (English and Português).
3. One paragraph: what it is, for whom, the problem it solves (Control-M XML exports are hard
   to manage; JSON in git, links as first-class, environment-neutral base).
4. Why not X: short comparison with the Control-M UI, Automation API JSON, raw XML + git.
5. Install (`pip install controlm-chain-admin`, `[web]` extra) and requirements.
6. Quickstart: `init`, `distinct`, `import`, `validate`, `export`, `serve` in 10 lines, with
   the synthetic fixture so the reader can run it without real data.
7. Concepts in a small table (chain repository, base, environment, link, constant, override).
8. Status / roadmap pointer to `BACKLOG.md`, Contributing pointer, Licence.

No real data in any example: application `P77`, hosts `srvu-p77-*`, addresses `@example.com`.

## Conventions

- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`,
  `ci:`), imperative, ≤ 72 chars subject, body explains why. Breaking change → `!` and footer.
- **Versions**: SemVer; `0.x` while the JSON layout may change; tag `vX.Y.Z` = release.
- **Branches**: `main` protected by CI; short-lived `feat/<topic>`, `fix/<topic>`.
- **Python names**: package `controlm_chain_admin`, modules and functions `snake_case`,
  classes `PascalCase`, constants `UPPER_SNAKE`, private `_leading_underscore`.
- **CLI**: command `ctmchain`, subcommands kebab-case (`rename-job`), flags `--kebab-case`.
- **JSON keys**: attributes mirrored from Control-M XML keep their exact XML name
  (`JOBNAME`, `SUB_APPLICATION`) for fidelity; keys that belong to this tool are
  `snake_case` (`envs`, `links`, `cleanup`, `external`).
- **Docs**: English first, Portuguese twin, same headings; code blocks copy-pasteable.
- **Issues/PRs**: labels `bug`, `enhancement`, `docs`, `good first issue`; PR title in
  Conventional Commits form.

## Verify

1. Run `.claude/skills/oss-repo-standards/check_repo.sh`; it lists missing files/sections and
   checks the last 20 commit subjects against Conventional Commits. All items `OK` or an
   accepted `TODO` with the backlog story that will add it.
2. `gh api repos/{owner}/{repo}/community/profile --jq .health_percentage` must be `100`
   once the files exist.
3. Read the README top to bottom as a stranger: can they install and run the quickstart in
   five minutes without asking anything? Every command copy-pasteable and tested.
4. Grep the docs for anything that looks like real data (see `verify`'s no-real-data phase).
5. Finish with the `verify` skill and paste its report in the PR.
