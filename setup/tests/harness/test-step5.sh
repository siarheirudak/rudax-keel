#!/usr/bin/env bash
# Step 5 discovery checks. RESULT lines use BLOCKED for a held property.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
export KEEL_FORBID_LIVE=1
exec python3 "$HERE/step5_check.py"
