#!/usr/bin/env bash
# rudax-keel variant 2 prototype (tested on Linux; macOS Docker Desktop untested). bash 3.2+.
# Usage: keel.sh <cmd>
# cmds: init-repo | setup | reset-shadow | mode | role <name> <rw|ro> <sh-cmd> | role-env <sh-cmd> | export | gate | push-stub
#       | repo-gc | repo-prune | set-main <sha> | cleanup
# env: KEEL_ROOT (default ~/keel-proto), TASK, DOCKER (docker | "sudo docker" | podman), IMG,
#      KEEL_POINTER_MODE (auto | pointer | env)
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=setup/lib/portable.sh
. "$HERE/lib/portable.sh"
P=${KEEL_ROOT:-$HOME/keel-proto}; T=${TASK:-task-1}
mkdir -p "$P"; P=$(abs_dir "$P")    # physical path: Docker Desktop shares /private/tmp, not /tmp
R=$P/repo; W=$P/work/$T; S=$P/shadow/$T.git; B=$P/bundles; G=$P/gate/$T.git
DOCKER=${DOCKER:-docker}; IMG=${IMG:-keel-git}
UIDGID="$(id -u):$(id -g)"
MAX_BUNDLE=${MAX_BUNDLE:-1048576}; MAX_LINES=${MAX_LINES:-5000}; MAX_FILES=${MAX_FILES:-500}
# matched case-insensitively (macOS/Windows checkouts fold case: .GitHub/ == .github/)
# Pi Agent process set (scripts/check-scope.py), plus .gitmodules.
# .pi/ and .agents/ match at any depth. setup/README.md and setup/TESTING.md
# are ordinary docs (whole path, any case).
FORBID_PREFIX='^(\.github|setup|scripts)/|(^|/)\.pi/|(^|/)\.agents/'
FORBID_NAME='(^|/)(agents\.md|agents\.override\.md|claude\.md|codeowners|\.shellcheckrc|\.gitmodules)$'
DOTGIT='(^|/)\.git(/|$)'
TEST_ENTRY=${KEEL_TEST_ENTRY:-test.sh}   # test entrypoint, always taken from MAIN, never from the bundle
AGENT_IDENT=${KEEL_AGENT_IDENT:-agent <a@x>}
if ! path_is_shared "$P"; then
  echo "KEEL_ROOT $P is not under a Docker Desktop shared dir (/Users, /Volumes, /private, /tmp, /var/folders)." >&2
  echo "Use a path under \$HOME, or add it in Docker Desktop > Settings > Resources > File sharing." >&2; exit 4; fi
# container hardening applied to EVERY container (agent, setup, export, test)
# shellcheck disable=SC2054  # commas belong to the --tmpfs option value, not array separators
HARDEN=(--rm --network none --user "$UIDGID" --cap-drop ALL --security-opt no-new-privileges
  --read-only --tmpfs /tmp:rw,size=64m --pids-limit "${PIDS:-128}" --memory "${MEM:-512m}" --cpus "${CPUS:-1}")
case "$DOCKER" in *podman*) HARDEN+=(--userns=keep-id);; esac
GITENV=(-e HOME=/tmp -e "GIT_CONFIG_PARAMETERS='core.hooksPath'='/dev/null' 'core.fsmonitor'='false'"
  -e GIT_AUTHOR_NAME=agent -e GIT_AUTHOR_EMAIL=a@x -e GIT_COMMITTER_NAME=agent -e GIT_COMMITTER_EMAIL=a@x)
hgit(){ env -i PATH=/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin HOME="$P/.gatehome" GIT_CONFIG_NOSYSTEM=1 git -c core.hooksPath=/dev/null -c core.fsmonitor=false -c core.pager=cat -c protocol.allow=never -c protocol.file.allow=always "$@"; }
crun(){ $DOCKER run "${HARDEN[@]}" "${GITENV[@]}" "$@"; }
mode(){ cat "$P/$T.mode" 2>/dev/null || echo pointer; }
# work-tree mounts for the current mode. $1 = rw|ro. Sets array MNT.
work_mounts(){ local m=$1
  if [ "$(mode)" = pointer ]; then MNT=(-v "$W:/work:$m" -v "$W/.git:/work/.git:ro" -v "$S:/shadow/$T.git:$m")
  else MNT=(-v "$W:/work:$m" -v "$S:/shadow/$T.git:$m" -e "GIT_DIR=/shadow/$T.git" -e GIT_WORK_TREE=/work); fi; }
reset_shadow(){ # plain file ops only, never git on host against the shadow; never follow agent symlinks
  [ -e "$S" ] || [ -L "$S" ] || return 0
  local d f
  for d in "$S" "$S/objects" "$S/objects/info"; do
    if [ -L "$d" ] || { [ -e "$d" ] && [ ! -d "$d" ]; }; then echo "REFUSED: shadow tampered: $d is a symlink or not a directory" >&2; exit 8; fi; done
  mkdir -p "$S/objects/info"
  for f in config objects/info/alternates objects/info/http-alternates commondir config.worktree; do rm -f "$S/$f"; done
  rm -rf "$S/hooks" "$S/info" && mkdir "$S/hooks" "$S/info"   # rm -rf removes a symlink itself, not its target
  ( set -C   # noclobber: fail rather than write through anything recreated in between
    printf '[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n\tbare = false\n\tlogallrefupdates = true\n' > "$S/config" &&
    echo /base/objects > "$S/objects/info/alternates" ) || { echo "REFUSED: could not rewrite shadow control files" >&2; exit 8; }; }
