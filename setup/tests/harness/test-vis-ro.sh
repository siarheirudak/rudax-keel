#!/usr/bin/env bash
# A DOCKER command that cannot reach a daemon must not be scored NOT BLOCKED.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SUITE=$HERE/visibility-suite.sh

check_unavailable() {
  local docker_cmd=$1 out errf ec
  errf=$(mktemp)
  set +e
  out=$(VIS_RO_ONLY=1 DOCKER="$docker_cmd" bash "$SUITE" 2>"$errf")
  ec=$?
  set +e
  rm -f "$errf"
  if [ "$ec" -eq 0 ]; then
    return 1
  fi
  if [ "$out" != "RESULT V-RO: ERROR docker unavailable" ]; then
    printf '%s\n' "$out" >&2
    return 1
  fi
  if printf '%s\n' "$out" | grep -q 'NOT BLOCKED'; then
    return 1
  fi
  return 0
}

if ! check_unavailable /bin/false; then
  echo "failing DOCKER was not reported as docker unavailable" >&2
  exit 1
fi
if ! check_unavailable "sh -c false"; then
  echo "multi-word failing DOCKER was not reported as docker unavailable" >&2
  exit 1
fi

root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
cat >"$root/docker" << 'EOF'
#!/bin/sh
echo "cannot connect to the docker daemon" >&2
exit 1
EOF
chmod +x "$root/docker"
errf=$root/err.txt
set +e
out=$(VIS_RO_ONLY=1 DOCKER="$root/docker" bash "$SUITE" 2>"$errf")
ec=$?
set +e
if [ "$ec" -eq 0 ] || [ "$out" != "RESULT V-RO: ERROR docker unavailable" ] || ! grep -q 'cannot connect to the docker daemon' "$errf" || printf '%s\n' "$out" | grep -q 'NOT BLOCKED'; then
  echo "docker stderr was swallowed or the verdict was wrong" >&2
  printf '%s\n' "$out" >&2
  cat "$errf" >&2
  exit 1
fi

mut=$root/suite.sh
python3 - "$SUITE" "$mut" << 'PY'
import sys
src, dst = sys.argv[1:]
old = 'res V-RO "ERROR docker unavailable"'
new = 'res V-RO "NOT BLOCKED (nested ro failed)"'
text = open(src, encoding="utf-8").read()
if text.count(old) != 1:
    raise SystemExit("mutant needle count %s" % text.count(old))
open(dst, "w", encoding="utf-8").write(text.replace(old, new, 1))
PY
chmod +x "$mut"
set +e
out=$(VIS_RO_ONLY=1 DOCKER=/bin/false bash "$mut" 2>/dev/null)
set +e
if printf '%s\n' "$out" | grep -q 'RESULT V-RO: ERROR docker unavailable'; then
  echo "mutant still reported docker unavailable" >&2
  exit 1
fi
if ! printf '%s\n' "$out" | grep -q 'NOT BLOCKED'; then
  echo "mutant did not produce the old verdict" >&2
  printf '%s\n' "$out" >&2
  exit 1
fi
echo "nested ro: docker unavailable is an error, not NOT BLOCKED"
