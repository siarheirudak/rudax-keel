#!/usr/bin/env bash
# Refuse Chromium launches that turn the sandbox off. No browser is started.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/.." && pwd -P)
# shellcheck source=setup/lib/runtime.sh
. "$SETUP/lib/runtime.sh"
keel_chromium_argv "$@"
