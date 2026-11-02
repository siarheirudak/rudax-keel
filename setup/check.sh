#!/usr/bin/env bash
# Fail when a shell script the harness executes directly is not mode 100755.
# Modes come from `git ls-files -s`, not from the working tree.
# A direct execution is ./file.sh or "$HERE/file.sh" / "$SETUP/file.sh" used as
# a command. `bash file.sh` and a sourced file are not in that set.
set -u
mode_check=1 # script-mode
if [ "$mode_check" != 1 ]; then
  exit 0
fi

repo=
list_only=0
while [ "$#" -gt 0 ]; do
  case $1 in
    --repo)
      repo=${2:-}
      shift 2
      ;;
    --list)
      list_only=1
      shift
      ;;
    *)
      echo "ERROR: script mode: unknown argument" >&2
      exit 2
      ;;
  esac
done
if [ -z "$repo" ]; then
  repo=$(cd "$(dirname "$0")/.." && pwd)
fi

paths=$(python3 - "$repo" << 'PY'
import os, re, sys
root = sys.argv[1]
runners = []
wf = os.path.join(root, ".github", "workflows")
if os.path.isdir(wf):
    for name in sorted(os.listdir(wf)):
        if name.endswith((".yml", ".yaml")):
            runners.append(os.path.join(wf, name))
for rel in (
    "setup/tests/harness/run-tests.sh",
    "setup/tests/harness/test-doctor-ids.sh",
    "scripts/check.sh",
    "scripts/check-gate.sh",
):
    path = os.path.join(root, rel)
    if os.path.isfile(path):
        runners.append(path)

here_re = re.compile(r'"?\$HERE/([A-Za-z0-9_./-]+\.sh)"?')
setup_re = re.compile(r'"?\$SETUP/([A-Za-z0-9_./-]+\.sh)"?')
dot_re = re.compile(r'(?<![\w.])\./([A-Za-z0-9_./-]+\.sh)')

def skipped(prefix):
    text = prefix.rstrip()
    if text.endswith(("=", '="', "='")):
        return True
    return text.endswith(("bash", "source", "."))

found = set()
for path in runners:
    rel_runner = os.path.relpath(path, root).replace(os.sep, "/")
    here = os.path.dirname(rel_runner)
    for line in open(path, encoding="utf-8"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for rx, base in ((here_re, here), (setup_re, "setup"), (dot_re, "")):
            for match in rx.finditer(line):
                if skipped(line[: match.start()]):
                    continue
                rel = match.group(1)
                full = os.path.normpath(os.path.join(base, rel) if base else rel)
                full = full.replace(os.sep, "/")
                if full.startswith("../") or full == "..":
                    continue
                found.add(full)
for item in sorted(found):
    print(item)
PY
) || {
  echo "ERROR: script mode: could not list scripts" >&2
  exit 1
}

if [ "$list_only" -eq 1 ]; then
  printf '%s\n' "$paths"
  exit 0
fi

bad=0
oldifs=$IFS
IFS='
'
for path in $paths; do
  [ -n "$path" ] || continue
  mode=$(git -C "$repo" ls-files -s -- "$path" | awk 'NR==1 { print $1 }')
  if [ "$mode" != 100755 ]; then
    if [ -z "$mode" ]; then
      mode=missing
    fi
    echo "ERROR: script mode: $path is $mode, not 100755" >&2
    bad=1
  fi
done
IFS=$oldifs
if [ "$bad" -ne 0 ]; then
  exit 1
fi
exit 0
