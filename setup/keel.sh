#!/usr/bin/env bash
# rudax-keel variant 2 prototype (tested on Linux; macOS Docker Desktop untested). bash 3.2+.
# Usage: keel.sh <cmd>
# cmds: init-repo | setup | reset-shadow | mode | proto <name> <rw|ro> <sh-cmd> | proto-env <sh-cmd> | role <name> [rw|ro] <sh-cmd> | role-env <name> <sh-cmd> | export | gate | push-stub
#       | repo-gc | repo-prune | set-main <sha> | cleanup
# env: KEEL_ROOT (default ~/keel-proto), TASK, DOCKER (docker | "sudo docker" | podman), IMG,
#      KEEL_POINTER_MODE (auto | pointer | env)
set -u
# Installed before the task is known. A later trap replaces it once the real
# body exists, and this one keeps an early exit from depending on unset names.
trap 'ec=$?; exit "$ec"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
HERE=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=setup/lib/portable.sh
. "$HERE/lib/portable.sh"
# shellcheck source=setup/lib/egress.sh
. "$HERE/lib/egress.sh"
P=${KEEL_ROOT:-$HOME/keel-proto}; T=${TASK:-task-1}
task_check=1  # task-name-check
keel_task_ok() {
  local name=$1
  (
    LC_ALL=C
    [[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]]
  )
}
if [ "$task_check" = 1 ] && ! keel_task_ok "$T"; then
  echo "REFUSED: task name" >&2
  exit 1
fi
sha_check=1  # commit-id-check
keel_sha_ok() {
  local sha=$1
  (
    LC_ALL=C
    [[ "$sha" =~ ^[0-9a-f]{40}$ ]]
  )
}
keel_require_sha() {
  if [ "$sha_check" != 1 ]; then
    return 0
  fi
  if keel_sha_ok "$1"; then
    return 0
  fi
  echo "REFUSED: commit id" >&2
  return 1
}
mkdir -p "$P"; P=$(abs_dir "$P")    # physical path: Docker Desktop shares /private/tmp, not /tmp
R=$P/repo; W=$P/work/$T; S=$P/shadow/$T.git; B=$P/bundles; G=$P/gate/$T.git
DOCKER=${DOCKER:-docker}; IMG=${IMG:-keel-git}
UIDGID="$(id -u):$(id -g)"
MAX_BUNDLE=${MAX_BUNDLE:-1048576}; MAX_LINES=${MAX_LINES:-5000}; MAX_FILES=${MAX_FILES:-500}
# matched case-insensitively (macOS/Windows checkouts fold case: .GitHub/ == .github/)
# Pi Agent process set (scripts/check-scope.py), plus .gitmodules.
# .pi/ and .agents/ match at any depth. setup/README.md and setup/TESTING.md
# are ordinary docs (whole path, any case).
FORBID_PREFIX='^(\.github|setup|scripts|\.keel)/|(^|/)\.pi/|(^|/)\.agents/'
FORBID_NAME='(^|/)(agents\.md|agents\.override\.md|claude\.md|codeowners|\.shellcheckrc|\.gitmodules)$'
DOTGIT='(^|/)\.git(/|$)'
TEST_ENTRY=${KEEL_TEST_ENTRY:-test.sh}   # test entrypoint, always taken from MAIN, never from the bundle
AGENT_IDENT=${KEEL_AGENT_IDENT:-agent <a@x>}
if ! path_is_shared "$P"; then
  echo "KEEL_ROOT $P is not under a Docker Desktop shared dir (/Users, /Volumes, /private, /tmp, /var/folders)." >&2
  echo "Use a path under \$HOME, or add it in Docker Desktop > Settings > Resources > File sharing." >&2; exit 4; fi
# container hardening applied to EVERY container (agent, setup, export, test)
# --memory-swap equals --memory so the cgroup cannot add swap on top of the limit.
# Some cgroup v2 hosts still report memory.swap.max as "max" when swap accounting
# is missing. That file alone is not proof the limit held.
# shellcheck disable=SC2054  # commas belong to the --tmpfs option value, not array separators
HARDEN=(--rm --network none --user "$UIDGID" --cap-drop ALL --security-opt no-new-privileges
  --read-only --tmpfs /tmp:rw,size=64m --pids-limit "${PIDS:-128}" --memory "${MEM:-512m}" --memory-swap "${MEM:-512m}" --cpus "${CPUS:-1}")
case "$DOCKER" in *podman*) HARDEN+=(--userns=keep-id);; esac
# Only these names are passed into a container. Host secret names are not copied.
GITENV=(-e HOME=/tmp -e "GIT_CONFIG_PARAMETERS='core.hooksPath'='/dev/null' 'core.fsmonitor'='false'"
  -e GIT_AUTHOR_NAME=agent -e GIT_AUTHOR_EMAIL=a@x -e GIT_COMMITTER_NAME=agent -e GIT_COMMITTER_EMAIL=a@x)
