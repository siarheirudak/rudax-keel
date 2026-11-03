#!/usr/bin/env bash
# Live doctor acceptance: the failing CRITICAL ids must be exactly ENV-05.
# This file is the only scorer. The doctor and the launch path do not accept a wider set.
set -u
score_exact=1 # doctor-score-exact
file=${1:-}
if [ -z "$file" ] || [ ! -f "$file" ]; then
  echo "ERROR: doctor score: missing log" >&2
  exit 1
fi
if [ "$score_exact" != 1 ]; then
  grep -q 'NOT READY' "$file"
  exit 0
fi
if grep -q 'READY WITH WARNINGS' "$file"; then
  echo "ERROR: doctor score: READY WITH WARNINGS" >&2
  exit 1
fi
if ! grep -q 'NOT READY' "$file" && grep -q 'READY' "$file"; then
  echo "ERROR: doctor score: READY" >&2
  exit 1
fi
if ! grep -q 'ENV-05' "$file"; then
  echo "ERROR: doctor score: ENV-05 missing" >&2
  exit 1
fi
fails=$(grep '❌' "$file" | grep CRITICAL | awk '{ print $2 }')
# shellcheck disable=SC2086
set -- $fails
if [ "$#" -eq 1 ] && [ "$1" = ENV-05 ]; then
  exit 0
fi
echo "ERROR: doctor score: failing critical set is${fails:+ $fails}" >&2
exit 1
