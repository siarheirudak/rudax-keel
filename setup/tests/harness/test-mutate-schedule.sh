#!/usr/bin/env bash
# Nightly schedule. No matrix. The per-PR workflow stays dispatch-only.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
ROOT=$(cd "$HERE/../../.." && pwd)
full=$ROOT/.github/workflows/mutate-full.yml
pr=$ROOT/.github/workflows/mutate-pr.yml

fail() { printf '%s\n' "$1" >&2; exit 1; }

cron=$(grep -E '^[[:space:]]*- cron:' "$full" || true)
if [ "$cron" != '    - cron: "17 18 * * *"' ]; then
  fail "cron is not 17 18 * * *"
fi
if grep -q '17 6 \* \* \*' "$full"; then
  fail "old cron remains"
fi
if grep -Eq '^[[:space:]]*(matrix|strategy):' "$full"; then
  fail "NIGHT-A1 matrix or strategy is present"
fi

python3 - "$full" << 'PY' || exit 1
import sys
text = open(sys.argv[1], encoding="utf-8").read().splitlines()
start = None
for index, line in enumerate(text):
    if line == "  mutants:":
        start = index
        break
if start is None:
    sys.exit("NIGHT-A1 mutants job missing")
end = len(text)
for index in range(start + 1, len(text)):
    line = text[index]
    if line.startswith("  ") and not line.startswith("   ") and line.rstrip().endswith(":"):
        end = index
        break
job = "\n".join(text[start:end])
if "contents: read" not in job:
    sys.exit("NIGHT-A1 mutants job is not contents: read")
if "contents: write" in job or "actions: write" in job:
    sys.exit("NIGHT-A1 mutants job gained write permission")
PY

python3 - "$pr" << 'PY' || exit 1
import sys
text = open(sys.argv[1], encoding="utf-8").read().splitlines()
start = None
for index, line in enumerate(text):
    if line == "on:":
        start = index
        break
if start is None:
    sys.exit("NIGHT-A1 mutate-pr has no on block")
end = len(text)
for index in range(start + 1, len(text)):
    line = text[index]
    if line and not line.startswith(" ") and not line.startswith("#"):
        end = index
        break
block = "\n".join(text[start:end])
if "workflow_dispatch:" not in block:
    sys.exit("NIGHT-A1 mutate-pr is not dispatch-only")
for banned in ("pull_request:", "pull_request_target:", "schedule:", "push:"):
    if banned in block:
        sys.exit("NIGHT-A1 mutate-pr trigger includes " + banned)
PY

echo "mutate schedule: cron is 17 18 * * *; NIGHT-A1 holds"
