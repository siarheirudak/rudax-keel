#!/usr/bin/env bash
# Fake-gh tests for apply-github-rules.sh and verify-github-rules.sh.
# Never calls GitHub. gh on PATH is setup/tests/mock-gh.py.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BASH_BIN=$(command -v bash)
export BASH_BIN
WORKDIR=$(mktemp -d)
BIN="$WORKDIR/bin"
BASIC="$WORKDIR/basic"
export GH_MOCK_STATE="$WORKDIR/state.json"
export GH_MOCK_LOG="$WORKDIR/calls.log"
export SETUP_LOG_DIR="$WORKDIR/logs"
unset GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN || true
mkdir -p "$BIN" "$BASIC" "$SETUP_LOG_DIR"
cat >"$BIN/gh" <<EOF
#!/bin/bash
exec python3 "$ROOT/setup/tests/mock-gh.py" "\$@"
EOF
chmod +x "$BIN/gh"
for tool in date tee mkdir cat sed grep tr mktemp dirname pwd base64; do
  src=$(command -v "$tool")
  ln -s "$src" "$BASIC/$tool"
done
ln -s "$BIN/gh" "$BASIC/gh"
export PATH="$BIN:$PATH"

APPLY="$ROOT/setup/apply-github-rules.sh"
VERIFY="$ROOT/setup/verify-github-rules.sh"
rc=0
out=""

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  printf '%s\n' "$out" >&2
  if [[ -f $GH_MOCK_LOG ]]; then
    printf 'calls:\n' >&2
    cat "$GH_MOCK_LOG" >&2 || true
  fi
  exit 1
}

ok() {
  printf 'ok %s\n' "$1"
}

reset() {
  python3 "$ROOT/setup/tests/mock-gh.py" --init
  : >"$GH_MOCK_LOG"
}

mutate() {
  GH_MOCK_MUTATION=$1 python3 - <<'PY'
import json, os
path = os.environ["GH_MOCK_STATE"]
state = json.load(open(path, encoding="utf-8"))
exec(os.environ["GH_MOCK_MUTATION"])
json.dump(state, open(path, "w", encoding="utf-8"))
PY
  : >"$GH_MOCK_LOG"
}

clear_calls() {
  mutate 'state["calls"]=[]'
}

run() {
  rc=0
  out=$("$BASH_BIN" "$@" 2>&1) || rc=$?
}

run_pipe() {
  local input=$1
  shift
  rc=0
  out=$(printf '%s\n' "$input" | "$BASH_BIN" "$@" 2>&1) || rc=$?
}

need() {
  case $out in
    *"$1"*) ;;
    *) fail "missing [$1]" ;;
  esac
}

forbid() {
  case $out in
    *"$1"*) fail "unexpected [$1]" ;;
  esac
}

assert_rc() {
  if [[ $rc -ne $1 ]]; then
    fail "exit $rc, want $1"
  fi
}

count_method() {
  awk -v method="$1" -v needle="$2" '$1 == method && index($2, needle) { n++ } END { print n + 0 }' "$GH_MOCK_LOG"
}

count_exact() {
  awk -v method="$1" -v path="$2" '$1 == method && $2 == path { n++ } END { print n + 0 }' "$GH_MOCK_LOG"
}

write_count() {
  awk '$1 == "POST" || $1 == "PUT" || $1 == "PATCH" { n++ } END { print n + 0 }' "$GH_MOCK_LOG"
}

accept_agent() {
  mutate 'state["collaborators"]["agent"]={"permission":"write","role_name":"write"}; state["invitations"]=[]'
}

assert_links() {
  local bad
  bad=$(printf '%s\n' "$out" | grep -E ' - (OK|ALREADY|NOT YET|FAIL)' | grep -v 'docs/why.md#' || true)
  if [[ -n $bad ]]; then
    out=$bad
    fail "step without why.md link"
  fi
}

# --- usage ---
run "$APPLY"
assert_rc 2
need "Usage:"
ok "apply usage"

run "$VERIFY" only-one
assert_rc 2
need "Usage:"
ok "verify usage"

run "$APPLY" owner/repo agent --nope
assert_rc 2
need "Unknown option"
ok "unknown flag"

