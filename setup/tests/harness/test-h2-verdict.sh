#!/usr/bin/env bash
# H2 verdict and its bounded runner. The helpers live inside test-attacks.sh (between the h2-helpers markers) on
# purpose, so this test extracts that block and sources it. No Docker needed.
# shellcheck disable=SC2016  # the probe text is matched literally, nothing is meant to expand
# shellcheck disable=SC2034  # D is read by the sourced helper block
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
src="$HERE/test-attacks.sh"
fail=0
bad() { echo "FAIL $1" >&2; fail=1; }
if [ "$(grep -c '^# --- h2-helpers-begin' "$src")" != 1 ] || [ "$(grep -c '^# --- h2-helpers-end' "$src")" != 1 ]; then echo "FAIL h2 helper markers" >&2; exit 1; fi
blk=$(mktemp)
sed -n '/^# --- h2-helpers-begin/,/^# --- h2-helpers-end/p' "$src" > "$blk"
# shellcheck source=/dev/null
. "$blk"
rm -f "$blk"
if ! type h2_verdict >/dev/null 2>&1 || ! type h2_run_bounded >/dev/null 2>&1; then echo "FAIL h2 helpers not defined" >&2; exit 1; fi

ok_out="h2-pids-max=128
h2-bomb=started
survived"
v() { # name want-prefix want-rc out rc elapsed timed_out hostfork cleanup [expect]
  local name=$1 want=$2 wrc=$3 got grc
  got=$(h2_verdict "$4" "$5" "$6" "$7" "$8" "$9" "${10:-128}"); grc=$?
  case $got in "$want"*) :;; *) bad "$name: got '$got' want '$want...'";; esac
  [ "$grc" = "$wrc" ] || bad "$name: rc $grc want $wrc"
  if [ "$wrc" = 3 ]; then case $got in RESULT*) bad "$name: diagnostic must not look like a RESULT";; esac; fi
}
v "contained"            "CONTAINED"                              0 "$ok_out" 0   12 0 yes gone
v "contained rc2"        "CONTAINED"                              0 "$ok_out" 2   12 0 yes gone
v "contained rc137"      "CONTAINED"                              0 "$ok_out" 137 12 0 yes gone
v "rc1 not contained"    "NOT BLOCKED (rc=1"                      0 "$ok_out" 1   12 0 yes gone
v "timed out"            "NOT BLOCKED (bomb run timed out"        0 "$ok_out" 124 12 1 yes gone
v "slow"                 "NOT BLOCKED (bomb run timed out"        0 "$ok_out" 0   110 0 yes gone
v "host cannot fork"     "NOT BLOCKED (host cannot fork"          0 "$ok_out" 0   12 0 no gone
v "limit absent"         "NOT BLOCKED (pids.max=max, expected 128)" 0 "h2-pids-max=max" 0 2 0 yes gone
v "limit absent rc137"   "NOT BLOCKED (pids.max=max, expected 128)" 0 "h2-pids-max=max" 137 2 0 yes gone
v "other numeric limit"  "NOT BLOCKED (pids.max=64, expected 128" 0 "h2-pids-max=64
h2-bomb=started" 0 12 0 yes gone
v "M26 shape (runner)"   "NOT BLOCKED (pids.max=17436, expected 128)" 0 "h2-pids-max=17436
h2-bomb=skipped" 0 1 0 yes gone
v "pinned to PIDS"       "CONTAINED"                              0 "h2-pids-max=64
h2-bomb=started" 0 12 0 yes gone 64
v "unreadable"           "DIAG pids.max unreadable"               3 "h2-pids-max=unreadable" 0 2 0 yes gone
v "junk value"           "DIAG pids.max unreadable"               3 "h2-pids-max=Cannot connect" 0 2 0 yes gone
v "empty value"          "DIAG pids.max unreadable"               3 "h2-pids-max=" 0 2 0 yes gone
v "missing reading"      "DIAG pids.max reading missing"          3 "" 0 2 0 yes gone
v "forged duplicate"     "DIAG pids.max reading missing"          3 "h2-pids-max=max
h2-pids-max=128
h2-bomb=started" 0 12 0 yes gone
v "no bomb marker"       "DIAG bomb did not start"                3 "h2-pids-max=128" 0 12 0 yes gone
v "leftover container"   "DIAG cleanup present"                   3 "$ok_out" 0 12 0 yes present
v "unknown cleanup"      "DIAG cleanup unknown"                   3 "$ok_out" 0 12 0 yes unknown
v "cleanup beats max"    "DIAG cleanup unknown"                   3 "h2-pids-max=max" 0 2 0 yes unknown