tasks_active(){ ls -d "$P"/work/*/ >/dev/null 2>&1; }
need_docker(){ $DOCKER info >/dev/null 2>&1 || { docker_hint >&2; exit 5; }; }
case "${1:-}" in
init-repo) mkdir -p "$R" "$P/.gatehome"; cd "$R" || exit 1; git init -q; git symbolic-ref HEAD refs/heads/main
  git config gc.auto 0; git config maintenance.auto false; git config gc.pruneExpire never; git config gc.reflogExpireUnreachable never
  printf '#!/bin/sh\nset -e\ngrep -q hello app.txt && echo TESTS-OK\n' > test.sh; echo hello > app.txt; mkdir -p .github; echo ci > .github/ci.yml; echo rules > AGENTS.md
  git add -A; git -c user.name=h -c user.email=h@x commit -qm init; echo "repo main=$(git rev-parse main) gc.auto=$(git config gc.auto) gc.pruneExpire=$(git config gc.pruneExpire)";;
setup) need_docker; M=$(git -C "$R" rev-parse main); mkdir -p "$W" "$B" "$(dirname "$S")"
  git init -q --bare "$S"; reset_shadow; echo "$M" > "$P/$T.base"
  printf 'gitdir: /shadow/%s.git\n' "$T" > "$W/.git"
  want=${KEEL_POINTER_MODE:-auto}; md='env'
  if [ "$want" != env ]; then
    if err=$(crun -v "$W:/work" -v "$W/.git:/work/.git:ro" "$IMG" true 2>&1); then md=pointer
    elif [ "$want" = pointer ]; then echo "single-file ro bind rejected: $err" >&2; exit 6
    else echo "WARN: single-file ro bind rejected by Docker ($(echo "$err" | tail -1)); falling back to GIT_DIR/GIT_WORK_TREE" >&2; fi
  fi
  [ $md = env ] && rm -f "$W/.git"      # env mode: no pointer file at all
  echo $md > "$P/$T.mode"; work_mounts rw
  crun -v "$R/.git/objects:/base/objects:ro" "${MNT[@]}" -w /work "$IMG" sh -c \
   "git update-ref refs/heads/$T $M && git symbolic-ref HEAD refs/heads/$T && git checkout -q -f $T && git log --oneline -1" \
   || { echo "setup container failed. If this is Docker Desktop, check that $P is in Settings > Resources > File sharing." >&2; exit 7; }
  echo "mode=$md";;
mode) mode;;
reset-shadow) reset_shadow; echo "shadow reset";;
role) shift; name=$1 m=$2; shift 2; reset_shadow
  echo "== role $name ($m) [shadow reset, mode=$(mode)]"; work_mounts "$m"
  crun -v "$R/.git/objects:/base/objects:ro" "${MNT[@]}" -w /work "$IMG" sh -c "$*";;
role-env) shift; WE=$P/work/$T-env; mkdir -p "$WE"; reset_shadow
  crun -e "GIT_DIR=/shadow/$T.git" -e GIT_WORK_TREE=/work -v "$R/.git/objects:/base/objects:ro" -v "$WE:/work" -v "$S:/shadow/$T.git" -w /work "$IMG" sh -c "$*";;
export) M=$(cat "$P/$T.base"); rm -f "$B/$T.bundle"; reset_shadow
  crun -v "$R/.git/objects:/base/objects:ro" -v "$S:/shadow/$T.git:ro" -v "$B:/bundles" "$IMG" \
    git --git-dir="/shadow/$T.git" bundle create "/bundles/$T.bundle" "refs/heads/$T" "^$M";;
gate) F=$B/$T.bundle; M=$(git -C "$R" rev-parse main); I=refs/keel/incoming/$T
  fail(){ echo "GATE FAIL: $*"; rm -rf "$G"; exit 1; }
  mkdir -p "$P/.gatehome" "$P/gate"; [ -f "$F" ] || fail "no bundle"
  bad=$(find "$P/work" "$P/shadow" "$B" ! -user "$(id -u)" 2>/dev/null | head -3)
  if [ -n "$bad" ]; then
    if is_darwin; then echo "GATE WARN: foreign-owned files on Darwin (virtiofs ownership mapping; not enforced): $bad"
    else fail "foreign-owned files: $bad"; fi; fi
  sz=$(file_size "$F"); [ "$sz" -le "$MAX_BUNDLE" ] || fail "bundle $sz > $MAX_BUNDLE bytes"
  rm -rf "$G"; hgit init -q --bare "$G"; echo "$R/.git/objects" > "$G/objects/info/alternates"; hgit -C "$G" update-ref refs/heads/main "$M"
  hgit -C "$G" bundle verify -q "$F" || fail "bundle verify"
  heads=$(hgit -C "$G" bundle list-heads "$F"); if [ "$(echo "$heads" | wc -l | tr -d ' ')" != 1 ] || [ "$(echo "$heads" | awk '{print $2}')" != "refs/heads/$T" ]; then fail "refs in bundle must be exactly refs/heads/$T, got: $(echo "$heads" | tr '\n' ' ')"; fi
  pre=$(sed -n '2,/^$/p' "$F" | grep -a '^-' | cut -c2-41); [ "$pre" = "$M" ] || fail "bundle base '$pre' != current main $M"
  hgit -C "$G" -c fetch.fsckObjects=true -c transfer.fsckObjects=true fetch -q --no-tags "$F" "+refs/heads/$T:$I" || fail "fetch/fsck"
  [ "$(hgit -C "$G" merge-base main "$I")" = "$M" ] || fail "merge-base != main"
  [ -z "$(hgit -C "$G" rev-list --min-parents=2 "main..$I")" ] || fail "merge commit in change (exactly one parent required)"
  [ -z "$(hgit -C "$G" rev-list --max-parents=0 "main..$I")" ] || fail "orphan/root commit in change"
  # -z: NUL-separated, never C-quoted, spaces intact. Record = ":om nm os ns ST\0path\0"
  : > "$P/.gatehome/paths"; nf=0; sym=; gl=
  while IFS= read -r -d '' meta && IFS= read -r -d '' path; do
    nf=$((nf+1)); printf '%s\n' "$path" >> "$P/.gatehome/paths"
    nm=$(echo "$meta" | cut -d' ' -f2)
    [ "$nm" = 120000 ] && sym="$sym $path"; [ "$nm" = 160000 ] && gl="$gl $path"
  done < <(hgit -C "$G" diff --raw -z --no-renames main "$I")
  grep -iE "$DOTGIT" "$P/.gatehome/paths" && fail "nested .git path in change"
  grep -ivxE 'setup/readme\.md|setup/testing\.md' "$P/.gatehome/paths" | grep -iE "$FORBID_PREFIX|$FORBID_NAME" && fail "forbidden path touched"
  [ -z "$sym" ] || fail "symlink in change:$sym"
  [ -z "$gl" ] || fail "submodule/gitlink in change:$gl"
  [ "$nf" -le "$MAX_FILES" ] || fail "$nf files changed > $MAX_FILES"
  badid=$(hgit -C "$G" log --format='%an <%ae>|%cn <%ce>' "main..$I" | grep -vxF "$AGENT_IDENT|$AGENT_IDENT" | head -1)
  [ -z "$badid" ] || fail "commit identity '$badid' is not the agent identity '$AGENT_IDENT'"
  lines=$(hgit -C "$G" diff --numstat main "$I" | awk '{a+=($1=="-"?0:$1)+($2=="-"?0:$2)}END{print a+0}'); [ "$lines" -le "$MAX_LINES" ] || fail "diff $lines lines > $MAX_LINES"
  TD=$(mktemp -d "$P/.gatehome/src.XXXXXX"); TE=$(mktemp -d "$P/.gatehome/entry.XXXXXX")
  hgit -C "$G" archive "$I" | tar -x --no-same-owner -C "$TD"
  hgit -C "$G" show "main:$TEST_ENTRY" > "$TE/entry.sh" || { rm -rf "$TD" "$TE"; fail "no $TEST_ENTRY on main"; }
  $DOCKER run "${HARDEN[@]}" -e HOME=/tmp -v "$TD:/src:ro" -v "$TE:/keel-entry:ro" -w /src "$IMG" sh /keel-entry/entry.sh || { rm -rf "$TD" "$TE"; fail "tests (main:$TEST_ENTRY)"; }
  rm -rf "$TD" "$TE"; echo "GATE PASS: $(hgit -C "$G" rev-parse "$I") files=$nf lines=$lines (objects held in $G)";;
push-stub) I=$(hgit -C "$G" rev-parse "refs/keel/incoming/$T") || exit 1
  echo "[stub] broker (token) would run: git -C $G -c core.hooksPath=/dev/null push origin $I:refs/heads/agent/$T ; open PR agent/$T -> main";;
repo-gc|repo-prune) tasks_active && { echo "REFUSED: tasks active ($(cd "$P/work" && echo *)); no gc/prune"; exit 3; }
  if [ "$1" = repo-gc ]; then git -C "$R" gc -q; else git -C "$R" prune; fi; echo "$1 done";;
set-main) new=$2; old=$(git -C "$R" rev-parse main)
  if tasks_active && ! git -C "$R" merge-base --is-ancestor "$old" "$new"; then echo "REFUSED: main $old -> $new is not fast-forward while tasks active"; exit 3; fi
  git -C "$R" update-ref refs/heads/main "$new" "$old" && echo "main -> $new";;
cleanup) rm -rf "$W" "$P/work/$T-env" "$S" "$G" "$B/$T.bundle" "$P/$T.base" "$P/$T.mode"; mkdir -p "$P/work"; echo "cleaned $T";;
*) sed -n 2,7p "$0"; exit 2;;
esac
