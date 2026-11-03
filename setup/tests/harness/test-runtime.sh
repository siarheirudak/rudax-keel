#!/usr/bin/env bash
# Runtime oracles. No production environment selects the fixture.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)
# shellcheck source=setup/lib/runtime.sh
. "$SETUP/lib/runtime.sh"
STUB=$HERE/runtime-stub.sh
FIX=$HERE/fixtures
happy_only=0
[ "${1:-}" = --happy ] && happy_only=1
res(){ echo "RESULT $1: $2"; }

ec=0
out=$(bash "$STUB" --info-file "$FIX/runtime-rootless.info" launch 2>&1) || ec=$?
if [ "$ec" -eq 0 ] && ! printf '%s\n' "$out" | grep -q 'REFUSE	runtime'; then
  res R-H1 "BLOCKED (rootless fixture accepted)"
else
  res R-H1 "NOT BLOCKED"
fi
if [ "$happy_only" -eq 1 ]; then
  if [ "$ec" -ne 0 ]; then exit 1; fi
  exit 0
fi

lec=0
launch=$(bash "$STUB" --info-file "$FIX/runtime-rootful.info" launch 2>&1) || lec=$?
cls=$(bash "$STUB" --info-file "$FIX/runtime-rootful.info" classify 2>&1) || true
doc=$("$SETUP/keel-doctor.sh" 2>&1 || true)
if [ "$lec" -ne 0 ] && printf '%s\n' "$launch" | grep -q 'REFUSE	runtime	rootful' \
  && printf '%s\n' "$cls" | grep -qx rootful \
  && printf '%s\n' "$doc" | grep 'ENV-05' | grep -q CRITICAL \
  && printf '%s\n' "$doc" | grep 'ENV-05' | grep -q '❌'; then
  res R-A1 "BLOCKED (rootful fixture refused)"
else
  res R-A1 "NOT BLOCKED"
fi

saved=${KEEL_WORK_MIN_FREE:-}
export KEEL_WORK_MIN_FREE=999999999999999
if bash "$STUB" disk; then
  res R-A4 "NOT BLOCKED"
else
  res R-A4 "BLOCKED (free space below the minimum)"
fi
if [ -n "$saved" ]; then KEEL_WORK_MIN_FREE=$saved; else unset KEEL_WORK_MIN_FREE; fi

cec=0
chr=$(bash "$SETUP/chrome/chromium-argv.sh" --no-sandbox 2>&1) || cec=$?
if [ "$cec" -ne 0 ] && printf '%s\n' "$chr" | grep -q 'REFUSE	chromium	sandbox'; then
  res R-A5 "BLOCKED (sandbox flag refused)"
else
  res R-A5 "NOT BLOCKED"
fi

uec=0
ucls=$(bash "$STUB" --info-file "$FIX/runtime-userns.info" classify 2>&1) || uec=$?
if [ "$uec" -ne 0 ] && printf '%s\n' "$ucls" | grep -qx rootful; then
  res R-A7 "BLOCKED (userns remap is rootful)"
else
  res R-A7 "NOT BLOCKED"
fi

K=$SETUP/keel.sh
root=$(mktemp -d)
export KEEL_ROOT=$root
miss=
for spec in \
  "proto proto t rw true" \
  "role role developer true" \
  "role-env role-env developer true" \
  "export export" \
  "setup setup" \
  "proto-env proto-env true" \
  "egress-up egress-up" \
  "gate gate"
 do
  # shellcheck disable=SC2086
  set -- $spec
  name=$1
  shift
  ec=0
  out=$("$K" "$@" 2>&1) || ec=$?
  if [ "$ec" -eq 0 ] || ! printf '%s\n' "$out" | grep -q 'REFUSE	runtime	rootful'; then
    miss="$miss $name"
  fi
done
export KEEL_WORK_MIN_FREE=999999999999999
for spec in \
  "proto proto t rw true" \
  "role role developer true" \
  "export export" \
  "setup setup"
 do
  # shellcheck disable=SC2086
  set -- $spec
  name=$1
  shift
  ec=0
  out=$("$K" "$@" 2>&1) || ec=$?
  if [ "$ec" -eq 0 ] || ! printf '%s\n' "$out" | grep -q 'REFUSE	runtime	disk'; then
    miss="$miss disk-$name"
  fi
done
unset KEEL_WORK_MIN_FREE
rm -rf "$root"
if ! grep -Fqx 'launch_guard(){ keel_require_runtime || exit $?; } # launch-guard' "$K"; then
  miss="$miss production-guard"
fi
exec_root=$(mktemp -d)
ec=0
out=$(KEEL_ROOT=$exec_root DOCKER=false bash "$STUB" --exec -- proto t rw true 2>&1) || ec=$?
if printf '%s\n' "$out" | grep -q 'REFUSE	runtime	rootful' || printf '%s\n' "$out" | grep -q '^stub:'; then
  miss="$miss exec-rootful"
fi
rm -rf "$exec_root"
if [ -z "$miss" ]; then
  res R-A9 "BLOCKED (role proto export setup and the other launch paths refuse)"
else
  res R-A9 "NOT BLOCKED ($miss)"
fi

score_fix=$(mktemp)
cat > "$score_fix" << 'EOF'
❌ ENV-05  CRITICAL     isolation boundary: rootful
❌ ENV-07  CRITICAL     hardening flags accepted: stripped
❌ NOT READY (0 passed, 0 warnings, 2 failed; 2 critical)
EOF
if bash "$HERE/doctor-score.sh" "$score_fix" >/dev/null 2>&1; then
  res R-A8 "NOT BLOCKED"
else
  res R-A8 "BLOCKED (second critical stays red)"
fi
rm -f "$score_fix"
