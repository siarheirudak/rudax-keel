#!/usr/bin/env bash
# shellcheck disable=SC2016  # agent commands are single-quoted on purpose: they expand inside the container, not on the host
# Attack tests. Run: DOCKER="sudo docker" ./test-attacks.sh
set -u; HERE=$(cd "$(dirname "$0")" && pwd -P); SETUP=$(cd "$HERE/../.." && pwd -P); K="$HERE/harness-keel.sh"; # shellcheck source=setup/lib/portable.sh
. "$SETUP/lib/portable.sh"; export KEEL_ROOT=${KEEL_ROOT:-$HOME/keel-proto}; P=$KEEL_ROOT
R=$P/repo W=$P/work/task-1 S=$P/shadow/task-1.git; D=${DOCKER:-docker}
unset GH_TOKEN GITHUB_TOKEN BOT_GH_TOKEN GITHUB_PAT AWS_SECRET_ACCESS_KEY AWS_ACCESS_KEY_ID API_KEY API_TOKEN NPM_TOKEN PYPI_TOKEN PASSWORD OPENAI_API_KEY KEEL_SECRET ANTHROPIC_API_KEY GEMINI_API_KEY GOOGLE_API_KEY OPENROUTER_API_KEY || true
# shellcheck source=setup/tests/harness/h3-verdict.sh
. "$HERE/h3-verdict.sh"
res(){ echo "RESULT $1: $2"; }

