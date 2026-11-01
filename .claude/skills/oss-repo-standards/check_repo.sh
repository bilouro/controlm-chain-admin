#!/usr/bin/env bash
# check_repo.sh — open-source hygiene checklist for controlm-chain-admin. Prints OK/MISSING per item.
set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
MISSING=0
ok()   { printf 'OK       %s\n' "$1"; }
miss() { printf 'MISSING  %s\n' "$1"; MISSING=$((MISSING+1)); }
has_file() { [ -e "$1" ] && ok "$1" || miss "$1"; }
has_section() { [ -f "$1" ] && grep -qiE "$2" "$1" && ok "$1: $3" || miss "$1: $3"; }

echo "== community files"
for f in README.md LICENSE CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md CHANGELOG.md \
         .github/ISSUE_TEMPLATE/bug_report.md .github/ISSUE_TEMPLATE/feature_request.md \
         .github/PULL_REQUEST_TEMPLATE.md .github/workflows/ci.yml .github/workflows/release.yml \
         .editorconfig .pre-commit-config.yaml pyproject.toml mkdocs.yml; do has_file "$f"; done

echo "== README sections"
has_section README.md 'img.shields.io|badge' "badges"
has_section README.md '^## .*(install|instala)' "Install section"
has_section README.md '^## .*(quick ?start|usage|getting started)' "Quickstart section"
has_section README.md 'contribut' "Contributing pointer"
has_section README.md '^## .*licen[cs]e|MIT' "Licence"

echo "== changelog / metadata"
has_section CHANGELOG.md '^## \[Unreleased\]' "Unreleased section"
has_section pyproject.toml '^\[project.urls\]' "project.urls"
has_section pyproject.toml 'classifiers' "classifiers"
has_section pyproject.toml 'ctmchain *=' "ctmchain script"
has_section mkdocs.yml 'i18n' "bilingual docs (mkdocs-static-i18n)"
has_section .github/workflows/release.yml 'id-token: *write' "Trusted Publishing (OIDC)"

echo "== commits (last 20 subjects, Conventional Commits)"
BAD="$(git log -20 --format=%s 2>/dev/null | grep -vE '^(feat|fix|docs|test|refactor|chore|ci|build|perf|style|revert)(\([a-z0-9/_-]+\))?!?: .+' || true)"
if [ -z "$BAD" ]; then ok "all recent subjects follow Conventional Commits"; else printf 'MISSING  non-conventional subjects:\n%s\n' "$BAD" | sed 's/^/         /'; MISSING=$((MISSING+1)); fi

echo "== GitHub community profile"
if command -v gh >/dev/null && gh repo view --json nameWithOwner --jq .nameWithOwner >/dev/null 2>&1; then
  REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
  PCT="$(gh api "repos/$REPO/community/profile" --jq .health_percentage 2>/dev/null || echo '?')"
  [ "$PCT" = "100" ] && ok "community profile 100%" || printf 'INFO     community profile: %s%%\n' "$PCT"
else
  echo "INFO     gh not available or not a GitHub repo; skipped"
fi

echo; [ $MISSING -eq 0 ] && echo "RESULT: OK" || { echo "RESULT: $MISSING item(s) missing"; exit 1; }
