#!/usr/bin/env bash
# Visibility checks for folder allowlists, the unified deny, and launch logs.
# shellcheck disable=SC2016
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)
K=$SETUP/keel.sh
# shellcheck source=setup/lib/portable.sh
. "$SETUP/lib/portable.sh"
export KEEL_ROOT=${KEEL_ROOT:-$HOME/keel-proto}
export P=$KEEL_ROOT
export W=$P/work/task-1
export SETUP
export DOCKER=${DOCKER:-docker}
res(){ echo "RESULT $1: $2"; }
bad=0
mark(){
  if [ "$2" = ok ]; then res "$1" "BLOCKED ($3)"; else res "$1" "NOT BLOCKED ($3)"; bad=1; fi
}
need_log(){
  python3 - "$1" "$2" "$3" << 'PY'
import json, sys
path, role, needle = sys.argv[1:]
try:
    lines = open(path, encoding="utf-8")
except OSError:
    sys.exit(1)
for line in lines:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except ValueError:
        continue
    if role != "*" and obj.get("role") != role:
        continue
    if needle in json.dumps(obj):
        sys.exit(0)
sys.exit(1)
PY
}
LOG(){ echo "$P/.keel/logs/launch.jsonl"; }

rm -rf "$P"
"$K" init-repo >/dev/null
"$K" setup >/dev/null
mkdir -p "$W/briefs" "$W/docs" "$W/src" "$W/tests" "$W/skills-draft" "$W/skill-review" \
  "$W/plans" "$W/findings" "$W/qa-stub" "$W/research-stub" \
  "$W/.keel/decisions/task-1" "$W/.agents/skills/draft" "$P/.keel"
echo readme > "$W/tests/readme.txt"
echo code > "$W/src/app.c"
echo d1 > "$W/.keel/decisions/task-1/d1.md"
echo hand > "$W/briefs/handoff.md"
echo skill > "$W/.agents/skills/draft/SKILL.md"
echo ROOTSECRET > "$W/.env"
echo UNDERSECRET > "$W/src/.env"
echo CASESECRET > "$W/src/.ENV"
echo cust > "$W/src/customer.txt"
echo checklist > "$W/skill-review/list.txt"
echo postbase > "$W/src/feature.txt"
TOKEN='ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
export GH_TOKEN="$TOKEN"
export KEEL_SECRET='envonlysecretvalue123456'
python3 - << 'PY'
import base64, os
token = os.environ["GH_TOKEN"]
secret = os.environ["KEEL_SECRET"]
blob = base64.b64encode(token.encode()).decode()
text = token + "\n" + blob + "\n" + secret + "\npassword=hunter2hunter2hunter2\nZz9unknownSecretValue1234567890abcd\n"
open("/tmp/vis-fixture.txt","w",encoding="utf-8").write(text)
open(os.environ["P"] + "/.keel/redact-fixture","w",encoding="utf-8").write(text)
print("blob", blob)
PY
python3 - << 'PY'
import os, unicodedata
root = os.environ["W"]
nfd = unicodedata.normalize("NFD", "caf\u00e9")
nfc = unicodedata.normalize("NFC", "caf\u00e9")
open(os.path.join(root, "src", nfd), "w", encoding="utf-8").write("CAFESCRET\n")
open(os.path.join(root, ".keel", "deny.local"), "w", encoding="utf-8").write("src/customer.txt\nsrc/" + nfc + "\n")
open("/tmp/vis-nfd.txt", "w", encoding="utf-8").write(nfd)
PY