# H2 reads the launched container's own pids cap before any workload.
# A missing, unlimited, or non-128 cap is NOT BLOCKED only after that container is gone.
# Unreadable evidence is H2-INFRA and is not an H2 verdict.
# The 160-start ceiling is a probe bound, not the product pids guard.
# EXIT, INT, and TERM remove this cid only. SIGKILL of the job, or loss of the runner,
# cannot be trapped; the in-container wait and child lifetime are the bound that remains.
h2_note(){ [ -n "${H2_TRACE:-}" ] && printf '%s\n' "$1" >> "$H2_TRACE"; }
h2_uint(){ printf '%s' "$1" | grep -Eq '^[0-9]{1,7}$'; }
h2_classify(){
  local cfg=$1 eff=$2
  if [ -z "$cfg" ] || [ -z "$eff" ] || [ "$cfg" = unreadable ] || [ "$eff" = unreadable ]; then echo infra; return; fi
  if [ "$cfg" != 0 ] && ! h2_uint "$cfg"; then echo infra; return; fi
  if [ "$eff" != max ] && ! h2_uint "$eff"; then echo infra; return; fi
  if [ "$cfg" = 0 ]; then
    if [ "$eff" = max ]; then echo not_blocked; else echo infra; fi
    return
  fi
  if [ "$eff" = max ] || [ "$cfg" != "$eff" ]; then echo infra; return; fi
  if [ "$cfg" = 128 ]; then echo probe; return; fi
  echo not_blocked
}
h2_attribute(){
  local started=$1 denied=$2 ev0=$3 ev1=$4 cur=$5
  h2_uint "$started" || { h2_attr=bad-record; echo infra; return; }
  h2_uint "$cur" || { h2_attr=bad-record; echo infra; return; }
  [ "$denied" = 0 ] || [ "$denied" = 1 ] || { h2_attr=bad-record; echo infra; return; }
  [ "$started" -le 160 ] || { h2_attr=bad-record; echo infra; return; }
  if [ "$cur" -gt 128 ] || [ "$started" -gt 128 ]; then h2_attr=not-enforced; echo not_enforced; return; fi
  if ! h2_uint "$ev0" || ! h2_uint "$ev1"; then h2_attr=events-missing; echo infra; return; fi
  if [ "$ev1" -gt "$ev0" ] && [ "$cur" -le 128 ] && [ "$started" -le 128 ]; then h2_attr=contained; echo contained; return; fi
  if [ "$started" -eq 160 ] && [ "$denied" = 0 ] && [ "$ev1" -eq "$ev0" ]; then h2_attr=not-enforced; echo not_enforced; return; fi
  h2_attr=no-delta
  echo infra
}
h2_ms(){
  local t sec frac
  t=${EPOCHREALTIME:-}
  if [ -z "$t" ]; then
    echo $(( $(date +%s) * 1000 ))
    return
  fi
  sec=${t%%.*}
  frac=${t#*.}
  frac=${frac:0:3}
  while [ "${#frac}" -lt 3 ]; do frac="${frac}0"; done
  echo $((10#$sec * 1000 + 10#$frac))
}
h2_clock_start(){ h2_clock_ms=$(h2_ms); }
h2_call_seconds(){
  local budget=$1 reserve=$2 now left cap
  now=$(h2_ms)
  left=$(( budget * 1000 - (now - h2_clock_ms) - reserve * 1000 ))
  if [ "$left" -lt 1000 ]; then
    echo 0
    return
  fi
  left=$(( left / 1000 ))
  cap=${H2_DOCKER_DEADLINE:-12}
  if [ "$left" -gt "$cap" ]; then left=$cap; fi
  echo "$left"
}
h2_docker(){
  local deadline pid rc outf errf
  if [ "${h2_phase:-run}" = cleanup ]; then
    deadline=${H2_CLEANUP_CALL:-4}
  elif [ "${h2_phase:-run}" = cap ]; then
    deadline=${H2_CAP_CALL:-${H2_DOCKER_DEADLINE:-12}}
  elif [ -n "${h2_call_budget:-}" ]; then
    deadline=$h2_call_budget
  else
    deadline=${H2_DOCKER_DEADLINE:-12}
  fi
  if [ "$deadline" -le 0 ]; then
    return 124
  fi
  # timeout puts itself in a new process group. Waiting for it in the
  # foreground defers TERM/INT until that deadline, and its stdout must not
  # hold a command-substitution pipe open. wait stays interruptible and still
  # returns timeout's status, including 124. The pid file lets the trap reap it.
  if [ -n "${h2_dir:-}" ]; then
    outf=$(mktemp "$h2_dir/out.XXXXXX")
    errf=$(mktemp "$h2_dir/err.XXXXXX")
  else
    outf=$(mktemp)
    errf=$(mktemp)
  fi
  if [ -n "${H2_DOCKER:-}" ]; then
    timeout --kill-after=1 "$deadline" "$H2_DOCKER" "$@" >"$outf" 2>"$errf" &
  else
    # shellcheck disable=SC2086
    timeout --kill-after=1 "$deadline" $D "$@" >"$outf" 2>"$errf" &
  fi
  pid=$!
  if [ -n "${h2_dir:-}" ]; then printf '%s\n' "$pid" > "$h2_dir/docker.pid"; fi
  if [ -n "${H2_FAKE_STATE:-}" ]; then printf '%s\n' "$pid" > "$H2_FAKE_STATE/docker.pid"; fi
  wait "$pid"
  rc=$?
  rm -f "${h2_dir:-}/docker.pid" "${H2_FAKE_STATE:-}/docker.pid"
  cat "$outf"
  cat "$errf" >&2
  rm -f "$outf" "$errf"
  return "$rc"
}
h2_past_acquire(){
  local now left
  now=$(h2_ms)
  left=$(( ${H2_CID_DEADLINE:-15} * 1000 - (now - h2_clock_ms) ))
  [ "$left" -le 0 ]
}
h2_acquire_call(){
  h2_call_budget=$(h2_call_seconds "${H2_CID_DEADLINE:-15}" "${H2_CLEANUP_RESERVE:-3}")
  if [ "${h2_call_budget:-0}" -le 0 ]; then
    h2_status=124
    h2_out=
    return 124
  fi
  h2_out=$(h2_docker "$@" 2>/dev/null)
  h2_status=$?
  if h2_past_acquire; then
    if [ "$h2_status" -eq 0 ]; then
      h2_status=124
      h2_acquire_why=late
    fi
  fi
  return "$h2_status"
}
h2_cid_hex(){ printf '%s' "$1" | grep -Eq '^[0-9a-f]{12,64}$'; }
h2_field(){
  printf '%s\n' "$1" | awk -v key="$2" '{
    n = split($0, parts, " ")
    for (i = 1; i <= n; i++) {
      split(parts[i], kv, "=")
      if (kv[1] == key) { print kv[2]; exit 0 }
    }
    exit 1
  }'
}
h2_write_inner(){
  cat > "$1" << 'EOF'
#!/bin/sh
i=0
while [ ! -f /work/h2-go ]; do
  i=$((i + 1))
  if [ "$i" -gt 250 ]; then
    printf '%s\n' 'wait-expired' > /work/h2-result
    exit 2
  fi
  sleep 0.1
done
go=$(cat /work/h2-go 2>/dev/null || true)
if [ "$go" != probe ]; then
  printf '%s\n' 'skipped' > /work/h2-result
  exit 0
fi
ev_field(){ awk '$1=="max"{print $2; found=1} END{if (!found) print "missing"}' "$1" 2>/dev/null || echo missing; }
ev0=$(ev_field /sys/fs/cgroup/pids.events)
started=0
denied=0
i=0
pids=""
while [ "$i" -lt 160 ]; do
  if sleep 2 >/dev/null 2>&1 & then
    pids="$pids $!"
    started=$((started + 1))
  else
    denied=1
    break
  fi
  i=$((i + 1))
done
sleep 0.2
ev1=$(ev_field /sys/fs/cgroup/pids.events)
cur=$(cat /sys/fs/cgroup/pids.current 2>/dev/null || echo missing)
for p in $pids; do kill "$p" 2>/dev/null || true; done
wait 2>/dev/null || true
printf 'started=%s denied=%s ev0=%s ev1=%s cur=%s\n' "$started" "$denied" "$ev0" "$ev1" "$cur" > /work/h2-result
exit 0
EOF
  chmod 755 "$1"
}
h2_reset_run(){
  h2_emitted=0
  h2_in_trap=0
  h2_cleaned=0
  h2_rc=1
  h2_client_pid=
  h2_watch_pid=
  h2_cid=
  h2_dir=
  h2_cidfile=
  h2_stage=
  h2_reason=
  h2_acquire_why="no-cid"
  h2_attr=
}
h2_set_diag(){
  local stage=$1 reason=$2
  case $stage in
    acquire|cap|probe|attribute|cleanup|trap|verdict) ;;
    *) stage=unknown ;;
  esac
  case $reason in
    no-cid|cid-shape|id-mismatch|not-running|timeout|late|deadline|cfg-unreadable|eff-unreadable|disagree|absent|wrong|no-result|bad-record|events-missing|no-delta|not-enforced|contained|unverified|term|int|unknown) ;;
    *) reason=unknown ;;
  esac
  h2_stage=$stage
  h2_reason=$reason
}
h2_emit_diag(){
  h2_set_diag "${h2_stage:-unknown}" "${h2_reason:-unknown}"
  printf 'h2-diag: stage=%s reason=%s\n' "$h2_stage" "$h2_reason"
  h2_note "diag-$h2_stage-$h2_reason"
}
h2_kill_pidfile(){
  local f=$1 pid
  [ -n "$f" ] && [ -f "$f" ] || return 0
  pid=$(tr -d '[:space:]' < "$f")
  rm -f "$f"
  [ -n "$pid" ] || return 0
  kill -9 -- -"$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
}
h2_signal_stop(){
  local pid=$1 f recorded
  h2_kill_pidfile "${H2_FAKE_STATE:-}/docker.pid"
  for f in client.pid watch.pid; do
    [ -f "${H2_FAKE_STATE:-}/$f" ] || continue
    recorded=$(tr -d '[:space:]' < "$H2_FAKE_STATE/$f")
    [ -n "$recorded" ] || continue
    kill -9 -- -"$recorded" 2>/dev/null || kill -9 "$recorded" 2>/dev/null || true
  done
  kill -9 -- -"$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
h2_reap_all(){
  local pid
  h2_kill_pidfile "${h2_dir:-}/docker.pid"
  h2_kill_pidfile "${H2_FAKE_STATE:-}/docker.pid"
  for pid in ${h2_watch_pid:-} ${h2_client_pid:-}; do
    [ -n "$pid" ] || continue
    kill -9 -- -"$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  h2_watch_pid=
  h2_client_pid=
}
h2_view(){
  local cid=$1 out rc errf
  errf=$(mktemp)
  out=$(h2_docker inspect -f '{{.State.Running}}' "$cid" 2>"$errf")
  rc=$?
  if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ] || [ "$rc" -eq 143 ]; then
    rm -f "$errf"
    printf '%s\n' uncertain
    return
  fi
  if [ "$rc" -eq 0 ]; then
    case $out in
      true) printf '%s\n' running;;
      false) printf '%s\n' stopped;;
      *) printf '%s\n' uncertain;;
    esac
    rm -f "$errf"
    return
  fi
  if ! h2_docker info >/dev/null 2>&1; then
    rm -f "$errf"
    printf '%s\n' uncertain
    return
  fi
  if grep -Eq 'No such (container|object)' "$errf"; then
    printf '%s\n' absent
  else
    printf '%s\n' uncertain
  fi
  rm -f "$errf"
}
h2_cleanup_once(){
  local cid=$1 view
  h2_phase=cleanup
  h2_docker stop -t 1 "$cid" >/dev/null 2>&1 || true
  h2_docker rm -f "$cid" >/dev/null 2>&1 || true
  view=$(h2_view "$cid")
  h2_phase=run
  case $view in
    absent|stopped) return 0;;
  esac
  return 1
}
h2_cleanup(){
  local cid=""
  if [ "${h2_cleaned:-0}" = 1 ]; then
    return 0
  fi
  if [ -n "${h2_cidfile:-}" ] && [ -f "$h2_cidfile" ]; then
    cid=$(tr -d '[:space:]' < "$h2_cidfile")
  fi
  if h2_cid_hex "$cid"; then
    if ! h2_cleanup_once "$cid"; then
      if ! h2_cleanup_once "$cid"; then
        h2_reap_all
        return 1
      fi
    fi
  fi
  h2_reap_all
  rm -f "$W/h2-go" "$W/h2-ready" "$W/h2-result" "$W/h2-inner.sh"
  rm -f "${h2_dir:-}/armed"
  h2_cleaned=1
  return 0
}
h2_say_infra(){
  [ "${h2_emitted:-0}" = 1 ] && return 0
  h2_emitted=1
  h2_emit_diag
  h2_note verdict-infra
  res H2-INFRA "ERROR"
}
h2_say_h2(){
  [ "${h2_emitted:-0}" = 1 ] && return 0
  h2_emitted=1
  h2_emit_diag
  h2_note verdict
  res H2 "$1"
}
h2_after_cleanup(){
  local kind=$1 detail=$2
  h2_note cleanup-begin
  if ! h2_cleanup; then
    h2_note cleanup-fail
    h2_set_diag cleanup unverified
    h2_say_infra
    return 1
  fi
  h2_note cleanup-ok
  case $kind in
    contained) h2_say_h2 "CONTAINED (pids limit 128, controller denied)"; return 0;;
    not_blocked) h2_say_h2 "NOT BLOCKED ($detail)"; return 0;;
    *) h2_say_infra; return 1;;
  esac
}
h2_trap(){
  local why=$1
  [ "${h2_in_trap:-0}" = 1 ] && return 0
  h2_in_trap=1
  h2_kill_pidfile "${h2_dir:-}/docker.pid"
  h2_kill_pidfile "${H2_FAKE_STATE:-}/docker.pid"
  h2_note "trap-$why"
  h2_cleanup || true
  if [ "$why" != EXIT ]; then
    case $why in
      TERM) h2_set_diag trap term ;;
      INT) h2_set_diag trap int ;;
      *) h2_set_diag trap unknown ;;
    esac
    h2_say_infra
    exit 1
  fi
}
h2_arm_watchdog(){
  set -m
  (
    sleep "${H2_WATCHDOG_SECS:-40}"
    if [ -f "${h2_dir:-}/armed" ] && [ -f "${h2_cidfile:-}" ]; then
      cid=$(tr -d '[:space:]' < "$h2_cidfile")
      if h2_cid_hex "$cid"; then
        h2_docker rm -f "$cid" >/dev/null 2>&1 || true
      fi
    fi
  ) &
  h2_watch_pid=$!
  set +m
  echo 1 > "$h2_dir/armed"
}
h2_wait_cid(){
  local got run rc
  h2_phase=acquire
  h2_clock_start
  h2_acquire_why=deadline
  rc=1
  while true; do
    if [ "$(h2_call_seconds "${H2_CID_DEADLINE:-15}" "${H2_CLEANUP_RESERVE:-3}")" -le 0 ] || h2_past_acquire; then
      break
    fi
    if [ ! -f "$h2_cidfile" ]; then
      h2_acquire_why="no-cid"
      sleep 0.1
      continue
    fi
    h2_cid=$(tr -d '[:space:]' < "$h2_cidfile")
    if ! h2_cid_hex "$h2_cid"; then
      h2_acquire_why="cid-shape"
      sleep 0.1
      continue
    fi
    h2_acquire_call inspect -f '{{.Id}}' "$h2_cid"
    if [ "$h2_acquire_why" = late ]; then
      break
    fi
    if [ "$h2_status" -eq 124 ] || [ "$h2_status" -eq 137 ] || [ "$h2_status" -eq 143 ]; then
      h2_acquire_why=timeout
      break
    fi
    got=$(printf '%s' "$h2_out" | tr -d '[:space:]')
    if [ "$h2_status" -eq 0 ] && [ "$got" != "$h2_cid" ]; then
      h2_acquire_why="id-mismatch"
    fi
    h2_acquire_call inspect -f '{{.State.Running}}' "$h2_cid"
    if [ "$h2_acquire_why" = late ]; then
      break
    fi
    if [ "$h2_status" -eq 124 ] || [ "$h2_status" -eq 137 ] || [ "$h2_status" -eq 143 ]; then
      h2_acquire_why=timeout
      break
    fi
    run=$(printf '%s' "$h2_out" | tr -d '[:space:]')
    if [ "$h2_status" -eq 0 ] && [ "$got" = "$h2_cid" ] && [ "$run" = true ] && ! h2_past_acquire; then
      h2_note cid-ok
      rc=0
      break
    fi
    if [ "$h2_status" -eq 0 ] && [ "$run" != true ]; then
      h2_acquire_why="not-running"
    fi
    if h2_past_acquire; then
      h2_acquire_why=late
      break
    fi
    sleep 0.1
  done
  unset h2_call_budget
  h2_phase=cap
  return "$rc"
}
h2_read_cap(){
  local rc
  h2_phase=cap
  unset h2_call_budget
  h2_out=$(h2_docker inspect -f '{{.HostConfig.PidsLimit}}' "$h2_cid" 2>/dev/null)
  rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$h2_out" ]; then
    h2_cfg=unreadable
  else
    h2_cfg=$(printf '%s' "$h2_out" | tr -d '[:space:]')
  fi
  h2_out=$(h2_docker exec "$h2_cid" cat /sys/fs/cgroup/pids.max 2>/dev/null)
  rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$h2_out" ]; then
    h2_eff=unreadable
  else
    h2_eff=$(printf '%s' "$h2_out" | tr -d '[:space:]')
  fi
  h2_note inspect
}
h2_start_target(){
  h2_dir=$(mktemp -d)
  chmod 700 "$h2_dir"
  h2_cidfile=$h2_dir/cid
  rm -f "$W/h2-go" "$W/h2-ready" "$W/h2-result"
  set -m
  if [ "${H2_LAUNCH:-real}" = real ]; then
    h2_write_inner "$W/h2-inner.sh"
    KEEL_CIDFILE=$h2_cidfile $K proto h2 rw 'sh /work/h2-inner.sh' &
  else
    "$H2_DOCKER" run --cidfile "$h2_cidfile" sh -c 'wait' &
  fi
  h2_client_pid=$!
  set +m
  h2_arm_watchdog
  if [ -n "${H2_FAKE_STATE:-}" ]; then
    printf '%s\n' "$h2_client_pid" > "$H2_FAKE_STATE/client.pid"
    printf '%s\n' "$h2_watch_pid" > "$H2_FAKE_STATE/watch.pid"
  fi
}
h2_execute(){
  local class line started denied ev0 ev1 cur attr
  h2_reset_run
  if [ "${H2_TRAP_DISABLE:-0}" != 1 ]; then
    trap 'h2_trap TERM' TERM
    trap 'h2_trap INT' INT
  fi
  trap 'h2_trap EXIT' EXIT
  mkdir -p "$W"
  h2_start_target
  if ! h2_wait_cid; then
    h2_set_diag acquire "${h2_acquire_why:-deadline}"
    h2_after_cleanup infra ""
    h2_rc=1
  else
    h2_note trap-ready
    h2_read_cap
    class=$(h2_classify "$h2_cfg" "$h2_eff")
    case $class in
      infra)
        if [ "$h2_cfg" = unreadable ]; then h2_set_diag cap cfg-unreadable
        elif [ "$h2_eff" = unreadable ]; then h2_set_diag cap eff-unreadable
        else h2_set_diag cap disagree
        fi
        h2_after_cleanup infra ""
        h2_rc=1
        ;;
      not_blocked)
        h2_note no-release
        if [ "$h2_cfg" = 0 ]; then
          h2_set_diag verdict absent
          h2_after_cleanup not_blocked "no product pids limit" && h2_rc=0
        else
          h2_set_diag verdict wrong
          h2_after_cleanup not_blocked "product pids limit wrong" && h2_rc=0
        fi
        ;;
      probe)
        h2_note release
        printf '%s\n' probe > "$W/h2-go"
        h2_clock_start
        while [ ! -s "$W/h2-result" ]; do
          if [ "$(h2_call_seconds "${H2_PROBE_DEADLINE:-20}" 0)" -le 0 ]; then
            break
          fi
          sleep 0.1
        done
        line=$(head -n 1 "$W/h2-result" 2>/dev/null || true)
        if ! printf '%s' "$line" | grep -Eq '^started=[0-9]{1,4} denied=[01] ev0=([0-9]{1,7}|missing) ev1=([0-9]{1,7}|missing) cur=([0-9]{1,7}|missing)$'; then
          if [ -z "$line" ]; then h2_set_diag probe no-result
          else h2_set_diag probe bad-record
          fi
          h2_after_cleanup infra ""
          h2_rc=1
        else
          started=$(h2_field "$line" started) || started=
          denied=$(h2_field "$line" denied) || denied=
          ev0=$(h2_field "$line" ev0) || ev0=
          ev1=$(h2_field "$line" ev1) || ev1=
          cur=$(h2_field "$line" cur) || cur=
          h2_attribute "$started" "$denied" "$ev0" "$ev1" "$cur" >"$h2_dir/attr.out"
          attr=$(cat "$h2_dir/attr.out")
          case $attr in
            contained)
              h2_set_diag verdict contained
              h2_after_cleanup contained "" && h2_rc=0
              ;;
            not_enforced)
              h2_set_diag attribute not-enforced
              h2_after_cleanup not_blocked "pids limit 128 not enforced" && h2_rc=0
              ;;
            *)
              h2_set_diag attribute "${h2_attr:-no-delta}"
              h2_after_cleanup infra "" || true
              ;;
          esac
        fi
        ;;
      *)
        h2_set_diag cap disagree
        h2_after_cleanup infra ""
        h2_rc=1
        ;;
    esac
  fi
  h2_reap_all
  trap - EXIT INT TERM
  return "${h2_rc:-1}"
}
run_h2(){
  fresh
  H2_DOCKER=
  H2_LAUNCH=real
  h2_execute
}