hgit(){ env -i PATH=/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin HOME="$P/.gatehome" GIT_CONFIG_NOSYSTEM=1 git -c core.hooksPath=/dev/null -c core.fsmonitor=false -c core.pager=cat -c protocol.allow=never -c protocol.file.allow=always "$@"; }
# Start the container CLI with an explicit environment. A listed or matching
# name is dropped even when it is also on this list. The runtime's own
# configuration is outside this launch.
docker_cli() {
  local allow name names="" kept
  allow="PATH HOME USER LOGNAME LANG LC_ALL TMPDIR XDG_RUNTIME_DIR XDG_CONFIG_HOME DBUS_SESSION_BUS_ADDRESS DOCKER_HOST DOCKER_CONTEXT DOCKER_CONFIG DOCKER_CERT_PATH DOCKER_TLS_VERIFY CONTAINER_HOST CONTAINER_CONNECTION CONTAINERS_CONF CONTAINERS_STORAGE_CONF CONTAINERS_REGISTRIES_CONF"
  # The list is a fixed set of names. Splitting it is the point.
  # shellcheck disable=SC2086
  for name in $allow; do
    if [ -n "${!name+x}" ]; then
      names="$names $name"
    fi
  done
  # shellcheck disable=SC2086
  kept=$(python3 "$HERE/lib/secret_names.py" keep-names $names)
  _cli_env_run "$kept" "$@"
}
_cli_env_run() {
  local kept=$1
  shift
  local name
  local -a acc
  acc=()
  # Names come back separated by spaces. None of them contain whitespace.
  # shellcheck disable=SC2086
  for name in $kept; do
    acc+=("$name=${!name}")
  done
  if [ -n "$keel_arm_file" ] && keel_arm_ok "$keel_arm_file"; then
    local gate pid rc=0
    mkdir -p -- "$P/containers/$T" || return 91
    gate=$(mktemp "$P/containers/$T/.gate.XXXXXX") || return 91
    rm -f -- "$gate"
    mkfifo "$gate" || return 91
    # Holding the fifo open lets the child read it without losing the caller's stdin.
    exec 7<>"$gate" || return 91
    _keel_held_exec "$gate" "$@" <&0 &
    pid=$!
    keel_tool note "$keel_arm_file" "$pid" || true
    printf '\n' >&7 || true
    exec 7>&-
    wait "$pid" || rc=$?
    rm -f -- "$gate"
    return "$rc"
  fi
  _keel_exec_env "$@"
}
_keel_exec_env() {
  if [ "${#acc[@]}" -eq 0 ]; then
    env -i "$@"
    return $?
  fi
  env -i "${acc[@]}" "$@"  # cli-env-reset
}
_keel_held_exec() {
  local gate=$1
  shift
  IFS= read -r _ < "$gate" || true
  exec 7>&- 2>/dev/null || true
  _keel_exec_env "$@"
}
# shellcheck disable=SC2119
launch_guard(){ keel_require_runtime || exit $?; } # launch-guard
crun(){
  launch_guard
  local a harden=()
  if [ -n "${KEEL_CIDFILE:-}" ]; then
    for a in "${HARDEN[@]}"; do
      [ "$a" = "--rm" ] && continue
      harden+=("$a")
    done
    harden+=(--cidfile "$KEEL_CIDFILE")
  else
    harden=("${HARDEN[@]}")
  fi
  if [ -n "$keel_arm_name" ]; then
    harden+=(--name "$keel_arm_name" --label "$keel_arm_label")
  fi
  # shellcheck disable=SC2086  # a two-word container command is a supported form, so this stays split
  docker_cli $DOCKER run "${harden[@]}" "${GITENV[@]}" "$@"
}
KEEL_CMD=${1:-}
KEEL_ROLE_NAME=${KEEL_ROLE_NAME:-}
keel_arm_file=
keel_arm_name=
keel_arm_label=
keel_name_seq=0
KEEL_ENV_TREE=
quarantine_nested=1  # nested-git-on
quarantine_fail=1  # quarantine-fail-closed
leftover_check=1  # leftover-container-check
keel_tool() {
  python3 - "$P" "$T" "$@" << 'PY'
import ctypes, errno, hashlib, os, stat, sys, tempfile

root_p, task = sys.argv[1], sys.argv[2]
cmd = sys.argv[3]
rest = sys.argv[4:]
LABEL_KEY = "keel.identity"
AT_SYMLINK_NOFOLLOW = 0x100
libc = ctypes.CDLL(None, use_errno=True)

def fail(reason):
    sys.stderr.write(reason + "\n")
    raise SystemExit(2)

def state_tag():
    return hashlib.sha256(root_p.encode("utf-8")).hexdigest()[:12]

def label_value():
    return "s%st%s" % (state_tag(), task)

def containers_dir():
    return os.path.join(root_p, "containers", task)

def atomic_write(path, text):
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".part.", dir=folder)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)

def parse_record(path):
    try:
        raw = open(path, "r", encoding="utf-8").read()
    except OSError:
        return None
    if raw == "" or raw[-1] != "\n" or "\n\n" in raw:
        return None
    allowed = {"v", "name", "label", "pid", "start", "cid", "probe"}
    found = {}
    for line in raw.splitlines():
        if "=" not in line:
            return None
        key, val = line.split("=", 1)
        if key not in allowed or key in found:
            return None
        found[key] = val
    for key in ("v", "name", "label", "pid", "start", "cid"):
        if key not in found:
            return None
    if found["v"] != "1":
        return None
    name = found["name"]
    if not name.startswith("keelc-") or "/" in name or "\n" in name:
        return None
    expect = "%s=%s" % (LABEL_KEY, label_value())
    if found["label"] != expect:
        return None
    for key in ("pid", "start"):
        if found[key] != "" and not found[key].isdigit():
            return None
    cid = found["cid"]
    if cid != "" and (len(cid) != 64 or any(c not in "0123456789abcdef" for c in cid)):
        return None
    if (found["pid"] == "") != (found["start"] == ""):
        return None
    probe = found.get("probe", "")
    if probe not in ("", "unreadable"):
        return None
    found["path"] = path
    return found

