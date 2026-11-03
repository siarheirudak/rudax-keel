#!/usr/bin/env bash
# run-tests.sh: build the image, run both suites, then print the keel-doctor verdict last. Any OS with bash 3.2+ and Docker.
# Creates a THROWAWAY repo under $KEEL_ROOT (wiped!). No network, no tokens, no GitHub.
# env: DOCKER (default docker; Linux without docker group: DOCKER="sudo docker"), KEEL_ROOT (default ~/keel-proto),
#      KEEL_MUTATE_BASE (commit to diff; otherwise GITHUB_BASE_REF or origin/main)
#      KEEL_MUTATE_FORCE=1 runs the full CI mutant set and does not consult the diff
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)
# shellcheck source=setup/lib/portable.sh
. "$SETUP/lib/portable.sh"
DOCKER=${DOCKER:-docker}; export DOCKER
echo "== script modes"
bash "$SETUP/check.sh" || exit 1
echo "== mutant select"
python3 "$HERE/test-mutant-select.py" || exit 1
python3 "$HERE/mutate-issue.py" --self-test || exit 1
echo "== mutate plan"
"$HERE/test-mutate-plan.sh" || exit 1
echo "== attack results"
"$HERE/test-attack-results.sh" || exit 1
echo "== nested ro probe"
"$HERE/test-vis-ro.sh" || exit 1
echo "== memory verdict"
"$HERE/test-h3-verdict.sh" || exit 1
mkdir -p "$HERE/logs"
TS=$(date +%Y%m%d-%H%M%S)
$DOCKER info >/dev/null 2>&1 || { echo "ERROR: $(docker_hint)" >&2; exit 5; }
echo "== gitleaks"
bash "$SETUP/gitleaks-install.sh" || { echo "ERROR: gitleaks install failed" >&2; exit 1; }
echo "== build image keel-git (native arch: $($DOCKER info --format '{{.Architecture}}'))"
$DOCKER build -q -t keel-git -f "$SETUP/docker/keel-git.Dockerfile" "$SETUP/docker" >/dev/null || { echo "ERROR: image build failed" >&2; exit 1; }
echo "== build image keel-proxy"
$DOCKER build -q -t keel-proxy -f "$SETUP/docker/keel-proxy.Dockerfile" "$SETUP/docker" >/dev/null || { echo "ERROR: proxy image build failed" >&2; exit 1; }
rc=0
echo "== visibility self-test"
python3 "$SETUP/lib/visibility.py" self-test || rc=1
echo "== egress self-test"
python3 "$SETUP/lib/egress.py" self-test || rc=1
if [ "${KEEL_SKIP_SUITES:-}" != 1 ]; then
echo "== happy path  -> logs/happy-$TS.log"
"$HERE/test-happy.sh" > "$HERE/logs/happy-$TS.log" 2>&1 || rc=1
grep -aE 'GATE PASS|RESULT|mode=' "$HERE/logs/happy-$TS.log"
echo "== attacks     -> logs/attacks-$TS.log"
"$HERE/test-attacks.sh" > "$HERE/logs/attacks-$TS.log" 2>&1 || rc=1
grep -a '^RESULT ' "$HERE/logs/attacks-$TS.log"
# shellcheck source=setup/tests/harness/attack-results.sh
. "$HERE/attack-results.sh"
open_attacks=$(attack_results_open "$HERE/logs/attacks-$TS.log")
if [ -n "$open_attacks" ]; then
  echo "ERROR: an attack printed NOT BLOCKED, WRONG REASON, or ERROR" >&2
  printf '%s\n' "$open_attacks" >&2
  rc=1
fi
echo "== keel-doctor (verdict last; on a fresh throwaway repo, the suites wiped theirs)"
[ -n "${KEEL_REPO:-}" ] || "$SETUP/keel.sh" init-repo >/dev/null
doc_log=$(mktemp)
"$SETUP/keel-doctor.sh" >"$doc_log" 2>&1 || true
cat "$doc_log"
bash "$HERE/doctor-score.sh" "$doc_log" || rc=1
rm -f "$doc_log"
fi
echo "== doctor result ids"
"$HERE/test-doctor-ids.sh" || rc=1
echo "== mutate"
# shellcheck source=setup/tests/harness/mutate-plan.sh
. "$HERE/mutate-plan.sh"
decision_file=$(mktemp)
mutate_ok=1
if [ "${KEEL_MUTATE_FORCE:-}" = 1 ]; then
  printf '%s\n' "RESULT mutate: run" >"$decision_file"
  mutate_ok=0
elif mutate_plan >"$decision_file"; then
  mutate_ok=0
fi
if [ "$mutate_ok" -eq 0 ]; then
  decision=$(cat "$decision_file")
  rm -f "$decision_file"
  printf '%s\n' "$decision"
  ids=
  case $decision in
    "RESULT mutate: run")
      ids=$(python3 "$HERE/mutant_files.py" --ci) || {
        echo "ERROR: mutate: ci list failed" >&2
        rc=1
        ids=
      }
      ;;
    "RESULT mutate: skipped (no harness files changed)")
      ;;
    "RESULT mutate: run "*)
      ids=${decision#"RESULT mutate: run "}
      ;;
    *)
      echo "ERROR: mutate: unexpected decision" >&2
      rc=1
      ;;
  esac
  if [ -n "$ids" ]; then
    # shellcheck disable=SC2086
    if ! python3 "$HERE/mutant_files.py" --check-ids $ids; then
      echo "ERROR: mutate: id list rejected" >&2
      rc=1
    else
      echo "mutate: running selected mutants"
      mutate_start=$(date +%s)
      # shellcheck disable=SC2086
      python3 "$HERE/mutate.py" $ids || rc=1
      mutate_end=$(date +%s)
      echo "mutate: elapsed $((mutate_end - mutate_start))s"
    fi
  fi
else
  rm -f "$decision_file"
  rc=1
fi
exit $rc
