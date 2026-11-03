#!/usr/bin/env bash
# Test-only entrypoint for runtime fixtures.
# Production scripts do not call this and do not select a fixture from the environment.
# Usage: runtime-stub.sh --info-file FILE classify|launch
#        runtime-stub.sh disk
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)
# shellcheck source=setup/lib/runtime.sh
. "$SETUP/lib/runtime.sh"
info_file=
cmd=
while [ $# -gt 0 ]; do
  case $1 in
    --info-file) info_file=${2:-}; shift 2;;
    classify|launch|disk) cmd=$1; shift;;
    *) echo "usage: runtime-stub.sh --info-file FILE classify|launch" >&2; exit 2;;
  esac
done
case $cmd in
  classify) keel_classify_runtime --info-file "$info_file";;
  launch) keel_require_runtime --info-file "$info_file";;
  disk) keel_disk_ok "${KEEL_ROOT:-$HOME}";;
  *) echo "usage: runtime-stub.sh --info-file FILE classify|launch" >&2; exit 2;;
esac
