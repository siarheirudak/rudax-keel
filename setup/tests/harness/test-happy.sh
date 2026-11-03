#!/usr/bin/env bash
# Happy path: steps 0-5,7. Run: DOCKER="sudo docker" ./test-happy.sh
set -u; HERE=$(cd "$(dirname "$0")" && pwd -P); SETUP=$(cd "$HERE/../.." && pwd -P); K="$SETUP/keel.sh"; # shellcheck source=setup/lib/portable.sh
. "$SETUP/lib/portable.sh"; export KEEL_ROOT=${KEEL_ROOT:-$HOME/keel-proto}
echo "### script modes"
if ! mode_out=$(bash "$SETUP/check.sh" 2>&1); then
  printf '%s\n' "$mode_out" >&2
  echo "RESULT MODE-H1: NOT BLOCKED"
  exit 1
fi
mode_list=$(bash "$SETUP/check.sh" --list)
if ! printf '%s\n' "$mode_list" | grep -qx 'setup/tests/harness/test-attack-results.sh'; then
  echo "RESULT MODE-H1: NOT BLOCKED"
  echo "direct script missing from the mode list" >&2
  exit 1
fi
if printf '%s\n' "$mode_list" | grep -qx 'setup/tests/harness/h3-verdict.sh' || printf '%s\n' "$mode_list" | grep -qx 'setup/gitleaks-install.sh'; then
  echo "RESULT MODE-H1: NOT BLOCKED"
  echo "sourced or bash script was treated as directly executed" >&2
  exit 1
fi
echo "RESULT MODE-H1: BLOCKED (directly executed scripts are 100755)"
bash "$HERE/test-runtime.sh" --happy || exit 1
rm -rf "$KEEL_ROOT"; echo "### step0"; $K init-repo
echo "### step1 setup"; $K setup; echo "pointer mode: $($K mode)"
echo "### step2 role A (coder) commits"; $K proto coder rw 'echo feature > feature.txt && git add feature.txt && git commit -qm "A: feature" && git log --oneline -2'
echo "### step2 role B fresh container sees A's file, commits"; $K proto tester rw 'cat feature.txt && echo more >> feature.txt && git commit -qam "B: more" && git log --oneline -3 && git status --short | wc -l'
echo "### owner check (expect none)"; find "$KEEL_ROOT" ! -user "$(id -u)" | head
echo "### host git in work dir (pointer to /shadow, absent on host)"; git -C "$KEEL_ROOT/work/task-1" status 2>&1 | head -2
echo "### step3 export"; $K export && ls -l "$KEEL_ROOT/bundles"
C0=$(git -C "$KEEL_ROOT/repo" count-objects -v | fingerprint)
echo "### step4 gate (temp bare repo w/ alternates)"
out=$($K gate 2>&1); rc=$?; printf '%s\n' "$out"; echo "gate rc=$rc"
if [ "$rc" -eq 0 ] && printf '%s\n' "$out" | grep -q 'GATE PASS'; then echo "RESULT SEC-H1: BLOCKED (clean bundle)"; else echo "RESULT SEC-H1: NOT BLOCKED"; exit 1; fi
[ "$C0" = "$(git -C "$KEEL_ROOT/repo" count-objects -v | fingerprint)" ] && echo "real repo object store UNCHANGED by gate" || echo "real repo object store CHANGED"
echo "### step5"; $K push-stub
echo "### step1-alt GIT_DIR/GIT_WORK_TREE (no pointer file)"
$K proto-env 'git checkout -q -f task-1 2>&1; ls; echo env > envfile && git add envfile && git commit -qm "env-variant commit" && git log --oneline -1; ls -a'
echo "### step7 cleanup"; $K cleanup; ls "$KEEL_ROOT"/work "$KEEL_ROOT"/shadow "$KEEL_ROOT"/gate; git -C "$KEEL_ROOT/repo" for-each-ref
KEEL_ROOT="${KEEL_ROOT}-eg" bash "$HERE/test-egress.sh" || exit 1
KEEL_ROOT="${KEEL_ROOT}-vis" bash "$HERE/visibility-suite.sh" || exit 1
