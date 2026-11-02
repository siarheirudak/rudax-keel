#!/usr/bin/env bash
# Print attack results that are still open. NOT BLOCKED is not a pass.
# shellcheck shell=bash
attack_results_open() {
  local log=$1
  local pattern='^RESULT .*(NOT BLOCKED|WRONG REASON|: ERROR)'  # not-blocked-fails
  grep -aE "$pattern" "$log" || true
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -u
  if [ "$#" -ne 1 ]; then
    echo "usage: attack-results.sh LOG" >&2
    exit 2
  fi
  attack_results_open "$1"
fi