echo "### developer bundle"
out=$($K role developer 'printf "tests=%s\n" "$(cat /work/tests/readme.txt)"; echo hack > /work/tests/hack.txt && echo WRITE-OK || echo WRITE-FAIL; printf "under=%s\n" "$(cat /work/src/.env 2>/dev/null)"; cat /work/.env >/dev/null 2>&1 && echo ROOT-OK || echo NOROOT; printf "case=%s\n" "$(cat /work/src/.ENV 2>/dev/null)"; printf "cust=%s\n" "$(cat /work/src/customer.txt 2>/dev/null)"; echo STDOUT-MARKER')
echo "$out"
if echo "$out" | grep -q 'tests=readme' && echo "$out" | grep -q WRITE-FAIL && [ ! -e "$W/tests/hack.txt" ]; then mark V-H1 ok "read tests, write failed"; mark V-A2 ok "tests stay read-only"; else mark V-H1 bad "tests=$out"; mark V-A2 bad "write"; fi
if echo "$out" | grep -q UNDERSECRET; then mark V-A20 bad "deny lost"; mark V-H3 bad "under visible"; else mark V-A20 ok "deny wins"; mark V-H3 ok "basename withheld"; fi
if echo "$out" | grep -q NOROOT && ! echo "$out" | grep -q ROOTSECRET; then mark V-A1 ok "root secret absent"; else mark V-A1 bad "root visible"; fi
if echo "$out" | grep -q CASESECRET; then mark V-A15 bad "casefold"; else mark V-A15 ok "casefold withheld"; fi
if echo "$out" | grep -q '^cust=cust'; then mark V-A25 bad "customer visible"; else mark V-A25 ok "project deny held"; fi
if echo "$out" | grep -q STDOUT-MARKER && ! grep -q STDOUT-MARKER "$(LOG)"; then mark V-A24b ok "stdout not logged"; else mark V-A24b bad "stdout in log"; fi

nfd=$(cat /tmp/vis-nfd.txt)
out=$($K role developer "cat \"/work/src/$nfd\" 2>/dev/null || echo NOCAFE")
echo "cafe: $out"
if echo "$out" | grep -q CAFESCRET; then mark V-A16 bad "nfd visible"; else mark V-A16 ok "nfd withheld"; fi

echo "### orchestrator auditor architect skills tester"
out=$($K role orchestrator 'cat /work/.keel/decisions/task-1/d1.md; echo orch >> /work/.keel/decisions/task-1/d1.md; cat /work/.env >/dev/null 2>&1 && echo ROOT-OK || echo NOROOT')
echo "$out"
if echo "$out" | grep -q '^d1$' && grep -q orch "$W/.keel/decisions/task-1/d1.md" && echo "$out" | grep -q NOROOT; then mark V-H2 ok "decisions rw, secret absent"; else mark V-H2 bad "$out"; fi
out=$($K role auditor 'cat /work/.keel/decisions/task-1/d1.md >/dev/null 2>&1 && echo DEC-OK || echo NODEC; cat /work/.agents/skills/draft/SKILL.md >/dev/null 2>&1 && echo SKILL-OK || echo NOSKILL')
echo "$out"
if echo "$out" | grep -q NODEC && echo "$out" | grep -q NOSKILL; then mark V-H5 ok "auditor withheld"; mark V-A5 ok "auditor log later"; else mark V-H5 bad "$out"; mark V-A5 bad "$out"; fi
out=$($K role skills_auditor 'cat /work/skill-review/list.txt')
echo "$out"
if echo "$out" | grep -q checklist; then mark V-H6 ok "stub launched"; else mark V-H6 bad "$out"; fi
out=$($K role architect 'printf "h=%s d=%s\n" "$(cat /work/briefs/handoff.md)" "$(cat /work/.keel/decisions/task-1/d1.md)"')
echo "$out"
if echo "$out" | grep -q 'h=hand' && echo "$out" | grep -q 'd=d1'; then mark V-H7 ok "architect reads"; else mark V-H7 bad "$out"; fi
out=$($K role developer 'echo x > /work/.keel/decisions/task-1/pwn && echo WROTE || echo NOWRITE; cat /work/.keel/decisions/task-1/d1.md >/dev/null 2>&1 && echo DEC-OK || echo NODEC')
echo "devdec: $out"
out2=$($K role tester 'cat /work/src/feature.txt >/dev/null 2>&1 && echo FEAT-OK || echo NOFEAT; cat /work/.keel/decisions/task-1/d1.md >/dev/null 2>&1 && echo DEC-OK || echo NODEC')
echo "tester: $out2"
if echo "$out" | grep -q NODEC && echo "$out" | grep -q NOWRITE && echo "$out2" | grep -q NODEC && echo "$out2" | grep -q NOFEAT; then mark V-A27 ok "developer and tester miss decisions"; mark V-H4 ok "tester misses post-base"; mark V-A6 ok "tester post-base"; else mark V-A27 bad "dec"; mark V-H4 bad "$out2"; mark V-A6 bad "$out2"; fi

