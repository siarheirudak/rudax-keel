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
# shellcheck source=setup/tests/harness/attack-results.sh
. "$HERE/attack-results.sh"
DOCKER=${DOCKER:-docker}; export DOCKER

# Whole-line allowlist. A suffix, an unknown pair, or a control character
# never matches, so the log text is not copied to the job output.
h2_diag_allowed() {
  case $1 in
    'h2-diag: stage=acquire reason=no-cid'|\
    'h2-diag: stage=acquire reason=cid-shape'|\
    'h2-diag: stage=acquire reason=id-mismatch'|\
    'h2-diag: stage=acquire reason=not-running'|\
    'h2-diag: stage=acquire reason=timeout'|\
    'h2-diag: stage=acquire reason=late'|\
    'h2-diag: stage=acquire reason=deadline'|\
    'h2-diag: stage=cap reason=cfg-unreadable'|\
    'h2-diag: stage=cap reason=eff-unreadable'|\
    'h2-diag: stage=cap reason=disagree'|\
    'h2-diag: stage=probe reason=no-result'|\
    'h2-diag: stage=probe reason=bad-record'|\
    'h2-diag: stage=attribute reason=bad-record'|\
    'h2-diag: stage=attribute reason=events-missing'|\
    'h2-diag: stage=attribute reason=no-delta'|\
    'h2-diag: stage=attribute reason=not-enforced'|\
    'h2-diag: stage=cleanup reason=unverified'|\
    'h2-diag: stage=trap reason=term'|\
    'h2-diag: stage=trap reason=int'|\
    'h2-diag: stage=verdict reason=contained'|\
    'h2-diag: stage=verdict reason=absent'|\
    'h2-diag: stage=verdict reason=wrong')
      return 0
      ;;
  esac
  return 1
}

# Print at most 32 validated records from a captured attacks log.
# Longer or non-printable lines are dropped. Extra valid records keep the
# newest 32 and a count, not the dropped text.
publish_h2_diag() {
  local log=$1 line tmp n omit
  tmp=$(mktemp)
  while IFS= read -r line || [ -n "$line" ]; do
    [ "${#line}" -le 64 ] || continue
    case $line in
      *[![:print:]]*) continue ;;
    esac
    h2_diag_allowed "$line" || continue
    printf '%s\n' "$line" >> "$tmp"
  done < "$log"
  n=$(wc -l < "$tmp" | tr -d ' ')
  if [ "$n" -gt 32 ]; then
    omit=$((n - 32))
    tail -n 32 "$tmp"
    printf 'h2-publish: omitted=%s\n' "$omit"
  else
    cat "$tmp"
  fi
  rm -f "$tmp"
}

# Same block the attacks suite uses. suite_rc is that suite's status.
# Open RESULT lines still fail the run. A diagnostic cannot clear that.
report_attacks() {
  local log=$1 suite_rc=$2 open_attacks
  grep -a '^RESULT ' "$log" || true
  publish_h2_diag "$log"
  open_attacks=$(attack_results_open "$log")
  if [ -n "$open_attacks" ]; then
    echo "ERROR: an attack printed NOT BLOCKED, WRONG REASON, or ERROR" >&2
    printf '%s\n' "$open_attacks" >&2
    return 1
  fi
  [ "$suite_rc" -eq 0 ]
}

