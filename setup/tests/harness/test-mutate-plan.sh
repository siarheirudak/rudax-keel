#!/usr/bin/env bash
# Missing base must fail. The old "no-changed-files pass" line must not come back.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
PLAN=$HERE/mutate-plan.sh
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT

git_repo() {
  local dir=$1
  git -C "$dir" init -q
  git -C "$dir" config user.name t
  git -C "$dir" config user.email t@x
  git -C "$dir" config commit.gpgsign false
}

assert_missing_fails() {
  local script=$1 repo=$2 out errf ec
  errf=$root/err.txt
  : >"$errf"
  set +e
  out=$(env -u KEEL_MUTATE_BASE -u GITHUB_BASE_REF KEEL_MUTATE_REPO="$repo" bash "$script" 2>"$errf")
  ec=$?
  set +e
  if [ "$ec" -eq 0 ]; then
    return 1
  fi
  if printf '%s\n' "$out" | grep -q 'no-changed-files pass'; then
    return 1
  fi
  if printf '%s\n' "$out" | grep -q 'RESULT mutate:.*pass'; then
    return 1
  fi
  if ! grep -q 'ERROR: mutate:' "$errf"; then
    return 1
  fi
  return 0
}

empty=$root/empty
mkdir -p "$empty"
git_repo "$empty"
printf 'x\n' >"$empty/README"
git -C "$empty" add README
git -C "$empty" commit -qm init
if ! assert_missing_fails "$PLAN" "$empty"; then
  echo "missing base did not fail closed" >&2
  exit 1
fi

same=$root/same
mkdir -p "$same"
git_repo "$same"
printf 'x\n' >"$same/README"
git -C "$same" add README
git -C "$same" commit -qm init
git -C "$same" branch -M main
git -C "$same" update-ref refs/remotes/origin/main HEAD
out=$(env -u GITHUB_BASE_REF KEEL_MUTATE_BASE=origin/main KEEL_MUTATE_REPO="$same" bash "$PLAN")
if [ "$out" != "RESULT mutate: skipped (no harness files changed)" ]; then
  echo "expected skip, got: $out" >&2
  exit 1
fi

changed=$root/changed
mkdir -p "$changed"
git_repo "$changed"
mkdir -p "$changed/setup"
printf 'a\n' >"$changed/setup/keel.sh"
git -C "$changed" add setup/keel.sh
git -C "$changed" commit -qm base
git -C "$changed" branch -M main
git -C "$changed" update-ref refs/remotes/origin/main HEAD
git -C "$changed" checkout -q -b feature
printf 'b\n' >"$changed/setup/keel.sh"
git -C "$changed" add setup/keel.sh
git -C "$changed" commit -qm change
out=$(env -u GITHUB_BASE_REF KEEL_MUTATE_BASE=origin/main KEEL_MUTATE_REPO="$changed" bash "$PLAN")
case $out in
  "RESULT mutate: run "*) ;;
  *)
    echo "expected selective run, got: $out" >&2
    exit 1
    ;;
esac
if ! printf '%s\n' "$out" | grep -Eq '(^| )M03( |$)'; then
  echo "keel.sh selection dropped M03: $out" >&2
  exit 1
fi
if printf '%s\n' "$out" | grep -Eq '(^| )M51( |$)'; then
  echo "keel.sh selection included M51: $out" >&2
  exit 1
fi

expect_full() {
  local file=$1 repo
  repo=$root/case-$(printf '%s' "$file" | tr '/' '-')
  mkdir -p "$repo/$(dirname "$file")"
  git_repo "$repo"
  printf 'a\n' >"$repo/$file"
  git -C "$repo" add -- "$file"
  git -C "$repo" commit -qm base
  git -C "$repo" branch -M main
  git -C "$repo" update-ref refs/remotes/origin/main HEAD
  git -C "$repo" checkout -q -b feature
  printf 'b\n' >"$repo/$file"
  git -C "$repo" add -- "$file"
  git -C "$repo" commit -qm change
  out=$(env -u GITHUB_BASE_REF KEEL_MUTATE_BASE=origin/main KEEL_MUTATE_REPO="$repo" bash "$PLAN")
  if [ "$out" != "RESULT mutate: run" ]; then
    echo "expected full run for $file, got: $out" >&2
    exit 1
  fi
}