h2_write_fake(){
  cat > "$1" << 'EOF'
#!/bin/sh
set -u
log=${H2_FAKE_LOG:?}
state=${H2_FAKE_STATE:?}
work=${H2_WORK:?}
mode=${H2_FAKE_MODE:?}
printf '%s\n' "$*" >> "$log"
cmd=$1
shift
mine=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
other=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
mkdir -p "$state"
write_cid(){
  if [ -f "$work/h2-go" ]; then echo go-before-cid >> "$log"; fi
  printf '%s\n' "$mine" > "$1"
  echo running > "$state/phase"
}
case "$cmd" in
  run)
    cidfile=
    while [ $# -gt 0 ]; do
      if [ "$1" = --cidfile ]; then cidfile=${2:-}; shift 2; continue; fi
      shift
    done
    [ -n "${cidfile:-}" ] || exit 2
    if [ "$mode" = nocid ] || [ "$mode" = hang-before-cid ]; then
      i=0
      while [ "$i" -lt 400 ]; do
        [ -f "$state/stop" ] && exit 0
        i=$((i + 1))
        sleep 0.05
      done
      exit 0
    fi
    if [ "$mode" = delay-cid ]; then sleep 0.4; fi
    if [ "$mode" = rm-hang ]; then
      write_cid "$cidfile"
      i=0
      while [ "$i" -lt 400 ]; do
        [ -f "$state/stop" ] && exit 0
        i=$((i + 1))
        sleep 0.05
      done
      exit 0
    fi
    write_cid "$cidfile"
    if [ "$mode" = client-dead ]; then exit 0; fi
    i=0
    while [ "$i" -lt 400 ]; do
      [ -f "$state/stop" ] && exit 0
      if [ -f "$work/h2-go" ]; then
        go=$(cat "$work/h2-go" 2>/dev/null || true)
        if [ "$go" = probe ]; then
          case $mode in
            nearcap) printf '%s\n' 'started=96 denied=1 ev0=0 ev1=0 cur=96' > "$work/h2-result";;
            events-missing) printf '%s\n' 'started=20 denied=1 ev0=missing ev1=missing cur=120' > "$work/h2-result";;
            *) printf '%s\n' 'started=20 denied=1 ev0=0 ev1=1 cur=120' > "$work/h2-result";;
          esac
        fi
        exit 0
      fi
      i=$((i + 1))
      sleep 0.05
    done
    exit 0
    ;;
  inspect)
    fmt=
    cid=
    while [ $# -gt 0 ]; do
      if [ "$1" = -f ]; then fmt=${2:-}; shift 2; continue; fi
      case $1 in
        -*) shift;;
        *) cid=$1; shift;;
      esac
    done
    [ "${cid:-}" = "$mine" ] || exit 1
    if [ "$mode" = cid-hang ]; then sleep 30; exit 1; fi
    if [ ! -f "$state/stop" ]; then
      n=0
      if [ -f "$state/ninspect" ]; then n=$(cat "$state/ninspect"); fi
      n=$((n + 1))
      echo "$n" > "$state/ninspect"
      case $mode in
        slow-hang)
          if [ "$n" -eq 1 ]; then sleep 1.2
          elif [ "$n" -ge 2 ]; then sleep 30; exit 1
          fi
          ;;
        first-timeout)
          if [ "$n" -eq 1 ]; then sleep 30; exit 1; fi
          ;;
        late-success)
          if [ "$n" -eq 1 ]; then sleep 1.8
          elif [ "$n" -eq 2 ]; then sleep 1.5
          fi
          ;;
      esac
    fi
    if [ "$mode" = daemon-after ] && [ -f "$state/cap-served" ]; then
      echo "cannot connect" >&2
      exit 1
    fi
    if [ -f "$state/stop" ]; then
      case $mode in
        inspect-empty) exit 0;;
        inspect-timeout) sleep 30; exit 1;;
        *)
          echo "Error: No such container" >&2
          exit 1
          ;;
      esac
    fi
    case ${fmt:-} in
      '{{.State.Running}}') echo true;;
      '{{.Id}}') printf '%s\n' "$mine";;
      '{{.HostConfig.PidsLimit}}')
        case $mode in
          higher) echo 256;;
          lower) echo 64;;
          unlimited|client-dead|delay-cid|inspect-empty|inspect-timeout) echo 0;;
          daemon-after)
            echo 1 > "$state/cap-served"
            echo 0
            ;;
          unreadable) exit 1;;
          hold-cid) sleep 30; exit 1;;
          *) echo 128;;
        esac
        ;;
      *) exit 1;;
    esac
    ;;
  exec)
    cid=
    while [ $# -gt 0 ]; do
      case $1 in
        -*) shift;;
        *) cid=$1; shift; break;;
      esac
    done
    [ "${cid:-}" = "$mine" ] || exit 1
    text="$*"
    case $text in
      *pids.max*)
        case $mode in
          higher) echo 256;;
          lower) echo 64;;
          unlimited|client-dead|delay-cid|daemon-after|inspect-empty|inspect-timeout) echo max;;
          disagree) echo max;;
          unreadable) exit 1;;
          *) echo 128;;
        esac
        ;;
      *pids.events*) printf '%s\n' 'max 0';;
      *) exit 1;;
    esac
    ;;
  stop) exit 0;;
  info)
    if [ "$mode" = daemon-after ] && [ -f "$state/cap-served" ]; then
      echo "cannot connect" >&2
      exit 1
    fi
    exit 0
    ;;
  rm)
    cid=
    while [ $# -gt 0 ]; do
      case $1 in
        -*) shift;;
        *) cid=$1; shift;;
      esac
    done
    if [ "${cid:-}" = "$other" ]; then echo rm-other >> "$log"; exit 0; fi
    if [ "${cid:-}" != "$mine" ]; then echo rm-unexpected >> "$log"; exit 1; fi
    if [ "$mode" = rm-fail ]; then exit 1; fi
    if [ "$mode" = rm-hang ]; then sleep 30; exit 1; fi
    if [ "$mode" = rm-lie ]; then exit 0; fi
    if [ "$mode" = rm-retry ] && [ ! -f "$state/rm1" ]; then
      echo 1 > "$state/rm1"
      exit 0
    fi
    echo 1 > "$state/stop"
    exit 0
    ;;
  *) exit 0;;
