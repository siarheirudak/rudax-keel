#!/usr/bin/env bash
# NOT BLOCKED must fail the result checker. Dropping it from the pattern is caught.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SCRIPT=$HERE/attack-results.sh
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT

bad=$root/bad.log
good=$root/good.log
wrong=$root/wrong.log
errlog=$root/err.log
printf '%s\n' 'RESULT E-A1: NOT BLOCKED' 'RESULT E-A2: BLOCKED (unauthorized host)' >"$bad"
printf '%s\n' 'RESULT E-A1: BLOCKED (unauthorized host)' >"$good"
printf '%s\n' 'RESULT E-A1: WRONG REASON (expected /x/)' >"$wrong"
printf '%s\n' 'RESULT E-A1: ERROR docker' >"$errlog"

flags() {
  local out
  out=$(bash "$1" "$2")
  [ -n "$out" ]
}

if ! flags "$SCRIPT" "$bad"; then
  echo "RESULT CHK-1: NOT BLOCKED"
  echo "checker treated NOT BLOCKED as pass" >&2
  exit 1
fi
if flags "$SCRIPT" "$good"; then
  echo "RESULT CHK-1: NOT BLOCKED"
  echo "checker flagged a blocked result" >&2
  exit 1
fi
if ! flags "$SCRIPT" "$wrong"; then
  echo "RESULT CHK-1: NOT BLOCKED"
  echo "checker treated WRONG REASON as pass" >&2
  exit 1
fi
if ! flags "$SCRIPT" "$errlog"; then
  echo "RESULT CHK-1: NOT BLOCKED"
  echo "checker treated ERROR as pass" >&2
  exit 1
fi
echo "RESULT CHK-1: BLOCKED (NOT BLOCKED is not a pass)"

mut=$root/attack-results.sh
python3 - "$SCRIPT" "$mut" << 'PY'
import sys
src, dst = sys.argv[1:]
old = "NOT BLOCKED|"
text = open(src, encoding="utf-8").read()
if text.count(old) != 1:
    raise SystemExit("mutant needle count %s" % text.count(old))
open(dst, "w", encoding="utf-8").write(text.replace(old, "", 1))
PY
if flags "$mut" "$bad"; then
  echo "NOT BLOCKED pass mutant was not caught" >&2
  exit 1
fi
echo "attack results: NOT BLOCKED is not a pass"
