#!/usr/bin/env bash
# keel-doctor: is this machine ready to run the rudax-keel agent harness (variant 2)? bash 3.2+.
# Usage: keel-doctor.sh [--attacks | --score-log FILE | --pi | --pi-score FILE | --disc | --disc-score FILE]
# env: KEEL_ROOT (default ~/keel-proto), KEEL_REPO (default $KEEL_ROOT/repo), DOCKER (docker | "sudo docker" | podman)
# Exit: 0 = READY or READY WITH WARNINGS, 1 = NOT READY (a CRITICAL check failed), 2 = usage.
# Docs: docs/harness-checks-why.md#<id>
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=setup/lib/portable.sh
. "$HERE/lib/portable.sh"
KEEL_ROOT=${KEEL_ROOT:-$HOME/keel-proto}; KEEL_REPO=${KEEL_REPO:-$KEEL_ROOT/repo}; DOCKER=${DOCKER:-docker}
ATTACKS=0
SCORE_LOG=
PI_ONLY=0
PI_SCORE=
DISC_ONLY=0
DISC_SCORE=
while [ $# -gt 0 ]; do
  case $1 in
    --attacks) ATTACKS=1;;
    --score-log)
      shift
      [ $# -ge 1 ] || { echo "missing log path" >&2; exit 2; }
      SCORE_LOG=$1
      ATTACKS=1;;
    --pi) PI_ONLY=1;;
    --pi-score)
      shift
      [ $# -ge 1 ] || { echo "missing score path" >&2; exit 2; }
      PI_SCORE=$1
      PI_ONLY=1;;
    --disc) DISC_ONLY=1;;
    --disc-score)
      shift
      [ $# -ge 1 ] || { echo "missing score path" >&2; exit 2; }
      DISC_SCORE=$1
      DISC_ONLY=1;;
    -h|--help) sed -n 2,6p "$0"; exit 0;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
  shift
done

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then G=$'\033[32m' Y=$'\033[33m' R=$'\033[31m' B=$'\033[1m' D=$'\033[2m' N=$'\033[0m'; else G='' Y='' R='' B='' D='' N=''; fi
PASS=0 WARN=0 FAIL=0 CRIT_FAIL=0
# check <ID> <LEVEL> <pass|warn|fail> <what> <detail>
check(){ local id=$1 lvl=$2 st=$3 what=$4 det=${5-} icon col
  case $st in pass) icon="✅" col=$G; PASS=$((PASS+1));; warn) icon="⚠️ " col=$Y; WARN=$((WARN+1));;
    *) icon="❌" col=$R; FAIL=$((FAIL+1)); [ "$lvl" = CRITICAL ] && CRIT_FAIL=$((CRIT_FAIL+1));; esac
  printf '%s %s%-7s%s %s%-11s%s %s%s%s%s\n' "$icon" "$B" "$id" "$N" "$D" "$lvl" "$N" "$col" "$what" "${det:+: $det}" "$N"; }
section(){ printf '\n%s%s%s\n' "$B" "$1" "$N"; }

# Missing or skipped Pi rows are failures. A zero here ignores both.
score_pi_file() {
  local file=$1 id status detail
  local pi_rows_required=1 # pi-rows-required
  local seen=" "
  while IFS=$(printf '\t') read -r id status detail; do
    [ -n "$id" ] || continue
    seen="$seen$id "
    if [ "$status" = pass ]; then
      check "$id" CRITICAL pass "pi launch" "$detail"
    elif [ "$status" = skip ] && [ "$pi_rows_required" != 1 ]; then
      check "$id" CRITICAL pass "pi launch" "$detail"
    else
      check "$id" CRITICAL fail "pi launch" "${detail:-$status}"
    fi
  done < "$file"
  if [ "$pi_rows_required" = 1 ]; then
    for id in PI-01 PI-02 PI-03 PI-04 PI-05 PI-06 PI-07 PI-08 PI-09; do
      case $seen in
        *" $id "*) ;;
        *) check "$id" CRITICAL fail "pi launch" "no result";;
      esac
    done
  fi
}