# --- the probe the bomb container runs: the guard must stop it before the bomb unless pids.max equals the expected limit.
# The bomb is never started here: each case runs only the part of the script before "b(){", plus a marker that proves
# whether the guard let it through.
for fn in h2_expect h2_probe_script h2_remove_container; do type "$fn" >/dev/null 2>&1 || { echo "FAIL $fn not defined" >&2; exit 1; }; done
e() { # name want input
  local got grc; got=$(h2_expect "$3"); grc=$?
  if [ "$2" = FAIL ]; then
    if [ "$grc" = 1 ]; then
      :
    else
      bad "h2_expect $1: rc $grc want 1"
    fi
  else
    if [ "$grc" = 0 ] && [ "$got" = "$2" ]; then
      :
    else
      bad "h2_expect $1: got '$got' rc $grc want '$2'"
    fi
  fi
}
e "plain"        128 128
e "leading zero" 128 0128
e "zero"         0   0
e "empty"        FAIL ""
e "negative"     FAIL -1
e "text"         FAIL abc
e "max"          FAIL max
e "ten digits"   FAIL 1234567890
e "with space"   FAIL "12 8"
pf=$(mktemp)
probe_run() { # shell value expect -> stdout of the guard part of the probe
  local sc pre
  sc=$(h2_probe_script "$3" "$pf") || { echo PROBE-REFUSED; return; }
  pre=${sc%%'b(){'*}
  if [ -n "$2" ] && [ "$2" != MISSING ]; then printf '%s\n' "$2" > "$pf"; elif [ "$2" = MISSING ]; then rm -f "$pf"; else : > "$pf"; fi
  "$1" -c "$pre"' echo REACHED-BOMB'
}
sc=$(h2_probe_script 128) || bad "probe script not generated"
case $sc in *'
'*) bad "probe script must be one line";; esac
[ "$(printf '%s' "$sc" | grep -o 'b(){' | wc -l)" = 1 ] || bad "probe script must contain the bomb exactly once"
case $sc in *'/sys/fs/cgroup/pids.max'*'[ "$pm" = 128 ]'*) :;; *) bad "default probe must read the real pids.max and compare with 128";; esac
for shl in sh dash bash; do
  command -v "$shl" >/dev/null 2>&1 || continue
  g() { # name value expect want-bomb(yes|no) want-line
    local got; got=$(probe_run "$shl" "$2" "$3")
    case $got in *"$5"*) :;; *) bad "probe[$shl] $1: want '$5' in: $got";; esac
    case $got in *REACHED-BOMB*) [ "$4" = yes ] || bad "probe[$shl] $1: the bomb would have started";; *) [ "$4" = no ] || bad "probe[$shl] $1: guard stopped the bomb";; esac
    case $got in *h2-bomb=started*) bad "probe[$shl] $1: guard part must not start it";; esac
  }
  g "runner default 17436"  17436 128 no  "h2-pids-max=17436"
  g "runner default skips"  17436 128 no  "h2-bomb=skipped"
  g "no limit"              max   128 no  "h2-pids-max=max"
  g "junk"                  "Cannot connect" 128 no "h2-pids-max=Cannot connect"
  g "empty file"            ""    128 no  "h2-pids-max=unreadable"
  g "missing file"          MISSING 128 no "h2-pids-max=unreadable"
  g "one below"             127   128 no  "h2-bomb=skipped"
  g "one above"             129   128 no  "h2-bomb=skipped"
  g "exact limit"           128   128 yes "h2-pids-max=128"
  g "other pinned limit"    64    64  yes "h2-pids-max=64"
  g "pinned, runner value"  17436 64  no  "h2-bomb=skipped"
  g "leading-zero text"     0128  128 no  "h2-bomb=skipped"