# --- missing jq ---
hash -r
rc=0
out=$(PATH="$BASIC" "$BASH_BIN" "$APPLY" owner/repo agent 2>&1) || rc=$?
hash -r
export PATH="$BIN:$PATH"
assert_rc 1
need "jq is not on PATH"
if [[ -s $GH_MOCK_LOG ]]; then
  fail "jq-missing test called gh"
fi
ok "missing jq"

# --- happy path: create, second run skips, verify read-only after accept ---
reset
run "$APPLY" owner/repo agent
assert_rc 0
need "created protect-main"
need "created protect-tags"
need "CI not added yet; re-run after layer 2 merge"
need "invitation sent with write"
forbid "created require-checks"
assert_links
python3 - <<'PY'
import json, os, sys
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
names = [item["name"] for item in state["rulesets"]]
if names != ["protect-main", "protect-tags"] and sorted(names) != ["protect-main", "protect-tags"]:
    sys.exit("rulesets: " + ",".join(names))
text = state["files"].get(".github/CODEOWNERS", "")
if text.strip() != "* @owner":
    sys.exit("codeowners: " + text)
if "siarhei" in text:
    sys.exit("hardcoded owner in codeowners")
perms = state["workflow_perms"]
if perms["default_workflow_permissions"] != "read" or perms["can_approve_pull_request_reviews"] is not False:
    sys.exit("workflow perms " + json.dumps(perms))
if state["fork_policy"] != "all_external_contributors":
    sys.exit("fork " + state["fork_policy"])
if state["allowed_actions"] != "selected":
    sys.exit("allowed " + state["allowed_actions"])
selected = state["selected"]
if selected["github_owned_allowed"] is not True or selected["verified_allowed"] is not False or selected["patterns_allowed"] != []:
    sys.exit("selected " + json.dumps(selected))
puts = [call for call in state["calls"] if call["method"] == "PUT"]
kinds = []
for call in puts:
    path = call["path"]
    if path.endswith("/actions/permissions/workflow"):
        kinds.append("workflow")
        body = call["body"]
        if body["default_workflow_permissions"] != "read" or body["can_approve_pull_request_reviews"] is not False:
            sys.exit("bad workflow body")
    elif path.endswith("/fork-pr-contributor-approval"):
        kinds.append("fork")
    elif path.endswith("/actions/permissions"):
        kinds.append("policy")
    elif path.endswith("/selected-actions"):
        kinds.append("selected")
if kinds != ["workflow", "fork", "policy", "selected"]:
    sys.exit("action put order " + ",".join(kinds))
paths = [call["method"] + " " + call["path"] for call in state["calls"]]
code_at = next(i for i, path in enumerate(paths) if path == "PUT repos/owner/repo/contents/.github/CODEOWNERS")
rule_at = next(i for i, path in enumerate(paths) if path == "POST repos/owner/repo/rulesets")
if code_at > rule_at:
    sys.exit("CODEOWNERS was written after protect-main")
PY
ok "apply creates rules and actions"

clear_calls
run "$APPLY" owner/repo agent
assert_rc 0
need "already matches setup/rulesets/protect-main.json"
need "already matches setup/rulesets/protect-tags.json"
need "CI not added yet; re-run after layer 2 merge"
need "invitation already pending"
if [[ $(write_count) -ne 0 ]]; then
  fail "second apply wrote: $(write_count)"
fi
ok "second apply skips"

clear_calls
run "$VERIFY" owner/repo agent
assert_rc 1
need "invitation pending"
ok "verify fails while invite is pending"

accept_agent
clear_calls
run "$VERIFY" owner/repo agent
assert_rc 0
need "protect-main matches"
need "protect-tags matches"
need "CI not added yet; re-run after layer 2 merge"
need "agent has write"
forbid "warning:"
if [[ $(write_count) -ne 0 ]]; then
  fail "verify wrote"
fi
methods=$(awk '{print $1}' "$GH_MOCK_LOG" | sort -u)
if [[ $methods != "GET" ]]; then
  fail "verify methods: $methods"
fi
ok "verify read-only"

# --- not admin does not mutate ---
reset
mutate 'state["admin"]=False'
run "$APPLY" owner/repo agent
assert_rc 1
need "without admin"
if [[ $(write_count) -ne 0 ]]; then
  fail "not-admin wrote"
fi
ok "not admin"

