#!/usr/bin/env bash
# Test-only entrypoint for runtime fixtures.
# Production scripts do not call this and do not select a fixture from the environment.
# Usage:
#   runtime-stub.sh --info-file FILE classify|launch
#   runtime-stub.sh disk
#   runtime-stub.sh --exec -- <keel.sh args>
# --exec classifies the rootless fixture, then runs that keel.sh command.
# The on-disk keel.sh is not modified and still classifies the live daemon.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)
# shellcheck source=setup/lib/runtime.sh
. "$SETUP/lib/runtime.sh"

exec_keel() {
  local dst info status
  info=$HERE/fixtures/runtime-rootless.info
  if [ ! -f "$info" ]; then
    echo "stub: rootless fixture missing" >&2
    return 1
  fi
  # Keep the command beside the real setup files. A copied tree of symlinks
  # makes the deny base look replaced, and the role policy refuses that.
  dst=$(mktemp "$SETUP/keel.harness.XXXXXX")
  # shellcheck disable=SC2064
  trap 'rm -f "$dst"' RETURN
  if ! python3 - "$SETUP/keel.sh" "$dst" "$info" << 'PY'
import pathlib, shlex, sys
src, dst, info = sys.argv[1:]
text = pathlib.Path(src).read_text()
old = "launch_guard(){ keel_require_runtime || exit $?; } # launch-guard"
if text.count(old) != 1:
    sys.stderr.write("stub: launch guard is not the production call\n")
    sys.exit(1)
new = "launch_guard(){ keel_require_runtime --info-file %s || exit $?; } # launch-guard" % shlex.quote(info)
pathlib.Path(dst).write_text(text.replace(old, new, 1))
PY
  then
    return 1
  fi
  chmod 755 "$dst"
  "$dst" "$@"
  status=$?
  return "$status"
}

if [ "${1:-}" = --exec ]; then
  shift
  if [ "${1:-}" != -- ]; then
    echo "usage: runtime-stub.sh --exec -- <keel.sh args>" >&2
    exit 2
  fi
  shift
  exec_keel "$@"
  exit $?
fi

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
