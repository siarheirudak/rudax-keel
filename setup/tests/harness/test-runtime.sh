#!/usr/bin/env bash
# Runtime oracles. No production environment selects the fixture.
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)
# shellcheck source=setup/lib/runtime.sh
. "$SETUP/lib/runtime.sh"
STUB=$HERE/runtime-stub.sh
FIX=$HERE/fixtures
happy_only=0
[ "${1:-}" = --happy ] && happy_only=1
res(){ echo "RESULT $1: $2"; }

ec=0
out=$(bash "$STUB" --info-file "$FIX/runtime-rootless.info" launch 2>&1) || ec=$?
if [ "$ec" -eq 0 ] && ! printf '%s\n' "$out" | grep -q 'REFUSE	runtime'; then
  res R-H1 "BLOCKED (rootless fixture accepted)"
else
  res R-H1 "NOT BLOCKED"
fi
if [ "$happy_only" -eq 1 ]; then
  if [ "$ec" -ne 0 ]; then exit 1; fi
  exit 0
fi

lec=0
launch=$(bash "$STUB" --info-file "$FIX/runtime-rootful.info" launch 2>&1) || lec=$?
cls=$(bash "$STUB" --info-file "$FIX/runtime-rootful.info" classify 2>&1) || true
ra1_repo=$(mktemp -d)
doc=$(KEEL_REPO="$ra1_repo" "$SETUP/keel-doctor.sh" 2>&1 || true)
rm -rf "$ra1_repo"
if [ "$lec" -ne 0 ] && printf '%s\n' "$launch" | grep -q 'REFUSE	runtime	rootful' \
  && printf '%s\n' "$cls" | grep -qx rootful \
  && printf '%s\n' "$doc" | grep 'ENV-05' | grep -q CRITICAL \
  && printf '%s\n' "$doc" | grep 'ENV-05' | grep -q '❌'; then
  res R-A1 "BLOCKED (rootful fixture refused)"
else
  res R-A1 "NOT BLOCKED"
fi

saved=${KEEL_WORK_MIN_FREE:-}
export KEEL_WORK_MIN_FREE=999999999999999
if bash "$STUB" disk; then
  res R-A4 "NOT BLOCKED"
else
  res R-A4 "BLOCKED (free space below the minimum)"
fi
if [ -n "$saved" ]; then KEEL_WORK_MIN_FREE=$saved; else unset KEEL_WORK_MIN_FREE; fi

cec=0
chr=$(bash "$SETUP/chrome/chromium-argv.sh" --no-sandbox 2>&1) || cec=$?
if [ "$cec" -ne 0 ] && printf '%s\n' "$chr" | grep -q 'REFUSE	chromium	sandbox'; then
  res R-A5 "BLOCKED (sandbox flag refused)"
else
  res R-A5 "NOT BLOCKED"
fi

uec=0
ucls=$(bash "$STUB" --info-file "$FIX/runtime-userns.info" classify 2>&1) || uec=$?
if [ "$uec" -ne 0 ] && printf '%s\n' "$ucls" | grep -qx rootful; then
  res R-A7 "BLOCKED (userns remap is rootful)"
else
  res R-A7 "NOT BLOCKED"
fi

K=$SETUP/keel.sh
root=$(mktemp -d)
export KEEL_ROOT=$root
miss=
for spec in \
  "proto proto t rw true" \
  "role role developer true" \
  "role-env role-env developer true" \
  "export export" \
  "setup setup" \
  "proto-env proto-env true" \
  "egress-up egress-up" \
  "gate gate"
 do
  # shellcheck disable=SC2086
  set -- $spec
  name=$1
  shift
  ec=0
  out=$("$K" "$@" 2>&1) || ec=$?
  if [ "$ec" -eq 0 ] || ! printf '%s\n' "$out" | grep -q 'REFUSE	runtime	rootful'; then
    miss="$miss $name"
  fi
done
export KEEL_WORK_MIN_FREE=999999999999999
for spec in \
  "proto proto t rw true" \
  "role role developer true" \
  "export export" \
  "setup setup"
 do
  # shellcheck disable=SC2086
  set -- $spec
  name=$1
  shift
  ec=0
  out=$("$K" "$@" 2>&1) || ec=$?
  if [ "$ec" -eq 0 ] || ! printf '%s\n' "$out" | grep -q 'REFUSE	runtime	disk'; then
    miss="$miss disk-$name"
  fi