out=$($K role developer 'echo PWNLOG > /work/.keel/logs/launch.jsonl && echo LOG-OK || echo NOLOG; echo PWNRUN > /work/.keel/runs/task-1/x && echo RUN-OK || echo NORUN; echo PWNDENY > /work/.keel/deny.local && echo DENY-OK || echo NODENY; cat /work/.git/hooks/pre-commit >/dev/null 2>&1 && echo HOOK-OK || echo NOHOOK')
echo "escapes: $out"
if echo "$out" | grep -q NOLOG && ! grep -q PWNLOG "$(LOG)"; then mark V-A23 ok "logs absent"; else mark V-A23 bad "$out"; fi
if echo "$out" | grep -q NORUN; then mark V-A28 ok "runs absent"; else mark V-A28 bad "$out"; fi
if echo "$out" | grep -q NODENY && ! grep -q PWNDENY "$W/.keel/deny.local"; then mark V-A25b ok "deny.local not written"; else mark V-A25b bad "$out"; fi
if echo "$out" | grep -q NOHOOK; then mark V-A11 ok "hooks absent"; else mark V-A11 bad "$out"; fi

rm -f "$W/.keel/deny.local"
out=$($K role developer 'printf "cust=%s\n" "$(cat /work/src/customer.txt 2>/dev/null)"')
echo "reload: $out"
if echo "$out" | grep -q '^cust=cust'; then mark V-A25c bad "snapshot dropped"; else mark V-A25c ok "snapshot kept"; fi

out=$(KEEL_EXTRA_MOUNTS=/ MNT=rw $K role developer 'cat /work/.env >/dev/null 2>&1 && echo ROOT-OK || echo NOROOT')
echo "widen: $out"
if echo "$out" | grep -q NOROOT; then mark V-A17 ok "env did not widen"; else mark V-A17 bad "$out"; fi
out=$($K role-env developer 'cat /work/.env >/dev/null 2>&1 && echo ROOT-OK || echo NOROOT')
echo "role-env: $out"
out2=$($K role-env 'cat /' ; echo rc:$?)
echo "role-env bare: $out2"
if echo "$out" | grep -q NOROOT && echo "$out2" | grep -q role_env_args; then mark V-A18 ok "role-env gated"; else mark V-A18 bad "env"; fi

out=$($K role critic 'echo CRITIC-OK')
out3=$($K role verifier 'ls /work/findings >/dev/null && echo FINDINGS-OK')
out4=$($K role qa 'ls /work/qa-stub >/dev/null && echo QA-OK')
out5=$($K role researcher 'ls /work/research-stub >/dev/null && echo RESEARCH-OK')
echo "stubs $out $out3 $out4 $out5"
if echo "$out" | grep -q CRITIC-OK && echo "$out3" | grep -q FINDINGS-OK && echo "$out4" | grep -q QA-OK && echo "$out5" | grep -q RESEARCH-OK; then mark V-H6b ok "other stubs"; else mark V-H6b bad "stubs"; fi

out=$($K role notarealrole true 2>&1; echo rc:$?)
echo "unknown: $out"
if echo "$out" | grep -q unknown_role; then mark V-A12 ok "unknown refused"; else mark V-A12 bad "$out"; fi

ln -s ../.env "$W/src/leak"
out=$($K role developer 'cat /work/src/leak || echo NOLEAK' 2>&1; echo rc:$?)
echo "link: $out"
if ! echo "$out" | grep -q ROOTSECRET && { echo "$out" | grep -q NOLEAK || echo "$out" | grep -q symlink_escape; } && grep -q ROOTSECRET "$W/.env"; then mark V-A7 ok "symlink withheld"; else mark V-A7 bad "$out"; fi
rm -f "$W/src/leak"
ln "$W/src/.env" "$W/src/alias"
out=$($K role developer 'printf "alias=%s\n" "$(cat /work/src/alias 2>/dev/null)"' 2>&1)
echo "hard: $out"
if ! echo "$out" | grep -q UNDERSECRET && echo "$out" | grep -q hardlink_withheld; then mark V-A8 ok "hardlink refused"; else mark V-A8 bad "$out"; fi