def record_text(fields):
    lines = [
        "v=1",
        "name=%s" % fields["name"],
        "label=%s" % fields["label"],
        "pid=%s" % fields.get("pid", ""),
        "start=%s" % fields.get("start", ""),
        "cid=%s" % fields.get("cid", ""),
    ]
    if fields.get("probe"):
        lines.append("probe=%s" % fields["probe"])
    return "\n".join(lines) + "\n"

def proc_state(pid, recorded, unreadable):
    if unreadable:
        return "alive"
    path = "/proc/%s/stat" % pid
    marker = None
    try:
        data = open(path, "rb").read()
    except FileNotFoundError:
        return "gone"
    except PermissionError:
        return "alive"
    except OSError:
        return "unknown"
    end = data.rfind(b")")
    if end < 0:
        return "unknown"
    fields = data[end + 2:].split()
    if len(fields) < 20:
        return "unknown"
    try:
        marker = fields[19].decode("ascii")
    except UnicodeError:
        return "unknown"
    if marker != recorded:
        return "gone"
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return "gone"
    except PermissionError:
        return "alive"
    except OSError:
        return "unknown"
    return "alive"

def chmod_at(dirfd, name, mode):
    rc = libc.fchmodat(ctypes.c_int(dirfd), os.fsencode(name), ctypes.c_uint(mode & 0o7777), ctypes.c_int(AT_SYMLINK_NOFOLLOW))
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), name)

def recheck(tree, path):
    tree = os.path.abspath(tree)
    if os.path.islink(tree):
        return False
    path = os.path.abspath(path)
    try:
        if os.path.commonpath([tree, path]) != tree:
            return False
    except ValueError:
        return False
    rel = os.path.relpath(path, tree)
    cur = tree
    if rel == ".":
        return not os.path.islink(tree)
    for part in rel.split(os.sep):
        if part in ("", ".", ".."):
            return False
        cur = os.path.join(cur, part)
        if not os.path.lexists(cur) or os.path.islink(cur):
            return False
    return True

def move_tree(tree, dest, uid, pointer):
    found = []

    def restore(dirfd, path):
        if not recheck(tree, path):
            fail("recheck")
        try:
            names = os.listdir(dirfd)
        except OSError:
            fail("scan")
        for name in names:
            if name in (".", ".."):
                continue
            child = os.path.join(path, name)
            try:
                st = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
            except OSError:
                fail("scan")
            if stat.S_ISLNK(st.st_mode):
                continue
            if not recheck(tree, child):
                fail("recheck")
            if st.st_uid != uid:
                fail("foreign-owner")
            if name.lower() == ".git":
                try:
                    chmod_at(dirfd, name, st.st_mode | (0o700 if stat.S_ISDIR(st.st_mode) else 0o600))
                except OSError:
                    fail("perm-restore")
                found.append(child)
                continue
            if stat.S_ISDIR(st.st_mode):
                try:
                    chmod_at(dirfd, name, st.st_mode | 0o700)
                except OSError:
                    fail("perm-restore")
                if not recheck(tree, child):
                    fail("recheck")
                try:
                    cfd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dirfd)
                except OSError:
                    fail("recheck")
                try:
                    restore(cfd, child)
                finally:
                    os.close(cfd)
            else:
                try:
                    chmod_at(dirfd, name, st.st_mode | 0o600)
                except OSError:
                    fail("perm-restore")

    if os.path.islink(tree) or not os.path.isdir(tree):
        fail("scan")
    parent = os.path.dirname(tree)
    base = os.path.basename(tree)
    if not recheck(tree, tree):
        fail("recheck")
    try:
        st = os.lstat(tree)
    except OSError:
        fail("scan")
    if st.st_uid != uid:
        fail("foreign-owner")
    try:
        pfd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        fail("perm-restore")
    try:
        chmod_at(pfd, base, st.st_mode | 0o700)
    except OSError:
        fail("perm-restore")
    finally:
        os.close(pfd)
    try:
        rfd = os.open(tree, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        fail("recheck")
    try:
        restore(rfd, tree)
    finally:
        os.close(rfd)
    pointer_b = pointer.encode("utf-8")
    for path in found:
        rel = os.path.relpath(path, tree)
        if os.sep not in rel and pointer_b:
            try:
                st = os.lstat(path)
                data = open(path, "rb").read() if stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode) else b""
            except OSError:
                data = b""
            if data == pointer_b:
                continue
        if not recheck(tree, path):
            fail("recheck")
        target = os.path.join(dest, rel)
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
        except OSError:
            fail("dest")
        if not recheck(tree, path):
            fail("recheck")
        try:
            os.rename(path, target)
        except OSError:
            fail("move")
        sys.stdout.buffer.write(os.fsencode(rel) + b"\0")

if cmd == "tag":
    sys.stdout.write(state_tag())
elif cmd == "write":
    name, label = rest[0], rest[1]
    path = os.path.join(containers_dir(), name + ".rec")
    atomic_write(path, record_text({"name": name, "label": label, "pid": "", "start": "", "cid": ""}))
    sys.stdout.write(path)
