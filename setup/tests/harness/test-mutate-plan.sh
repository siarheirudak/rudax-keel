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
if [ "$out" != "RESULT mutate: run" ]; then
  echo "expected run, got: $out" >&2
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