score_disc_file() {
  local file=$1 id status detail
  local disc_rows_required=1 # disc-rows-required
  local seen=" "
  while IFS=$(printf '\t') read -r id status detail; do
    [ -n "$id" ] || continue
    seen="$seen$id "
    if [ "$status" = pass ]; then
      check "$id" CRITICAL pass "discoveries" "$detail"
    elif [ "$disc_rows_required" != 1 ]; then
      check "$id" CRITICAL pass "discoveries" "$detail"
    else
      check "$id" CRITICAL fail "discoveries" "${detail:-$status}"
    fi
  done < "$file"
  if [ "$disc_rows_required" = 1 ]; then
    for id in DISC-01 DISC-02 DISC-03 DISC-04 DISC-05 DISC-06 DISC-07a DISC-07b DISC-08; do
      case $seen in
        *" $id "*) ;;
        *) check "$id" CRITICAL fail "discoveries" "no result";;
      esac
    done
  fi
}

run_disc_live() {
  local disc_tmp table
  section "Discoveries"
  disc_tmp=$(mktemp -d "${TMPDIR:-/tmp}/keel-disc.XXXXXX")
  table=$disc_tmp/rows.tsv
  python3 "$HERE/lib/discovery_filter.py" doctor --harness "$HERE" --keel "$KEEL_ROOT" >"$table" 2>"$disc_tmp/err" || true
  score_disc_file "$table"
  rm -rf "$disc_tmp"
}

run_pi_live() {
  local pi_tmp table
  section "Pi launch"
  pi_tmp=$(mktemp -d "${TMPDIR:-/tmp}/keel-pi.XXXXXX")
  table=$pi_tmp/rows.tsv
  python3 "$HERE/lib/pi_launch.py" doctor \
    --harness "$HERE" --keel "$pi_tmp/keel" --work "$pi_tmp/work" \
    --repo "$pi_tmp/repo" --task pi-doctor >"$table" 2>"$pi_tmp/err" || true
  score_pi_file "$table"
  rm -rf "$pi_tmp"
}

finish() {
  echo
  summary="${PASS} passed, ${WARN} warnings, ${FAIL} failed"
  if [ $CRIT_FAIL -gt 0 ]; then printf '%s❌ NOT READY%s (%s; %d critical)\n' "$R$B" "$N" "$summary" "$CRIT_FAIL"; exit 1
  elif [ $((WARN + FAIL)) -gt 0 ]; then printf '%s⚠️  READY WITH WARNINGS%s (%s)\n' "$Y$B" "$N" "$summary"; exit 0
  else printf '%s✅ READY%s (%s)\n' "$G$B" "$N" "$summary"; exit 0; fi
}

if [ -n "$PI_SCORE" ]; then
  section "Pi launch"
  score_pi_file "$PI_SCORE"
  finish
fi
if [ "$PI_ONLY" = 1 ]; then
  run_pi_live
  finish
fi
if [ -n "$DISC_SCORE" ]; then
  section "Discoveries"
  score_disc_file "$DISC_SCORE"
  finish
fi
if [ "$DISC_ONLY" = 1 ]; then
  run_disc_live
  finish
fi

section "Environment"
os=$(uname -s); arch=$(uname -m)
if [ "$os" = Linux ]; then check ENV-01 CRITICAL pass "OS" "Linux $(uname -r) $arch (tested)"; else check ENV-01 CRITICAL warn "OS" "untested OS ($os $(uname -r) $arch)"; fi

gv=$(git --version 2>/dev/null | awk '{print $3}')
if [ -z "$gv" ]; then check ENV-02 CRITICAL fail "git" "not on PATH$(is_darwin && echo '; run: xcode-select --install')"
elif ver_ge "$gv" 2.30; then check ENV-02 CRITICAL pass "git" "$gv"
else check ENV-02 CRITICAL warn "git" "$gv is old; tested with 2.45-2.47"; fi

