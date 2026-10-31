#!/usr/bin/env bash
# A visibility result id that is absent must make keel-doctor --score-log exit NOT READY.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)
DOC=$SETUP/keel-doctor.sh
ids=$(sed -n 's/^ATK_IDS="\(.*\)"/\1/p' "$DOC")
[ -n "$ids" ] || { echo "ATK_IDS missing" >&2; exit 1; }
case " $ids " in
  *" V-A10-hardlink "*) ;;
  *) echo "V-A10-hardlink is not required" >&2; exit 1;;
esac
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
full=$tmp/full.log
miss=$tmp/miss.log
: > "$full"
: > "$miss"
for id in $ids; do
  printf 'RESULT %s: BLOCKED (score)\n' "$id" >> "$full"
  if [ "$id" != "V-A10-hardlink" ]; then
    printf 'RESULT %s: BLOCKED (score)\n' "$id" >> "$miss"
  fi
done
while IFS= read -r name; do
  [ -n "$name" ] || continue
  unset "$name"
done <<EOF
$(env | cut -d= -f1 | grep -E '^(GH_|GITHUB_)|^BOT_GH_TOKEN$' || true)
EOF
export KEEL_ROOT=$tmp/root
export KEEL_REPO=$KEEL_ROOT/repo
"$SETUP/keel.sh" init-repo >/dev/null
miss_out=$tmp/miss.out
full_out=$tmp/full.out
set +e
"$DOC" --score-log "$miss" >"$miss_out" 2>&1
miss_ec=$?
"$DOC" --score-log "$full" >"$full_out" 2>&1
full_ec=$?
set +e
fail=0
if [ "$miss_ec" -eq 0 ] || ! grep -q 'NOT READY' "$miss_out" || ! grep -q 'ATK-V-A10-hardlink' "$miss_out" || ! grep -q 'no result in log' "$miss_out"; then
  echo "missing V-A10-hardlink did not make doctor NOT READY (exit $miss_ec)" >&2
  cat "$miss_out" >&2
  fail=1
fi
if [ "$full_ec" -ne 0 ] || grep -q 'NOT READY' "$full_out"; then
  echo "complete result list was not ready (exit $full_ec)" >&2
  cat "$full_out" >&2
  fail=1
fi
if [ "$fail" -ne 0 ]; then exit 1; fi
echo "doctor ids: missing V-A10-hardlink is NOT READY; full list is ready"
