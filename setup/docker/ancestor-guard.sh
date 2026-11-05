#!/bin/sh
# Fail when an ancestor of ROOT/work holds a Pi context file.
# Pi walks from the working directory to filesystem /, not only to the git root.
set -u
guard_on=1 # ancestor-guard
if [ "$guard_on" != 1 ]; then
  exit 0
fi
root=${1:-}
if [ -z "$root" ] || [ ! -d "$root" ]; then
  echo "ancestor guard: root missing" >&2
  exit 1
fi
case $root in
  /) ;;
  */) root=${root%/} ;;
esac
work=${2:-$root/work}
dir=$(dirname "$work")
while true; do
  for name in AGENTS.md AGENTS.MD CLAUDE.md CLAUDE.MD; do
    if [ -e "$dir/$name" ] || [ -L "$dir/$name" ]; then
      echo "ancestor context file: $dir/$name" >&2
      exit 1
    fi
  done
  if [ "$dir" = "$root" ] || [ "$dir" = "/" ]; then
    break
  fi
  next=$(dirname "$dir")
  if [ "$next" = "$dir" ]; then
    break
  fi
  dir=$next
done
exit 0