# --- agent token refused ---
reset
mutate 'state["login"]="agent"'
run "$APPLY" owner/repo agent
assert_rc 1
need "agent GitHub account"
if [[ $(write_count) -ne 0 ]]; then
  fail "agent token wrote"
fi
ok "agent token"

# --- empty repo ---
reset
mutate 'state["empty"]=True'
run "$APPLY" owner/repo agent
assert_rc 1
need "repository is empty"
forbid "CI not added yet"
if [[ $(count_method POST /rulesets) -ne 0 ]]; then
  fail "empty repo created a ruleset"
fi
if [[ $(count_exact PUT repos/owner/repo/contents/.github/CODEOWNERS) -ne 0 ]]; then
  fail "empty repo wrote CODEOWNERS"
fi
ok "empty repo"

# --- admin agent fails, and is not demoted ---
reset
mutate 'state["collaborators"]["agent"]={"permission":"admin","role_name":"admin"}'
run "$APPLY" owner/repo agent
assert_rc 1
need "role is admin, expected write"
need "Left unchanged"
forbid "warning:"
if [[ $(count_method PUT /collaborators/agent) -ne 0 ]]; then
  fail "admin agent was changed"
fi
accept_agent
mutate 'state["collaborators"]["agent"]={"permission":"admin","role_name":"admin"}'
run "$VERIFY" owner/repo agent
assert_rc 1
need "role is admin, expected write"
ok "admin agent"

# --- pending invite preset ---
reset
mutate 'state["invitations"]=[{"invitee":{"login":"agent"}}]'
run "$APPLY" owner/repo agent
assert_rc 0
need "invitation already pending"
if [[ $(count_method PUT /collaborators/agent) -ne 0 ]]; then
  fail "pending invite was re-sent"
fi
ok "pending invite"

# --- maintain becomes write ---
reset
mutate 'state["collaborators"]["agent"]={"permission":"maintain","role_name":"maintain"}'
run "$APPLY" owner/repo agent
assert_rc 0
need "changed role from maintain to write"
python3 - <<'PY'
import json, os, sys
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
role = state["collaborators"]["agent"]["permission"]
if role != "write":
    sys.exit(role)
PY
ok "maintain to write"

# --- drifted protect-main is updated ---
reset
python3 - <<'PY'
import json, os
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
state["rulesets"] = [{
    "id": 7,
    "name": "protect-main",
    "source_type": "Repository",
    "target": "branch",
    "enforcement": "disabled",
    "bypass_actors": [],
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [{"type": "deletion"}],
}]
state["files"][".github/CODEOWNERS"] = "* @owner\n"
state["next_id"] = 8
json.dump(state, open(os.environ["GH_MOCK_STATE"], "w", encoding="utf-8"))
PY
: >"$GH_MOCK_LOG"
run "$APPLY" owner/repo agent
assert_rc 0
need "updated protect-main"
if [[ $(count_exact PUT repos/owner/repo/rulesets/7) -ne 1 ]]; then
  fail "drifted ruleset was not updated"
fi
python3 - <<'PY'
import json, os, sys
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
live = next(item for item in state["rulesets"] if item["id"] == 7)
if live["enforcement"] != "active":
    sys.exit(live["enforcement"])
if live["source_type"] != "Repository":
    sys.exit(live["source_type"])
PY
ok "drifted protect-main"

# --- org ruleset is not edited ---
reset
python3 - <<'PY'
import json, os
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
state["rulesets"] = [{
    "id": 99,
    "name": "protect-main",
    "source_type": "Organization",
    "target": "branch",
    "enforcement": "active",
    "bypass_actors": [],
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [{"type": "deletion"}],
}]
state["next_id"] = 100
json.dump(state, open(os.environ["GH_MOCK_STATE"], "w", encoding="utf-8"))
PY
: >"$GH_MOCK_LOG"
run "$APPLY" owner/repo agent
assert_rc 0
need "created protect-main"
if [[ $(count_exact PUT repos/owner/repo/rulesets/99) -ne 0 ]]; then
  fail "org ruleset was edited"
fi
if [[ $(count_exact POST repos/owner/repo/rulesets) -lt 1 ]]; then
  fail "repository ruleset was not created beside the org ruleset"
fi
ok "org ruleset left alone"