expect_selective() {
  local file=$1 repo out id
  shift
  repo=$root/sel-$(printf '%s' "$file" | tr '/' '-')
  mkdir -p "$repo/$(dirname "$file")"
  git_repo "$repo"
  printf 'a\n' >"$repo/$file"
  git -C "$repo" add -- "$file"
  git -C "$repo" commit -qm base
  git -C "$repo" branch -M main
  git -C "$repo" update-ref refs/remotes/origin/main HEAD
  git -C "$repo" checkout -q -b feature
  printf 'b\n' >"$repo/$file"
  git -C "$repo" add -- "$file"
  git -C "$repo" commit -qm change
  out=$(env -u GITHUB_BASE_REF KEEL_MUTATE_BASE=origin/main KEEL_MUTATE_REPO="$repo" bash "$PLAN")
  case $out in
    "RESULT mutate: run "*) ;;
    *)
      echo "expected selective run for $file, got: $out" >&2
      exit 1
      ;;
  esac
  if [ "$out" = "RESULT mutate: run" ]; then
    echo "expected selective run for $file, got the full set" >&2
    exit 1
  fi
  for id in "$@"; do
    case $id in
      '!'*)
        id=${id#!}
        if printf '%s\n' "$out" | grep -Eq "(^| )${id}( |$)"; then
          echo "$file selected ${id}: $out" >&2
          exit 1
        fi
        ;;
      *)
        if ! printf '%s\n' "$out" | grep -Eq "(^| )${id}( |$)"; then
          echo "$file dropped ${id}: $out" >&2
          exit 1
        fi
        ;;
    esac
  done
}

expect_skip() {
  local file=$1 repo out
  repo=$root/skip-$(printf '%s' "$file" | tr '/' '-')
  mkdir -p "$repo/$(dirname "$file")"
  git_repo "$repo"
  printf 'a\n' >"$repo/$file"
  git -C "$repo" add -- "$file"
  git -C "$repo" commit -qm base
  git -C "$repo" branch -M main
  git -C "$repo" update-ref refs/remotes/origin/main HEAD
  git -C "$repo" checkout -q -b feature
  printf 'b\n' >"$repo/$file"
  git -C "$repo" add -- "$file"
  git -C "$repo" commit -qm change
  out=$(env -u GITHUB_BASE_REF KEEL_MUTATE_BASE=origin/main KEEL_MUTATE_REPO="$repo" bash "$PLAN")
  if [ "$out" != "RESULT mutate: skipped (no harness files changed)" ]; then
    echo "expected skip for $file, got: $out" >&2
    exit 1
  fi
}

expect_skip setup/tests/harness/mutate.py
expect_skip .github/workflows/checks.yml
expect_skip setup/tests/harness/mutate-plan.sh
expect_full setup/docker/keel-git.Dockerfile
expect_full setup/not-a-mapped-target
expect_full setup/allow/README.md
expect_full setup/egress/README.md
expect_full setup/allow/foo.paths.bak
expect_full setup/allow/nested/x.paths
expect_full setup/tests/harness/runtime-stub.sh
expect_selective setup/allow/developer.paths M45 '!M03' '!M53'
expect_selective setup/deny/base M51 '!M03' '!M53'
expect_selective setup/egress/developer.allow M53 '!M03' '!M45'
expect_selective setup/check.sh M79 '!M03'
expect_selective setup/keel-doctor.sh M89 M110 M129 '!M03'
expect_selective setup/docker/ancestor-guard.sh M108 '!M03'
expect_selective setup/tests/harness/test-attacks.sh M03 M79 '!M80'
expect_selective setup/tests/harness/test-runtime.sh M80 '!M03'
expect_selective setup/tests/harness/test-mutant-result.sh M92 M93 '!M03'
expect_selective setup/tests/harness/test-step4.sh M94 '!M03' '!M99'
expect_selective setup/tests/harness/test-step5.sh M119 '!M03' '!M99'
expect_selective setup/tests/harness/test-egress.sh M53 '!M45'
expect_selective setup/tests/harness/visibility-suite.sh M45 '!M53'
# A scripts-only edit of the gate is not a skip. Other scripts files still are.
expect_selective setup/tests/harness/mutant-result.py M92 M93 '!M03'
expect_selective .github/workflows/mutate-full.yml M171 M175 '!M03'
expect_selective scripts/check-gate.sh M92 M93 '!M03'
expect_selective scripts/gate-jobs.txt M92 M93 '!M03'
expect_selective scripts/tests/test_gate_jobs.py M92 M93 '!M03'

