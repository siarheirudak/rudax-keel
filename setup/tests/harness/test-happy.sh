#!/usr/bin/env bash
# Happy path: steps 0-5,7. Run: DOCKER="sudo docker" ./test-happy.sh
set -u; HERE=$(cd "$(dirname "$0")" && pwd -P); SETUP=$(cd "$HERE/../.." && pwd -P); K="$SETUP/keel.sh"; # shellcheck source=setup/lib/portable.sh
. "$SETUP/lib/portable.sh"; export KEEL_ROOT=${KEEL_ROOT:-$HOME/keel-proto}
rm -rf "$KEEL_ROOT"; echo "### step0"; $K init-repo
echo "### step1 setup"; $K setup; echo "pointer mode: $($K mode)"
echo "### step2 role A (coder) commits"; $K role coder rw 'echo feature > feature.txt && git add feature.txt && git commit -qm "A: feature" && git log --oneline -2'
echo "### step2 role B fresh container sees A's file, commits"; $K role tester rw 'cat feature.txt && echo more >> feature.txt && git commit -qam "B: more" && git log --oneline -3 && git status --short | wc -l'
echo "### owner check (expect none)"; find "$KEEL_ROOT" ! -user "$(id -u)" | head
echo "### host git in work dir (pointer to /shadow, absent on host)"; git -C "$KEEL_ROOT/work/task-1" status 2>&1 | head -2
echo "### step3 export"; $K export && ls -l "$KEEL_ROOT/bundles"
C0=$(git -C "$KEEL_ROOT/repo" count-objects -v | fingerprint)
echo "### step4 gate (temp bare repo w/ alternates)"; $K gate; echo "gate rc=$?"
[ "$C0" = "$(git -C "$KEEL_ROOT/repo" count-objects -v | fingerprint)" ] && echo "real repo object store UNCHANGED by gate" || echo "real repo object store CHANGED"
echo "### step5"; $K push-stub
echo "### step1-alt GIT_DIR/GIT_WORK_TREE (no pointer file)"
$K role-env 'git checkout -q -f task-1 2>&1; ls; echo env > envfile && git add envfile && git commit -qm "env-variant commit" && git log --oneline -1; ls -a'
echo "### step7 cleanup"; $K cleanup; ls "$KEEL_ROOT"/work "$KEEL_ROOT"/shadow "$KEEL_ROOT"/gate; git -C "$KEEL_ROOT/repo" for-each-ref