dcli=${DOCKER##* }; DOK=0
if ! command -v "$dcli" >/dev/null 2>&1; then
  check ENV-03 CRITICAL fail "container CLI" "'$dcli' not on PATH$(is_darwin && echo '; install Docker Desktop')"
else check ENV-03 CRITICAL pass "container CLI" "$($DOCKER --version 2>/dev/null | head -1)"; DOK=1; fi

if [ $DOK = 1 ] && info=$($DOCKER info --format '{{.ServerVersion}}|{{.OperatingSystem}}|{{.Architecture}}|{{json .SecurityOptions}}|{{.CgroupVersion}}' 2>/dev/null); then
  sv=$(echo "$info" | cut -d'|' -f1); dos=$(echo "$info" | cut -d'|' -f2); darch=$(echo "$info" | cut -d'|' -f3)
  check ENV-04 CRITICAL pass "daemon running" "server $sv on '$dos' ($darch)"
  # shellcheck source=setup/lib/runtime.sh
  . "$HERE/lib/runtime.sh"
  env05_level=CRITICAL # env05-level
  cls_ec=0
  cls=$(keel_classify_runtime) || cls_ec=$?
  case $cls_ec in
    0) check ENV-05 "$env05_level" pass "isolation boundary" "$cls";;
    2) check ENV-05 RECOMMENDED warn "isolation boundary" "$cls (untested; not an egress pass)";;
    *) check ENV-05 "$env05_level" fail "isolation boundary" "$cls; a container escape on a rootful daemon is host root";;
  esac
  if iarch=$($DOCKER image inspect --format '{{.Architecture}}' keel-git 2>/dev/null || $DOCKER image inspect --format '{{.Architecture}}' localhost/keel-git 2>/dev/null); then
    na=$darch; case $na in x86_64) na=amd64;; aarch64) na=arm64;; esac
    if [ "$iarch" = "$na" ]; then check ENV-06 RECOMMENDED pass "image keel-git" "present, $iarch (native)"; else check ENV-06 RECOMMENDED warn "image keel-git" "arch $iarch, daemon is $darch (emulated, slow); rebuild: $DOCKER build -t keel-git -f $HERE/docker/keel-git.Dockerfile $HERE/docker"; fi
  else check ENV-06 RECOMMENDED warn "image keel-git" "missing; run: $DOCKER build -t keel-git -f $HERE/docker/keel-git.Dockerfile $HERE/docker"; fi
  if out=$($DOCKER run --rm --network none --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp --pids-limit 64 --memory 128m --cpus 0.5 --user "$(id -u):$(id -g)" keel-git true 2>&1); then
    check ENV-07 CRITICAL pass "hardening flags accepted" "cap-drop, no-new-privileges, read-only, pids/memory/cpus"
  else check ENV-07 CRITICAL fail "hardening flags accepted" "$(echo "$out" | tail -1 | cut -c1-140)"; fi
  # ENV-08: mount KEEL_ROOT + single-file ro bind (pointer mode) probe
  mkdir -p "$KEEL_ROOT" 2>/dev/null; kr=$(abs_dir "$KEEL_ROOT")
  if [ -z "$kr" ] || ! path_is_shared "$kr"; then
    check ENV-08 CRITICAL fail "KEEL_ROOT mountable" "${kr:-$KEEL_ROOT} is not in a Docker Desktop shared dir; use a path under \$HOME or add it in Settings > Resources > File sharing"
  else
    pd=$(mktemp -d "$kr/.doctor-probe.XXXXXX"); echo "gitdir: /x" > "$pd/.git"
    if ! err=$($DOCKER run --rm --network none --user "$(id -u):$(id -g)" -v "$pd:/work" keel-git ls /work/.git 2>&1); then
      check ENV-08 CRITICAL fail "KEEL_ROOT mountable" "bind mount of $kr failed: $(echo "$err" | tail -1 | cut -c1-120)"
    elif $DOCKER run --rm --network none --user "$(id -u):$(id -g)" -v "$pd:/work" -v "$pd/.git:/work/.git:ro" keel-git sh -c 'echo y > /work/.git' 2>/dev/null; then
      check ENV-08 CRITICAL fail "pointer mode" "single-file ro bind accepted but WRITABLE inside the container"
    elif $DOCKER run --rm --network none --user "$(id -u):$(id -g)" -v "$pd:/work" -v "$pd/.git:/work/.git:ro" keel-git cat /work/.git >/dev/null 2>&1; then
      check ENV-08 CRITICAL pass "pointer mode" "single-file ro bind works (primary mode)"
    else check ENV-08 CRITICAL warn "pointer mode" "single-file ro bind rejected; keel.sh falls back to GIT_DIR/GIT_WORK_TREE (no pointer file)"; fi
    rm -rf "$pd"
  fi
