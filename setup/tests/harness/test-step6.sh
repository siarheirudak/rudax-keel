#!/usr/bin/env bash
# Step 6 standards generator. RESULT lines use BLOCKED for a held property.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
ROOT=$(cd "$HERE/../../.." && pwd -P)
# Drift check first. A later mutant still has to print RESULT lines, so a
# failing check does not abort the suite.
python3 "$ROOT/setup/standards/gen.py" --check || true
export KEEL_FORBID_LIVE=1
exec python3 "$HERE/step6_check.py"