esac
EOF
  chmod 755 "$1"
}
h2_case_begin(){
  local mode=$1
  h2_case_root=$(mktemp -d)
  W=$h2_case_root/work
  mkdir -p "$W"
  H2_FAKE_MODE=$mode
  H2_FAKE_LOG=$h2_case_root/docker.log
  H2_FAKE_STATE=$h2_case_root/state
  H2_WORK=$W
  H2_TRACE=$h2_case_root/trace
  H2_DOCKER=$h2_case_root/docker
  H2_LAUNCH=fake
  H2_CID_DEADLINE=${H2_CID_DEADLINE_CASE:-3}
  H2_PROBE_DEADLINE=${H2_PROBE_DEADLINE_CASE:-3}
  H2_DOCKER_DEADLINE=${H2_DOCKER_DEADLINE_CASE:-3}
  H2_CLEANUP_CALL=${H2_CLEANUP_CALL_CASE:-4}
  H2_CLEANUP_RESERVE=${H2_CLEANUP_RESERVE_CASE:-1}
  H2_WATCHDOG_SECS=30
  : > "$H2_FAKE_LOG"
  : > "$H2_TRACE"
  mkdir -p "$H2_FAKE_STATE"
  h2_write_fake "$H2_DOCKER"
  export H2_FAKE_MODE H2_FAKE_LOG H2_FAKE_STATE H2_WORK H2_TRACE H2_DOCKER H2_LAUNCH
}
h2_case_end(){
  if [ -n "${h2_watch_pid:-}" ]; then kill "$h2_watch_pid" 2>/dev/null || true; wait "$h2_watch_pid" 2>/dev/null || true; fi
  if [ -n "${h2_client_pid:-}" ]; then kill "$h2_client_pid" 2>/dev/null || true; wait "$h2_client_pid" 2>/dev/null || true; fi
  rm -rf "${h2_case_root:-}"
  h2_case_root=
}
h2_fail(){ echo "h2-self: FAIL $1" >&2; h2_self_failed=1; }
h2_self_test(){
  local t0 out rc saved_w
  t0=$(date +%s)
  h2_self_failed=0
  saved_w=$W
  set +e
  h2_expect(){ if [ "$2" != "$3" ]; then h2_fail "$1 got [$2] want [$3]"; fi; }
  h2_pair(){ printf '%s\n%s' "$1" "$2"; }
  h2_expect class128 "$(h2_classify 128 128)" probe
  h2_expect class-max "$(h2_classify 0 max)" not_blocked
  h2_expect class-low "$(h2_classify 64 64)" not_blocked
  h2_expect class-high "$(h2_classify 256 256)" not_blocked
  h2_expect class-unread "$(h2_classify unreadable unreadable)" infra
  h2_expect class-empty "$(h2_classify '' '')" infra
  h2_expect class-disagree "$(h2_classify 128 max)" infra
  h2_expect class-safety "$(h2_classify 0 max)" not_blocked
  h2_expect attr-deny "$(h2_attribute 20 1 0 1 120)" contained
  h2_expect attr-event "$(h2_attribute 20 0 0 2 100)" contained
  h2_expect attr-parent "$(h2_attribute 4 0 0 0 4)" infra
  h2_expect attr-near "$(h2_attribute 96 1 0 0 96)" infra
  h2_expect attr-miss "$(h2_attribute 20 1 missing missing 120)" infra
  h2_expect attr-ceiling "$(h2_attribute 160 0 0 0 160)" not_enforced
  h2_expect attr-over "$(h2_attribute 20 1 0 1 200)" not_enforced
  h2_run_case(){
    h2_case_begin "$1"
    out=$(h2_execute)
    rc=$?
    h2_case_out=$out
    h2_case_rc=$rc
    h2_case_trace=$(cat "$H2_TRACE" 2>/dev/null || true)
    h2_case_log=$(cat "$H2_FAKE_LOG" 2>/dev/null || true)
    h2_case_end
  }
  h2_run_case 128
  h2_expect live128-rc "$h2_case_rc" 0
  h2_expect live128-out "$h2_case_out" "$(h2_pair 'h2-diag: stage=verdict reason=contained' 'RESULT H2: CONTAINED (pids limit 128, controller denied)')"
  printf '%s\n' "$h2_case_trace" | grep -q '^release$' || h2_fail "live128 no release"
  printf '%s\n' "$h2_case_trace" | awk 'BEGIN{ok=0} /^cleanup-ok$/{ok=1} /^verdict$/{if(!ok) bad=1} END{exit bad+0}' || h2_fail "live128 verdict before cleanup"
  printf '%s\n' "$h2_case_log" | grep -q 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff' && h2_fail "live128 touched other cid"
  h2_run_case unlimited
  h2_expect live-max-rc "$h2_case_rc" 0
  h2_expect live-max-out "$h2_case_out" "$(h2_pair 'h2-diag: stage=verdict reason=absent' 'RESULT H2: NOT BLOCKED (no product pids limit)')"
  printf '%s\n' "$h2_case_trace" | grep -q '^no-release$' || h2_fail "unlimited released a load"
  printf '%s\n' "$h2_case_log" | grep -q 'go-before-cid' && h2_fail "go before cid"
  h2_run_case lower
  h2_expect live-low "$h2_case_out" "$(h2_pair 'h2-diag: stage=verdict reason=wrong' 'RESULT H2: NOT BLOCKED (product pids limit wrong)')"
  h2_run_case higher
  h2_expect live-high "$h2_case_out" "$(h2_pair 'h2-diag: stage=verdict reason=wrong' 'RESULT H2: NOT BLOCKED (product pids limit wrong)')"
  h2_run_case unreadable
  h2_expect unread-rc "$h2_case_rc" 1
  h2_expect unread-out "$h2_case_out" "$(h2_pair 'h2-diag: stage=cap reason=cfg-unreadable' 'RESULT H2-INFRA: ERROR')"
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "unreadable emitted H2"
  H2_CID_DEADLINE_CASE=4
  H2_CLEANUP_RESERVE_CASE=1
  h2_run_case delay-cid
  H2_CID_DEADLINE_CASE=3
  H2_CLEANUP_RESERVE_CASE=1
  h2_expect delay-out "$h2_case_out" "$(h2_pair 'h2-diag: stage=verdict reason=absent' 'RESULT H2: NOT BLOCKED (no product pids limit)')"
  printf '%s\n' "$h2_case_log" | grep -q 'go-before-cid' && h2_fail "delay go before cid"
  H2_CID_DEADLINE_CASE=1
  h2_run_case nocid
  H2_CID_DEADLINE_CASE=3
  h2_expect nocid-rc "$h2_case_rc" 1
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "nocid emitted H2"
  printf '%s\n' "$h2_case_out" | grep -qx 'h2-diag: stage=acquire reason=deadline' || h2_fail "nocid diag"
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2-INFRA: ERROR$' || h2_fail "nocid missing infra"
  h2_run_case rm-fail
  h2_expect rmfail-rc "$h2_case_rc" 1
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "rm-fail emitted H2"
  h2_run_case rm-lie
  h2_expect rmlie-rc "$h2_case_rc" 1
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "rm-lie emitted H2"
  h2_run_case client-dead
  h2_expect dead-out "$h2_case_out" "$(h2_pair 'h2-diag: stage=verdict reason=absent' 'RESULT H2: NOT BLOCKED (no product pids limit)')"
  printf '%s\n' "$h2_case_log" | grep -q 'rm -f 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef' || h2_fail "client-dead did not remove cid"
  H2_DOCKER_DEADLINE_CASE=1
  H2_CLEANUP_CALL_CASE=1
  hang_dir=$(mktemp -d)
  (
    h2_run_case rm-hang
    printf '%s\n' "$h2_case_rc" > "$hang_dir/rc"
    printf '%s\n' "$h2_case_out" > "$hang_dir/out"
  ) &
  hang_pid=$!
  i=0
  while [ "$i" -lt 80 ]; do
    kill -0 "$hang_pid" 2>/dev/null || break
    i=$((i + 1))
    sleep 0.1
  done
  if kill -0 "$hang_pid" 2>/dev/null; then
    kill -9 "$hang_pid" 2>/dev/null || true
    wait "$hang_pid" 2>/dev/null || true
    h2_fail "rm-hang hard deadline"
    h2_case_rc=1
    h2_case_out=
  else
    wait "$hang_pid" 2>/dev/null || true
    h2_case_rc=$(cat "$hang_dir/rc" 2>/dev/null || echo 1)
    h2_case_out=$(cat "$hang_dir/out" 2>/dev/null || true)
  fi
  rm -rf "$hang_dir"
  H2_DOCKER_DEADLINE_CASE=3
  H2_CLEANUP_CALL_CASE=4
  h2_expect hang-rc "$h2_case_rc" 1
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "rm-hang emitted H2"
  h2_grade_captured(){
    local src=$1
    python3 - "$HERE" "$src" << 'PY' || h2_fail "captured-grade"
import sys
sys.path.insert(0, sys.argv[1])
import mutate
import mutate_shards as ms
text = open(sys.argv[2], encoding="utf-8").read()
allowed = {
    "h2-diag: stage=acquire reason=no-cid",
    "h2-diag: stage=acquire reason=cid-shape",
    "h2-diag: stage=acquire reason=id-mismatch",
    "h2-diag: stage=acquire reason=not-running",
    "h2-diag: stage=acquire reason=timeout",
    "h2-diag: stage=acquire reason=late",
    "h2-diag: stage=acquire reason=deadline",
    "h2-diag: stage=cap reason=cfg-unreadable",
    "h2-diag: stage=cap reason=eff-unreadable",
    "h2-diag: stage=cap reason=disagree",
    "h2-diag: stage=probe reason=no-result",
    "h2-diag: stage=probe reason=bad-record",
    "h2-diag: stage=attribute reason=events-missing",
    "h2-diag: stage=attribute reason=no-delta",
    "h2-diag: stage=attribute reason=not-enforced",
    "h2-diag: stage=cleanup reason=unverified",
    "h2-diag: stage=trap reason=term",
    "h2-diag: stage=trap reason=int",
    "h2-diag: stage=verdict reason=contained",
    "h2-diag: stage=verdict reason=absent",
    "h2-diag: stage=verdict reason=wrong",
}
diags = [line for line in text.splitlines() if line.startswith("h2-diag:")]
if len(diags) != 1 or diags[0] not in allowed:
    raise SystemExit("diag missing or unsafe")
for line in text.splitlines():
    if line.startswith("RESULT H2:"):
        raise SystemExit("captured definitive H2")
red, _detail = mutate.judge(["H2"], text)
tag = mutate.verdict_tag(["H2"], red)
if tag == "yes" or (red and "H2" in red):
    raise SystemExit("captured earned an H2 kill")
base = ms.classify_baseline("1", "test-attacks.sh", [("M26", ["H2"])], text, 1)
if not base or base.get("reason") != "status":
    raise SystemExit("baseline accepted a failed helper")
PY
  }
  h2_save_case(){
    h2_case_file=$(mktemp)
    printf '%s\n' "$h2_case_out" > "$h2_case_file"
  }
  h2_run_case nearcap
  h2_expect near-rc "$h2_case_rc" 1
  printf '%s\n' "$h2_case_out" | grep -qx 'h2-diag: stage=attribute reason=no-delta' || h2_fail "nearcap diag"
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "nearcap emitted H2"
  h2_save_case
  h2_grade_captured "$h2_case_file"
  h2_run_case events-missing
  h2_expect miss-rc "$h2_case_rc" 1
  printf '%s\n' "$h2_case_out" | grep -qx 'h2-diag: stage=attribute reason=events-missing' || h2_fail "missing events diag"
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "missing events emitted H2"
  h2_save_case
  h2_grade_captured "$h2_case_file"
  h2_run_case daemon-after
  h2_expect daemon-rc "$h2_case_rc" 1
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "daemon loss emitted H2"
  h2_save_case
  h2_grade_captured "$h2_case_file"
  h2_case_begin daemon-after
  h2_execute >/dev/null || true
  h2_before=$(grep -c 'rm -f' "$H2_FAKE_LOG" || true)
  h2_cleanup >/dev/null || true
  h2_after=$(grep -c 'rm -f' "$H2_FAKE_LOG" || true)
  [ "$h2_after" -gt "$h2_before" ] || h2_fail "cleanup latch blocked a retry"
  h2_case_end
  h2_run_case inspect-empty
  h2_expect empty-rc "$h2_case_rc" 1
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "empty inspect emitted H2"
  h2_save_case
  h2_grade_captured "$h2_case_file"
  H2_CLEANUP_CALL_CASE=1
  h2_run_case inspect-timeout
  H2_CLEANUP_CALL_CASE=4
  h2_expect ito-rc "$h2_case_rc" 1
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "inspect timeout emitted H2"
  h2_save_case
  h2_grade_captured "$h2_case_file"
  H2_CID_DEADLINE_CASE=2
  H2_DOCKER_DEADLINE_CASE=2
  H2_CLEANUP_CALL_CASE=1
  cid_t=$(date +%s)
  h2_run_case cid-hang
  cid_el=$(( $(date +%s) - cid_t ))
  H2_CID_DEADLINE_CASE=3
  H2_DOCKER_DEADLINE_CASE=3
  H2_CLEANUP_CALL_CASE=4
  [ "$cid_el" -le 8 ] || h2_fail "cid hang took ${cid_el}s"
  h2_expect cidhang-rc "$h2_case_rc" 1
  printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "cid hang emitted H2"
  printf '%s\n' "$h2_case_log" | grep -q 'rm -f' || h2_fail "cid hang skipped cleanup"
  h2_save_case
  h2_grade_captured "$h2_case_file"
  h2_run_case rm-retry
  h2_expect retry-rc "$h2_case_rc" 0
  h2_expect retry-out "$h2_case_out" "$(h2_pair 'h2-diag: stage=verdict reason=contained' 'RESULT H2: CONTAINED (pids limit 128, controller denied)')"
  h2_retry_n=$(printf '%s\n' "$h2_case_log" | grep -c 'rm -f' || true)
  [ "$h2_retry_n" -ge 2 ] || h2_fail "retry did not remove twice"
  # Acquisition budget 4s, cleanup reserve 1s, per-call cap 4s, kill-after 1s.
  # A refreshed second call is about 1s. Reusing the first 3s budget overruns this allowance.
  h2_budget_case(){
    local mode=$1 allowance=$2
    local started elapsed
    H2_CID_DEADLINE_CASE=4
    H2_DOCKER_DEADLINE_CASE=4
    H2_CLEANUP_RESERVE_CASE=1
    H2_CLEANUP_CALL_CASE=1
    started=$(h2_ms)
    h2_run_case "$mode"
    elapsed=$(( $(h2_ms) - started ))
    H2_CID_DEADLINE_CASE=3
    H2_DOCKER_DEADLINE_CASE=3
    H2_CLEANUP_RESERVE_CASE=1
    H2_CLEANUP_CALL_CASE=4
    [ "$elapsed" -le "$allowance" ] || h2_fail "$mode took ${elapsed}ms allowance ${allowance}ms"
    [ "$h2_case_rc" -ne 0 ] || h2_fail "$mode rc 0"
    printf '%s\n' "$h2_case_out" | grep -qx 'h2-diag: stage=acquire reason=timeout' || h2_fail "$mode diag"
    printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2:' && h2_fail "$mode emitted H2"
    printf '%s\n' "$h2_case_out" | grep -q '^RESULT H2-INFRA: ERROR$' || h2_fail "$mode missing infra"
    printf '%s\n' "$h2_case_log" | grep -q 'rm -f' || h2_fail "$mode skipped cleanup"
    printf '%s\n' "$h2_case_trace" | grep -q '^cid-ok$' && h2_fail "$mode accepted a late cid"
    h2_save_case
    h2_grade_captured "$h2_case_file"
    rm -f "$h2_case_file"
  }
  # 1.2s first inspect + 1s refreshed hang + 1s kill-after.
  h2_budget_case slow-hang 4000
  id_n=$(printf '%s\n' "$h2_case_log" | grep -c 'inspect -f {{.Id}}' || true)
  [ "$id_n" -eq 1 ] || h2_fail "slow-hang repeated the first inspect ($id_n)"
  # One hung Id inspect. A laundered timeout would start another full-budget inspect.
  h2_budget_case first-timeout 5000
  id_n=$(printf '%s\n' "$h2_case_log" | grep -c 'inspect -f {{.Id}}' || true)
  [ "$id_n" -eq 1 ] || h2_fail "first-timeout did not stop on the timeout status ($id_n)"
  # Second success is only valid if it returns before the acquisition deadline.
  h2_budget_case late-success 5000
  # hold-cid's cap inspect blocks until H2_DOCKER_DEADLINE (8s). The early
  # bound is 3s, so a natural timeout cannot satisfy the trap marker.
  h2_signal_case(){
    local sig=$1 send=$2 disarm=$3
    local sig_pid sig_rc mark elapsed client_pid watch_pid ok
    h2_case_begin hold-cid
    H2_CID_DEADLINE=8
    H2_DOCKER_DEADLINE=8
    H2_TRAP_DISABLE=$disarm
    export H2_TRAP_DISABLE
    set -m
    (
      h2_execute
    ) >"$h2_case_root/sig.out" 2>/dev/null &
    sig_pid=$!
    set +m
    i=0
    while [ "$i" -lt 30 ]; do
      if grep -qx 'trap-ready' "$H2_TRACE" 2>/dev/null; then
        break
      fi
      i=$((i + 1))
      sleep 0.1
    done
    if ! grep -qx 'trap-ready' "$H2_TRACE" 2>/dev/null; then
      h2_signal_stop "$sig_pid"
      unset H2_TRAP_DISABLE
      h2_case_end
      return 1
    fi
    mark=$(h2_ms)
    if [ "$send" = 1 ]; then
      kill -s "$sig" -- -"$sig_pid" 2>/dev/null || true
    fi
    i=0
    while [ "$i" -lt 30 ]; do
      if ! kill -0 "$sig_pid" 2>/dev/null; then
        break
      fi
      i=$((i + 1))
      sleep 0.1
    done
    elapsed=$(( $(h2_ms) - mark ))
    if kill -0 "$sig_pid" 2>/dev/null; then
      h2_signal_stop "$sig_pid"
      unset H2_TRAP_DISABLE
      h2_case_end
      return 1
    fi
    wait "$sig_pid"
    sig_rc=$?
    sig_out=$(cat "$h2_case_root/sig.out" 2>/dev/null || true)
    sig_log=$(cat "$H2_FAKE_LOG" 2>/dev/null || true)
    client_pid=$(cat "$H2_FAKE_STATE/client.pid" 2>/dev/null || true)
    watch_pid=$(cat "$H2_FAKE_STATE/watch.pid" 2>/dev/null || true)
    ok=0
    if [ "$sig_rc" -ne 0 ] \
      && [ "$elapsed" -lt 3000 ] \
      && grep -qx "trap-$sig" "$H2_TRACE" \
      && printf '%s\n' "$sig_out" | grep -qx "h2-diag: stage=trap reason=$(printf '%s' "$sig" | tr '[:upper:]' '[:lower:]')" \
      && ! printf '%s\n' "$sig_out" | grep -q '^RESULT H2:' \
      && printf '%s\n' "$sig_out" | grep -q '^RESULT H2-INFRA: ERROR$' \
      && printf '%s\n' "$sig_log" | grep -q 'rm -f 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef' \
      && [ -n "$client_pid" ] && ! kill -0 "$client_pid" 2>/dev/null \
      && [ -n "$watch_pid" ] && ! kill -0 "$watch_pid" 2>/dev/null \
      && ! kill -0 -- -"$client_pid" 2>/dev/null \
      && ! kill -0 -- -"$watch_pid" 2>/dev/null
    then
      ok=1
    fi
    unset H2_TRAP_DISABLE
    h2_case_end
    [ "$ok" -eq 1 ]
  }
  h2_signal_case TERM 1 0 || h2_fail "TERM cleanup"
  h2_signal_case INT 1 0 || h2_fail "INT cleanup"
  if h2_signal_case TERM 0 0; then h2_fail "missing signal still passed"; fi
  if h2_signal_case TERM 1 1; then h2_fail "missing trap still passed"; fi
  python3 - "$HERE" << 'PY' || h2_fail "judge"
import sys
sys.path.insert(0, sys.argv[1])
import mutate
import mutate_shards as ms
def tag(text):
    red, _detail = mutate.judge(["H2"], text)
    return mutate.verdict_tag(["H2"], red), red
kill, red = tag("RESULT A1: BLOCKED (x)\nRESULT H2: NOT BLOCKED (no product pids limit)\n")
if kill != "yes" or "H2" not in red:
    raise SystemExit("not-blocked was not a kill")
no, red = tag("RESULT A1: BLOCKED (x)\nRESULT H2-INFRA: ERROR\n")
if no != "NO" or "H2" in red:
    raise SystemExit("infra earned an H2 kill")
false_kill, red = tag("RESULT H2: ERROR\n")
if false_kill != "yes" or "H2" not in red:
    raise SystemExit("grader no longer treats H2 ERROR as red")
base = ms.classify_baseline("1", "test-attacks.sh", [("M26", ["H2"])], "RESULT H2: CONTAINED (pids limit 128, controller denied)\n", 0)
if base is not None:
    raise SystemExit("baseline contained rejected")
bad = ms.classify_baseline("1", "test-attacks.sh", [("M26", ["H2"])], "RESULT H2-INFRA: ERROR\n", 1)
if not bad or bad.get("reason") != "status":
    raise SystemExit("baseline accepted nonzero")
PY
  python3 - "$SETUP/keel.sh" << 'PY' || h2_fail "anchor"
import sys
text = open(sys.argv[1], encoding="utf-8").read()
old = '--pids-limit "${PIDS:-128}" '
if text.count(old) != 1:
    raise SystemExit("anchor count")
PY
  python3 - "$HERE/test-attacks.sh" << 'PY' || h2_fail "bomb"
import sys
text = open(sys.argv[1], encoding="utf-8").read()
needle = "b " + "| b"
if needle in text:
    raise SystemExit("bomb")
PY
  W=$saved_w
  if [ "$h2_self_failed" -ne 0 ]; then
    echo "h2-self: FAIL" >&2
    return 1
  fi
  echo "h2-self: elapsed $(( $(date +%s) - t0 ))s"
  echo "h2-self: ok"
  return 0
}
if [ "${1:-}" = --h2-self-test ] || [ "${1:-}" = --h2-entry-probe ] || [ "${KEEL_NS:-base}" = base ]; then
  if ! ( h2_self_test ); then
    exit 1
  fi
