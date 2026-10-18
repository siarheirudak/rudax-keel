#!/usr/bin/env bash
# Download the pinned actionlint release, check its checksum, and lint workflows.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

version=1.7.12
os_name=$(uname -s | tr '[:upper:]' '[:lower:]')
machine=$(uname -m)
case $machine in
  x86_64) arch=amd64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) arch=$machine ;;
esac
suffix="${os_name}_${arch}"
case $suffix in
  linux_amd64) checksum=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 ;;
  linux_arm64) checksum=325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6 ;;
  darwin_amd64) checksum=5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644 ;;
  darwin_arm64) checksum=aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f ;;
  *)
    printf 'actionlint skipped: no pinned binary for %s (linux/darwin and amd64/arm64 only)\n' "$suffix" >&2
    exit 0
    ;;
esac

tarball="actionlint_${version}_${suffix}.tar.gz"
url="https://github.com/rhysd/actionlint/releases/download/v${version}/${tarball}"

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

curl -fsSL -o "${tmpdir}/${tarball}" "$url"
sumfile="${tmpdir}/checksum"
printf '%s  %s\n' "$checksum" "${tmpdir}/${tarball}" >"$sumfile"
if command -v sha256sum >/dev/null 2>&1; then
  if ! sha256sum -c "$sumfile" >/dev/null; then
    printf 'how to fix: the actionlint download %s did not match the pinned sha256; do not run it\n' "$tarball" >&2
    exit 1
  fi
elif command -v shasum >/dev/null 2>&1; then
  if ! shasum -a 256 -c "$sumfile" >/dev/null; then
    printf 'how to fix: the actionlint download %s did not match the pinned sha256; do not run it\n' "$tarball" >&2
    exit 1
  fi
else
  printf 'how to fix: install sha256sum or shasum so the actionlint download can be checked\n' >&2
  exit 1
fi
tar -xzf "${tmpdir}/${tarball}" -C "$tmpdir" actionlint

set +e
out=$("$tmpdir/actionlint" -color 2>&1)
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  printf '%s\n' "$out" >&2
  files=$(printf '%s\n' "$out" | sed -n 's/^\(\.github\/workflows\/[^:]*\):.*/\1/p' | sort -u | paste -sd, -)
  if [[ -z $files ]]; then
    files=".github/workflows"
  fi
  printf 'how to fix: fix the actionlint findings in %s\n' "$files" >&2
  exit 1
fi