if python3 - << 'PY'
import json, os, sys
p=os.environ["P"]+"/.keel/logs/launch.jsonl"
token=os.environ["GH_TOKEN"]
secret=os.environ["KEEL_SECRET"]
blob=__import__("base64").b64encode(token.encode()).decode()
text=open(p,encoding="utf-8").read()
bad=[]
if token in text or secret in text or blob in text or "Zz9unknownSecretValue1234567890abcd" in text or "hunter2hunter2hunter2" in text:
    bad.append("raw")
if "STDOUT-MARKER" in text:
    bad.append("stdout")
if "[REDACTED:token]" not in text or "[REDACTED:env]" not in text or "[REDACTED:password]" not in text or "[REDACTED:unknown]" not in text:
    bad.append("placeholder")
counts=[]
for line in text.splitlines():
    if not line.strip():
        continue
    obj=json.loads(line)
    counts.append(obj.get("redactions"))
    if obj.get("event")=="launch_ok" and obj.get("role")=="developer":
        if "mounted_roots" not in obj or "denied_withheld" not in obj:
            bad.append("fields")
if any(c != 5 for c in counts):
    bad.append("count %s" % counts[:8])
print("REDACT", "ok" if not bad else "bad "+",".join(bad))
sys.exit(0 if not bad else 1)
PY
then
  mark V-A24 ok "redacted"; mark V-A29 ok "count"; mark V-A30 ok "unknown"; mark V-A31 ok "base64 and multiline"; mark V-H8 ok "log fields"
else
  mark V-A24 bad "redact"; mark V-A29 bad "count"; mark V-A30 bad "unknown"; mark V-A31 bad "encoded"; mark V-H8 bad "log"
fi

# logs for a sample of roles
if need_log "$(LOG)" developer launch_ok && need_log "$(LOG)" auditor launch_ok && need_log "$(LOG)" notarealrole unknown_role && need_log "$(LOG)" "" role_env_args && need_log "$(LOG)" developer symlink_escape && need_log "$(LOG)" developer hardlink_withheld; then
  mark V-LOG ok "log entries"
else
  mark V-LOG bad "missing log"
  bad=1
fi

# parser attacks on a temp harness
python3 - << 'PY'
import os, shutil, subprocess, sys, json, textwrap, tempfile
setup=os.environ["SETUP"]
py=os.path.join(setup,"lib","visibility.py")
td=tempfile.mkdtemp()
def harness():
    h=os.path.join(td,"h")
    if os.path.isdir(h):
        shutil.rmtree(h)
    os.makedirs(os.path.join(h,"allow"))
    os.makedirs(os.path.join(h,"deny"))
    shutil.copy(os.path.join(setup,"deny","base"), os.path.join(h,"deny","base"))
    for name in os.listdir(os.path.join(setup,"allow")):
        src=os.path.join(setup,"allow",name)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(h,"allow",name))
    return h
def mounts(h, work, keel, role):
    os.makedirs(work, exist_ok=True)
    os.makedirs(keel, exist_ok=True)
    p=subprocess.run([sys.executable, py, "mounts", "--role", role, "--work", work, "--harness", h, "--keel", keel, "--task", "task-1", "--repo", work], capture_output=True, text=True)
    log=os.path.join(keel,".keel","logs","launch.jsonl")
    return p.returncode, p.stdout, p.stderr, log

def check(code, cond, log, needle, role):
    if log and needle and cond:
        text=open(log,encoding="utf-8").read()
        if needle not in text:
            cond = False
    if cond:
        print("RESULT %s: BLOCKED (parser)" % code)
        return 0
    print("RESULT %s: NOT BLOCKED (parser)" % code)
    return 1

rc=0
h=harness()
open(os.path.join(h,"allow","developer.paths"),"w").write("\n# empty\n")
w=os.path.join(td,"w1"); k=os.path.join(td,"k1")
c,out,err,log=mounts(h,w,k,"developer")
rc |= check("V-A13", c!=0 and "allow_empty" in out, log, "allow_empty", "developer")

h=harness()
open(os.path.join(h,"allow","developer.paths"),"w").write("/etc\n")
w=os.path.join(td,"w2"); k=os.path.join(td,"k2")
c,out,err,log=mounts(h,w,k,"developer")
rc |= check("V-A14", c!=0 and "allow_escape" in out, log, "allow_escape", "developer")

