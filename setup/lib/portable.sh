# shellcheck shell=bash
# Portable helpers for keel scripts. Works on bash 3.2 (macOS /bin/bash) and BSD or GNU userland.
# Source it; do not execute. No bash-4 features (no assoc arrays, mapfile, ${v,,}, |&, &>>, wait -n).
KEEL_OS=$(uname -s)
is_darwin(){ [ "$KEEL_OS" = Darwin ]; }
# file size in bytes (no stat -c / stat -f split)
file_size(){ wc -c < "$1" | tr -d ' '; }
# absolute physical path of an existing directory (no readlink -f / realpath)
abs_dir(){ (cd "$1" 2>/dev/null && pwd -P); }
# content fingerprint of stdin (cksum is POSIX; md5sum/shasum differ by OS)
fingerprint(){ cksum | awk '{print $1"-"$2}'; }
# version compare: ver_ge 2.47.3 2.30 -> true (no sort -V)
ver_ge(){ awk -v a="$1" -v b="$2" 'BEGIN{n=split(a,x,".");m=split(b,y,".");for(i=1;i<=(n>m?n:m);i++){p=x[i]+0;q=y[i]+0;if(p>q)exit 0;if(p<q)exit 1}exit 0}'; }
# run with a timeout: GNU timeout, Homebrew gtimeout, else perl alarm (perl ships with macOS)
run_timeout(){ local s=$1; shift
  if command -v timeout >/dev/null 2>&1; then timeout "$s" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@"
  else perl -e 'alarm shift @ARGV; exec @ARGV or die "exec: $!"' "$s" "$@"; fi; }
# free GiB on the filesystem holding $1 (df -Pk is POSIX on both)
free_gib(){ df -Pk "$1" | awk 'NR==2{print int($4/1024/1024)}'; }
# Docker Desktop? (macOS/Windows VM, or Docker Desktop for Linux)
docker_is_desktop(){ $DOCKER info --format '{{.OperatingSystem}}' 2>/dev/null | grep -qi 'docker desktop'; }
# Docker Desktop only bind-mounts from shared dirs. Defaults: /Users /Volumes /private /tmp /var/folders
# Extra shares you added in Docker Desktop: KEEL_SHARED_DIRS=/opt/x:/data
path_is_shared(){ is_darwin || return 0; local d IFS=:
  for d in /Users /Volumes /private /tmp /var/folders ${KEEL_SHARED_DIRS:-}; do case "$1" in "$d"|"$d"/*) return 0;; esac; done; return 1; }
docker_hint(){ if is_darwin; then echo "Docker Desktop is not running or not reachable. Start it (open -a Docker), wait for 'Engine running', then retry."
  else echo "Docker daemon not reachable. Start it (sudo systemctl start docker) or set DOCKER=\"sudo docker\"."; fi; }