fi
if [ "${1:-}" = --h2-self-test ]; then
  exit 0
fi
if [ "${1:-}" = --h2-entry-probe ]; then
  if [ -n "${H2_DOCKER:-}${H2_TRACE:-}${H2_CID_DEADLINE:-}${H2_PROBE_DEADLINE:-}${H2_DOCKER_DEADLINE:-}${H2_WATCHDOG_SECS:-}${H2_LAUNCH:-}${H2_FAKE_MODE:-}${H2_CLEANUP_CALL:-}" ]; then
    echo "h2-entry: leaked" >&2
    exit 1
  fi
  h2_clock_start
  if [ "$(h2_call_seconds 15 0)" != 12 ]; then
    echo "h2-entry: default budget drifted" >&2
    exit 1
  fi
  echo "h2-entry: attacks-continue"
  exit 0
fi

echo "### MODE-A1 directly executed script mode"
mode_fix=$(mktemp -d)
git -C "$mode_fix" init -q
git -C "$mode_fix" config user.email t@x
git -C "$mode_fix" config user.name t
mkdir -p "$mode_fix/setup/tests/harness"
printf '%s\n' '"$HERE/bad-mode.sh"' > "$mode_fix/setup/tests/harness/run-tests.sh"
printf '%s\n' 'echo hi' > "$mode_fix/setup/tests/harness/bad-mode.sh"
git -C "$mode_fix" add setup/tests/harness/run-tests.sh setup/tests/harness/bad-mode.sh
mode_out=$(bash "$SETUP/check.sh" --repo "$mode_fix" 2>&1) || mode_ec=$?
mode_ec=${mode_ec:-0}
if [ "$mode_ec" -ne 0 ] && printf '%s\n' "$mode_out" | grep -qx 'ERROR: script mode: setup/tests/harness/bad-mode.sh is 100644, not 100755'; then
  res MODE-A1 "BLOCKED (setup/tests/harness/bad-mode.sh)"
