#!/usr/bin/env bash
# Turn an H3 probe into one result phrase.
# Contained only after memory.max matched and the allocator itself was OOM-killed.
# --memory-swap is set equal to --memory. memory.swap.max may still read "max"
# on a cgroup v2 host that does not account swap; that reading is not the verdict.
h3_mem_bytes() {
  local mem=$1 n
  case $mem in
    *g|*G) n=${mem%[gG]}; printf '%s\n' $((n * 1024 * 1024 * 1024));;
    *m|*M) n=${mem%[mM]}; printf '%s\n' $((n * 1024 * 1024));;
    *k|*K) n=${mem%[kK]}; printf '%s\n' $((n * 1024));;
    *) printf '%s\n' "$mem";;
  esac
}

h3_verdict() {
  local out=$1 rc=$2 oom=$3 expect=$4 max arc
  max=$(printf '%s\n' "$out" | sed -n 's/^mem-max=//p' | tail -1)
  if [ "$max" != "$expect" ] || ! printf '%s\n' "$out" | grep -qx 'mem-limit=present'; then
    printf '%s\n' "ERROR memory limit not applied"
    return 0
  fi
  arc=$(printf '%s\n' "$out" | sed -n 's/^alloc-rc=//p' | tail -1)
  if [ "$arc" = 137 ]; then
    printf '%s\n' "CONTAINED (allocator exit 137)"
    return 0
  fi
  # A 137 with no allocator status is the cgroup kill. Any other alloc-rc is not OOM.
  if [ -z "$arc" ] && { [ "$rc" = 137 ] || [ "$oom" = true ]; }; then
    printf '%s\n' "CONTAINED (container OOM)"
    return 0
  fi
  printf '%s\n' "NOT BLOCKED"
}