# --- duplicate names fail closed ---
reset
python3 - <<'PY'
import json, os
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
base = {
    "name": "protect-main",
    "source_type": "Repository",
    "target": "branch",
    "enforcement": "active",
    "bypass_actors": [],
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [{"type": "deletion"}],
}
state["rulesets"] = [dict(base, id=1), dict(base, id=2)]
state["next_id"] = 3
json.dump(state, open(os.environ["GH_MOCK_STATE"], "w", encoding="utf-8"))
PY
: >"$GH_MOCK_LOG"
run "$APPLY" owner/repo agent
assert_rc 1
need "found 2 repository rulesets named protect-main"
if [[ $(count_method PUT /rulesets/) -ne 0 ]]; then
  fail "duplicate names still updated"
fi
python3 - <<'PY'
import json, os, sys
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
main = [item for item in state["rulesets"] if item["name"] == "protect-main" and item["source_type"] == "Repository"]
if len(main) != 2:
    sys.exit("protect-main count %s" % len(main))
posted = [call for call in state["calls"] if call["method"] == "POST" and call["path"].endswith("/rulesets") and call["body"]["name"] == "protect-main"]
if posted:
    sys.exit("posted another protect-main")
PY
ok "duplicate names"

# --- CODEOWNERS ---
reset
mutate 'state["files"][".github/CODEOWNERS"]="* @siarheirudak\n"'
run "$APPLY" owner/repo agent
assert_rc 0
need "rewrote CODEOWNERS to * @owner"
python3 - <<'PY'
import json, os, sys
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
text = state["files"].get(".github/CODEOWNERS", "")
if text.strip() != "* @owner":
    sys.exit("rewritten codeowners: " + text)
puts = [call for call in state["calls"] if call["method"] == "PUT" and call["path"].endswith("CODEOWNERS")]
if len(puts) != 1 or puts[0]["body"].get("sha") != "file":
    sys.exit("missing sha on rewrite")
paths = [call["method"] + " " + call["path"] for call in state["calls"]]
code_at = next(i for i, path in enumerate(paths) if path == "PUT repos/owner/repo/contents/.github/CODEOWNERS")
rule_at = next(i for i, path in enumerate(paths) if path == "POST repos/owner/repo/rulesets")
if code_at > rule_at:
    sys.exit("template CODEOWNERS was written after protect-main")
PY
ok "template CODEOWNERS rewritten before rules"

reset
mutate 'state["files"][".github/CODEOWNERS"]="* @someoneelse\n"'
run "$APPLY" owner/repo agent
assert_rc 1
need "will not rewrite"
need "still creates protect-main"
need "pull request"
python3 - <<'PY'
import json, os, sys
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
text = state["files"].get(".github/CODEOWNERS", "")
if text.strip() != "* @someoneelse":
    sys.exit("custom codeowners changed: " + text)
puts = [call for call in state["calls"] if call["method"] == "PUT" and call["path"].endswith("CODEOWNERS")]
if puts:
    sys.exit("custom CODEOWNERS was rewritten")
names = [item["name"] for item in state["rulesets"]]
if "protect-main" not in names:
    sys.exit("protect-main was not created after CODEOWNERS FAIL")
PY
ok "custom CODEOWNERS left in place"

reset
mutate 'state["files"][".github/CODEOWNERS"]="* @someoneelse\n/docs/ @team\n"'
run "$APPLY" --rewrite-codeowners owner/repo agent
assert_rc 0
need "rewrote CODEOWNERS to * @owner"
python3 - <<'PY'
import json, os, sys
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
text = state["files"].get(".github/CODEOWNERS", "")
if text.strip() != "* @owner":
    sys.exit("forced codeowners: " + text)
puts = [call for call in state["calls"] if call["method"] == "PUT" and call["path"].endswith("CODEOWNERS")]
if len(puts) != 1 or puts[0]["body"].get("sha") != "file":
    sys.exit("missing sha on forced rewrite")
PY
ok "CODEOWNERS force rewrite"

