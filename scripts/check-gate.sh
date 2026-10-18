#!/usr/bin/env bash
# Fail unless every needed job succeeded. Write the table to the job summary.
set -euo pipefail

names=(actionlint shellcheck json md-links action-pins fake-gh project)
vars=(R_ACTIONLINT R_SHELLCHECK R_JSON R_MD_LINKS R_ACTION_PINS R_FAKE_GH R_PROJECT)
fail=0
summary=${GITHUB_STEP_SUMMARY-}
lines="| Job | Result |
|---|---|"

index=0
while [[ $index -lt ${#names[@]} ]]; do
  name=${names[$index]}
  var=${vars[$index]}
  result=${!var-}
  if [[ -z $result ]]; then
    result=missing
  fi
  lines="${lines}
| ${name} | ${result} |"
  if [[ $result != success ]]; then
    fail=1
  fi
  index=$((index + 1))
done

printf '%s\n' "$lines"
if [[ -n $summary ]]; then
  printf '%s\n' "$lines" >>"$summary"
fi
if [[ $fail -ne 0 ]]; then
  printf 'how to fix: open the failed, cancelled, or skipped job in the table above and fix that finding\n' >&2
  exit 1
fi