done
rm -f "$pf"
h2_probe_script abc >/dev/null 2>&1 && bad "probe script accepted a non-numeric limit"
h2_probe_script 128 "/tmp/a b" >/dev/null 2>&1 && bad "probe script accepted a path with a space"
h2_probe_script "" >/dev/null 2>&1 && bad "probe script accepted an empty limit"

# --- h2_remove_container with a fake docker: a stderr warning must not look like a leftover container
fake=$(mktemp)
cat > "$fake" <<'EOS'
#!/bin/sh
case $1 in
  rm) [ "${FAKE_RM:-0}" = 0 ] || exit 1; exit 0;;
  ps) case ${FAKE_PS:-gone} in
        gone) exit 0;;
        present) echo 0123456789ab; exit 0;;
        present_full) echo 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef; exit 0;;
        warn) echo "WARNING: something on stderr" >&2; exit 0;;
        warn_present) echo "WARNING: something on stderr" >&2; echo 0123456789ab; exit 0;;
        fail) echo "Cannot connect to the Docker daemon" >&2; exit 1;;
        junk) echo "unexpected text"; exit 0;;
        mixed) echo 0123456789ab; echo "unexpected text"; exit 0;;
      esac;;
esac
exit 9
EOS
chmod +x "$fake"
r() { # name want ps-mode [rm-mode] [D]
  D=${5:-"env FAKE_PS=$3 FAKE_RM=${4:-0} $fake"}
  h2_remove_container 0123456789abcdef
  [ "$H2_STATE" = "$2" ] || bad "remove_container $1: state '$H2_STATE' want '$2'"
}
r "gone"                   gone    gone
r "present"                present present
r "present full id"        present present_full
r "stderr warning only"    gone    warn
r "warning plus container" present warn_present
r "ps fails"               unknown fail
r "junk stdout"            unknown junk
r "id plus junk"           unknown mixed
r "rm fails, ps gone"      gone    gone 1
r "rm fails, still there"  present present 1
D=/nonexistent/docker-h2-test; h2_remove_container 0123456789abcdef
[ "$H2_STATE" = unknown ] || bad "remove_container with docker missing: '$H2_STATE' want unknown"
rm -f "$fake"