reset
python3 - <<'PY'
import json, os
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
state["rulesets"] = [{
    "id": 3,
    "name": "protect-main",
    "source_type": "Repository",
    "target": "branch",
    "enforcement": "active",
    "bypass_actors": [],
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [{"type": "deletion"}],
}]
state["files"][".github/CODEOWNERS"] = "* @siarheirudak\n"
state["next_id"] = 4
json.dump(state, open(os.environ["GH_MOCK_STATE"], "w", encoding="utf-8"))
PY
: >"$GH_MOCK_LOG"
run "$APPLY" --rewrite-codeowners owner/repo agent
assert_rc 1
need "will not change CODEOWNERS"
need "admin bypass"
if [[ $(count_exact PUT repos/owner/repo/contents/.github/CODEOWNERS) -ne 0 ]]; then
  fail "CODEOWNERS was rewritten while protect-main exists"
fi
ok "CODEOWNERS blocked when protect-main exists"

reset
mutate 'state["files"][".github/CODEOWNERS"]="* @owner\n"'
run "$APPLY" owner/repo agent
assert_rc 0
need "already * @owner"
if [[ $(count_exact PUT repos/owner/repo/contents/.github/CODEOWNERS) -ne 0 ]]; then
  fail "matching CODEOWNERS was rewritten"
fi
ok "CODEOWNERS left in place"

reset
mutate 'state["login"]="siarheirudak"; state["owner_login"]="siarheirudak"; state["files"][".github/CODEOWNERS"]="* @siarheirudak\n"'
run "$APPLY" siarheirudak/repo agent
assert_rc 0
need "already * @siarheirudak"
if [[ $(count_exact PUT repos/siarheirudak/repo/contents/.github/CODEOWNERS) -ne 0 ]]; then
  fail "owner repo committed CODEOWNERS"
fi
ok "owner repo makes no CODEOWNERS commit"

reset
mutate 'state["codeowners_put_status"]=403'
run "$APPLY" owner/repo agent
assert_rc 1
need "admin bypass"
need "pull request"
python3 - <<'PY'
import json, os, sys
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
if ".github/CODEOWNERS" in state["files"]:
    sys.exit("file was written despite rejection")
PY
ok "CODEOWNERS ruleset rejection"

# --- require-checks ---
reset
mutate 'state["files"][".github/workflows/checks.yml"]="name: checks\n"'
run "$APPLY" owner/repo agent
assert_rc 0
need "created require-checks"
python3 - <<'PY'
import json, os, sys
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
live = next(item for item in state["rulesets"] if item["name"] == "require-checks")
if live["bypass_actors"] != []:
    sys.exit("bypass not empty")
checks = live["rules"][0]["parameters"]["required_status_checks"]
if checks != [{"context": "checks / gate"}]:
    sys.exit(str(checks))
if live["rules"][0]["parameters"]["strict_required_status_checks_policy"] is not True:
    sys.exit("not strict")
PY
clear_calls
run "$APPLY" owner/repo agent
assert_rc 0
need "already matches setup/rulesets/require-checks.json"
if [[ $(count_exact POST repos/owner/repo/rulesets) -ne 0 ]]; then
  fail "require-checks was created twice"
fi
ok "require-checks created then skipped"

reset
mutate 'state["files"][".github/workflows/checks.yml"]="name: checks\n"'
run "$APPLY" owner/repo agent
assert_rc 0
mutate 'state["rulesets"]=[item for item in state["rulesets"] if item["name"]!="require-checks"]'
accept_agent
run "$VERIFY" owner/repo agent
assert_rc 1
need "no repository ruleset named require-checks"
ok "verify fails when checks.yml exists and require-checks is missing"

reset
mutate 'state["files"][".github/workflows/checks.yml"]="name: checks\n"'
run "$APPLY" owner/repo agent
assert_rc 0
mutate '''
for item in state["rulesets"]:
    if item["name"] == "require-checks":
        item["enforcement"] = "disabled"
'''
accept_agent
run "$VERIFY" owner/repo agent
assert_rc 1
need "require-checks enforcement is disabled, expected active"
ok "verify fails when require-checks is disabled"

# --- Free private ---
reset
mutate 'state["private"]=True; state["plan"]="free"'
run "$APPLY" owner/repo agent
assert_rc 1
need "push directly to main"
need "re-run with --accept-risk"
if [[ $(awk '$2 ~ /rulesets/ { n++ } END { print n + 0 }' "$GH_MOCK_LOG") -ne 0 ]]; then
  fail "free private touched rulesets"
fi
if [[ $(write_count) -ne 0 ]]; then
  fail "free private wrote before acceptance"