done
unset KEEL_WORK_MIN_FREE
rm -rf "$root"
if ! grep -Fqx 'launch_guard(){ keel_require_runtime || exit $?; } # launch-guard' "$K"; then
  miss="$miss production-guard"
fi
exec_root=$(mktemp -d)
ec=0
out=$(KEEL_ROOT=$exec_root DOCKER=false bash "$STUB" --exec -- proto t rw true 2>&1) || ec=$?
if printf '%s\n' "$out" | grep -q 'REFUSE	runtime	rootful' || printf '%s\n' "$out" | grep -q '^stub:'; then
  miss="$miss exec-rootful"
fi
rm -rf "$exec_root"
if [ -z "$miss" ]; then
  res R-A9 "BLOCKED (role proto export setup and the other launch paths refuse)"
else
  res R-A9 "NOT BLOCKED ($miss)"
fi

score_fix=$(mktemp)
cat > "$score_fix" << 'EOF'
❌ ENV-05  CRITICAL     isolation boundary: rootful
❌ ENV-07  CRITICAL     hardening flags accepted: stripped
❌ NOT READY (0 passed, 0 warnings, 2 failed; 2 critical)
EOF
if bash "$HERE/doctor-score.sh" "$score_fix" >/dev/null 2>&1; then
  res R-A8 "NOT BLOCKED"
else
  res R-A8 "BLOCKED (second critical stays red)"
fi
rm -f "$score_fix"

# GitHub rules row. A temporary gh is first on PATH. The real gh is never run.
gh_root=$(mktemp -d)
gh_bin=$gh_root/bin
gh_work=$gh_root/work
mkdir -p "$gh_bin" "$gh_work"
gh_repo=$gh_root/repo
gh_plain=$gh_root/plain
gh_noremote=$gh_root/noremote
mkdir -p "$gh_plain"
git -C "$gh_root" init -q "$gh_repo"
git -C "$gh_repo" remote add origin 'https://fixtureuser:fixturepw@example.invalid/fixture/repo.git'
git -C "$gh_root" init -q "$gh_noremote"
cat >"$gh_bin/gh" <<EOF
#!/bin/sh
exec python3 "$SETUP/tests/mock-gh.py" "\$@"
EOF
chmod +x "$gh_bin/gh"
gh_mock_body=$(cat "$gh_bin/gh")

gh_clear_overrides() {
  local name
  for name in GH_REPO GH_HOST GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN; do
    unset "$name"
  done
}

gh_install_mock() {
  printf '%s\n' "$gh_mock_body" >"$gh_bin/gh"
  chmod +x "$gh_bin/gh"
}

gh_reset() {
  GH_MOCK_STATE=$gh_work/state.json GH_MOCK_LOG=$gh_work/calls.log python3 "$SETUP/tests/mock-gh.py" --init
  : >"$gh_work/calls.log"
}

gh_mutate() {
  GH_MOCK_STATE=$gh_work/state.json GH_MOCK_MUTATION=$1 python3 - <<'PY'
import json, os
path = os.environ["GH_MOCK_STATE"]
state = json.load(open(path, encoding="utf-8"))
exec(os.environ["GH_MOCK_MUTATION"])
json.dump(state, open(path, "w", encoding="utf-8"))
PY
  : >"$gh_work/calls.log"
}

gh_rule() {
  gh_mutate "$1"
}

gh_run() {
  local repo=$1
  gh_clear_overrides
  gh_ec=0
  gh_out=$(
    KEEL_REPO="$repo" \
    GH_MOCK_STATE="$gh_work/state.json" \
    GH_MOCK_LOG="$gh_work/calls.log" \
    PATH="$gh_bin:$PATH" \
    "$SETUP/keel-doctor.sh" --github 2>&1
  ) || gh_ec=$?
}

gh_run_named() {
  local repo=$1 name=$2 value=$3
  gh_clear_overrides
  export "$name=$value"
  gh_ec=0
  gh_out=$(
    KEEL_REPO="$repo" \
    GH_MOCK_STATE="$gh_work/state.json" \
    GH_MOCK_LOG="$gh_work/calls.log" \
    PATH="$gh_bin:$PATH" \
    "$SETUP/keel-doctor.sh" --github 2>&1
  ) || gh_ec=$?
  unset "$name"
}

