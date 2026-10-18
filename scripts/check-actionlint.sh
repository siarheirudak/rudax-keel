#!/usr/bin/env bash
# Download the pinned actionlint release, check its checksum, and lint workflows.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

version=1.7.12
checksum=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8
tarball="actionlint_${version}_linux_amd64.tar.gz"
url="https://github.com/rhysd/actionlint/releases/download/v${version}/${tarball}"

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

curl -fsSL -o "${tmpdir}/${tarball}" "$url"
if ! printf '%s  %s\n' "$checksum" "${tmpdir}/${tarball}" | sha256sum -c - >/dev/null; then
  printf 'how to fix: the actionlint download %s did not match the pinned sha256; do not run it\n' "$tarball" >&2
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
