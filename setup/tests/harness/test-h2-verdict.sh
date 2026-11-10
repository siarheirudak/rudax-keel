#!/usr/bin/env bash
# H2 verdict and its bounded runner. The helpers live inside test-attacks.sh (between the h2-helpers markers) on
# purpose, so this test extracts that block and sources it. No Docker needed.
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
v "limit absent"         "NOT BLOCKED (no pids limit: pids.max=max" 0 "h2-pids-max=max" 0 2 0 yes gone
v "limit absent rc137"   "NOT BLOCKED (no pids limit"             0 "h2-pids-max=max" 137 2 0 yes gone
v "other numeric limit"  "NOT BLOCKED (pids.max=64, expected 128" 0 "h2-pids-max=64
h2-bomb=started" 0 12 0 yes gone
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
if [ "$fail" -ne 0 ]; then exit 1; fi
echo "h2 verdict: limit read from the bomb container, diagnostics never a RESULT"
