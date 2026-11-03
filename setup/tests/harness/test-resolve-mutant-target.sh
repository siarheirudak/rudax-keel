#!/usr/bin/env bash
# Resolver inputs and the dispatch workflow. No network.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
ROOT=$(cd "$HERE/../../.." && pwd)
python3 "$HERE/resolve-mutant-target.py" --self-test || exit 1
wf="$ROOT/.github/workflows/mutate-pr.yml"
fail=0
need() {
  if ! grep -q "$2" "$1"; then
    echo "missing $2" >&2
    fail=1
  fi
}
# shellcheck disable=SC2016
need "$wf" 'run-name: mutants ${{ inputs.sha }}'
need "$wf" 'github.event.repository.default_branch'
need "$wf" 'setup/tests/harness/resolve-mutant-target.py'
need "$wf" 'actions/checkout@11d5960a326750d5838078e36cf38b85af677262'
if [ "$fail" -ne 0 ]; then
  exit 1
fi
exit 0