h=harness()
open(os.path.join(h,"allow","developer.paths"),"w").write("src extra\n")
w=os.path.join(td,"w3"); k=os.path.join(td,"k3")
c,out,err,log=mounts(h,w,k,"developer")
rc |= check("V-A4", c!=0 and "allow_malformed" in out, log, "allow_malformed", "developer")

h=harness()
w=os.path.join(td,"w4"); k=os.path.join(td,"k4")
os.makedirs(os.path.join(w,".keel"), exist_ok=True)
open(os.path.join(w,".keel","deny.local"),"w").write("this is bad\n")
c,out,err,log=mounts(h,w,k,"developer")
rc |= check("V-A21", c!=0 and "deny_local_malformed" in out, log, "deny_local_malformed", "developer")

h=harness()
w=os.path.join(td,"w5"); k=os.path.join(td,"k5")
os.makedirs(os.path.join(w,".keel"), exist_ok=True)
open(os.path.join(w,".keel","deny.local"),"w").write("src/*\n")
c,out,err,log=mounts(h,w,k,"developer")
rc |= check("V-A22", c!=0 and "deny_local_glob" in out, log, "deny_local_glob", "developer")

h=harness()
w=os.path.join(td,"w6"); k=os.path.join(td,"k6")
os.makedirs(os.path.join(w,"src"), exist_ok=True)
os.makedirs(os.path.join(w,"docs"), exist_ok=True)
os.makedirs(os.path.join(w,"tests"), exist_ok=True)
os.makedirs(os.path.join(w,".keel"), exist_ok=True)
open(os.path.join(w,"src",".env"),"w").write("UNDERSECRET\n")
open(os.path.join(w,".keel","deny.local"),"w").write("- .env\n")
c,out,err,log=mounts(h,w,k,"developer")
leaked = c==0 and "/work/src/.env" not in out
rc |= check("V-A19", (c!=0 and "deny_narrow" in out) and not leaked, log, "deny_narrow", "developer")
rc |= check("V-A3", (c!=0 and "deny_narrow" in out), log, "deny_narrow", "developer")

h=harness()
base=os.path.join(h,"deny","base")
text=open(base,encoding="utf-8").read().replace("name .env\n","")
open(base,"w",encoding="utf-8").write(text)
w=os.path.join(td,"w7"); k=os.path.join(td,"k7")
c,out,err,log=mounts(h,w,k,"developer")
rc |= check("V-A3b", c!=0 and "deny_base_narrow" in out, log, "deny_base_narrow", "developer")

h=harness()
base=os.path.join(h,"deny","base")
os.rename(base, base+".real")
os.symlink(base+".real", base)
w=os.path.join(td,"w8"); k=os.path.join(td,"k8")
c,out,err,log=mounts(h,w,k,"developer")
rc |= check("V-A26", c!=0 and "deny_base_symlink" in out, log, "deny_base_symlink", "developer")

h=harness()
base=os.path.join(h,"deny","base")
os.remove(base)
os.mkdir(base)
w=os.path.join(td,"w9"); k=os.path.join(td,"k9")
c,out,err,log=mounts(h,w,k,"developer")
rc |= check("V-A32", c!=0 and "deny_base_symlink" in out, log, "deny_base_symlink", "developer")
sys.exit(rc)
PY
prc=$?
if [ $prc -eq 0 ]; then mark V-PARSE ok "parser attacks"; else mark V-PARSE bad "parser rc=$prc"; fi

# nested ro
vro=$(mktemp -d)
mkdir -p "$vro/parent/child"
echo child > "$vro/parent/child/file.txt"
if docker run --rm --read-only --user "$(id -u):$(id -g)" -v "$vro/parent:/work:rw" -v "$vro/parent/child:/work/child:ro" keel-git sh -c 'echo hack > /work/child/file.txt && echo WRITE-OK || echo WRITE-FAIL' | grep -q WRITE-FAIL; then
  mark V-RO ok "nested read-only child"
else
  mark V-RO bad "nested ro failed"
fi
rm -rf "$vro"

"$K" cleanup >/dev/null
if [ -e "$P/task-1.deny" ] || [ -d "$P/.keel/runs" ]; then mark V-RUNS bad "left behind"; else mark V-RUNS ok "cleaned"; fi
echo BAD=$bad
exit $bad