else
  res MODE-A1 "NOT BLOCKED"
fi
rm -rf "$mode_fix"
bash "$HERE/test-runtime.sh" || true
bash "$HERE/test-mutant-result.sh" || true
fresh(){ rm -rf "$P"; $K init-repo >/dev/null; $K setup >/dev/null; }
h3_diag(){
  echo "  H3 diag:"
  $K proto h3diag ro 'echo memory.max=$(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo missing); echo memory.swap.max=$(cat /sys/fs/cgroup/memory.swap.max 2>/dev/null || echo missing); echo swaps=$(cat /proc/swaps 2>/dev/null); free' || true
  echo "  host swaps: $(tr '\n' ';' < /proc/swaps 2>/dev/null || true)"
  echo "  host free: $(free -m 2>/dev/null | tr '\n' ';')"
  echo "  docker cgroup:"
  $D info 2>/dev/null | grep -i -E 'cgroup|Memory|Swap' || true
}
run_h3(){
  local bytes chunks out rc cidf cid oom verdict
  bytes=$(h3_mem_bytes "${MEM:-512m}")
  chunks=$(( (bytes * 2) / 1048576 + 256 ))
  cat > "$W/h3-alloc.sh" << EOF
#!/bin/sh
mm=\$(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo missing)
echo mem-max=\$mm
sw=\$(cat /sys/fs/cgroup/memory.swap.max 2>/dev/null || echo missing)
echo mem-swap-max=\$sw
if [ "\$mm" != "$bytes" ]; then
  echo mem-limit=absent
  exit 0
fi
echo mem-limit=present
awk 'BEGIN{ for (i=0;i<$chunks;i++) a[i]=sprintf("%1048576d", i) }'
echo alloc-rc=\$?
EOF
  cidf=$(mktemp)
  rm -f "$cidf"
  set +e
  out=$(KEEL_CIDFILE="$cidf" $K proto mem rw 'sh /work/h3-alloc.sh' 2>&1)
  rc=$?
  set +e
  oom=unknown
  swap_pin=unknown
  if [ -s "$cidf" ]; then
    cid=$(cat "$cidf")
    oom=$($D inspect -f '{{.State.OOMKilled}}' "$cid" 2>/dev/null || echo gone)
    mem=$($D inspect -f '{{.HostConfig.Memory}}' "$cid" 2>/dev/null || echo 0)
    swp=$($D inspect -f '{{.HostConfig.MemorySwap}}' "$cid" 2>/dev/null || echo 0)
    if [ "$mem" -gt 0 ] 2>/dev/null && [ "$swp" = "$mem" ]; then swap_pin=present; else swap_pin=absent; fi
    $D rm -f "$cid" >/dev/null 2>&1 || true
  fi
  rm -f "$cidf" "$W/h3-alloc.sh"
  echo "  docker-rc=$rc oom=$oom"
  echo "$out"
  verdict=$(h3_verdict "$out
swap-pin=$swap_pin" "$rc" "$oom" "$bytes")
  res H3 "$verdict"
  case $verdict in
    CONTAINED*) return 0;;
    *) h3_diag; return 1;;
  esac
}
if [ "${H3_ONLY:-}" = 1 ]; then
  fresh
  run_h3
  exit $?
fi
# gate_expect_fail <ID> <regex the GATE FAIL reason must match>: failing for a DIFFERENT reason is not a pass
gate_expect_fail(){ out=$($K gate 2>&1); rc=$?; echo "$out" | tail -2; why=$(echo "$out" | grep 'GATE FAIL' | head -1)
  if [ $rc -eq 0 ]; then res "$1" "NOT BLOCKED"; elif echo "$why" | grep -qE "$2"; then res "$1" "BLOCKED (gate: $why)"; else res "$1" "WRONG REASON (expected /$2/, got: ${why:-rc=$rc})"; fi; }

echo "### A1 write to /base/objects"; fresh
$K proto evil rw 'touch /base/objects/pwn 2>&1; mkdir /base/objects/aa 2>&1; echo x > /base/objects/info/alternates 2>&1; echo rc=$?'
if [ -e "$R/.git/objects/pwn" ]; then res A1 "NOT BLOCKED"; else res A1 "BLOCKED (read-only mount)"; fi
echo "  side note: agent CAN edit shadow alternates (rw shadow):"; $K proto evil rw 'echo /tmp >> /shadow/task-1.git/objects/info/alternates && echo edited-shadow-alternates'

echo "### A2 rewrite pointer file"; fresh
if [ "$($K mode)" = env ]; then res A2 "N/A: env fallback mode, no pointer file (GIT_DIR set by harness)"; else before=$(cat "$W/.git")
$K proto evil rw 'echo "gitdir: /tmp/x" > /work/.git 2>&1; rm -f /work/.git 2>&1; mv /work/.git /work/g 2>&1; echo done'
if [ "$(cat "$W/.git")" = "$before" ]; then res A2 "BLOCKED (ro bind on file; rm/mv EBUSY)"; else res A2 "NOT BLOCKED"; fi; fi

echo "### A3 hooks + core.fsmonitor in shadow config"; fresh; rm -f "$P"/PWNED-*
HOSTMARK="$P/PWNED-HOST"
$K proto evil rw "git config core.fsmonitor 'touch /bundles/RAN-IN-EXPORT-CONTAINER; touch $HOSTMARK-fsmon; false' && git config core.hooksPath /shadow/task-1.git/hooks && for h in pre-commit post-commit post-checkout reference-transaction pre-auto-gc; do printf '#!/bin/sh\ntouch $HOSTMARK-%s 2>/dev/null; touch /work/.hookran-%s\n' \$h \$h > /shadow/task-1.git/hooks/\$h; chmod +x /shadow/task-1.git/hooks/\$h; done; git config alias.bundle '!touch $HOSTMARK-alias'; git config core.pager 'touch $HOSTMARK-pager'; echo x > a3.txt; git add a3.txt; git commit -qm a3; ls -a /work | grep hookran"
$K export; ls "$P/bundles"; $K gate; $K push-stub
if ls "$P"/PWNED-* 2>/dev/null; then res A3 "NOT BLOCKED (host marker exists)"; else res A3 "BLOCKED: on host (no PWNED-HOST* marker after export+gate+push-stub; hooks only ran inside agent container)"; fi

echo "### A4 commit touching .github/"; fresh
$K proto evil rw 'echo evil >> .github/ci.yml && git commit -qam a4'; $K export >/dev/null; gate_expect_fail A4 'forbidden path'
echo "### A4b AGENTS.md and .pi/"; fresh
$K proto evil rw 'mkdir .pi && echo x > .pi/s && echo y >> AGENTS.md && git add -A && git commit -qm a4b'; $K export >/dev/null; gate_expect_fail A4b 'forbidden path'

echo "### A5 symlink to /etc/passwd"; fresh
$K proto evil rw 'ln -s /etc/passwd pw && git add pw && git commit -qm a5'; $K export >/dev/null; gate_expect_fail A5 'symlink'

echo "### A6 huge patch (3MB random)"; fresh
$K proto evil rw 'head -c 3000000 /dev/urandom | base64 > big.txt && git add big.txt && git commit -qm a6'; $K export >/dev/null; gate_expect_fail A6 'bundle [0-9]+ >'
echo "### A6b many lines but small bundle (compressible)"; fresh
$K proto evil rw 'seq 1 20000 > lines.txt && git add lines.txt && git commit -qm a6b'; $K export >/dev/null; gate_expect_fail A6b 'lines >'

echo "### A7 extra branch/tag in bundle (handcrafted)"; fresh
$K proto evil rw 'echo z > z && git add z && git commit -qm a7 && git branch evil && git tag v666'
M=$(cat "$P/task-1.base")
$D run --rm --network none --user "$(id -u):$(id -g)" -v "$R/.git/objects:/base/objects:ro" -v "$S:/s:ro" -v "$P/bundles:/bundles" keel-git git --git-dir=/s bundle create /bundles/task-1.bundle refs/heads/task-1 refs/heads/evil refs/tags/v666 "^$M"
gate_expect_fail A7 'refs in bundle'
echo "  A7b: only a different branch name"; $D run --rm --network none --user "$(id -u):$(id -g)" -v "$R/.git/objects:/base/objects:ro" -v "$S:/s:ro" -v "$P/bundles:/bundles" keel-git git --git-dir=/s bundle create /bundles/task-1.bundle refs/heads/evil "^$M"
gate_expect_fail A7b 'refs in bundle'

echo "### A8 bundle based on old main"; fresh
$K proto a rw 'echo q > q && git add q && git commit -qm a8'; $K export >/dev/null
(cd "$R" && echo v2 >> app.txt && git -c user.name=h -c user.email=h@x commit -qam "main moves")
gate_expect_fail A8 'bundle base|merge-base'
echo "### A8b bundle with full history (no prerequisite)"; fresh
$K proto a rw 'echo q > q && git add q && git commit -qm a8b'
$D run --rm --network none --user "$(id -u):$(id -g)" -v "$R/.git/objects:/base/objects:ro" -v "$S:/s:ro" -v "$P/bundles:/bundles" keel-git git --git-dir=/s bundle create /bundles/task-1.bundle refs/heads/task-1
gate_expect_fail A8b 'bundle base|merge-base'

echo "### A9 reviewer role commits (ro mounts)"; fresh; before=$(cd "$S" && find . -type f | sort | fingerprint)
$K proto reviewer ro 'cat app.txt; echo r > review.txt 2>&1; git commit --allow-empty -qm "reviewer" 2>&1; git update-ref refs/heads/task-1 HEAD~0 2>&1; mkdir -p /tmp/report && echo "finding: ok" > /tmp/report/r.md && echo wrote-tmp-only'
after=$(cd "$S" && find . -type f | sort | fingerprint)
if [ "$before" = "$after" ] && [ ! -e "$W/review.txt" ]; then res A9 "BLOCKED (work+shadow ro; no change in shadow)"; else res A9 "NOT BLOCKED"; fi