gh_ok=1
gh_note=
gh_mark() {
  local label=$1
  if [ "$gh_ok" -ne 1 ]; then
    gh_note="$gh_note $label"
  fi
  gh_ok=1
}

gh_line() {
  printf '%s\n' "$gh_out" | grep -F 'GH-01' || true
}

gh_expect() {
  local icon=$1 detail=$2 verdict=$3 gets=$4
  local line n bad
  gh_ok=1
  [ "$gh_ec" -eq 0 ] || gh_ok=0
  line=$(gh_line)
  n=$(printf '%s\n' "$gh_out" | grep -c -F 'GH-01' || true)
  [ "$n" -eq 1 ] || gh_ok=0
  printf '%s\n' "$line" | grep -F -q "$icon" || gh_ok=0
  printf '%s\n' "$line" | grep -F -q "$detail" || gh_ok=0
  printf '%s\n' "$gh_out" | grep -F -q "$verdict" || gh_ok=0
  if [ "$verdict" = "READY WITH WARNINGS" ]; then
    :
  elif printf '%s\n' "$gh_out" | grep -F -q 'READY WITH WARNINGS'; then
    gh_ok=0
  fi
  bad=$(grep -v '^GET ' "$gh_work/calls.log" || true)
  [ -z "$bad" ] || gh_ok=0
  n=$(grep -c '^GET ' "$gh_work/calls.log" || true)
  [ "$n" -eq "$gets" ] || gh_ok=0
  printf '%s\n' "$gh_out" | grep -F -q 'fixtureuser' && gh_ok=0
  printf '%s\n' "$gh_out" | grep -F -q 'fixturepw' && gh_ok=0
  printf '%s\n' "$gh_out" | grep -F -q 'example.invalid' && gh_ok=0
  printf '%s\n' "$gh_out" | grep -F -q 'Upgrade to GitHub Pro' && gh_ok=0
  printf '%s\n' "$gh_out" | grep -F -q 'Not Found' && gh_ok=0
  printf '%s\n' "$gh_out" | grep -F -q 'sign-in required' && gh_ok=0
}

rule_base='import json
rule = json.load(open("'"$SETUP"'/rulesets/require-checks.json", encoding="utf-8"))
rule["id"] = 1
rule["source_type"] = "Repository"
'