else
  [ $DOK = 1 ] && check ENV-04 CRITICAL fail "daemon running" "$(docker_hint)"
  for x in "ENV-05 RECOMMENDED isolation boundary" "ENV-06 RECOMMENDED image keel-git" "ENV-07 CRITICAL hardening flags accepted" "ENV-08 CRITICAL pointer mode"; do
    # shellcheck disable=SC2086  # intentional word split of "ID LEVEL description"
    set -- $x; id=$1 lvl=$2; shift 2; [ "$lvl" = CRITICAL ] && st=fail || st=warn; check "$id" "$lvl" "$st" "$*" "skipped: no daemon"; done
fi

section "Secrets"
toks=$(env | cut -d= -f1 | grep -E '^(GH_|GITHUB_)|^BOT_GH_TOKEN$' | paste -sd, -)
if [ -z "$toks" ]; then check SEC-01 CRITICAL pass "no GitHub token in environment"; else check SEC-01 CRITICAL fail "GitHub token variables in environment" "$toks (names only; values not printed)"; fi

section "Repository ($KEEL_REPO)"
if git -C "$KEEL_REPO" rev-parse --git-dir >/dev/null 2>&1; then
  rc(){ local id=$1 key=$2 want=$3 got; got=$(git -C "$KEEL_REPO" config --get "$key"); if [ "$got" = "$want" ]; then check "$id" CRITICAL pass "$key=$want"; else check "$id" CRITICAL fail "$key" "is '${got:-unset}', expected $want (git -C $KEEL_REPO config $key $want)"; fi; }
  rc REPO-01 gc.auto 0; rc REPO-02 maintenance.auto false; rc REPO-03 gc.pruneExpire never
  if br=$(git -C "$KEEL_REPO" symbolic-ref --short HEAD 2>/dev/null); [ "$br" = main ]; then check REPO-04 RECOMMENDED pass "on main"; else check REPO-04 RECOMMENDED warn "branch" "HEAD is '${br:-detached}', expected main"; fi
else check REPO-01 CRITICAL fail "repository" "no git repo at $KEEL_REPO (set KEEL_REPO, or run: keel.sh init-repo for a throwaway one)"; fi

section "Visibility"
if ! command -v python3 >/dev/null 2>&1; then
  check VIS-01 CRITICAL fail "allow and deny loader" "python3 is missing"
else
  if verr=$(python3 "$HERE/lib/visibility.py" doctor --harness "$HERE" 2>&1); then
    check VIS-01 CRITICAL pass "allow and deny loader" "folder allowlists and the deny base parse"
  else
    check VIS-01 CRITICAL fail "allow and deny loader" "$(printf '%s' "$verr" | head -1 | cut -c1-140)"
  fi
fi

section "Egress"
# shellcheck source=setup/lib/egress.sh
. "$HERE/lib/egress.sh"
egress_names
if $DOCKER image inspect keel-proxy >/dev/null 2>&1; then
  check EG-01 CRITICAL pass "proxy image" "keel-proxy present"
else
  check EG-01 CRITICAL fail "proxy image" "keel-proxy is missing"
fi
if got=$($DOCKER network inspect -f '{{.Internal}}' "$EGRESS_NET" 2>/dev/null); [ "$got" = true ]; then
  check EG-02 CRITICAL pass "egress network" "$EGRESS_NET internal"
else
  check EG-02 CRITICAL fail "egress network" "${EGRESS_NET} internal flag is '${got:-missing}'"
fi
health=$($DOCKER run --rm --network "$EGRESS_NET" keel-git sh -c 'printf "GET http://keel-proxy/ HTTP/1.1\r\nHost: keel-proxy\r\nConnection: close\r\n\r\n" | nc -w 3 keel-proxy 3128' 2>&1 || true)
if printf '%s\n' "$health" | grep -q DENIED; then
  check EG-03 CRITICAL pass "proxy health" "forward port answered"
else
  check EG-03 CRITICAL fail "proxy health" "$(printf '%s' "$health" | tail -1 | cut -c1-120)"
fi

section "Secret scan"
gl=${KEEL_GITLEAKS:-$HOME/.cache/keel/gitleaks-8.30.1/gitleaks}
ver=""
if [ -x "$gl" ]; then
  ver=$("$gl" version 2>/dev/null | tr -d '[:space:]')
fi
if [ "$ver" = "8.30.1" ]; then
  check GL-01 CRITICAL pass "gitleaks" "8.30.1 present"
else
  check GL-01 CRITICAL fail "gitleaks" "need executable 8.30.1"
fi

