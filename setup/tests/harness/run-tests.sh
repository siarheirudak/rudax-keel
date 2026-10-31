#!/usr/bin/env bash
# run-tests.sh: build the image, run both suites, then print the keel-doctor verdict last. Any OS with bash 3.2+ and Docker.
# Creates a THROWAWAY repo under $KEEL_ROOT (wiped!). No network, no tokens, no GitHub.
# env: DOCKER (default docker; Linux without docker group: DOCKER="sudo docker"), KEEL_ROOT (default ~/keel-proto)
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)
# shellcheck source=setup/lib/portable.sh
. "$SETUP/lib/portable.sh"
DOCKER=${DOCKER:-docker}; export DOCKER
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
echo "== keel-doctor (verdict last; on a fresh throwaway repo, the suites wiped theirs)"
[ -n "${KEEL_REPO:-}" ] || "$SETUP/keel.sh" init-repo >/dev/null
"$SETUP/keel-doctor.sh" || rc=1
fi
echo "== mutate"
repo=$(cd "$SETUP/.." && pwd)
base=${KEEL_MUTATE_BASE:-}
if [ -z "$base" ]; then
  if [ -n "${GITHUB_BASE_REF:-}" ]; then
    git -C "$repo" fetch --depth=1 origin "$GITHUB_BASE_REF" >/dev/null 2>&1 || true
    base="origin/$GITHUB_BASE_REF"
  elif git -C "$repo" rev-parse --verify origin/main >/dev/null 2>&1; then
    base=origin/main
  fi
fi
names=""
if [ -n "$base" ] && git -C "$repo" rev-parse --verify "$base" >/dev/null 2>&1; then
  names=$(git -C "$repo" diff --name-only "$base"...HEAD -- setup/keel.sh setup/lib setup/allow setup/deny setup/keel-doctor.sh setup/tests/harness || true)
  dirty=$(git -C "$repo" status --porcelain -- setup/keel.sh setup/lib setup/allow setup/deny setup/keel-doctor.sh setup/tests/harness || true)
  names="${names}"$'\n'"${dirty}"
fi
if [ -z "$(printf '%s\n' "$names" | sed '/^$/d')" ]; then
  echo "RESULT mutate: no-changed-files pass"
else
  echo "mutate: harness files changed; running the visibility set"
  python3 "$HERE/mutate.py" M45 M46 M47 M48 M49 M50 M51 || rc=1
fi
exit $rc
