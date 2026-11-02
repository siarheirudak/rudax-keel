#!/usr/bin/env bash
# Egress allowlist checks. Distinct tool-missing errors are not BLOCKED.
# shellcheck disable=SC2016
set -u
HERE=$(cd "$(dirname "$0")" && pwd -P)
SETUP=$(cd "$HERE/../.." && pwd -P)
K=$SETUP/keel.sh
# shellcheck source=setup/lib/portable.sh
. "$SETUP/lib/portable.sh"
export KEEL_ROOT=${KEEL_ROOT:-$HOME/keel-proto}
export DOCKER=${DOCKER:-docker}
unset GH_TOKEN GITHUB_TOKEN BOT_GH_TOKEN GITHUB_PAT AWS_SECRET_ACCESS_KEY AWS_ACCESS_KEY_ID API_KEY API_TOKEN NPM_TOKEN PYPI_TOKEN PASSWORD OPENAI_API_KEY KEEL_SECRET ANTHROPIC_API_KEY GEMINI_API_KEY GOOGLE_API_KEY OPENROUTER_API_KEY || true
P=$KEEL_ROOT
bad=0
res(){ echo "RESULT $1: $2"; if [ "$2" != "${2#NOT BLOCKED}" ] || [ "$2" != "${2#ERROR}" ] || [ "$2" != "${2#WRONG REASON}" ]; then bad=1; fi; }
logf(){ echo "$P/.keel/logs/egress.jsonl"; }
cleanup_ns() {
  local n
  n=$(printf '%s' "${KEEL_NS:-}" | tr '[:upper:]' '[:lower:]')
  [ -n "$n" ] || return 0
  $DOCKER rm -f "keel-proxy-${n}" "keel-mock-${n}" >/dev/null 2>&1 || true
  $DOCKER network rm "keel-egress-${n}" "keel-out-${n}" >/dev/null 2>&1 || true
}
trap cleanup_ns EXIT
denied_hosts(){
  python3 - "$(logf)" "$@" << 'PY'
import json, sys
path, hosts = sys.argv[1], sys.argv[2:]
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
got = {row.get("host") for row in rows if row.get("reason") == "not_allowlisted"}
sys.exit(0 if set(hosts) <= got else 1)
PY
}

rm -rf "$P"
"$K" init-repo >/dev/null
"$K" setup >/dev/null
# A proxy left from another KEEL_ROOT keeps the old log mount. Start clean.
ns=$(printf '%s' "${KEEL_NS:-}" | tr '[:upper:]' '[:lower:]')
if [ -n "$ns" ]; then
  cleanup_ns
else
  $DOCKER rm -f keel-proxy keel-mock >/dev/null 2>&1 || true
fi
if ! up=$("$K" egress-up 2>&1); then
  printf '%s\n' "$up" >&2
  res E-H1 "ERROR egress setup failed"
  exit 1
fi

tools=$("$K" role developer 'command -v wget; command -v nc; command -v nslookup' 2>&1 || true)
if ! printf '%s\n' "$tools" | grep -q '/wget' || ! printf '%s\n' "$tools" | grep -q '/nc' || ! printf '%s\n' "$tools" | grep -q '/nslookup'; then
  for id in E-H1 E-H2 E-H3 E-H4 E-H5 E-H6 E-A1 E-A2 E-A3 E-A4 E-A5 E-A6 E-A7 E-A8 E-A9 E-A10 E-A11 E-A12 E-A13 E-A14 E-A15 E-A16 E-A17; do
    res "$id" "ERROR tool missing"
  done
  exit 1
fi

out=$("$K" role developer 'wget -q -T 8 -O- http://keel-mock/health' 2>&1 || true)
echo "E-H1: $out"
if printf '%s\n' "$out" | grep -q MOCK-OK; then res E-H1 "BLOCKED (mock via proxy)"; else res E-H1 "NOT BLOCKED ($out)"; fi

dark(){
  local id=$1 role=$2 out
  out=$("$K" role "$role" 'echo LAUNCH-OK; wget -q -T 5 -O- http://keel-mock/health 2>/dev/null; wget -q -T 3 -O- http://1.1.1.1/ >/dev/null 2>&1 && echo NET-OK; nslookup example.com >/dev/null 2>&1 && echo DNS-OK; true' 2>&1 || true)
  echo "$id: $out"
  if ! printf '%s\n' "$out" | grep -q LAUNCH-OK; then res "$id" "NOT BLOCKED (no launch)"; return; fi
  if printf '%s\n' "$out" | grep -qE 'MOCK-OK|NET-OK|DNS-OK'; then res "$id" "NOT BLOCKED"; else res "$id" "BLOCKED (no HTTP, no DNS)"; fi
}
dark E-H2 critic
dark E-H5 qa
dark E-H6 researcher
dark E-A3 critic
dark E-A4 qa
dark E-A7 researcher