section "Disk"
dir=$KEEL_ROOT; while [ ! -d "$dir" ]; do dir=$(dirname "$dir"); done
free=$(free_gib "$dir")
if [ "$free" -ge 10 ]; then check DISK-01 RECOMMENDED pass "free disk" "${free} GiB at $dir"
elif [ "$free" -ge 2 ]; then check DISK-01 RECOMMENDED warn "free disk" "${free} GiB at $dir (< 10 GiB)"
else check DISK-01 RECOMMENDED fail "free disk" "${free} GiB at $dir (< 2 GiB)"; fi
# shellcheck source=setup/lib/runtime.sh
. "$HERE/lib/runtime.sh"
if keel_disk_ok "$dir"; then check DISK-02 CRITICAL pass "work free space" "at least the configured minimum"
else check DISK-02 CRITICAL fail "work free space" "below the configured minimum"; fi
if command -v playwright >/dev/null 2>&1 || command -v chromium >/dev/null 2>&1 || command -v google-chrome >/dev/null 2>&1 || [ "${KEEL_PLAYWRIGHT:-}" = 1 ]; then
  chr_level=CRITICAL
  chr_detail="disable flags refused"
else
  chr_level=RECOMMENDED
  chr_detail="not installed; required before the QA browser step"
fi
if bash "$HERE/chrome/chromium-argv.sh" --version >/dev/null 2>&1; then
  check CHR-01 "$chr_level" pass "chromium sandbox argv" "$chr_detail"
else
  check CHR-01 "$chr_level" fail "chromium sandbox argv" "sandbox disable flag was accepted"
fi

run_pi_live
run_disc_live

# attack id -> human name (bash 3.2: no associative arrays)
ATK_IDS="N1 N2 A1 A2 A3 A12 A12b A4 A4b A4c A5 A6 A6b A6c A7 A7b A8 A8b A9 A10 A10b A11 A11-detect A13 A14 A15 A16 A17 A17b A17c A18 A18b A19 A19b A20 A21 A22 A22b H1 H2 H3 H4 H5 V-H9 V-H1 V-A2 V-A10-hardlink V-A20 V-H3 V-A1 V-A15 V-A25 V-A24b V-A16 V-H2 V-H5 V-A5 V-H6 V-H7 V-A27 V-H4 V-A6 V-A23 V-A28 V-A25b V-A11 V-A25c V-A17 V-A18 V-H6b V-A12 V-A7 V-A8 V-A24 V-A29 V-A30 V-A31 V-H8 V-LOG V-A13 V-A14 V-A4 V-A21 V-A22 V-A19 V-A3 V-A3b V-A26 V-A32 V-PARSE V-RO V-RUNS E-H1 E-H2 E-H3 E-H4 E-H5 E-H6 E-A1 E-A2 E-A3 E-A4 E-A5 E-A6 E-A7 E-A8 E-A9 E-A10 E-A11 E-A12 E-A13 E-A14 E-A15 E-A16 E-A17 S-H1 S-A1 S-A2 S-A3 S-A4 SEC-H1 SEC-03 SEC-04 SEC-05 MODE-A1 R-H1 R-A1 R-A4 R-A5 R-A7 R-A8 R-A9 M-H1 M-A1 M-A2 M-A3 M-A4"
atk_name(){ case $1 in
  N1) echo "proto and gate containers have no network";; N2) echo "host token not passed to container";; A1) echo "/base/objects is read-only";;
  A2) echo "pointer file can't be rewritten";; A3) echo "shadow hooks/fsmonitor never run on host";; A12) echo "role A's hook doesn't run in role B/export";;
  A4) echo "gate: .github/ forbidden";; A4b) echo "gate: AGENTS.md, .pi/ forbidden";; A5) echo "gate: symlink rejected";; A6) echo "gate: bundle size limit";;
  A6b) echo "gate: diff line limit";; A7) echo "gate: extra branch/tag rejected";; A7b) echo "gate: wrong branch name rejected";; A8) echo "gate: stale base rejected";;
  A8b) echo "gate: bundle without base rejected";; A12b) echo "forced git safety config in roles";; A4c) echo "gate: case/rename/mode forbidden-path variants";;
  A6c) echo "gate: changed-file count limit";; A13) echo "gate: fsck rejects corrupt objects";; A14) echo "gate: submodule/gitlink rejected";;
  A15) echo "gate: commit identity rejected";; A16) echo "push stub: one gated sha, one branch";; A17|A17b|A17c) echo "gate: NUL-safe path parsing (space, UTF-8, tab/quote)";; A18|A18b) echo "gate: Pi process paths";; A19|A19b) echo "reset_shadow refuses symlinks";; A20) echo "gate: nested .git path";; A21) echo "gate: tests from main's entrypoint";; A22|A22b) echo "gate: no merge/orphan commits";; H5) echo "cpu limit";; A9) echo "reviewer can't commit";; A10) echo "gc guard";; A10b) echo "main can't move backwards";;
  A11) echo "no root-owned files";; A11-detect) echo "gate rejects foreign-owned files";; H1) echo "no mount/chown/caps";; H2) echo "fork bomb contained";;
  H3) echo "memory limit";; H4) echo "no writes outside mounts";; S-H1) echo "role starts when no secret name is set";; S-A1) echo "role refuses a denylisted secret name";; S-A2) echo "format patterns are redacted";; S-A3) echo "mount error is logged";; S-A4) echo "KEEL_SECRET name refuses the role";; SEC-H1) echo "clean bundle passes the secret scan";; SEC-03) echo "secret shape in the change fails the gate";; SEC-04) echo "inline allow comment still fails the gate";; SEC-05) echo "product ignore file still fails the gate";; MODE-A1) echo "directly executed script is mode 100755";; R-H1) echo "rootless fixture passes the runtime check";; R-A1) echo "rootful fixture refuses launch";; R-A4) echo "low free space refuses launch";; R-A5) echo "chromium sandbox flags are refused";; R-A7) echo "userns remap is not rootless";; R-A8) echo "live doctor scorer stays exact";; R-A9) echo "each launch path refuses rootful and low disk";; M-H1) echo "mutant run matches the head";; M-A1) echo "stale mutant run is rejected";; M-A2) echo "missing mutant run is rejected";; M-A3) echo "spoofed mutant result is rejected";; M-A4) echo "gate calls the mutant binder";; *) echo "$1";; esac; }

