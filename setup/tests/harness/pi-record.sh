#!/bin/sh
# Record the argv sent to the real pi binary, then exec it.
set -u
out=${PI_RECORD_ARGV:?}
: > "$out"
for arg in "$@"; do
  printf '%s\n' "$arg" >> "$out"
done
exec "$KEEL_PI_BIN" "$@"
