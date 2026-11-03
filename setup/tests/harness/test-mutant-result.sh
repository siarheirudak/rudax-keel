#!/usr/bin/env bash
# Mutant-result binding. No network. The live gate reads GitHub itself.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
ROOT=$(cd "$HERE/../../.." && pwd)
KEEL_MUTANTS_OK=1 python3 "$HERE/mutant-result.py" --self-test || exit 1
if [ ! -f "$ROOT/.github/workflows/mutate-pr.yml" ]; then
  exit 0
fi
fail=0
need() {
  if ! grep -q "$2" "$ROOT/$1"; then
    echo "missing $2 in $1" >&2
    fail=1
  fi
}
need .github/workflows/checks.yml 'KEEL_MUTATE_DEFER=1'
need .github/workflows/checks.yml 'github.event.pull_request.head.sha'
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
if [ "$fail" -ne 0 ]; then
  exit 1
fi
exit 0
