#!/usr/bin/env bash
# Decide which harness mutants run.
# stdout is one line:
#   RESULT mutate: skipped (no harness files changed)
#   RESULT mutate: run
#   RESULT mutate: run <ids>
# "run" with no ids is the full CI set. A missing base, or a git diff that
# fails, exits 1 with ERROR: mutate: on stderr.
# The diff is setup/, .github/, and the gate paths outside those trees.
# A mapped target, an exact policy path, or a listed oracle script selects its
# CI mutants. Any other file in the diff selects the full set.
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)

mutate_fail() { printf 'ERROR: mutate: %s\n' "$1" >&2; exit 1; } # missing-base-fails

mutate_have() { git -C "$1" rev-parse --verify "${2}^{commit}" >/dev/null 2>&1; }

mutate_fetch_branch() {
  local repo=$1 branch=$2
  git -C "$repo" remote get-url origin >/dev/null 2>&1 || return 1
  GIT_TERMINAL_PROMPT=0 git -C "$repo" fetch -q --depth=200 --no-tags origin \
    "refs/heads/${branch}:refs/remotes/origin/${branch}" >&2 || return 1
  if [ "$(git -C "$repo" rev-parse --is-shallow-repository 2>/dev/null || printf '%s' false)" = true ]; then
    GIT_TERMINAL_PROMPT=0 git -C "$repo" fetch -q --deepen=200 --no-tags origin >&2 || return 1
  fi
}

mutate_plan() {
  local repo base branch namesf errf names extra staged explicit shallow
  repo=${KEEL_MUTATE_REPO:-$(cd "$SETUP/.." && pwd)}
  namesf=$(mktemp)
  errf=$(mktemp)
  # shellcheck disable=SC2064
  trap "rm -f '$namesf' '$errf'" RETURN
  explicit=0
  base=${KEEL_MUTATE_BASE:-}
  if [ -n "$base" ]; then
    explicit=1
  elif [ -n "${GITHUB_BASE_REF:-}" ]; then
    base="origin/${GITHUB_BASE_REF}"
  else
    base=origin/main
  fi
  branch=${base#origin/}
  if ! mutate_have "$repo" "$base"; then
    if [ "$branch" != "$base" ]; then
      mutate_fetch_branch "$repo" "$branch" || true
    fi
  fi
  if ! mutate_have "$repo" "$base"; then
    if [ "$explicit" -eq 1 ]; then
      mutate_fail "base ref '${base}' does not resolve"
    fi
    mutate_fail "base ref missing" # missing-base-fails
  fi
  shallow=$(git -C "$repo" rev-parse --is-shallow-repository 2>/dev/null || printf '%s' false)
  set -- setup .github scripts/check-gate.sh scripts/gate-jobs.txt scripts/tests/test_gate_jobs.py
  if ! git -C "$repo" diff --name-only "$base"...HEAD -- "$@" >"$namesf" 2>"$errf"; then
    if [ "$shallow" = true ] && git -C "$repo" remote get-url origin >/dev/null 2>&1; then
      GIT_TERMINAL_PROMPT=0 git -C "$repo" fetch -q --deepen=200 --no-tags origin >&2 \
        || mutate_fail "git diff against ${base} failed"
      if ! git -C "$repo" diff --name-only "$base"...HEAD -- "$@" >"$namesf" 2>"$errf"; then
        mutate_fail "git diff against ${base} failed"
      fi
    else
      mutate_fail "git diff against ${base} failed"
    fi
  fi
  if ! extra=$(git -C "$repo" diff --name-only HEAD -- "$@"); then
    mutate_fail "git diff of the work tree failed"
  fi
  if ! staged=$(git -C "$repo" diff --cached --name-only -- "$@"); then
    mutate_fail "git diff of the index failed"
  fi
  names=$(printf '%s\n%s\n%s\n' "$(cat "$namesf")" "$extra" "$staged" | sed '/^$/d' | sort -u)
  export KEEL_MUTATE_BASE=$base
  if [ -z "$names" ]; then
    printf '%s\n' "RESULT mutate: skipped (no harness files changed)"
    return 0
  fi
  decision=$(printf '%s\n' "$names" | python3 "$HERE/mutant_files.py" --decide) \
    || mutate_fail "selection failed"
  case $decision in
    "RESULT mutate: skipped (no harness files changed)") ;;
    "RESULT mutate: run") ;;
    "RESULT mutate: run "*) ;;
    *) mutate_fail "unexpected selection" ;;
  esac
  printf '%s\n' "$decision"
  return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  mutate_plan
fi