elif cmd == "note":
    path, pid = rest[0], rest[1]
    fields = parse_record(path)
    if fields is None or not pid.isdigit():
        raise SystemExit(2)
    state = proc_state(pid, "", False)
    # Read the marker even when the comparison value is empty.
    stat_path = "/proc/%s/stat" % pid
    try:
        data = open(stat_path, "rb").read()
        end = data.rfind(b")")
        marker = data[end + 2:].split()[19].decode("ascii")
    except (OSError, IndexError, UnicodeError):
        raise SystemExit(2)
    fields["pid"] = pid
    fields["start"] = marker
    atomic_write(path, record_text(fields))
elif cmd == "paths":
    folder = containers_dir()
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.endswith(".rec"):
                sys.stdout.buffer.write(os.fsencode(os.path.join(folder, name)) + b"\0")
elif cmd == "show":
    fields = parse_record(rest[0])
    if fields is None:
        raise SystemExit(2)
    sys.stdout.write("\n".join([fields["name"], fields["label"], fields["pid"], fields["start"], fields["cid"], fields.get("probe", "")]) + "\n")
elif cmd == "clear":
    path = rest[0]
    if parse_record(path) is None:
        raise SystemExit(2)
    os.remove(path)
elif cmd == "proc":
    fields = parse_record(rest[0])
    if fields is None or fields["pid"] == "":
        sys.stdout.write("unknown\n")
    else:
        fixture = os.environ.get("KEEL_REDACT_FIXTURE") == "1"
        unreadable = fixture and fields.get("probe") == "unreadable"
        sys.stdout.write(proc_state(fields["pid"], fields["start"], unreadable) + "\n")
elif cmd == "move":
    move_tree(rest[0], rest[1], int(rest[2]), rest[3] if len(rest) > 3 else "")
else:
    raise SystemExit(2)