fi
ok "free private non-tty stops"

reset
mutate 'state["private"]=True; state["plan"]="free"'
run_pipe yes "$APPLY" owner/repo agent
assert_rc 1
need "not a terminal"
if [[ $(write_count) -ne 0 ]]; then
  fail "piped yes wrote"
fi
ok "piped yes is not acceptance"

reset
mutate 'state["private"]=True; state["plan"]="free"'
run "$APPLY" --accept-risk owner/repo agent
assert_rc 1
need "accepted with --accept-risk"
need " - FAIL:"
forbid "created protect-main"
if [[ $(count_method POST /rulesets) -ne 0 ]]; then
  fail "accept-risk created a ruleset"
fi
if [[ $(count_exact PUT repos/owner/repo/actions/permissions/workflow) -ne 1 ]]; then
  fail "accept-risk did not set token permissions"
fi
if [[ $(awk '$2 ~ /fork-pr/ { n++ } END { print n + 0 }' "$GH_MOCK_LOG") -ne 0 ]]; then
  fail "private repo called fork approval"
fi
need "not applicable (private repo)"
if printf '%s\n' "$out" | grep 'not applicable (private repo)' | grep -q 'ALREADY'; then
  fail "private fork used ALREADY"
fi
accept_agent
run "$VERIFY" owner/repo agent
assert_rc 1
need "docs/why.md#free-private-risk"
need "checks are only advisory"
need " - FAIL:"
need "not applicable (private repo)"
if printf '%s\n' "$out" | grep 'not applicable (private repo)' | grep -q 'ALREADY'; then
  fail "private fork used ALREADY"
fi
ok "accept-risk and verify reminder"

# typed yes on a terminal
reset
mutate 'state["private"]=True; state["plan"]="free"'
rc=0
out=$(python3 - "$APPLY" owner/repo agent <<'PY'
import os, select, subprocess, sys, time
try:
    import pty
except ImportError:
    sys.stderr.write("no pty\n")
    sys.exit(2)
script, slug, agent = sys.argv[1], sys.argv[2], sys.argv[3]
master, slave = pty.openpty()
proc = subprocess.Popen(
    [os.environ.get("BASH_BIN", "bash"), script, slug, agent],
    stdin=slave,
    stdout=slave,
    stderr=slave,
    env=os.environ.copy(),
)
os.close(slave)
buf = b""
sent = False
deadline = time.time() + 8
while True:
    if proc.poll() is not None:
        while select.select([master], [], [], 0)[0]:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
        break
    remaining = deadline - time.time()
    if remaining <= 0:
        proc.kill()
        break
    ready, _, _ = select.select([master], [], [], min(0.2, remaining))
    if not ready:
        continue
    try:
        chunk = os.read(master, 4096)
    except OSError:
        break
    if not chunk:
        break
    buf += chunk
    if not sent and b"Type yes to continue:" in buf:
        os.write(master, b"yes\n")
        sent = True
rc = proc.wait()
sys.stdout.buffer.write(buf)
if not sent:
    sys.stderr.write("prompt not seen\n")
    sys.exit(3 if rc == 0 else rc)
sys.exit(rc)
PY
) || rc=$?
assert_rc 1
need "accepted by typing yes"
if [[ $(count_method POST /rulesets) -ne 0 ]]; then
  fail "typed yes created a ruleset"
fi
ok "typed yes"

reset
mutate 'state["private"]=True; state["plan"]="free"'
rc=0
out=$(python3 - "$APPLY" owner/repo agent <<'PY'
import os, select, subprocess, sys, time, pty
script, slug, agent = sys.argv[1], sys.argv[2], sys.argv[3]
master, slave = pty.openpty()
proc = subprocess.Popen(
    [os.environ.get("BASH_BIN", "bash"), script, slug, agent],
    stdin=slave, stdout=slave, stderr=slave, env=os.environ.copy(),
)
os.close(slave)
buf = b""
sent = False
deadline = time.time() + 8
while True:
    if proc.poll() is not None:
        break
    remaining = deadline - time.time()
    if remaining <= 0:
        proc.kill()
        break
    ready, _, _ = select.select([master], [], [], min(0.2, remaining))
    if not ready:
        continue
    try:
        chunk = os.read(master, 4096)
    except OSError:
        break
    if not chunk:
        break
    buf += chunk
    if not sent and b"Type yes to continue:" in buf:
        os.write(master, b"no\n")
        sent = True
rc = proc.wait()
sys.stdout.buffer.write(buf)
sys.exit(rc)
PY
) || rc=$?
assert_rc 1
need "declined"
if [[ $(write_count) -ne 0 ]]; then
  fail "declined still wrote"
