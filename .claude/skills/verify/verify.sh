#!/usr/bin/env bash
# verify.sh — the controlm-chain-admin quality gate. Prints a PASS/FAIL report, exits 1 on FAIL.
# Usage: .claude/skills/verify/verify.sh [--python] [--web] [--base <git-ref>]
set -uo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
RUN_PY=1; RUN_WEB=1; BASE="origin/main"
while [ $# -gt 0 ]; do
  case "$1" in
    --python) RUN_WEB=0 ;;
    --web) RUN_PY=0 ;;
    --base) BASE="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

declare -a REPORT=(); FAIL=0
record() { REPORT+=("$(printf '%-14s %s' "$1:" "$2")"); case "$2" in FAIL*) FAIL=1 ;; esac; }
run() { # run <label> <command...>; keeps the last 25 lines of output on failure
  local label="$1"; shift
  local out; out="$("$@" 2>&1)"; local rc=$?
  if [ $rc -eq 0 ]; then record "$label" "PASS"; else record "$label" "FAIL (exit $rc)"; printf '--- %s\n%s\n' "$label" "$(printf '%s\n' "$out" | tail -25)"; fi
  return $rc
}

# ---------------------------------------------------------------- Python
if [ $RUN_PY -eq 1 ] && [ -f pyproject.toml ]; then
  run "Lint (ruff)" ruff check . && run "Format (ruff)" ruff format --check . || true
  [ -d src ] && run "Types (mypy)" mypy src || true
  GATE="$(sed -n 's/^fail_under *= *\([0-9]*\).*/\1/p' pyproject.toml | head -1)"; GATE="${GATE:-90}"
  run "Tests (pytest)" pytest -q --cov=controlm_chain_admin --cov-report=term-missing --cov-fail-under="$GATE" || true
  if python3 -c "import build" 2>/dev/null; then run "Build (wheel)" python3 -m build --outdir /tmp/ctmchain-build-check || true; else record "Build (wheel)" "SKIPPED (pip install build)"; fi
  if [ -d src ] && grep -rnE "breakpoint\(\)|import pdb|pdb\.set_trace" src >/dev/null 2>&1; then record "Debug left (py)" "FAIL"; grep -rnE "breakpoint\(\)|import pdb|pdb\.set_trace" src; else record "Debug left (py)" "PASS"; fi
elif [ $RUN_PY -eq 1 ]; then
  record "Python" "SKIPPED (no pyproject.toml)"
fi

# ---------------------------------------------------------------- Frontend
if [ $RUN_WEB -eq 1 ] && [ -f web/package.json ]; then
  ( cd web && run "Lint (web)" npm run --silent lint && run "Types (web)" npm run --silent typecheck || true
    run "Tests (web)" npm test --silent -- --run --coverage || true
    run "Build (web)" npm run --silent build || true )
  if grep -rn "console.log" web/src >/dev/null 2>&1; then record "Debug left (web)" "FAIL"; grep -rn "console.log" web/src | head; else record "Debug left (web)" "PASS"; fi
elif [ $RUN_WEB -eq 1 ]; then
  record "Frontend" "SKIPPED (no web/package.json)"
fi

# ---------------------------------------------------------------- No real data
PATTERNS=".claude/no-real-data.patterns"
if [ -f "$PATTERNS" ]; then
  HITS="$(git ls-files -z | xargs -0 grep -nIiE -f "$PATTERNS" -- 2>/dev/null | grep -v "^${PATTERNS}:" || true)"
  if [ -n "$HITS" ]; then record "No real data" "FAIL ($(printf '%s\n' "$HITS" | wc -l | tr -d ' ') hits)"; printf '%s\n' "$HITS" | head -20; else record "No real data" "PASS"; fi
else
  record "No real data" "SKIPPED (no $PATTERNS; run locally before merging)"
fi

# ---------------------------------------------------------------- Diff
if git rev-parse --verify -q "$BASE" >/dev/null; then
  record "Diff vs $BASE" "$(git diff --shortstat "$BASE"...HEAD 2>/dev/null | sed 's/^ *//' || echo 'n/a')"
else
  record "Diff" "base $BASE not found (use --base)"
fi

echo; echo "VERIFICATION REPORT — $(date +%Y-%m-%d) — $(git rev-parse --short HEAD 2>/dev/null || echo 'no commits')"
printf '%s\n' "${REPORT[@]}"
if [ $FAIL -eq 1 ]; then echo "Overall:       NOT READY"; exit 1; else echo "Overall:       READY (hand review of the diff still required)"; fi
