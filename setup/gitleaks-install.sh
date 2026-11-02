#!/usr/bin/env bash
# Install the pinned gitleaks binary into the user cache. The gate does not download.
# shellcheck shell=bash
set -eu
VER=8.30.1
case $(uname -m) in
  x86_64) asset=linux_x64; sum=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb;;
  aarch64|arm64) asset=linux_arm64; sum=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080;;
  *) echo "gitleaks install: unsupported arch $(uname -m)" >&2; exit 1;;
esac
dest=${KEEL_GITLEAKS_DIR:-$HOME/.cache/keel/gitleaks-$VER}
if [ -x "$dest/gitleaks" ] && [ "$(cat "$dest/VERSION" 2>/dev/null || true)" = "$VER" ]; then
  exit 0
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
name=gitleaks_${VER}_${asset}.tar.gz
curl -fsSL -o "$tmp/$name" "https://github.com/gitleaks/gitleaks/releases/download/v${VER}/${name}"
printf '%s  %s\n' "$sum" "$tmp/$name" | sha256sum -c -
tar -xzf "$tmp/$name" -C "$tmp" gitleaks
mkdir -p "$dest"
mv "$tmp/gitleaks" "$dest/gitleaks"
chmod 755 "$dest/gitleaks"
printf '%s\n' "$VER" > "$dest/VERSION"
"$dest/gitleaks" version >/dev/null