other=$root/scripts-other
mkdir -p "$other/scripts"
git_repo "$other"
printf 'a\n' >"$other/scripts/check.sh"
git -C "$other" add scripts/check.sh
git -C "$other" commit -qm base
git -C "$other" branch -M main
git -C "$other" update-ref refs/remotes/origin/main HEAD
git -C "$other" checkout -q -b feature
printf 'b\n' >"$other/scripts/check.sh"
git -C "$other" add scripts/check.sh
git -C "$other" commit -qm change
out=$(env -u GITHUB_BASE_REF KEEL_MUTATE_BASE=origin/main KEEL_MUTATE_REPO="$other" bash "$PLAN")
if [ "$out" != "RESULT mutate: skipped (no harness files changed)" ]; then
  echo "scripts/check.sh was not a skip, got: $out" >&2
  exit 1
fi

bogus=$root/bogus
mkdir -p "$bogus"
git_repo "$bogus"
printf 'x\n' >"$bogus/README"
git -C "$bogus" add README
git -C "$bogus" commit -qm init
set +e
out=$(env -u GITHUB_BASE_REF KEEL_MUTATE_BASE=refs/does-not-exist KEEL_MUTATE_REPO="$bogus" bash "$PLAN" 2>"$root/bogus.err")
ec=$?
set +e
if [ "$ec" -eq 0 ] || ! grep -q 'does not resolve' "$root/bogus.err" || printf '%s\n' "$out" | grep -q pass; then
  echo "unresolved base did not fail" >&2
  cat "$root/bogus.err" >&2
  exit 1
fi

split=$root/split
mkdir -p "$split"
git_repo "$split"
printf 'a\n' >"$split/README"
git -C "$split" add README
git -C "$split" commit -qm main
git -C "$split" branch -M main
git -C "$split" update-ref refs/remotes/origin/main HEAD
git -C "$split" checkout -q --orphan other
git -C "$split" rm -q -rf . >/dev/null 2>&1 || true
printf 'b\n' >"$split/README"
git -C "$split" add README
git -C "$split" commit -qm other
set +e
out=$(env -u GITHUB_BASE_REF KEEL_MUTATE_BASE=origin/main KEEL_MUTATE_REPO="$split" bash "$PLAN" 2>"$root/split.err")
ec=$?
set +e
if [ "$ec" -eq 0 ] || ! grep -q 'git diff against' "$root/split.err" || printf '%s\n' "$out" | grep -q pass; then
  echo "diff without a merge base did not fail" >&2
  cat "$root/split.err" >&2
  exit 1
fi

mut=$root/mut-plan.sh
python3 - "$PLAN" "$mut" << 'PY'
import sys
src, dst = sys.argv[1:]
old = 'mutate_fail "base ref missing" # missing-base-fails'
new = "printf '%s\\n' 'RESULT mutate: no-changed-files pass'; return 0"
text = open(src, encoding="utf-8").read()
if text.count(old) != 1:
    raise SystemExit("mutant needle count %s" % text.count(old))
open(dst, "w", encoding="utf-8").write(text.replace(old, new, 1))
PY
chmod +x "$mut"
if assert_missing_fails "$mut" "$empty"; then
  echo "old silent-pass mutant was not caught" >&2
  exit 1
fi
echo "mutate plan: missing base fails; silent pass is caught"