echo "### A10 gc in repo while task active"; fresh
(cd "$R" && git checkout -qb side && echo s > s && git add s && git -c user.name=h -c user.email=h@x commit -qm side && git checkout -q main)
SIDE=$(git -C "$R" rev-parse side)
$K proto a rw "git update-ref refs/heads/task-1 $SIDE && git checkout -qf task-1 && echo t > t && git add t && git commit -qm on-side && echo ok"
git -C "$R" branch -qD side; git -C "$R" reflog expire --all --expire=now --expire-unreachable=now
echo "  [guard] keel.sh repo-gc / repo-prune while task dir exists:"; $K repo-gc; g1=$?; echo "  rc=$g1"; $K repo-prune; g2=$?; echo "  rc=$g2"
echo "  [config] plain 'git gc' (bypassing harness) with gc.pruneExpire=never:"; git -C "$R" gc -q
plain=$($K proto chk ro 'git log --oneline -1 >/dev/null 2>&1 && echo shadow-intact || echo SHADOW-BROKEN'); echo "$plain"
echo "  [bypass] explicit 'git gc --prune=now' outside the harness:"; git -C "$R" gc -q --prune=now
$K proto chk ro 'git log --oneline -1 >/dev/null 2>&1 && echo shadow-intact || echo SHADOW-BROKEN'
if [ $g1 != 3 ] || [ $g2 != 3 ]; then res A10 "NOT BLOCKED (guard did not refuse: repo-gc rc=$g1 repo-prune rc=$g2)"
elif ! echo "$plain" | grep -q shadow-intact; then res A10 "NOT BLOCKED (plain git gc broke the shadow: check gc.pruneExpire/reflog config)"
else res A10 "PARTIAL: guard REFUSES repo-gc/prune while tasks exist; plain git gc safe via gc.pruneExpire=never; explicit 'git gc --prune=now'/'git prune' run by hand outside the harness STILL breaks the shadow (residual, procedural)"; fi
echo "### A10b guard: moving main backwards while task active"; fresh
OLD=$(git -C "$R" rev-parse main); (cd "$R" && echo v2 >> app.txt && git -c user.name=h -c user.email=h@x commit -qam v2); NEW=$(git -C "$R" rev-parse main)
$K set-main "$OLD"; rb=$?; echo "  rc=$rb main=$(git -C "$R" rev-parse --short main)"
(cd "$R" && git -c user.name=h -c user.email=h@x commit -q --allow-empty -m v3); FF=$(git -C "$R" rev-parse main); git -C "$R" update-ref refs/heads/main "$NEW"
$K set-main "$FF"; echo "  ff rc=$?"
$K cleanup >/dev/null; $K set-main "$OLD"; echo "  backwards with no task: rc=$?"
if [ $rb = 3 ]; then res A10b "BLOCKED (non-ff main refused while task active; ff and no-task allowed)"; else res A10b "NOT BLOCKED"; fi

echo "### A11 root-owned files"; fresh
echo "  with --user (normal):"; $K proto a rw 'echo u > u && git add u && git commit -qm u; id -u'; find "$P" ! -user "$(id -u)" | head -3; n11=$(find "$P" ! -user "$(id -u)" | wc -l | tr -d ' '); echo "  count=$n11"
cu=$($K proto idchk ro 'id -u'); cu=$(echo "$cu" | tail -1); echo "  container uid=$cu host uid=$(id -u)"
echo "  negative control: container WITHOUT --user writes into /work and shadow:"
$D run --rm --network none -v "$W:/work" -v "$S:/s" keel-git sh -c 'touch /work/rootfile /s/objects/rootobj'
ls -l "$W/rootfile"; $K export >/dev/null
if is_darwin; then $K gate | grep -E "GATE (WARN|PASS|FAIL)"; res A11-detect "N/A: Darwin virtiofs maps ownership to the host user; gate only warns"; else gate_expect_fail A11-detect 'foreign-owned'; fi
$D run --rm --network none -v "$P:/p" keel-git chown -R "$(id -u):$(id -g)" /p
[ "$(find "$P" ! -user "$(id -u)" | wc -l)" = 0 ] && echo "  repaired via chown container"
if [ "$n11" = 0 ] && [ "$cu" = "$(id -u)" ]; then res A11 "BLOCKED by --user uid:gid (container uid = host uid, 0 foreign files)"; else res A11 "NOT BLOCKED (foreign files=$n11, container uid=$cu)"; fi


echo "### A12 hook planted by role A must not run in role B or export"; fresh; rm -f "$W"/.mark-*
$K proto A rw 'mkdir -p /work/.evilhooks; for h in pre-commit post-commit reference-transaction post-checkout; do printf "#!/bin/sh\ntouch /work/.mark-\$(basename \$0)-\$KEEL_ROLE 2>/dev/null; touch /bundles/.mark-export-\$(basename \$0) 2>/dev/null; true\n" | tee /shadow/task-1.git/hooks/$h /work/.evilhooks/$h >/dev/null; chmod +x /shadow/task-1.git/hooks/$h /work/.evilhooks/$h; done
git config core.fsmonitor "touch /work/.mark-fsmon; touch /bundles/.mark-export-fsmon; false"; git config core.hooksPath /work/.evilhooks
echo a > a12 && git add a12 && KEEL_ROLE=A git commit -qm A-same-container; echo "same-container markers: $(ls -a /work | grep -c mark)"
echo "--- attacker unsets env in own shell (expected to work for itself only):"; (unset GIT_CONFIG_PARAMETERS; echo b >> a12; KEEL_ROLE=Aself git commit -qam A-self); ls -a /work | grep mark'
rm -f "$W"/.mark-*; echo "  host removed role A self-markers; work-tree hooks dir remains: $(find "$W/.evilhooks" -mindepth 1 -maxdepth 1 | wc -l | tr -d " ") files"
b12=$($K proto B rw 'echo cfg=$(grep -c -E "fsmonitor|hooksPath" /shadow/task-1.git/config) hooks=$(ls /shadow/task-1.git/hooks | wc -l); echo c > b12 && git add b12 && KEEL_ROLE=B git commit -qm B && git status --short >/dev/null; ls -a /work | grep mark || echo no-markers-in-B'); echo "$b12"
$K export >/dev/null; find "$P/bundles" -maxdepth 1 -name "*mark*" | grep . || echo "no markers from export"
if find "$W" "$P/bundles" -maxdepth 1 -name "*mark*" | grep -q .; then res A12 "NOT BLOCKED (hook/fsmonitor marker found)"
elif ! echo "$b12" | grep -q 'cfg=0 hooks=0'; then res A12 "NOT BLOCKED (role A's shadow config/hooks survived into role B: reset_shadow not effective)"
else res A12 "BLOCKED (reset config+hooks before B/export; GIT_CONFIG_PARAMETERS forced off; work-tree hooks dir inert)"; fi
echo "### A12b forced git safety config inside every role"
out=$($K proto cfg ro 'echo hp=$(git config core.hooksPath) fm=$(git config core.fsmonitor)'); echo "$out"
if echo "$out" | grep -q 'hp=/dev/null fm=false'; then res A12b "BLOCKED (GIT_CONFIG_PARAMETERS forces hooksPath=/dev/null, fsmonitor=false)"; else res A12b "NOT BLOCKED (forced git config missing: $out)"; fi

echo "### H1 mount / chown / privilege"; fresh
out=$($K proto h rw 'mkdir -p /tmp/x; mount -t tmpfs t /tmp/x 2>&1 && echo MOUNT-OK; chown 0:0 /work/app.txt 2>&1 && echo CHOWN-OK; grep -E "^(CapEff|CapBnd|NoNewPrivs)" /proc/self/status; unshare -r true 2>&1 && echo UNSHARE-OK; true'); echo "$out"
if ! echo "$out" | grep -qE 'MOUNT-OK|CHOWN-OK|UNSHARE-OK' && echo "$out" | grep -q 'CapEff:.0000000000000000' && echo "$out" | grep -q 'CapBnd:.0000000000000000' && echo "$out" | grep -q 'NoNewPrivs:.1'; then res H1 "BLOCKED (mount/chown/unshare denied, CapEff=0, CapBnd=0, NoNewPrivs=1)"
elif [ "$(uname -s)" = Darwin ] && ! echo "$out" | grep -qE 'MOUNT-OK|UNSHARE-OK' && echo "$out" | grep -q 'CapEff:.0000000000000000' && echo "$out" | grep -q 'CapBnd:.0000000000000000' && echo "$out" | grep -q 'NoNewPrivs:.1'; then res H1 "BLOCKED (mount/unshare denied, CapEff=0, CapBnd=0, NoNewPrivs=1; chown on a Docker Desktop bind mount is emulated by virtiofs and does not change host ownership)"
else res H1 "NOT BLOCKED"; fi
echo "### H2 pids controller"
run_h2 || exit $?
echo "### H5 cpu limit"
cm=$($K proto cchk ro 'cat /sys/fs/cgroup/cpu.max 2>/dev/null || echo unknown'); cm=$(echo "$cm" | tail -1); echo "  cpu.max=$cm"
case $cm in max*|unknown|'') res H5 "NOT BLOCKED (no cpu quota: $cm)";; *) res H5 "CONTAINED (cpu quota $cm)";; esac
echo "### H3 memory limit"; fresh
run_h3 || true
echo "### H4 write outside mounts"; fresh
out=$($K proto w rw 'n=0; for f in /etc/x /usr/x /root/x /x /var/x /home/x /base/objects/x; do touch $f 2>/dev/null && n=$((n+1)); done; echo outside-writes=$n; echo rootfs=$(grep " / " /proc/mounts | tail -1 | cut -d" " -f4 | cut -d, -f1); dd if=/dev/zero of=/tmp/big bs=1M count=100 2>/dev/null; echo tmp-bytes=$(stat -c %s /tmp/big)'); echo "$out"
if echo "$out" | grep -q 'outside-writes=0' && echo "$out" | grep -q 'rootfs=ro' && [ "$(echo "$out" | sed -n 's/tmp-bytes=//p')" -le 67108864 ]; then res H4 "BLOCKED (rootfs mounted ro, 0 writes outside mounts; /tmp capped at 64 MiB)"; else res H4 "NOT BLOCKED"; fi

echo "### A4c forbidden-path variants: case fold, rename into .github/, exec bit on forbidden file"
for v in 'mkdir -p .GitHub/workflows && echo x > .GitHub/workflows/w.yml && git add -A && git commit -qm case' \
         'mkdir -p .github && git mv app.txt .github/app.txt && git commit -qm rename' \
         'chmod +x .github/ci.yml && git add -A && git commit -qm exec' \
         'echo y >> Agents.MD 2>/dev/null; cp AGENTS.md agents.md; git add -A && git commit -qm agents-case'; do
  fresh; $K proto evil rw "$v" >/dev/null 2>&1; $K export >/dev/null 2>&1; o=$($K gate 2>&1); echo "$o" | grep -q 'forbidden path' || { a4c="NOT BLOCKED ($v: $(echo "$o" | tail -1))"; break; }; a4c=ok; done