PY
}
keel_arm_ok() {
  local file=$1 base
  [ -f "$file" ] || return 1
  case "$file" in
    "$P/containers/$T/"*.rec) ;;
    *) return 1 ;;
  esac
  base=$(basename -- "$file" .rec)
  case "$base" in
    keelc-*) [ "$base" = "$keel_arm_name" ] || return 1 ;;
    *) return 1 ;;
  esac
}
keel_rt() {
  local -a bin
  # Split on spaces so a two-word container command stays two words.
  IFS=' ' read -r -a bin <<< "$DOCKER"
  [ "${#bin[@]}" -gt 0 ] || return 127
  LC_ALL=C "${bin[@]}" "$@"
}
keel_runtime_up() {
  keel_rt info >/dev/null 2>&1
}
keel_not_found_text() {
  # Container-scoped inspect only. A generic missing-object reply is not this.
  # Docker's container reply contains "No such container".
  # Podman's container reply contains "no such container".
  grep -q -e 'No such container' -e 'no such container' "$1"
}
keel_label_value() {
  printf 's%st%s' "$(keel_tool tag)" "$T"
}
keel_track_begin() {
  local tag name label path
  tag=$(keel_tool tag) || return 91
  keel_name_seq=$((keel_name_seq + 1))
  name=$(printf 'keelc-%s-%s-%s-%s' "$tag" "$T" "$$" "$(python3 -c 'import os; print(os.urandom(4).hex())')") || return 91
  label="keel.identity=$(keel_label_value)" || return 91
  path=$(keel_tool write "$name" "$label") || return 91
  keel_arm_name=$name
  keel_arm_label=$label
  keel_arm_file=$path
}
keel_show() {
  local file=$1
  keel_tool show "$file"
}
keel_proc_state() {
  local file=$1
  keel_tool proc "$file"
}
keel_label_ids() {
  local value=$1
  [ -n "$value" ] || return 1
  keel_rt ps -a --no-trunc --filter "label=keel.identity=${value}" --format '{{.ID}}'
}
keel_classify_file() {
  local file=$1 line name label pid cid err out id got status running hits
  line=$(keel_show "$file") || { printf '%s\n' unknown; return 0; }
  name=$(printf '%s\n' "$line" | sed -n '1p')
  label=$(printf '%s\n' "$line" | sed -n '2p')
  pid=$(printf '%s\n' "$line" | sed -n '3p')
  cid=$(printf '%s\n' "$line" | sed -n '5p')
  case "$name" in
    keelc-*) ;;
    *) printf '%s\n' unknown; return 0 ;;
  esac
  case "$label" in
    "keel.identity=$(keel_label_value)") ;;
    *) printf '%s\n' unknown; return 0 ;;
  esac
  if ! keel_runtime_up; then
    printf '%s\n' unknown
    return 0
  fi
  local proc=unknown
  if [ -z "$pid" ]; then
    proc=unknown
  else
    proc=$(keel_proc_state "$file" | head -n 1)
  fi
  err=$(mktemp "$P/containers/$T/.err.XXXXXX") || { printf '%s\n' unknown; return 0; }
  out=$(keel_rt container inspect --format '{{.Id}} {{.Name}} {{.State.Status}} {{.State.Running}}' -- "$name" 2>"$err") || true
  if ! keel_runtime_up; then
    rm -f -- "$err"
    printf '%s\n' unknown
    return 0
  fi
  if [ ! -s "$err" ] && [ -n "$out" ]; then
    id=$(printf '%s\n' "$out" | awk '{print $1}')
    got=$(printf '%s\n' "$out" | awk '{print $2}')
    status=$(printf '%s\n' "$out" | awk '{print $3}')
    running=$(printf '%s\n' "$out" | awk '{print $4}')
    rm -f -- "$err"
    if [ "$got" != "/$name" ] && [ "$got" != "$name" ]; then
      printf '%s\n' unknown
      return 0
    fi
    if [ "${#id}" -ne 64 ] || printf '%s' "$id" | grep -q '[^0-9a-f]'; then
      printf '%s\n' unknown
      return 0
    fi
    if [ -n "$cid" ] && [ "$cid" != "$id" ]; then
      printf '%s\n' unknown
      return 0
    fi
    if [ "$running" = true ] || [ "$status" = running ] || [ "$status" = restarting ] || [ "$status" = paused ]; then
      printf '%s\n' running
      return 0
    fi
    if [ "$status" = exited ] || [ "$status" = dead ]; then
      printf '%s\n' stopped
      return 0
    fi
    printf '%s\n' unknown
    return 0
  fi
  if keel_not_found_text "$err"; then
    rm -f -- "$err"
    hits=$(keel_label_ids "$(keel_label_value)" 2>/dev/null || true)
    if [ -n "$hits" ]; then
      printf '%s\n' unknown
      return 0
    fi
    if [ "$proc" = gone ]; then
      printf '%s\n' stopped
      return 0
    fi
    if [ "$proc" = alive ]; then
      printf '%s\n' running
      return 0
    fi
    printf '%s\n' unknown
    return 0
  fi
  rm -f -- "$err"
  printf '%s\n' unknown
}
keel_stop_name() {
  local name=$1
  case "$name" in
    keelc-*) ;;
    *) return 1 ;;
  esac
  keel_rt stop -t 2 -- "$name" >/dev/null 2>&1 || true
  keel_rt kill -- "$name" >/dev/null 2>&1 || true
}
keel_settle_one() {
  local file=$1 name state
  if [ "$leftover_check" != 1 ]; then
    return 0
  fi
  name=$(keel_show "$file" | sed -n '1p') || return 91
  state=$(keel_classify_file "$file")
  if [ "$state" = stopped ]; then
    keel_tool clear "$file" || return 91
    printf '%s\n' "container state stopped" >&2
    return 0
  fi
  if [ "$state" = running ]; then
    printf '%s\n' "container state running" >&2
    keel_stop_name "$name" || true
    state=$(keel_classify_file "$file")
    if [ "$state" = stopped ]; then
      keel_tool clear "$file" || return 91
      printf '%s\n' "container state stopped" >&2
      return 0
    fi
  fi
  printf '%s\n' "REFUSED: container state is not confirmed" >&2
  keel_tool_log container-unknown - || printf '%s\n' "quarantine record could not be written" >&2
  return 91
}
keel_tool_log() {
  local reason=$1 path=$2
  python3 "$HERE/lib/visibility.py" quarantine-fail \
    --role "${KEEL_ROLE_NAME:-}" --work "${W:-}" --harness "$HERE" \
    --keel "$P" --task "$T" --repo "${R:-}" --file "$path" --code "$reason"
}
keel_guard_trees() {
  local file
  if [ "$leftover_check" != 1 ]; then
    return 0
  fi
  mkdir -p -- "$P/containers/$T" || return 91
  keel_tool paths >"$P/containers/$T/.paths" || return 91
  while IFS= read -r -d '' file; do
    [ -n "$file" ] || continue
    keel_settle_one "$file" || return $?
  done <"$P/containers/$T/.paths"
  rm -f -- "$P/containers/$T/.paths"
}
keel_track_end() {
  local file=$keel_arm_file
  keel_arm_file=
  keel_arm_name=
  keel_arm_label=
  if [ -z "$file" ]; then
    return 0
  fi
  keel_settle_one "$file"
}
keel_finish_track() {
  local rc=$1 end=0
  keel_track_end || end=$?
  if [ "$rc" -eq 0 ] && [ "$end" -ne 0 ]; then
    return "$end"
  fi
  return "$rc"
}
keel_print_state() {
  local file state worst=none hits
  if ! keel_runtime_up; then
    printf '%s\n' unknown
    return 91
  fi
  while IFS= read -r -d '' file; do
    [ -n "$file" ] || continue
    state=$(keel_classify_file "$file")
    case "$state" in
      running) worst=running ;;
      unknown) [ "$worst" = running ] || worst=unknown ;;
      stopped) [ "$worst" = none ] && worst=stopped ;;
    esac
  done < <(keel_tool paths || true)
  hits=$(keel_label_ids "$(keel_label_value)" 2>/dev/null || true)
  if [ -n "$hits" ] && [ "$worst" = none ]; then
    worst=running
  fi
  printf '%s\n' "$worst"
  [ "$worst" != unknown ]
}
keel_quar_fail() {
  local reason=$1 path=$2
  if [ "$quarantine_fail" != 1 ]; then
    return 0
  fi
  if ! keel_tool_log "$reason" "$path"; then
    printf '%s\n' "quarantine record could not be written" >&2
  else
    printf '%s\n' "quarantine failed: $reason" >&2
  fi
  return 90
}
keel_quarantine_one() {
  local tree=$1 pointer=$2 dest rel qrc=0
  [ -d "$tree" ] || return 0
  mkdir -p -- "$P/containers/$T" || { keel_quar_fail temp-file -; return $?; }
  dest=$P/quarantine/$T/$$
  qrc=0
  keel_tool move "$tree" "$dest" "$(id -u)" "$pointer" >"$P/containers/$T/.moved" 2>"$P/containers/$T/.why" || qrc=$?
  if [ "$qrc" -ne 0 ]; then
    rel=$(head -n 1 "$P/containers/$T/.why" 2>/dev/null || printf '%s' scan)
    [ -n "$rel" ] || rel=scan
    keel_quar_fail "$rel" -
    return $?
  fi
  while IFS= read -r -d '' rel; do
    [ -n "$rel" ] || continue
    if ! record_nested_git "$rel"; then
      keel_quar_fail record "$rel"
      return $?
    fi
  done <"$P/containers/$T/.moved"
  rm -f -- "$P/containers/$T/.moved" "$P/containers/$T/.why"
}
record_nested_git() {
  python3 "$HERE/lib/visibility.py" nested-git --role "$KEEL_ROLE_NAME" --work "$W" --harness "$HERE" --keel "$P" --task "$T" --repo "$R" --file "$1"  # nested-git-record
}
quarantine_git_tree() {
  local cmd pointer qrc=0
  [ "${quarantine_nested:-0}" = 1 ] || return 0
  cmd=${KEEL_CMD:-}
  case "$cmd" in
    role|role-env|proto|proto-env) ;;
    *) return 0 ;;
  esac
  if ! keel_guard_trees; then
    keel_quar_fail stop-unconfirmed -
    return $?
  fi
  if [ "$cmd" = proto-env ] && [ -n "${KEEL_ENV_TREE:-}" ]; then
    keel_quarantine_one "$KEEL_ENV_TREE" "" || qrc=$?
    if [ "$qrc" -ne 0 ]; then
      return "$qrc"
    fi
  fi
  if [ -d "${W:-}" ]; then
    pointer=
    if [ "$(cat "$P/$T.mode" 2>/dev/null || printf '%s' pointer)" = pointer ]; then
      pointer=$(printf 'gitdir: /shadow/%s.git\n' "$T")
    fi
    keel_quarantine_one "$W" "$pointer" || return $?
  fi
}
keel_on_exit() {
  local ec=$?
  local q=0
  local root=${P:-}
  local task=${T:-}
  local cmd=${KEEL_CMD:-}
  local work=${W:-}
  if [ -n "$root" ] && [ -n "$task" ]; then
    quarantine_git_tree || q=$?
    rm -rf "$root/.keel/runs"
    if [ "$cmd" = cleanup ] || { [ "$cmd" = setup ] && [ "$ec" -ne 0 ]; }; then
      rm -rf "$root/$task.deny" "$work/.keel/runs"
    fi
  fi
  if [ "$q" -ne 0 ] && [ "$ec" -eq 0 ]; then
    ec=$q
  fi
  exit "$ec"
}
trap keel_on_exit EXIT