# Doctor 07b needs a key file outside KEEL_CI. That file is created only
# under a fresh temp root. The caller's KEEL_ROOT and key path are not
# created or overwritten. The EXIT trap removes the temp root.
prepare_doctor_root() {
  doc_real_root=${KEEL_ROOT:-$HOME/keel-proto}
  doc_real_key=${KEEL_JUDGE_KEY_FILE:-$doc_real_root/.keel/keys/openrouter.key}
  doc_root=$(mktemp -d "${TMPDIR:-/tmp}/keel-doctor.XXXXXX")
  trap 'rm -rf "$doc_root"' EXIT
  export KEEL_ROOT="$doc_root"
  unset KEEL_JUDGE_KEY_FILE
  if [ "${KEEL_CI:-}" != "1" ]; then
    mkdir -p "$doc_root/.keel/keys"
    (umask 077; printf '%s\n' 'local-doctor-placeholder' > "$doc_root/.keel/keys/openrouter.key")
    chmod 600 "$doc_root/.keel/keys/openrouter.key"
    export KEEL_JUDGE_KEY_FILE="$doc_root/.keel/keys/openrouter.key"
  fi
  if [ "${KEEL_JUDGE_KEY_FILE:-}" = "$doc_real_key" ]; then
    echo "ERROR: doctor root would use the real key path" >&2
    exit 1
  fi
  case $KEEL_ROOT in
    "$doc_real_root"|"$doc_real_root"/*)
      echo "ERROR: doctor root is inside the real KEEL_ROOT" >&2
      exit 1
      ;;
  esac
}

if [ "${1:-}" = "--doctor-root" ]; then
  prepare_doctor_root
  printf '%s\n' "$KEEL_ROOT"
  printf '%s\n' "${KEEL_JUDGE_KEY_FILE:-}"
  exit 0
fi

if [ "${1:-}" = "--attacks-record" ]; then
  if [ "$#" -ne 3 ]; then
    echo "usage: run-tests.sh --attacks-record LOG SUITE_RC" >&2
    exit 2
  fi
  report_attacks "$2" "$3"
  exit $?
fi

if [ "${1:-}" = "--h2-publish-self-test" ]; then
  set +e
  pub_fail() { echo "h2-publish: FAIL $1" >&2; exit 1; }
  pub_tmp=$(mktemp -d)
  trap 'rm -rf "$pub_tmp"' EXIT
  cat > "$pub_tmp/fail.log" << 'EOF'
RESULT A1: BLOCKED (read-only mount)
h2-diag: stage=acquire reason=timeout
h2-diag: stage=acquire reason=timeout leaked-secret
h2-diag: stage=trap reason=contained
h2-diag: stage=unknown reason=unknown
RESULT H2-INFRA: ERROR
GH_TOKEN=should-not-appear
EOF
  {
    printf 'h2-diag: stage=acquire reason=timeout\r\n'
    printf 'h2-diag: stage=acquire reason=no-cid\t\n'
    printf 'h2-diag: stage=cap reason=disagree\001\n'
    python3 -c 'print("h2-diag: stage=acquire reason=deadline " + ("x" * 80))'
  } >> "$pub_tmp/fail.log"
  bash "$HERE/run-tests.sh" --attacks-record "$pub_tmp/fail.log" 1 > "$pub_tmp/fail.out" 2> "$pub_tmp/fail.err"
  pub_ec=$?
  [ "$pub_ec" -ne 0 ] || pub_fail "failure path exited 0"
  grep -q 'ERROR: an attack printed NOT BLOCKED, WRONG REASON, or ERROR' "$pub_tmp/fail.err" || pub_fail "failure path dropped the error"
  grep -qx 'RESULT H2-INFRA: ERROR' "$pub_tmp/fail.err" || pub_fail "failure path dropped the open result"
  pub_want=$(printf '%s\n' 'RESULT A1: BLOCKED (read-only mount)' 'RESULT H2-INFRA: ERROR' 'h2-diag: stage=acquire reason=timeout')
  [ "$(cat "$pub_tmp/fail.out")" = "$pub_want" ] || pub_fail "failure stdout [$(cat "$pub_tmp/fail.out")]"
  grep -E -q 'leaked-secret|GH_TOKEN|unknown|disagree' "$pub_tmp/fail.out" && pub_fail "reflected untrusted diagnostic"
  cat > "$pub_tmp/bad.log" << 'EOF'
h2-diag: stage=attribute reason=bad-record
h2-diag: stage=attribute reason=bad-record extra
RESULT H2-INFRA: ERROR
EOF
  bash "$HERE/run-tests.sh" --attacks-record "$pub_tmp/bad.log" 1 > "$pub_tmp/bad.out" 2> "$pub_tmp/bad.err"
  pub_ec=$?
  [ "$pub_ec" -ne 0 ] || pub_fail "bad-record path exited 0"
  grep -q 'ERROR: an attack printed NOT BLOCKED, WRONG REASON, or ERROR' "$pub_tmp/bad.err" || pub_fail "bad-record dropped the error"
  grep -qx 'RESULT H2-INFRA: ERROR' "$pub_tmp/bad.err" || pub_fail "bad-record dropped H2-INFRA"
  pub_want=$(printf '%s\n' 'RESULT H2-INFRA: ERROR' 'h2-diag: stage=attribute reason=bad-record')
  [ "$(cat "$pub_tmp/bad.out")" = "$pub_want" ] || pub_fail "bad-record stdout [$(cat "$pub_tmp/bad.out")]"
  grep -q 'extra' "$pub_tmp/bad.out" && pub_fail "bad-record reflected a suffix"
  printf '%s\n' 'RESULT A1: BLOCKED (read-only mount)' 'h2-diag: stage=verdict reason=contained' > "$pub_tmp/ok.log"
  bash "$HERE/run-tests.sh" --attacks-record "$pub_tmp/ok.log" 0 > "$pub_tmp/ok.out" 2> "$pub_tmp/ok.err"
  pub_ec=$?
  [ "$pub_ec" -eq 0 ] || pub_fail "clean record exited $pub_ec"
  [ ! -s "$pub_tmp/ok.err" ] || pub_fail "clean record wrote an error"
  pub_want=$(printf '%s\n' 'RESULT A1: BLOCKED (read-only mount)' 'h2-diag: stage=verdict reason=contained')
  [ "$(cat "$pub_tmp/ok.out")" = "$pub_want" ] || pub_fail "clean stdout"
  printf '%s\n' 'h2-diag: stage=acquire reason=no-cid' > "$pub_tmp/die.log"
  bash "$HERE/run-tests.sh" --attacks-record "$pub_tmp/die.log" 1 > "$pub_tmp/die.out" 2> "$pub_tmp/die.err"
  pub_ec=$?
  [ "$pub_ec" -ne 0 ] || pub_fail "suite failure became success"
  [ ! -s "$pub_tmp/die.err" ] || pub_fail "suite failure invented an open result"
  [ "$(cat "$pub_tmp/die.out")" = "h2-diag: stage=acquire reason=no-cid" ] || pub_fail "suite failure hid the diagnostic"
  : > "$pub_tmp/many.log"
  pub_i=0
  while [ "$pub_i" -lt 40 ]; do
    if [ "$pub_i" -lt 8 ]; then
      printf '%s\n' 'h2-diag: stage=acquire reason=deadline' >> "$pub_tmp/many.log"
    else
      printf '%s\n' 'h2-diag: stage=cleanup reason=unverified' >> "$pub_tmp/many.log"
    fi
    pub_i=$((pub_i + 1))
  done
  bash "$HERE/run-tests.sh" --attacks-record "$pub_tmp/many.log" 0 > "$pub_tmp/many.out" 2> "$pub_tmp/many.err"
  pub_ec=$?
  [ "$pub_ec" -eq 0 ] || pub_fail "bounded record exited $pub_ec"
  [ "$(grep -c '^h2-diag: stage=cleanup reason=unverified$' "$pub_tmp/many.out")" -eq 32 ] || pub_fail "kept count"
  grep -q '^h2-diag: stage=acquire reason=deadline$' "$pub_tmp/many.out" && pub_fail "kept an older record"
  grep -qx 'h2-publish: omitted=8' "$pub_tmp/many.out" || pub_fail "omitted count"
  python3 - "$HERE" "$pub_tmp/fail.log" "$pub_tmp/fail.out" "$pub_tmp/bad.log" "$pub_tmp/bad.out" << 'PY' || pub_fail "grader"
import sys
sys.path.insert(0, sys.argv[1])
import mutate
import mutate_shards as ms
for path in sys.argv[2:]:
    text = open(path, encoding="utf-8").read()
    red, _detail = mutate.judge(["H2"], text)
    tag = mutate.verdict_tag(["H2"], red)
    if tag == "yes" or (red and "H2" in red):
        raise SystemExit("diagnostic earned an H2 kill")
base = ms.classify_baseline("1", "test-attacks.sh", [("M26", ["H2"])], text, 1)
if not base or base.get("reason") != "status":
    raise SystemExit("baseline treated the failed record as green")
PY
  echo "h2-publish: ok"
  exit 0
fi

echo "== script modes"
bash "$SETUP/check.sh" || exit 1
echo "== mutant select"
python3 "$HERE/test-mutant-select.py" || exit 1
echo "== mutate shards"
bash "$HERE/test-mutate-shards.sh" || exit 1
python3 "$HERE/mutate-full-state.py" --self-test || exit 1
python3 "$HERE/test-mutate-parse.py" || exit 1
python3 "$HERE/mutate-issue.py" --self-test || exit 1
echo "== mutate plan"
"$HERE/test-mutate-plan.sh" || exit 1
echo "== mutant dispatch"
bash "$HERE/test-resolve-mutant-target.sh" || exit 1
echo "== mutant result binding"
bash "$HERE/test-mutant-result.sh" || exit 1
echo "== mutate schedule"
bash "$HERE/test-mutate-schedule.sh" || exit 1
echo "== attack results"
"$HERE/test-attack-results.sh" || exit 1
echo "== h2 publish"
bash "$HERE/run-tests.sh" --h2-publish-self-test || exit 1
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
echo "== build image keel-pi"
$DOCKER build -q -t keel-pi -f "$SETUP/docker/keel-pi.Dockerfile" "$SETUP/docker" >/dev/null || { echo "ERROR: pi image build failed" >&2; exit 1; }
echo "== pi 0.73.1"
PI_DIR=${KEEL_PI_DIR:-$HOME/.cache/keel/pi-0.73.1}
if [ ! -x "$PI_DIR/node_modules/.bin/pi" ]; then
  mkdir -p "$PI_DIR"
  npm install --prefix "$PI_DIR" --silent @mariozechner/pi-coding-agent@0.73.1 || { echo "ERROR: pi install failed" >&2; exit 1; }
fi
export NODE_PATH="$PI_DIR/node_modules${NODE_PATH:+:$NODE_PATH}"
export KEEL_PI_BIN="$PI_DIR/node_modules/.bin/pi"
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
attacks_rc=0
"$HERE/test-attacks.sh" > "$HERE/logs/attacks-$TS.log" 2>&1 || attacks_rc=$?
report_attacks "$HERE/logs/attacks-$TS.log" "$attacks_rc" || rc=1
echo "== step 4     -> logs/step4-$TS.log"
bash "$HERE/test-step4.sh" > "$HERE/logs/step4-$TS.log" 2>&1 || rc=1
grep -a '^RESULT ' "$HERE/logs/step4-$TS.log" || true
open_step4=$(attack_results_open "$HERE/logs/step4-$TS.log")
if [ -n "$open_step4" ]; then
  echo "ERROR: a step 4 check printed NOT BLOCKED, WRONG REASON, or ERROR" >&2
  printf '%s\n' "$open_step4" >&2
  rc=1
fi
echo "== step 5     -> logs/step5-$TS.log"
bash "$HERE/test-step5.sh" > "$HERE/logs/step5-$TS.log" 2>&1 || rc=1
grep -a '^RESULT ' "$HERE/logs/step5-$TS.log" || true
open_step5=$(attack_results_open "$HERE/logs/step5-$TS.log")
if [ -n "$open_step5" ]; then
  echo "ERROR: a step 5 check printed NOT BLOCKED, WRONG REASON, or ERROR" >&2
  printf '%s\n' "$open_step5" >&2
  rc=1
fi
echo "== keel-doctor (verdict last; on a fresh throwaway repo, the suites wiped theirs)"
# The key file, when one is required, is created only inside this temp root.
saved_repo=${KEEL_REPO:-}
prepare_doctor_root
if [ -n "$saved_repo" ]; then
  export KEEL_REPO="$saved_repo"
else
  "$SETUP/keel.sh" init-repo >/dev/null
fi
# The live daemon stays rootful. Bring egress up through the test entrypoint
# so the doctor can score every other critical check.
if ! "$HERE/harness-keel.sh" egress-up >/dev/null; then
  echo "ERROR: egress-up failed before the doctor" >&2
  rc=1
fi
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
if [ "${KEEL_MUTATE_FORCE:-}" = 1 ] || [ "${KEEL_MUTATE_ALL:-}" = 1 ]; then
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
      if [ "${KEEL_MUTATE_ALL:-}" = 1 ]; then
        ids=$(python3 "$HERE/mutant_files.py" --all) || {
          echo "ERROR: mutate: all list failed" >&2
          rc=1
          ids=
        }
      elif [ "${KEEL_MUTATE_FORCE:-}" = 1 ]; then
        ids=$(python3 "$HERE/mutant_files.py" --full) || {
          echo "ERROR: mutate: full list failed" >&2
          rc=1
          ids=
        }
      else
        ids=$(python3 "$HERE/mutant_files.py" --ci) || {
          echo "ERROR: mutate: ci list failed" >&2
          rc=1
          ids=
        }
      fi
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
  if [ -n "$ids" ] && [ "${KEEL_MUTATE_DEFER:-}" = 1 ]; then
    echo "RESULT mutate: deferred"
  elif [ -n "$ids" ]; then
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
