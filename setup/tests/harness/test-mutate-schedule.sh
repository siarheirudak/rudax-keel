#!/usr/bin/env bash
# Nightly schedule. No matrix. The per-PR workflow stays dispatch-only.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
ROOT=$(cd "$HERE/../../.." && pwd)
full=$ROOT/.github/workflows/mutate-full.yml
pr=$ROOT/.github/workflows/mutate-pr.yml

fail() { printf '%s\n' "$1" >&2; exit 1; }

if ! grep -Fxq '    - cron: "17 18 * * *"' "$full"; then
  fail "daily cron is not 17 18 * * *"
fi
if ! grep -Fxq '    - cron: "17 18 * * 1"' "$full"; then
  fail "weekly cron is missing"
fi
if grep -q '17 6 \* \* \*' "$full"; then
  fail "old cron remains"
fi
if grep -q 'actions/cache' "$full" || grep -q 'actions/cache' "$pr"; then
  fail "mutate workflows use a cache"
fi
limit_note=$(python3 - "$full" "$pr" << 'PY'
import sys

prefix = "    timeout-minutes: "
suffix = " # shard-timeout"
missing = "shard timeout is missing"
outside = "shard timeout is not between 1 and 90 minutes"

def classify(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    marked = [line for line in lines if "# shard-timeout" in line]
    if len(marked) != 1:
        return missing
    line = marked[0]
    if not line.startswith(prefix) or not line.endswith(suffix):
        return missing
    if len(line) <= len(prefix) + len(suffix):
        return missing
    value = line[len(prefix):len(line) - len(suffix)]
    if len(value) < 1 or len(value) > 2:
        return outside
    for ch in value:
        if ch < "0" or ch > "9":
            return outside
    if len(value) > 1 and value[0] == "0":
        return outside
    try:
        number = int(value)
    except Exception:
        return outside
    maximum = 90
    if number >= 1 and number <= maximum:
        return ""
    return outside

if len(sys.argv) != 3:
    sys.stdout.write(missing + "\n")
    sys.exit(1)
for path in sys.argv[1:]:
    try:
        note = classify(path)
    except Exception:
        note = missing
    if note:
        sys.stdout.write(note + "\n")
        sys.exit(1)
sys.exit(0)
PY
) || fail "${limit_note:-shard timeout is missing}"
if ! grep -q 'fail-fast: false' "$full" || ! grep -q 'fail-fast: false' "$pr"; then
  fail "shard fail-fast is not false"
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