role_mounts() {
  local role=$1 mf rc=0 kind src dst how
  mkdir -p "$P/.keel/runs"
  mf=$P/.keel/runs/mounts.$$
  python3 "$HERE/lib/visibility.py" mounts --role "$role" --work "$W" --harness "$HERE" --keel "$P" --task "$T" --repo "$R" >"$mf" || rc=$?
  if [ "$rc" -ne 0 ]; then
    cat "$mf"
    rm -f "$mf"
    return "$rc"
  fi
  MNT=()
  bad=0
  while IFS=$'\t' read -r kind src dst how; do
    [ -n "${kind:-}" ] || continue
    if [ "$kind" != MOUNT ]; then
      echo "REFUSED: bad mount record" >&2
      bad=1
      break
    fi
    MNT+=(-v "$src:$dst:$how")
  done <"$mf"
  rm -f "$mf"
  [ "$bad" -eq 0 ] || return 1
  return 0
}
start_role() {
  local name=$1
  shift
  reset_shadow
  run_policy "$name" "$@"
}
run_policy() {
  local name=$1 rc=0
  shift
  role_mounts "$name" || return $?
  echo "== role $name (policy)"
  # Whole-tree fallback is not used.
  :
  if [ "${#MNT[@]}" -eq 0 ]; then
    crun_for "$name" -w /tmp "$IMG" sh -c "$*" || rc=$?
  else
    crun_for "$name" "${MNT[@]}" -w /work "$IMG" sh -c "$*" || rc=$?
  fi
  keel_finish_track "$rc"
}
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
# shellcheck source=setup/lib/runtime.sh
. "$HERE/lib/runtime.sh"
need_docker(){ $DOCKER info >/dev/null 2>&1 || { docker_hint >&2; exit 5; }; keel_disk_ok "$P" || { printf 'REFUSE\truntime\tdisk\t0\n' >&2; exit 1; }; }
case "$KEEL_CMD" in
  setup|reset-shadow|proto|proto-env|role|role-env|export|gate|cleanup)
    keel_guard_trees || exit $?
    ;;