fi
ok "typed no"

# public repository on Free still gets rulesets
reset
mutate 'state["private"]=False; state["plan"]="free"'
run "$APPLY" owner/repo agent
assert_rc 0
need "created protect-main"
forbid "GitHub Free"
ok "public free has rulesets"

# org plan, not the caller's plan
reset
mutate 'state["private"]=True; state["plan"]="pro"; state["owner_type"]="Organization"; state["owner_login"]="acme"; state["org_plan"]="free"'
run "$APPLY" acme/repo agent
assert_rc 1
need "re-run with --accept-risk"
if [[ $(write_count) -ne 0 ]]; then
  fail "org free wrote"
fi
ok "org plan is the repo plan"

# unknown plan probes rulesets
reset
mutate 'state["private"]=True; state["plan"]=None; state["ruleset_list_status"]=403'
run "$APPLY" owner/repo agent
assert_rc 1
need "re-run with --accept-risk"
if [[ $(count_method POST /rulesets) -ne 0 ]]; then
  fail "probe created a ruleset"
fi
ok "unknown plan probe"

# --- fork endpoint missing ---
reset
mutate 'state["fork_status"]=404'
run "$APPLY" owner/repo agent
assert_rc 1
need "outside collaborators"
need "Settings"
need " - FAIL:"
forbid "Unexpected error"
accept_agent
run "$VERIFY" owner/repo agent
assert_rc 1
need "outside collaborators"
need " - FAIL:"
ok "fork API missing"

# --- unpinned uses warns; third-party pin is allow-listed ---
reset
mutate 'state["files"][".github/workflows/demo.yml"]="name: demo\njobs:\n  demo:\n    steps:\n      - uses: actions/checkout@v4\n      - uses: ./local\n      - uses: docker://alpine:3\n"'
run "$APPLY" owner/repo agent
assert_rc 0
accept_agent
run "$VERIFY" owner/repo agent
assert_rc 0
need "OK: warning:"
need "actions/checkout@v4"
forbid "./local"
forbid "docker://alpine"
ok "unpinned warning"

reset
sha="0123456789abcdef0123456789abcdef01234567"
mutate "state[\"files\"][\".github/workflows/demo.yml\"]=\"name: demo\\njobs:\\n  demo:\\n    steps:\\n      - uses: example/action@${sha}\\n      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\\n\""
run "$APPLY" owner/repo agent
assert_rc 0
python3 - "$sha" <<'PY'
import json, os, sys
want = "example/action@" + sys.argv[1]
state = json.load(open(os.environ["GH_MOCK_STATE"], encoding="utf-8"))
patterns = state["selected"]["patterns_allowed"]
if patterns != [want]:
    sys.exit("patterns " + json.dumps(patterns))
PY
accept_agent
run "$VERIFY" owner/repo agent
assert_rc 0
forbid "warning:"
ok "third-party action allow-list"

# --- template does not hardcode the owner login ---
banned=$(printf '%s%s' siarhei rudak)
bad=""
while IFS= read -r hit; do
  case $hit in
    .github/CODEOWNERS:*|setup/TESTING.md:*|setup/apply-github-rules.sh:*|setup/tests/test-fake-gh.sh:*|docs/why.md:*) ;;
    *) bad="${bad}${hit}"$'\n' ;;
  esac
done < <(
  cd "$ROOT" || exit 1
  grep -RIn --exclude='*.png' --exclude-dir='.git' --exclude-dir='logs' "$banned" README.md docs setup .github || true
)
if [[ -n $bad ]]; then
  out=$bad
  fail "hardcoded owner login"
fi
ok "no hardcoded owner login"

if grep -n 'SKIPPED' "$ROOT/setup/apply-github-rules.sh" "$ROOT/setup/verify-github-rules.sh" "$ROOT/setup/common.sh"; then
  fail "SKIPPED is still a status"
fi
ok "no SKIPPED status"

printf 'ALL PASS\n'
