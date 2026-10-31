#!/usr/bin/env bash
# keel-doctor: is this machine ready to run the rudax-keel agent harness (variant 2)? bash 3.2+.
# Usage: keel-doctor.sh [--attacks]
# env: KEEL_ROOT (default ~/keel-proto), KEEL_REPO (default $KEEL_ROOT/repo), DOCKER (docker | "sudo docker" | podman)
# Exit: 0 = READY or READY WITH WARNINGS, 1 = NOT READY (a CRITICAL check failed), 2 = usage.
# Docs: docs/harness-checks-why.md#<id>
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=setup/lib/portable.sh
. "$HERE/lib/portable.sh"
KEEL_ROOT=${KEEL_ROOT:-$HOME/keel-proto}; KEEL_REPO=${KEEL_REPO:-$KEEL_ROOT/repo}; DOCKER=${DOCKER:-docker}
ATTACKS=0
for a in "$@"; do case $a in --attacks) ATTACKS=1;; -h|--help) sed -n 2,6p "$0"; exit 0;; *) echo "unknown option: $a" >&2; exit 2;; esac; done

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then G=$'\033[32m' Y=$'\033[33m' R=$'\033[31m' B=$'\033[1m' D=$'\033[2m' N=$'\033[0m'; else G='' Y='' R='' B='' D='' N=''; fi
PASS=0 WARN=0 FAIL=0 CRIT_FAIL=0
# check <ID> <LEVEL> <pass|warn|fail> <what> <detail>
check(){ local id=$1 lvl=$2 st=$3 what=$4 det=${5-} icon col
  case $st in pass) icon="✅" col=$G; PASS=$((PASS+1));; warn) icon="⚠️ " col=$Y; WARN=$((WARN+1));;
    *) icon="❌" col=$R; FAIL=$((FAIL+1)); [ "$lvl" = CRITICAL ] && CRIT_FAIL=$((CRIT_FAIL+1));; esac
  printf '%s %s%-7s%s %s%-11s%s %s%s%s%s\n' "$icon" "$B" "$id" "$N" "$D" "$lvl" "$N" "$col" "$what" "${det:+: $det}" "$N"; }
section(){ printf '\n%s%s%s\n' "$B" "$1" "$N"; }

section "Environment"
os=$(uname -s); arch=$(uname -m)
if [ "$os" = Linux ]; then check ENV-01 CRITICAL pass "OS" "Linux $(uname -r) $arch (tested)"; else check ENV-01 CRITICAL warn "OS" "untested OS ($os $(uname -r) $arch)"; fi

gv=$(git --version 2>/dev/null | awk '{print $3}')
if [ -z "$gv" ]; then check ENV-02 CRITICAL fail "git" "not on PATH$(is_darwin && echo '; run: xcode-select --install')"
elif ver_ge "$gv" 2.30; then check ENV-02 CRITICAL pass "git" "$gv"
else check ENV-02 CRITICAL warn "git" "$gv is old; tested with 2.45-2.47"; fi

dcli=${DOCKER##* }; DOK=0; DESKTOP=0
if ! command -v "$dcli" >/dev/null 2>&1; then
  check ENV-03 CRITICAL fail "container CLI" "'$dcli' not on PATH$(is_darwin && echo '; install Docker Desktop')"
else check ENV-03 CRITICAL pass "container CLI" "$($DOCKER --version 2>/dev/null | head -1)"; DOK=1; fi

if [ $DOK = 1 ] && info=$($DOCKER info --format '{{.ServerVersion}}|{{.OperatingSystem}}|{{.Architecture}}|{{json .SecurityOptions}}|{{.CgroupVersion}}' 2>/dev/null); then
  sv=$(echo "$info" | cut -d'|' -f1); dos=$(echo "$info" | cut -d'|' -f2); darch=$(echo "$info" | cut -d'|' -f3)
  case $dos in *[Dd]ocker\ [Dd]esktop*) DESKTOP=1;; esac
  check ENV-04 CRITICAL pass "daemon running" "server $sv on '$dos' ($darch)"
  if [ "$dcli" = podman ]; then rl=$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null)
    if [ "$rl" = true ]; then check ENV-05 RECOMMENDED pass "isolation boundary" "podman rootless"; else check ENV-05 RECOMMENDED warn "isolation boundary" "podman runs as root; a container escape = host root"; fi
  elif [ $DESKTOP = 1 ]; then
    if is_darwin || [ "$os" != Linux ]; then check ENV-05 RECOMMENDED pass "isolation boundary" "Docker Desktop VM: containers run inside a Linux VM, an escape lands in the VM, not on the host"
    else check ENV-05 RECOMMENDED warn "isolation boundary" "Docker Desktop for Linux VM (untested)"; fi
  elif echo "$info" | grep -q rootless; then check ENV-05 RECOMMENDED pass "isolation boundary" "rootless Docker"
  else check ENV-05 RECOMMENDED warn "isolation boundary" "daemon runs as root on this host; a container escape = host root"; fi
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

