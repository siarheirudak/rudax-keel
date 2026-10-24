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
echo "== happy path  -> logs/happy-$TS.log"
"$HERE/test-happy.sh" > "$HERE/logs/happy-$TS.log" 2>&1 || rc=1
grep -aE 'GATE PASS|RESULT|mode=' "$HERE/logs/happy-$TS.log"
echo "== attacks     -> logs/attacks-$TS.log"
"$HERE/test-attacks.sh" > "$HERE/logs/attacks-$TS.log" 2>&1 || rc=1
grep -a '^RESULT ' "$HERE/logs/attacks-$TS.log"
echo "== keel-doctor (verdict last; on a fresh throwaway repo, the suites wiped theirs)"
[ -n "${KEEL_REPO:-}" ] || "$SETUP/keel.sh" init-repo >/dev/null
"$SETUP/keel-doctor.sh" || rc=1
exit $rc