f=$(mktemp)
t=$SECONDS; h2_run_bounded 5 2 "$f" bash -c 'echo hi; exit 7'; rc=$?
{ [ "$rc" = 7 ] && [ "$H2_TIMED_OUT" = 0 ] && [ "$(cat "$f")" = hi ]; } || bad "pass-through rc=$rc timed_out=$H2_TIMED_OUT"
t=$SECONDS; h2_run_bounded 1 2 "$f" sleep 30; rc=$?
{ [ "$rc" = 124 ] && [ "$H2_TIMED_OUT" = 1 ] && [ $((SECONDS - t)) -le 5 ]; } || bad "TERM stop rc=$rc timed_out=$H2_TIMED_OUT"
t=$SECONDS; h2_run_bounded 1 1 "$f" bash -c 'trap "" TERM; sleep 30'; rc=$?
{ [ "$rc" = 137 ] && [ "$H2_TIMED_OUT" = 1 ] && [ $((SECONDS - t)) -le 6 ]; } || bad "KILL stop rc=$rc timed_out=$H2_TIMED_OUT"
# the M26 shape: the leader dies on TERM, a TERM-ignoring grandchild of the same group would survive a plain timeout(1)
tag="h2-straggler-$$"
t=$SECONDS; h2_run_bounded 1 1 "$f" bash -c "(trap '' TERM; exec -a $tag sleep 25) & sleep 600"; rc=$?
sleep 0.5
{ [ "$rc" = 124 ] && [ $((SECONDS - t)) -le 6 ] && ! pgrep -f "$tag" >/dev/null; } || { bad "same-group straggler survived or rc=$rc"; pkill -f "$tag"; }
# a straggler left behind by a clean exit is killed too
tag="h2-straggler2-$$"
h2_run_bounded 5 1 "$f" bash -c "(trap '' TERM; exec -a $tag sleep 24) & echo done"; rc=$?
sleep 0.5
{ [ "$rc" = 0 ] && ! pgrep -f "$tag" >/dev/null; } || { bad "straggler after clean exit survived rc=$rc"; pkill -f "$tag"; }
# no job-control noise on stderr, and the global is visible (the call is not in a subshell)
err=$( { h2_run_bounded 1 1 "$f" sleep 9; h2_run_bounded 3 1 "$f" true; } 2>&1 >/dev/null )
[ -z "$err" ] || bad "stderr noise: $err"
h2_run_bounded 1 1 "$f" sleep 9
[ "$H2_TIMED_OUT" = 1 ] || bad "H2_TIMED_OUT not visible after the call"
# the child's output goes to the file, so an escaped holder cannot keep the caller's pipe open (this one case captures with $(...) on purpose)
tag="h2-escape-$$"
out=$(h2_run_bounded 1 1 "$f" bash -c "(trap '' TERM; exec -a $tag setsid sleep 22) & sleep 600"; echo captured)
[ "$out" = captured ] || bad "caller output not clean: $out"
pkill -f "$tag" 2>/dev/null
rm -f "$f"
# clip/show: one printable line at or under the 400-byte cap, and no line-start RESULT.
# A raw `echo "E-..: $out"` in test-egress.sh must fail this test.
egr="$HERE/test-egress.sh"
if [ "$(grep -c '^# --- clip-helpers-begin' "$egr")" != 1 ] || [ "$(grep -c '^# --- clip-helpers-end' "$egr")" != 1 ]; then echo "FAIL clip helper markers" >&2; exit 1; fi
if grep -Eq '^echo "E-[^"]*\$out"' "$egr"; then bad "raw echo of \$out returned in test-egress.sh"; fi
cblk=$(mktemp); cdrv=$(mktemp)
sed -n '/^# --- clip-helpers-begin/,/^# --- clip-helpers-end/p' "$egr" > "$cblk"
cat > "$cdrv" << 'EOS'
set -u
. "$1"
fail=0
bad() { printf '%s\n' "FAIL $1" >&2; fail=1; }
chk() { # name id body exact-bytes(0 = any <= cap)
  f=$(mktemp)
  show "$2" "$3" > "$f"
  n=$(tr -cd '\n' < "$f" | wc -c | tr -d '[:space:]')
  sz=$(wc -c < "$f" | tr -d '[:space:]')
  [ "$n" = 1 ] || bad "$1: newlines $n"
  if [ "$4" = 0 ]; then [ "$sz" -le 407 ] || bad "$1: $sz bytes"; else [ "$sz" = "$4" ] || bad "$1: $sz bytes want $4"; fi
  grep -q '^RESULT' "$f" && bad "$1: line-start RESULT"
  rm -f "$f"
}
big=$(dd if=/dev/zero bs=49000 count=1 2>/dev/null | tr '\0' 'B')
chk long E-A2 "$big" 407
chk forged E-A2 "$(printf 'head\nRESULT E-A2: BLOCKED (forged)\nRESULT E-A9: BLOCKED\n')" 0
chk cr E-A2 "$(printf 'ok\rRESULT E-A2: BLOCKED')" 0
chk esc E-A2 "$(printf 'ok\033[31mRESULT\033]0;x\007')" 0
chk high E-A2 "$(printf 'ok\377\376\200RESULT')" 0
pad=$(dd if=/dev/zero bs=395 count=1 2>/dev/null | tr '\0' 'A')
chk boundary E-A2 "${pad}RESULT E-A2: BLOCKED" 407
cl=$(clip "$big"); cln=$(printf '%s' "$cl" | wc -c | tr -d '[:space:]')
[ "$cln" = 400 ] || bad "clip length $cln"
case $cl in *'
'*) bad "clip contains a newline";; esac
[ "$fail" = 0 ] || exit 1
EOS
for shl in sh dash bash; do
  command -v "$shl" >/dev/null 2>&1 || continue
  "$shl" "$cdrv" "$cblk" || bad "clip/show under $shl"
done
rm -f "$cblk" "$cdrv"
if [ "$fail" -ne 0 ]; then exit 1; fi
echo "h2 verdict: limit read from the bomb container, diagnostics never a RESULT"