out=$("$K" proto net ro 'echo LAUNCH-OK; wget -q -T 3 -O- http://1.1.1.1 >/dev/null 2>&1 && echo NET-OK; nslookup example.com >/dev/null 2>&1 && echo DNS-OK; true' 2>&1 || true)
echo "E-H4: $out"
if printf '%s\n' "$out" | grep -qE 'NET-OK|DNS-OK'; then res E-H4 "NOT BLOCKED"; else res E-H4 "BLOCKED (proto has no network)"; fi

: > "$(logf)" 2>/dev/null || true
mkdir -p "$P/.keel/logs"
: > "$(logf)"
out=$("$K" role developer 'wget -q -T 5 -O- http://example.com/secret?x=1 >/dev/null 2>&1; echo done' 2>&1 || true)
echo "E-H3: $out"
if python3 - "$(logf)" << 'PY'
import json, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
rows = [json.loads(line) for line in text.splitlines() if line.strip()]
ok = any(row.get("host") == "example.com:80" and row.get("reason") and "/secret" not in row.get("host","") and "x=1" not in json.dumps(row) for row in rows)
print("E-H3-LOG", "ok" if ok else "bad")
sys.exit(0 if ok else 1)
PY
then res E-H3 "BLOCKED (denial host:port)"; else res E-H3 "NOT BLOCKED (log)"; fi

out=$("$K" role developer 'wget -q -T 5 -O- http://example.com/secret?x=1 >/dev/null 2>&1; wget -q -T 5 -O- http://1.1.1.1/ >/dev/null 2>&1; echo done' 2>&1 || true)
echo "E-A1: $out"
if printf '%s\n' "$out" | grep -q MOCK-OK; then res E-A1 "NOT BLOCKED";
elif ! denied_hosts example.com:80 1.1.1.1:80; then res E-A1 "NOT BLOCKED (log)";
else res E-A1 "BLOCKED (unauthorized host)"; fi

out=$("$K" role developer 'env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy wget -q -T 3 -O- http://1.1.1.1/ ; echo raw-done' 2>&1 || true)
echo "E-A2: $out"
if printf '%s\n' "$out" | grep -q 'Network unreachable'; then res E-A2 "BLOCKED (no public route)"; else res E-A2 "NOT BLOCKED"; fi

out=$("$K" role developer 'grep -q egress /proc/mounts && echo MOUNTED || echo ABSENT; ls /allow/developer.allow >/dev/null 2>&1 && echo POLICY || echo ABSENT' 2>&1 || true)
echo "E-A5: $out"
if printf '%s\n' "$out" | grep -q POLICY || printf '%s\n' "$out" | grep -q MOUNTED; then res E-A5 "NOT BLOCKED"; else res E-A5 "BLOCKED (policy not mounted)"; fi

out=$("$K" role developer 'nc -w 2 keel-proxy 3129; echo nc-rc:$?' 2>&1 || true)
echo "E-A8: $out"
if printf '%s\n' "$out" | grep -q ADMIN-OK; then res E-A8 "NOT BLOCKED"; else res E-A8 "BLOCKED (admin port closed)"; fi

out=$("$K" role developer 'nslookup example.com 127.0.0.11; echo ns-rc:$?' 2>&1 || true)
echo "E-A9: $out"
if printf '%s\n' "$out" | grep -q 'Name:'; then res E-A9 "NOT BLOCKED"; else res E-A9 "BLOCKED (embedded DNS)"; fi

out=$("$K" role developer 'echo disabled=$(cat /proc/sys/net/ipv6/conf/all/disable_ipv6 2>/dev/null || echo missing)' 2>&1 || true)
echo "E-A10: $out"
if printf '%s\n' "$out" | grep -q 'disabled=1'; then res E-A10 "BLOCKED (ipv6 disabled)"; else res E-A10 "NOT BLOCKED"; fi

out=$("$K" role developer 'env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy wget -q -T 3 -O- http://169.254.169.254/ ; echo meta-done' 2>&1 || true)
echo "E-A11: $out"
if printf '%s\n' "$out" | grep -q 'Network unreachable'; then res E-A11 "BLOCKED (no metadata route)"; else res E-A11 "NOT BLOCKED"; fi