if [ $ATTACKS = 1 ]; then
  section "Attacks (test-attacks.sh in a throwaway dir; real containers on this machine)"
  if [ $CRIT_FAIL -gt 0 ] && [ -z "$SCORE_LOG" ]; then check ATK-00 CRITICAL fail "attack suite" "skipped: fix critical environment failures first"
  else
    if [ -n "$SCORE_LOG" ]; then
      ALOG=$SCORE_LOG
      if [ ! -f "$ALOG" ]; then check ATK-00 CRITICAL fail "attack log" "missing $ALOG"; ALOG=; fi
    else
      AROOT=$(mktemp -d "$HOME/.keel-doctor.XXXXXX"); ALOG=${KEEL_DOCTOR_LOG:-$HERE/tests/harness/logs/doctor-attacks-$(date +%Y%m%d-%H%M%S).log}; mkdir -p "$(dirname "$ALOG")"
      KEEL_ROOT=$AROOT/keel DOCKER=$DOCKER "$HERE/tests/harness/test-attacks.sh" >"$ALOG" 2>&1; rm -rf "$AROOT"
    fi
    if [ -n "$ALOG" ]; then
      printf '%s  raw log: %s%s\n' "$D" "$ALOG" "$N"
      SEEN=" "
      while IFS= read -r line; do
        id=${line#RESULT }; id=${id%%:*}; txt=${line#*: }
        # A skipped result is not a pass and not a failure.
        case $txt in *skipped*) continue;; esac
        SEEN="$SEEN$id "
        lvl=CRITICAL; [ "$id" = A10 ] && lvl=RECOMMENDED
        case $txt in BLOCKED*|CONTAINED*) st=pass;; PARTIAL*|RISK*|N/A*) st=warn;; *) st=fail;; esac
        check "ATK-$id" "$lvl" "$st" "$(atk_name "$id")" "$(echo "$txt" | cut -c1-110)"
      done <<EOT
$(grep -a '^RESULT ' "$ALOG")
EOT
      for id in $ATK_IDS; do case "$SEEN" in *" $id "*) ;; *) check "ATK-$id" CRITICAL fail "$(atk_name "$id")" "no result in log (suite crashed?)";; esac; done
    fi
  fi
fi

finish
