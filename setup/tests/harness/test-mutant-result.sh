#!/usr/bin/env bash
# Mutant-result binding. No network. The live gate reads GitHub itself.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
ROOT=$(cd "$HERE/../../.." && pwd)
KEEL_MUTANTS_OK=1 python3 "$HERE/mutant-result.py" --self-test || exit 1
a4=0
gate_src="$ROOT/scripts/check-gate.sh"
if [ -f "$gate_src" ]; then
  fix=$(mktemp -d)
  mkdir -p "$fix/scripts" "$fix/setup/tests/harness"
  cp "$gate_src" "$fix/scripts/check-gate.sh"
  printf '%s\n' actionlint > "$fix/scripts/gate-jobs.txt"
  printf '%s\n' 'import sys' 'sys.exit(1)' > "$fix/setup/tests/harness/mutant-result.py"
  ec=0
  GITHUB_EVENT_NAME=pull_request R_ACTIONLINT=success \
    bash "$fix/scripts/check-gate.sh" >/dev/null 2>&1 || ec=$?
  rm -rf "$fix"
  if [ "$ec" -eq 1 ]; then
    echo "RESULT M-A4: BLOCKED (gate calls the binder)"
  else
    echo "RESULT M-A4: NOT BLOCKED (exit $ec)"
    a4=1
  fi
fi
if [ ! -f "$ROOT/.github/workflows/mutate-pr.yml" ]; then
  exit "$a4"
fi
fail=0
need() {
  if ! grep -q "$2" "$ROOT/$1"; then
    echo "missing $2 in $1" >&2
    fail=1
  fi
}
need .github/workflows/checks.yml 'KEEL_MUTATE_DEFER=1'
if grep -q 'github.event.pull_request.head.sha' "$ROOT/.github/workflows/checks.yml"; then
  echo "gate sha is taken from the workflow expression" >&2
  fail=1
fi
if grep -q 'GITHUB_SHA' "$HERE/mutant-result.py"; then
  echo "binder reads GITHUB_SHA" >&2
  fail=1
fi
# shellcheck disable=SC2016
need .github/workflows/mutate-pr.yml 'run-name: mutants ${{ inputs.sha }}'
need .github/workflows/mutate-pr.yml 'github.event.repository.default_branch'
need .github/workflows/mutate-full.yml 'KEEL_MUTATE_FORCE=1'
if grep -q 'KEEL_MUTATE_DEFER' "$ROOT/.github/workflows/mutate-full.yml"; then
  echo "daily run defers mutants" >&2
  fail=1
fi
if grep -q 'KEEL_MUTANTS_OK' "$HERE/mutant-result.py"; then
  echo "binder reads a pass switch" >&2
  fail=1
fi
if [ "$fail" -ne 0 ] || [ "$a4" -ne 0 ]; then
  exit 1
fi
exit 0
