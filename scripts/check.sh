#!/usr/bin/env bash
# Same checks as .github/workflows/checks.yml. Nothing here is specific to one agent.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

project_checks() {
  # Single place for this repository's own tests.
  # npm test
  # pytest
  # go test ./...
  printf '%s\n' "no project checks yet"
}

if [[ ${1-} == --project-only ]]; then
  project_checks
  exit 0
fi

status=0
bash scripts/check-actionlint.sh || status=1
bash scripts/check-shellcheck.sh || status=1
bash scripts/check-json.sh || status=1
python3 scripts/check-md-links.py || status=1
python3 setup/tests/check-action-pins.py || status=1
bash setup/tests/test-fake-gh.sh || status=1
python3 scripts/check-scope.py --self-test || status=1
project_checks || status=1
exit "$status"
