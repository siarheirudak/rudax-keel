#!/usr/bin/env bash
# Step 4 launch checks. RESULT lines use BLOCKED for a held property.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
exec python3 "$HERE/step4_check.py"
