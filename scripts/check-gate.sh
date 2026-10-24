#!/usr/bin/env bash
# Fail unless every needed job succeeded. Write the table to the job summary.
# Job ids live in scripts/gate-jobs.txt. The env var is R_ plus the id,
# uppercased, with hyphens turned into underscores.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
jobs_file="$ROOT/scripts/gate-jobs.txt"
names=()
while IFS= read -r line || [[ -n $line ]]; do
  case $line in
    '' | \#*) continue ;;
  esac
  names+=("$line")
done <"$jobs_file"

fail=0
bad=""
summary=${GITHUB_STEP_SUMMARY-}
lines="| Job | Result |
|---|---|"

index=0
while [[ $index -lt ${#names[@]} ]]; do
  name=${names[$index]}
  var=$(printf '%s' "$name" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
  var="R_${var}"
  result=${!var-}
  if [[ -z $result ]]; then
    result=missing
  fi
  lines="${lines}
| ${name} | ${result} |"
  if [[ $result != success ]]; then
    fail=1
    bad="${bad}${name} "
  fi
  index=$((index + 1))
done

printf '%s\n' "$lines"
if [[ -n $summary ]]; then
  printf '%s\n' "$lines" >>"$summary"
fi
if [[ $fail -ne 0 ]]; then
  printf 'how to fix: these jobs are not success: %s\n' "${bad% }" >&2
  exit 1
fi
