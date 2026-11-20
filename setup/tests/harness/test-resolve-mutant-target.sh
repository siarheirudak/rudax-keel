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
if ! HERE="$HERE" PYTHONDONTWRITEBYTECODE=1 python3 - "$wf" <<'PY'
import os
import sys
sys.path.insert(0, os.environ["HERE"])
import gate_step_check as gate
reason = gate.mutate_pr_checkout_problems(open(sys.argv[1], encoding="utf-8").read())
if reason:
    sys.stderr.write("missing %s\n" % reason)
    raise SystemExit(1)
PY
then
  fail=1
fi
if [ "$fail" -ne 0 ]; then
  exit 1
fi
exit 0