before=$(wc -l < "$(logf)" | tr -d ' ')
out=$("$K" role developer 'printf "CONNECT keel-mock:22 HTTP/1.1\r\nHost: keel-mock:22\r\n\r\n" | nc -w 3 keel-proxy 3128; echo nc-done' 2>&1 || true)
echo "E-A12: $out"
if printf '%s\n' "$out" | grep -q '200 Connection Established'; then res E-A12 "NOT BLOCKED";
elif ! denied_hosts keel-mock:22; then res E-A12 "NOT BLOCKED (log)";
else res E-A12 "BLOCKED (port not allowed)"; fi

out=$("$K" role developer 'printf "CONNECT evil.example:443 HTTP/1.1\r\nHost: keel-mock:443\r\n\r\n" | nc -w 3 keel-proxy 3128; echo nc-done' 2>&1 || true)
echo "E-A13: $out"
if printf '%s\n' "$out" | grep -q '200 Connection Established'; then res E-A13 "NOT BLOCKED"; else res E-A13 "BLOCKED (CONNECT target)"; fi

out=$("$K" role developer 'wget -q -T 5 -O- http://keel-mock/redir; echo redir-done' 2>&1 || true)
echo "E-A14: $out"
if printf '%s\n' "$out" | grep -q SECRET-BODY; then res E-A14 "NOT BLOCKED";
elif ! grep -q 'keel-secret:80' "$(logf)"; then res E-A14 "NOT BLOCKED (log)";
else res E-A14 "BLOCKED (redirect rechecked)"; fi

before=$(wc -l < "$(logf)" | tr -d ' ')
out=$("$K" role developer 'printf "CONNECT a%%0d%%0asecond-record.example:443 HTTP/1.1\r\nHost: a%%0d%%0asecond-record.example:443\r\n\r\n" | nc -w 3 keel-proxy 3128; echo nc-done' 2>&1 || true)
echo "E-A15: $out"
after=$(wc -l < "$(logf)" | tr -d ' ')
if grep -q second-record "$(logf)" || [ "$((after - before))" -gt 1 ]; then res E-A15 "NOT BLOCKED";
else res E-A15 "BLOCKED (sanitized log)"; fi

out=$("$K" role developer 'wget -q -T 5 -O- http://evil.keel-mock/x >/dev/null 2>&1; wget -q -T 5 -O- http://Example.COM/x >/dev/null 2>&1; wget -q -T 5 -O- http://example.com./x >/dev/null 2>&1; wget -q -T 5 -O- http://xn--bcher-kva.de/x >/dev/null 2>&1; echo match-done' 2>&1 || true)
echo "E-A17: $out"
if printf '%s\n' "$out" | grep -q MOCK-OK; then res E-A17 "NOT BLOCKED";
elif ! denied_hosts evil.keel-mock:80; then res E-A17 "NOT BLOCKED (log)";
else res E-A17 "BLOCKED (exact match)"; fi

allow=$SETUP/egress/developer.allow
backup=$(mktemp)
cp "$allow" "$backup"
printf '%s\n' '*.example.com' > "$allow"
out=$("$K" role developer 'echo LAUNCH-OK' 2>&1 || true)
cp "$backup" "$allow"
rm -f "$backup"
echo "E-A6: $out"
if printf '%s\n' "$out" | grep -q malformed_profile && ! printf '%s\n' "$out" | grep -q LAUNCH-OK; then res E-A6 "BLOCKED (malformed profile)"; else res E-A6 "NOT BLOCKED"; fi

ns=$(printf '%s' "${KEEL_NS:-}" | tr '[:upper:]' '[:lower:]')
if [ -n "$ns" ]; then proxy_name="keel-proxy-${ns}"; else proxy_name="keel-proxy"; fi
$DOCKER stop "$proxy_name" >/dev/null 2>&1 || true
out=$("$K" role developer 'echo LAUNCH-OK' 2>&1 || true)
echo "E-A16: $out"
$DOCKER rm -f "$proxy_name" >/dev/null 2>&1 || true
"$K" egress-up >/dev/null 2>&1 || true
if printf '%s\n' "$out" | grep -q LAUNCH-OK && ! printf '%s\n' "$out" | grep -q REFUSE; then res E-A16 "NOT BLOCKED"; else res E-A16 "BLOCKED (proxy down)"; fi

echo EGRESS_BAD=$bad
exit $bad