section "Disk"
dir=$KEEL_ROOT; while [ ! -d "$dir" ]; do dir=$(dirname "$dir"); done
free=$(free_gib "$dir")
if [ "$free" -ge 10 ]; then check DISK-01 RECOMMENDED pass "free disk" "${free} GiB at $dir"
elif [ "$free" -ge 2 ]; then check DISK-01 RECOMMENDED warn "free disk" "${free} GiB at $dir (< 10 GiB)"
else check DISK-01 RECOMMENDED fail "free disk" "${free} GiB at $dir (< 2 GiB)"; fi

# attack id -> human name (bash 3.2: no associative arrays)
ATK_IDS="N1 N2 A1 A2 A3 A12 A12b A4 A4b A4c A5 A6 A6b A6c A7 A7b A8 A8b A9 A10 A10b A11 A11-detect A13 A14 A15 A16 A17 A17b A17c A18 A18b A19 A19b A20 A21 A22 A22b H1 H2 H3 H4 H5"
atk_name(){ case $1 in
  N1) echo "no network in agent container";; N2) echo "host token not passed to container";; A1) echo "/base/objects is read-only";;
  A2) echo "pointer file can't be rewritten";; A3) echo "shadow hooks/fsmonitor never run on host";; A12) echo "role A's hook doesn't run in role B/export";;
  A4) echo "gate: .github/ forbidden";; A4b) echo "gate: AGENTS.md, .pi/ forbidden";; A5) echo "gate: symlink rejected";; A6) echo "gate: bundle size limit";;
  A6b) echo "gate: diff line limit";; A7) echo "gate: extra branch/tag rejected";; A7b) echo "gate: wrong branch name rejected";; A8) echo "gate: stale base rejected";;
  A8b) echo "gate: bundle without base rejected";; A12b) echo "forced git safety config in roles";; A4c) echo "gate: case/rename/mode forbidden-path variants";;
  A6c) echo "gate: changed-file count limit";; A13) echo "gate: fsck rejects corrupt objects";; A14) echo "gate: submodule/gitlink rejected";;
  A15) echo "gate: commit identity rejected";; A16) echo "push stub: one gated sha, one branch";; A17|A17b|A17c) echo "gate: NUL-safe path parsing (space, UTF-8, tab/quote)";; A18|A18b) echo "gate: Pi process paths";; A19|A19b) echo "reset_shadow refuses symlinks";; A20) echo "gate: nested .git path";; A21) echo "gate: tests from main's entrypoint";; A22|A22b) echo "gate: no merge/orphan commits";; H5) echo "cpu limit";; A9) echo "reviewer can't commit";; A10) echo "gc guard";; A10b) echo "main can't move backwards";;
  A11) echo "no root-owned files";; A11-detect) echo "gate rejects foreign-owned files";; H1) echo "no mount/chown/caps";; H2) echo "fork bomb contained";;
  H3) echo "memory limit";; H4) echo "no writes outside mounts";; *) echo "$1";; esac; }

if [ $ATTACKS = 1 ]; then
  section "Attacks (test-attacks.sh in a throwaway dir; real containers on this machine)"
  if [ $CRIT_FAIL -gt 0 ]; then check ATK-00 CRITICAL fail "attack suite" "skipped: fix critical environment failures first"
  else
    AROOT=$(mktemp -d "$HOME/.keel-doctor.XXXXXX"); ALOG=${KEEL_DOCTOR_LOG:-$HERE/tests/harness/logs/doctor-attacks-$(date +%Y%m%d-%H%M%S).log}; mkdir -p "$(dirname "$ALOG")"
    KEEL_ROOT=$AROOT/keel DOCKER=$DOCKER "$HERE/tests/harness/test-attacks.sh" >"$ALOG" 2>&1; rm -rf "$AROOT"
    printf '%s  raw log: %s%s\n' "$D" "$ALOG" "$N"
    SEEN=" "
    while IFS= read -r line; do
      id=${line#RESULT }; id=${id%%:*}; txt=${line#*: }; SEEN="$SEEN$id "
      lvl=CRITICAL; [ "$id" = A10 ] && lvl=RECOMMENDED
      case $txt in BLOCKED*|CONTAINED*) st=pass;; PARTIAL*|RISK*|N/A*) st=warn;; *) st=fail;; esac
      check "ATK-$id" "$lvl" "$st" "$(atk_name "$id")" "$(echo "$txt" | cut -c1-110)"
    done <<EOT
$(grep -a '^RESULT ' "$ALOG")
EOT
    for id in $ATK_IDS; do case "$SEEN" in *" $id "*) ;; *) check "ATK-$id" CRITICAL fail "$(atk_name "$id")" "no result in log (suite crashed?)";; esac; done
  fi
fi

echo
summary="${PASS} passed, ${WARN} warnings, ${FAIL} failed"
if [ $CRIT_FAIL -gt 0 ]; then printf '%s❌ NOT READY%s (%s; %d critical)\n' "$R$B" "$N" "$summary" "$CRIT_FAIL"; exit 1
elif [ $((WARN + FAIL)) -gt 0 ]; then printf '%s⚠️  READY WITH WARNINGS%s (%s)\n' "$Y$B" "$N" "$summary"; exit 0
else printf '%s✅ READY%s (%s)\n' "$G$B" "$N" "$summary"; exit 0; fi
