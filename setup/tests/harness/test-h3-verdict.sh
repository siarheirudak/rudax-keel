#!/usr/bin/env bash
# An unrelated exit 137 must not count as the memory limit containing the allocator.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=setup/tests/harness/h3-verdict.sh
. "$HERE/h3-verdict.sh"
expect=536870912
present="mem-max=$expect
mem-swap-max=$expect
mem-limit=present"
fail=0
check() {
  local name=$1 want=$2 got
  got=$(h3_verdict "$3" "$4" "$5" "$expect")
  if [ "$got" != "$want" ]; then
    echo "FAIL $name: got '$got' want '$want'" >&2
    fail=1
  fi
}
check "alloc 137" "CONTAINED (allocator exit 137)" "$present
alloc-rc=137" 0 false
check "docker 137 after limit" "CONTAINED (container OOM)" "$present" 137 false
check "oom flag after limit" "CONTAINED (container OOM)" "$present" 0 true
check "unrelated 137 after success" "NOT BLOCKED" "$present
alloc-rc=0" 137 true
check "other alloc rc" "NOT BLOCKED" "$present
alloc-rc=1" 137 false
check "137 without limit" "ERROR memory limit not applied" "mem-max=max
mem-limit=absent" 137 true
check "missing max" "ERROR memory limit not applied" "" 137 true
if [ "$(h3_mem_bytes 512m)" != "$expect" ]; then
  echo "FAIL bytes" >&2
  fail=1
fi
if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "h3 verdict: unrelated 137 is not contained"