if [ "$a4c" = ok ]; then res A4c "BLOCKED (case-insensitive forbidden paths; rename and mode-only change both caught)"; else res A4c "$a4c"; fi
echo "### A6c many small files (0 lines each)"; fresh
$K proto evil rw 'mkdir m && i=0; while [ $i -lt 2000 ]; do : > m/f$i; i=$((i+1)); done; git add m && git commit -qm many'; $K export >/dev/null; gate_expect_fail A6c 'files changed >'
echo "### A13 bad date on an ancestor of main (not in the bundle)"; fresh
M0=$(git -C "$R" rev-parse main)
TREE=$(git -C "$R" rev-parse 'HEAD^{tree}')
B=$(printf "tree %s\nparent %s\nauthor agent <a@x> notadate\ncommitter agent <a@x> 1700000000 +0000\n\nbad\n" "$TREE" "$M0" | git -C "$R" hash-object -t commit -w --literally --stdin)
M1=$(GIT_AUTHOR_NAME=h GIT_AUTHOR_EMAIL=h@x GIT_AUTHOR_DATE='1700000000 +0000' GIT_COMMITTER_NAME=h GIT_COMMITTER_EMAIL=h@x GIT_COMMITTER_DATE='1700000000 +0000' git -C "$R" commit-tree "$TREE" -p "$B" -m base)
git -C "$R" update-ref refs/heads/main "$M1"
printf '%s\n' "$M1" > "$P/task-1.base"
$K proto evil rw "git update-ref refs/heads/task-1 $M1 && git checkout -qf task-1 && echo c > c13 && git add c13 && git commit -qm a13"
$K export >/dev/null; gate_expect_fail A13 'fetch/fsck'
echo "### A14 submodule / gitlink entry"; fresh
$K proto evil rw 'git update-index --add --cacheinfo 160000,$(git rev-parse HEAD),sub && git commit -qm gitlink'; $K export >/dev/null; gate_expect_fail A14 'submodule|forbidden path'
echo "### A15 commit with a substituted author identity"; fresh
$K proto evil rw 'echo s > s15 && git add s15 && git commit -qm a15 --author="Some Maintainer <maintainer@example.com>"'; $K export >/dev/null; gate_expect_fail A15 'identity'
echo "### A16 push stub pushes exactly the gated commit to exactly one branch"; fresh
$K proto a rw 'echo p > p16 && git add p16 && git commit -qm p16' >/dev/null; $K export >/dev/null; $K gate >/dev/null
inc=$(git -C "$P/gate/task-1.git" rev-parse refs/keel/incoming/task-1 2>/dev/null); ps=$($K push-stub); echo "$ps"
cmd=$(echo "$ps" | sed -n 's/.*would run: \(.*\) ; open PR.*/\1/p'); refs=${cmd##* push origin }
if [ -n "$inc" ] && [ "$(echo "$ps" | grep -c 'push ')" = 1 ] && [ "$refs" = "$inc:refs/heads/agent/task-1" ]; then res A16 "BLOCKED (single refspec <gated sha>:refs/heads/agent/task-1; no --all/--mirror/tags)"; else res A16 "NOT BLOCKED (stub pushes: $refs)"; fi

echo "### A17 forbidden path with a space (awk \$NF split)"; fresh
$K proto evil rw 'mkdir -p .github/workflows && echo x > ".github/workflows/evil x.yml" && git add -A && git commit -qm a17'; $K export >/dev/null; gate_expect_fail A17 'forbidden path'
echo "### A17b forbidden path with UTF-8 (git C-quotes it without -z)"; fresh
$K proto evil rw 'mkdir -p .github/workflows && echo x > ".github/workflows/$(printf "\303\251").yml" && git add -A && git commit -qm a17b'; $K export >/dev/null; gate_expect_fail A17b 'forbidden path'
echo "### A17c forbidden path with a tab and a double quote"; fresh
$K proto evil rw 'mkdir -p .github && echo x > ".github/$(printf "a\tb\"c").yml" && git add -A && git commit -qm a17c'; $K export >/dev/null; gate_expect_fail A17c 'forbidden path'
echo "### A18 nested docs/AGENTS.md"; fresh
$K proto evil rw 'mkdir -p docs && echo r > docs/AGENTS.md && git add -A && git commit -qm a18'; $K export >/dev/null; gate_expect_fail A18 'forbidden path'
echo "### A18b Pi process paths, one path per run"; miss=
for f in .pi/SYSTEM.md .pi/extensions/x.ts .pi/mcp.json .agents/skills/a/SKILL.md pkg/.pi/SYSTEM.md apps/.agents/skills/x/SKILL.md sub/AGENTS.override.md sub/claude.md CLAUDE.md CODEOWNERS .shellcheckrc lib/.gitmodules setup/keel.sh scripts/check.sh; do fresh
  $K proto evil rw "mkdir -p \"\$(dirname '$f')\" && echo x > '$f' && git add -A && git commit -qm a18b" >/dev/null; $K export >/dev/null
  $K gate 2>&1 | grep -q 'GATE FAIL: forbidden path' || miss="$miss $f"; done
fresh
$K proto evil rw 'mkdir -p setup && echo x > setup/README.md && echo y > setup/TESTING.md && git add -A && git commit -qm a18b-docs' >/dev/null; $K export >/dev/null
$K gate 2>&1 | grep -q 'GATE PASS' || miss="$miss setup-docs"
if [ -z "$miss" ]; then res A18b "BLOCKED (14/14 process paths: rule names anywhere, .pi/ and .agents/ at any depth, setup/ scripts/; setup/README.md and setup/TESTING.md are not forbidden)"; else res A18b "NOT BLOCKED:$miss"; fi
echo "### A19 shadow config replaced by a symlink to a host file"; fresh
echo victim > "$P/victim"
$K proto evil rw "rm /shadow/task-1.git/config && ln -s '$P/victim' /shadow/task-1.git/config && echo planted" ; $K reset-shadow 2>&1 | tail -1
if [ "$(cat "$P/victim")" = victim ] && [ ! -L "$P/shadow/task-1.git/config" ]; then res A19 "BLOCKED (reset_shadow unlinks before writing; host file untouched)"; else res A19 "NOT BLOCKED (victim: $(head -1 "$P/victim"))"; fi
echo "### A19b shadow objects/info replaced by a symlink to a host dir"; fresh
mkdir -p "$P/victimdir"
$K proto evil rw "rm -rf /shadow/task-1.git/objects/info && ln -s '$P/victimdir' /shadow/task-1.git/objects/info && echo planted"; out=$($K reset-shadow 2>&1); rc=$?; echo "$out" | tail -1
if [ ! -e "$P/victimdir/alternates" ] && [ $rc -ne 0 ] && echo "$out" | grep -q 'shadow tampered'; then res A19b "BLOCKED (refused: $(echo "$out" | tail -1))"; else res A19b "NOT BLOCKED (rc=$rc, host dir: $(ls "$P/victimdir"))"; fi
echo "### A20 nested .git directory committed as content"; fresh
$K proto evil rw 'b=$(echo "[core]" | git hash-object -w --stdin) && g=$(printf "100644 blob %s\tconfig\n" $b | git mktree --missing) && s=$(printf "040000 tree %s\t.git\n" $g | git mktree --missing) && r=$( (git ls-tree HEAD; printf "040000 tree %s\tsub\n" $s) | git mktree --missing) && c=$(echo a20 | git commit-tree $r -p HEAD) && git update-ref refs/heads/task-1 $c && git ls-tree -r --name-only $c | grep git/'
$K export >/dev/null; gate_expect_fail A20 'nested .git|fetch/fsck'
echo "### A21 agent rewrites test.sh to always pass and breaks the product"; fresh
$K proto evil rw 'printf "#!/bin/sh\necho TESTS-OK\n" > test.sh && echo broken > app.txt && git commit -qam a21'; $K export >/dev/null; gate_expect_fail A21 'tests \(main:'
echo "### A22 merge commit parking an orphan history"; fresh
$K proto evil rw 'o=$(echo o > /tmp/o && git hash-object -w /tmp/o) && t=$(printf "100644 blob %s\to\n" $o | git mktree) && orph=$(echo orphan | git commit-tree $t) && git merge -q -s ours --allow-unrelated-histories -m a22 $orph && git log --oneline | head -3'
$K export >/dev/null; gate_expect_fail A22 'merge commit|orphan'
echo "### A22b merge of two branches both based on main"; fresh
$K proto evil rw 'git checkout -qb side && echo s > s22 && git add s22 && git commit -qm side && git checkout -q task-1 && echo m > m22 && git add m22 && git commit -qm main22 && git merge -q --no-edit side && git log --oneline --graph | head -5'
$K export >/dev/null; gate_expect_fail A22b 'merge commit'

echo "### SEC-H1 clean bundle has no secret"
fresh
$K proto ok rw 'echo ok > ok.txt && git add ok.txt && git commit -qm clean' >/dev/null
$K export >/dev/null
out=$($K gate 2>&1); rc=$?
echo "$out" | tail -2
if [ "$rc" -eq 0 ] && printf '%s\n' "$out" | grep -q 'GATE PASS'; then res SEC-H1 "BLOCKED (clean bundle)"; else res SEC-H1 "NOT BLOCKED"; fi
echo "### SEC-03 secret shape in the change"
fresh
$K proto evil rw 'printf "%s\n" "ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE" > leak.txt && git add leak.txt && git commit -qm sec' >/dev/null
$K export >/dev/null
gate_expect_fail SEC-03 'secret'
echo "### SEC-04 inline allow comment"
fresh
$K proto evil rw 'printf "%s # gitleaks:allow\n" "ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE" > leak.txt && git add leak.txt && git commit -qm allowc' >/dev/null
$K export >/dev/null
gate_expect_fail SEC-04 'secret'
echo "### SEC-05 product ignore file"
fresh
$K proto evil rw 'printf "%s\n" "ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE" > leak.txt; printf "%s\n" "leak.txt:keel-github-pat:1" > .gitleaksignore; git add leak.txt .gitleaksignore && git commit -qm ign' >/dev/null
$K export >/dev/null
gate_expect_fail SEC-05 'secret'
echo "### N1 network from agent container"; fresh
out=$($K proto net rw 'ls /sys/class/net | tr "\n" " "; echo; wget -q -T 5 -O- http://1.1.1.1 >/dev/null 2>&1 && echo NET-OK; nslookup github.com >/dev/null 2>&1 && echo DNS-OK; true'); echo "$out"
if echo "$out" | grep -qE 'NET-OK|DNS-OK'; then res N1 "NOT BLOCKED"; else res N1 "BLOCKED (only $(echo "$out" | sed -n 2p)interfaces; no HTTP, no DNS)"; fi
echo "### N2 host token does not leak into containers"; fresh
out=$(GH_TOKEN=fake-doctor-canary GITHUB_TOKEN=fake-doctor-canary BOT_GH_TOKEN=fake-doctor-canary $K proto tok rw 'env | grep -cE "^(GH_|GITHUB_|BOT_GH_TOKEN)" ; grep -rl fake-doctor-canary /proc/1/environ 2>/dev/null | wc -l'); echo "$out"
if [ "$(echo "$out" | sed -n 2p)" = 0 ] && [ "$(echo "$out" | sed -n 3p)" = 0 ]; then res N2 "BLOCKED (token vars set on host are absent in container)"; else res N2 "NOT BLOCKED"; fi

bash "$HERE/test-egress.sh" || exit 1
bash "$HERE/visibility-suite.sh" || exit 1
$K cleanup >/dev/null; rm -rf "$P"; echo "### done"