gh_install_mock
gh_reset
gh_rule "$rule_base
state[\"rulesets\"] = [rule]
"
gh_run "$gh_repo"
gh_expect "✅" "on and matches setup/rulesets/require-checks.json" "✅ READY" 2
grep -F -q 'GET repos/{owner}/{repo}/rulesets' "$gh_work/calls.log" || gh_ok=0
grep -F -q 'GET repos/{owner}/{repo}/rulesets/1' "$gh_work/calls.log" || gh_ok=0
gh_mark "H1"
if [ -z "$gh_note" ]; then res GH-H1 "BLOCKED (2 GET)"; else res GH-H1 "NOT BLOCKED ($gh_note)"; fi

gh_note=
gh_install_mock
gh_reset
gh_run "$gh_repo"
gh_expect "⚠️" "not enabled; owner: run setup/apply-github-rules.sh" "READY WITH WARNINGS" 1
gh_mark "a"
gh_reset
gh_rule 'state["rulesets"] = [{"id": 4, "name": "other-rule", "source_type": "Repository"}]'
gh_run "$gh_repo"
gh_expect "⚠️" "not enabled; owner: run setup/apply-github-rules.sh" "READY WITH WARNINGS" 1
gh_mark "b"
gh_reset
gh_rule "$rule_base
rule[\"source_type\"] = \"Organization\"
state[\"rulesets\"] = [rule]
"
gh_run "$gh_repo"
gh_expect "⚠️" "not enabled; owner: run setup/apply-github-rules.sh" "READY WITH WARNINGS" 1
gh_mark "c"
gh_reset
gh_rule "$rule_base
other = json.loads(json.dumps(rule))
other[\"id\"] = 2
state[\"rulesets\"] = [rule, other]
"
gh_run "$gh_repo"
gh_expect "⚠️" "more than one require-checks ruleset; owner: run setup/verify-github-rules.sh" "READY WITH WARNINGS" 1
gh_mark "d"
if [ -z "$gh_note" ]; then res GH-A1 "BLOCKED (a 1 b 1 c 1 d 1 GET)"; else res GH-A1 "NOT BLOCKED ($gh_note)"; fi

gh_note=
gh_install_mock
gh_reset
gh_rule 'state["ruleset_list_status"] = 403'
gh_run "$gh_repo"
gh_expect "⚠️" "cannot read the rule (gh could not list rulesets); owner: run setup/verify-github-rules.sh" "READY WITH WARNINGS" 1
gh_mark "a"
gh_reset
gh_rule "$rule_base
rule[\"id\"] = \"1\"
state[\"rulesets\"] = [rule]
"
gh_run "$gh_repo"
gh_expect "⚠️" "cannot read the rule (gh could not read the ruleset); owner: run setup/verify-github-rules.sh" "READY WITH WARNINGS" 2
gh_mark "b"
gh_reset
gh_rule "$rule_base
state[\"gh_version\"] = \"1.6.0\"
state[\"rulesets\"] = [rule]
"
gh_run "$gh_repo"
gh_expect "⚠️" "cannot read the rule (gh is older than 1.7.0); owner: run setup/verify-github-rules.sh" "READY WITH WARNINGS" 0
gh_mark "c"
cat >"$gh_bin/gh" <<'EOF'
#!/bin/sh
printf '%s\n' 'sign-in required' >&2
exit 1
EOF
chmod +x "$gh_bin/gh"
: >"$gh_work/calls.log"
gh_run "$gh_repo"
gh_expect "⚠️" "cannot read the rule (gh version unknown); owner: run setup/verify-github-rules.sh" "READY WITH WARNINGS" 0
gh_mark "d"
if [ -z "$gh_note" ]; then res GH-A2 "BLOCKED (a 1 b 2 c 0 d 0 GET)"; else res GH-A2 "NOT BLOCKED ($gh_note)"; fi

gh_note=
gh_install_mock
for spec in \
  'rule["bypass_actors"][0]["bypass_mode"] = "always"' \
  'rule["bypass_actors"].append({"actor_id": 9, "actor_type": "Team", "bypass_mode": "pull_request"})' \
  'rule["rules"][0]["parameters"]["required_status_checks"][0]["integration_id"] = 1'
 do
  gh_reset
  gh_rule "$rule_base
$spec
state[\"rulesets\"] = [rule]
"
  gh_run "$gh_repo"
  gh_expect "⚠️" "differs from setup/rulesets/require-checks.json; owner: run setup/apply-github-rules.sh" "READY WITH WARNINGS" 2
  gh_mark "diff"
done
for spec in disabled evaluate; do
  gh_reset
  gh_rule "$rule_base
rule[\"enforcement\"] = \"$spec\"
state[\"rulesets\"] = [rule]
"
  gh_run "$gh_repo"
  gh_expect "⚠️" "not enabled (enforcement is not active); owner: run setup/apply-github-rules.sh" "READY WITH WARNINGS" 2
  gh_mark "$spec"
done
if [ -z "$gh_note" ]; then res GH-A3 "BLOCKED (a 2 b 2 c 2 d 2 e 2 GET)"; else res GH-A3 "NOT BLOCKED ($gh_note)"; fi

gh_note=
gh_install_mock
gh_reset
gh_run "$gh_noremote"
gh_expect "⚠️" "cannot read the rule (no git remote); owner: run setup/verify-github-rules.sh" "READY WITH WARNINGS" 0
gh_mark "a"
gh_reset
gh_run "$gh_plain"
gh_expect "⚠️" "cannot read the rule (no git repository at KEEL_REPO); owner: run setup/verify-github-rules.sh" "READY WITH WARNINGS" 0
gh_mark "b"
gh_n=$(printf '%s\n' "$doc" | grep -c -F 'GH-01' || true)
if [ "$gh_n" -eq 1 ]; then gh_ok=1; else gh_ok=0; fi
gh_mark "c"
gh_reset
gh_rule "$rule_base
state[\"rulesets\"] = [rule]
"
for name in GH_REPO GH_HOST GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN; do
  case $name in
    GH_REPO) value=fixture-owner/fixture-name ;;
    GH_HOST) value=fixture.example.invalid ;;
    GH_TOKEN) value=fixture-value-one ;;
    GITHUB_TOKEN) value=fixture-value-two ;;
    GH_ENTERPRISE_TOKEN) value=fixture-value-three ;;
    GITHUB_ENTERPRISE_TOKEN) value=fixture-value-four ;;
  esac
  gh_run_named "$gh_repo" "$name" "$value"
  gh_expect "⚠️" "cannot read the rule (GitHub variables in environment); owner: run setup/verify-github-rules.sh" "READY WITH WARNINGS" 0
  printf '%s\n' "$gh_out" | grep -F -q "$value" && gh_ok=0
  gh_mark "d-$name"
done
gh_run_named "$gh_repo" GH_TOKEN fixture-value-five
gh_expect "⚠️" "cannot read the rule (GitHub variables in environment); owner: run setup/verify-github-rules.sh" "READY WITH WARNINGS" 0
printf '%s\n' "$gh_out" | grep -F -q 'fixture-value-five' && gh_ok=0
gh_mark "e"
if [ -z "$gh_note" ]; then res GH-A4 "BLOCKED (a 0 b 0 c 1 d 0 e 0 GET)"; else res GH-A4 "NOT BLOCKED ($gh_note)"; fi

# The stand-in ends the doctor child that would print the verdict word.
# The version helper runs gh inside its own command substitution, so the
# stand-in walks up to that child shell and ends it.
gh_note=
cat >"$gh_bin/gh" <<'EOF'
#!/bin/sh
cur=$PPID
prev=$PPID
while true; do
  parent=$(ps -o ppid= -p "$cur" | tr -d ' ')
  args=$(ps -o args= -p "$parent" 2>/dev/null || true)
  case $args in
    *keel-doctor.sh*) prev=$cur; cur=$parent ;;
    *) break ;;
  esac
done
kill -9 "$prev"
exit 1
EOF
chmod +x "$gh_bin/gh"
: >"$gh_work/calls.log"
gh_run "$gh_repo"
gh_expect "⚠️" "cannot read the rule (no result); owner: run setup/verify-github-rules.sh" "READY WITH WARNINGS" 0
gh_mark "none"
if [ -z "$gh_note" ]; then res GH-A5 "BLOCKED (no verdict word)"; else res GH-A5 "NOT BLOCKED ($gh_note)"; fi

if python3 - "$SETUP/rulesets/require-checks.json" "$SETUP/rulesets/protect-main.json" <<'PY'
import json, sys
req = json.load(open(sys.argv[1], encoding="utf-8"))
prot = json.load(open(sys.argv[2], encoding="utf-8"))
actors = req["bypass_actors"]
checks = req["rules"][0]["parameters"]["required_status_checks"]
ok = req["name"] == "require-checks" and req["target"] == "branch" and req["enforcement"] == "active"
ok = ok and len(actors) == 1 and actors[0]["actor_id"] == 5
ok = ok and actors[0]["actor_type"] == "RepositoryRole" and actors[0]["bypass_mode"] == "pull_request"
ok = ok and req["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
ok = ok and req["conditions"]["ref_name"]["exclude"] == []
ok = ok and len(req["rules"]) == 1 and req["rules"][0]["type"] == "required_status_checks"
params = req["rules"][0]["parameters"]
ok = ok and params["strict_required_status_checks_policy"] is True
ok = ok and params["do_not_enforce_on_create"] is False
ok = ok and [item["context"] for item in checks] == ["keel-gate", "keel-process-files-separate"]
ok = ok and all(item["integration_id"] == 15368 for item in checks)
pactors = prot["bypass_actors"]
ok = ok and len(pactors) == 1 and pactors[0]["actor_id"] == 5
ok = ok and pactors[0]["actor_type"] == "RepositoryRole" and pactors[0]["bypass_mode"] == "pull_request"
sys.exit(0 if ok else 1)
PY
then
  res GH-A6 "BLOCKED (file values pinned)"
else
  res GH-A6 "NOT BLOCKED"
fi
rm -rf "$gh_root"
