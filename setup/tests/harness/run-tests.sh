#!/usr/bin/env bash
# run-tests.sh: build the image, run both suites, then print the keel-doctor verdict last. Any OS with bash 3.2+ and Docker.
# Creates a THROWAWAY repo under $KEEL_ROOT (wiped!). No network, no tokens, no GitHub.
# env: DOCKER (default docker; Linux without docker group: DOCKER="sudo docker"), KEEL_ROOT (default ~/keel-proto),
#      KEEL_MUTATE_BASE (commit to diff; otherwise GITHUB_BASE_REF or origin/main)
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)
# shellcheck source=setup/lib/portable.sh
. "$SETUP/lib/portable.sh"
DOCKER=${DOCKER:-docker}; export DOCKER
echo "== mutate plan"
"$HERE/test-mutate-plan.sh" || exit 1
echo "== nested ro probe"
"$HERE/test-vis-ro.sh" || exit 1
mkdir -p "$HERE/logs"
TS=$(date +%Y%m%d-%H%M%S)
$DOCKER info >/dev/null 2>&1 || { echo "ERROR: $(docker_hint)" >&2; exit 5; }
echo "== build image keel-git (native arch: $($DOCKER info --format '{{.Architecture}}'))"
$DOCKER build -q -t keel-git -f "$SETUP/docker/keel-git.Dockerfile" "$SETUP/docker" >/dev/null || { echo "ERROR: image build failed" >&2; exit 1; }
rc=0
echo "== visibility self-test"
python3 "$SETUP/lib/visibility.py" self-test || rc=1
if [ "${KEEL_SKIP_SUITES:-}" != 1 ]; then
echo "== happy path  -> logs/happy-$TS.log"
"$HERE/test-happy.sh" > "$HERE/logs/happy-$TS.log" 2>&1 || rc=1
grep -aE 'GATE PASS|RESULT|mode=' "$HERE/logs/happy-$TS.log"
echo "== attacks     -> logs/attacks-$TS.log"
"$HERE/test-attacks.sh" > "$HERE/logs/attacks-$TS.log" 2>&1 || rc=1
grep -a '^RESULT ' "$HERE/logs/attacks-$TS.log"
open_attacks=$(grep -aE '^RESULT .*(NOT BLOCKED|WRONG REASON)' "$HERE/logs/attacks-$TS.log" || true)
if [ -n "$open_attacks" ]; then
  echo "ERROR: an attack printed NOT BLOCKED or WRONG REASON" >&2
  printf '%s\n' "$open_attacks" >&2
  rc=1
fi
echo "== keel-doctor (verdict last; on a fresh throwaway repo, the suites wiped theirs)"
[ -n "${KEEL_REPO:-}" ] || "$SETUP/keel.sh" init-repo >/dev/null
"$SETUP/keel-doctor.sh" || rc=1
fi
echo "== doctor result ids"
"$HERE/test-doctor-ids.sh" || rc=1
echo "== mutate"
# shellcheck source=setup/tests/harness/mutate-plan.sh
. "$HERE/mutate-plan.sh"
decision_file=$(mktemp)
if mutate_plan >"$decision_file"; then
  decision=$(cat "$decision_file")
  rm -f "$decision_file"
  printf '%s\n' "$decision"
  case $decision in
    "RESULT mutate: run")
      echo "mutate: harness files changed; running the mutant set"
      python3 "$HERE/mutate.py" M17 M45 M46 M47 M48 M49 M50 M51 M52 || rc=1
      ;;
    "RESULT mutate: skipped (no harness files changed)")
      ;;
    *)
      echo "ERROR: mutate: unexpected decision" >&2
      rc=1
      ;;
  esac
else
  rm -f "$decision_file"
  rc=1
fi
exit $rc
