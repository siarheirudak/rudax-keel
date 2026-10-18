#!/usr/bin/env bash
# Shellcheck the setup scripts and the local check scripts. shellcheck is preinstalled.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

files=()
while IFS= read -r path; do
  files+=("$path")
done < <(find setup scripts -name '*.sh' -type f | sort)

if [[ ${#files[@]} -eq 0 ]]; then
  printf 'how to fix: no shell scripts found under setup/ or scripts/\n' >&2
  exit 1
fi

set +e
out=$(shellcheck -x "${files[@]}" 2>&1)
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  printf '%s\n' "$out" >&2
  bad=$(printf '%s\n' "$out" | sed -n 's/^\([^:]*\):[0-9].*/\1/p' | sort -u | paste -sd, -)
  if [[ -z $bad ]]; then
    bad="the scripts listed above"
  fi
  printf 'how to fix: run shellcheck -x on %s and fix what it reports\n' "$bad" >&2
  exit 1
fi