esac
case "${1:-}" in
egress-up) launch_guard; need_docker; egress_proxy_up;;
init-repo) mkdir -p "$R" "$P/.gatehome"; cd "$R" || exit 1; git init -q; git symbolic-ref HEAD refs/heads/main
  git config gc.auto 0; git config maintenance.auto false; git config gc.pruneExpire never; git config gc.reflogExpireUnreachable never
  printf '#!/bin/sh\nset -e\ngrep -q hello app.txt && echo TESTS-OK\n' > test.sh; echo hello > app.txt; mkdir -p .github; echo ci > .github/ci.yml; echo rules > AGENTS.md
  # Every default allow root, so each role can launch on this throwaway repo.
  sed -e 's/[[:space:]]*#.*//' -e '/^[[:space:]]*$/d' "$HERE"/allow/*.paths | while IFS= read -r rel; do
    rel=$(printf '%s' "$rel" | awk '{print $1}')
    [ -n "$rel" ] || continue
    if [ "$rel" = ".keel/decisions" ]; then rel=".keel/decisions/$T"; fi
    mkdir -p -- "$rel"
    : > "$rel/.keep"
  done
  mkdir -p .keel/memory
  : > .keel/memory/.keep
  git add -A; git -c user.name=h -c user.email=h@x commit -qm init; echo "repo main=$(git rev-parse main) gc.auto=$(git config gc.auto) gc.pruneExpire=$(git config gc.pruneExpire)";;
setup) launch_guard; M=$(hgit -C "$R" rev-parse main 2>/dev/null) || M=; keel_require_sha "$M" || exit 1  # setup-main-hgit
  need_docker; mkdir -p "$W" "$B" "$(dirname "$S")"
  hgit init -q --bare "$S"; reset_shadow; echo "$M" > "$P/$T.base"
  printf 'gitdir: /shadow/%s.git\n' "$T" > "$W/.git"
  want=${KEEL_POINTER_MODE:-auto}; md='env'
  if [ "$want" != env ]; then
    keel_track_begin || exit $?
    if err=$(crun -v "$W:/work" -v "$W/.git:/work/.git:ro" "$IMG" true 2>&1); then md=pointer
    elif [ "$want" = pointer ]; then echo "single-file ro bind rejected: $err" >&2; keel_track_end || exit $?; exit 6
    else echo "WARN: single-file ro bind rejected by Docker ($(echo "$err" | tail -1)); falling back to GIT_DIR/GIT_WORK_TREE" >&2; fi
    keel_track_end || exit $?
  fi
  [ $md = env ] && rm -f "$W/.git"      # env mode: no pointer file at all
  echo $md > "$P/$T.mode"; work_mounts rw
  keel_track_begin || exit $?
  # shellcheck disable=SC2016  # single quotes keep the setup script literal; the task and base are arguments inside the container
  crun -v "$R/.git/objects:/base/objects:ro" "${MNT[@]}" -w /work "$IMG" sh -c \
   'git update-ref refs/heads/"$1" "$2" && git symbolic-ref HEAD refs/heads/"$1" && git checkout -q -f "$1" && git log --oneline -1' \
   _ "$T" "$M" \
   || { keel_track_end || exit $?; echo "setup container failed. If this is Docker Desktop, check that $P is in Settings > Resources > File sharing." >&2; exit 7; }
  keel_track_end || exit $?
  echo "mode=$md";;
mode) mode;;
reset-shadow) reset_shadow; echo "shadow reset";;
proto) launch_guard; shift; name=$1 m=$2; shift 2; KEEL_ROLE_NAME=$name; reset_shadow
  echo "== role $name ($m) [shadow reset, mode=$(mode)]"; work_mounts "$m"
  use_none=1  # proto-network-none
  keel_track_begin || exit $?
  proto_rc=0
  if [ "$use_none" = 1 ]; then
    crun -v "$R/.git/objects:/base/objects:ro" "${MNT[@]}" -w /work "$IMG" sh -c "$*" || proto_rc=$?
  else
    skip=0
    args=()
    for a in "${HARDEN[@]}"; do
      if [ "$skip" = 1 ]; then skip=0; continue; fi
      if [ "$a" = "--network" ]; then skip=1; continue; fi
      args+=("$a")
    done
    if [ -n "$keel_arm_name" ]; then
      args+=(--name "$keel_arm_name" --label "$keel_arm_label")
    fi
    launch_guard
    # shellcheck disable=SC2086  # a two-word container command is a supported form, so this stays split
    docker_cli $DOCKER run "${args[@]}" "${GITENV[@]}" -v "$R/.git/objects:/base/objects:ro" "${MNT[@]}" -w /work "$IMG" sh -c "$*" || proto_rc=$?
  fi
  keel_finish_track "$proto_rc" || exit $?;;
proto-env) launch_guard; shift; KEEL_ROLE_NAME=proto-env; WE=$P/work/$T-env; mkdir -p "$WE"; KEEL_ENV_TREE=$WE; reset_shadow
  keel_track_begin || exit $?
  proto_env_rc=0
  crun -e "GIT_DIR=/shadow/$T.git" -e GIT_WORK_TREE=/work -v "$R/.git/objects:/base/objects:ro" -v "$WE:/work" -v "$S:/shadow/$T.git" -w /work "$IMG" sh -c "$*" || proto_env_rc=$?
  keel_finish_track "$proto_env_rc" || exit $?;;
role) launch_guard; shift; name=$1; shift
  KEEL_ROLE_NAME=$name
  if [ "${1:-}" = rw ] || [ "${1:-}" = ro ]; then shift; fi
  start_role "$name" "$@" || exit $?;;
role-env) launch_guard; shift
  if [ "$#" -lt 2 ]; then
    python3 "$HERE/lib/visibility.py" refuse --code role_env_args --role "" --work "$W" --harness "$HERE" --keel "$P" --task "$T" --repo "$R" --file role-env --line 0
    exit 1
  fi
  name=$1; shift
  KEEL_ROLE_NAME=$name
  start_role "$name" "$@" || exit $?;;
export) launch_guard; M=$(cat "$P/$T.base" 2>/dev/null || true); keel_require_sha "$M" || exit 1; rm -f "$B/$T.bundle"; reset_shadow
  crun -v "$R/.git/objects:/base/objects:ro" -v "$S:/shadow/$T.git:ro" -v "$B:/bundles" "$IMG" \
    git --git-dir="/shadow/$T.git" bundle create "/bundles/$T.bundle" "refs/heads/$T" "^$M";;
gate) launch_guard; F=$B/$T.bundle; M=$(hgit -C "$R" rev-parse main 2>/dev/null) || M=; keel_require_sha "$M" || exit 1; I=refs/keel/incoming/$T
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
  # Fetch checks the pack. A commit already in the base is not in the pack,
  # so it is not checked there. Fsck the received tip, which walks that history.
  hgit -C "$G" fsck --no-dangling "$I" >/dev/null || fail "fetch/fsck"
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
  # Scan the files this change adds or edits. Not the repository history.
  secret_scan=1  # secret-scan
  if [ "$secret_scan" = 1 ]; then
    gl=${KEEL_GITLEAKS:-$HOME/.cache/keel/gitleaks-8.30.1/gitleaks}
    [ -x "$gl" ] || fail "secret scan: gitleaks missing"
    scan=$P/.gatehome/secret-scan
    rm -rf "$scan"
    mkdir -p "$scan"
    while IFS= read -r -d '' path; do
      [ -n "$path" ] || continue
      case $path in
        /*|*../*) fail "secret scan: bad path";;
      esac
      # Product ignore and config files are not part of the scan tree.
      case $(basename -- "$path") in
        .gitleaks.toml|.gitleaksignore) continue;;  # harness-owned-ignore
      esac
      mkdir -p "$scan/$(dirname -- "$path")"
      hgit -C "$G" show "$I:$path" > "$scan/$path" || fail "secret scan: unreadable path"
    done < <(hgit -C "$G" diff -z --name-only --diff-filter=ACMRT main "$I")
    sec_ec=0
    (
      cd "$scan" || exit 2
      env -u GITLEAKS_CONFIG -u GITLEAKS_CONFIG_TOML \
        "$gl" dir --no-banner --redact --timeout 30 --ignore-gitleaks-allow \
        -i "$HERE/gitleaks.ignore" --config "$HERE/gitleaks.toml" . >/dev/null 2>&1
    ) || sec_ec=$?
    rm -rf "$scan"
    if [ "$sec_ec" -eq 1 ]; then
      fail "secret in change"
    elif [ "$sec_ec" -ne 0 ]; then
      fail "secret scan failed"
    fi
  fi
  TD=$(mktemp -d "$P/.gatehome/src.XXXXXX"); TE=$(mktemp -d "$P/.gatehome/entry.XXXXXX")
  hgit -C "$G" archive "$I" | tar -x --no-same-owner -C "$TD"
  hgit -C "$G" show "main:$TEST_ENTRY" > "$TE/entry.sh" || { rm -rf "$TD" "$TE"; fail "no $TEST_ENTRY on main"; }
  launch_guard
  # shellcheck disable=SC2086  # a two-word container command is a supported form, so this stays split
  docker_cli $DOCKER run "${HARDEN[@]}" -e HOME=/tmp -v "$TD:/src:ro" -v "$TE:/keel-entry:ro" -w /src "$IMG" sh /keel-entry/entry.sh || { rm -rf "$TD" "$TE"; fail "tests (main:$TEST_ENTRY)"; }
  rm -rf "$TD" "$TE"; echo "GATE PASS: $(hgit -C "$G" rev-parse "$I") files=$nf lines=$lines (objects held in $G)";;
push-stub) I=$(hgit -C "$G" rev-parse "refs/keel/incoming/$T") || exit 1
  echo "[stub] broker (token) would run: git -C $G -c core.hooksPath=/dev/null push origin $I:refs/heads/agent/$T ; open PR agent/$T -> main";;
repo-gc|repo-prune) tasks_active && { echo "REFUSED: tasks active ($(cd "$P/work" && echo *)); no gc/prune"; exit 3; }
  if [ "$1" = repo-gc ]; then hgit -C "$R" gc -q; else hgit -C "$R" prune; fi  # repo-gc-hgit
  echo "$1 done";;
set-main) new=${2:-}; keel_require_sha "$new" || exit 1; old=$(hgit -C "$R" rev-parse main)
  if tasks_active && ! hgit -C "$R" merge-base --is-ancestor "$old" "$new"; then echo "REFUSED: main $old -> $new is not fast-forward while tasks active"; exit 3; fi
  hgit -C "$R" update-ref refs/heads/main "$new" "$old" && echo "main -> $new"  # set-main-hgit
  ;;
cleanup) rm -rf "$P/$T.deny" "$P/.keel/runs" "$W/.keel/runs" "$W" "$P/work/$T-env" "$S" "$G" "$B/$T.bundle" "$P/$T.base" "$P/$T.mode" "$P/quarantine/$T" "$P/containers/$T"
  rm -f "$P/.keel/redact-fixture"
  mkdir -p "$P/work"; echo "cleaned $T";;
container-state) keel_print_state; exit $?;;
*) sed -n 2,7p "$0"; exit 2;;
esac
