#!/usr/bin/env python3
"""Mutation audit: remove one protection at a time in a temp copy, rerun test-attacks.sh,
and require that the guarding check(s) stop reporting BLOCKED/CONTAINED.
Usage: DOCKER="sudo docker" python3 setup/tests/harness/mutate.py [ID ...]   (box/Linux only; ~40 s per mutant)"""
import os, re, shutil, subprocess, sys, tempfile, concurrent.futures as cf
HARNESS = os.path.dirname(os.path.abspath(__file__))
SETUP = os.path.abspath(os.path.join(HARNESS, os.pardir, os.pardir))
K = 'keel.sh'
# id: (file, old, new, protection removed, expected red check IDs ([] = known masked by another layer))
M = {
 'M01': (K, '-v "$R/.git/objects:/base/objects:ro" "${MNT[@]}" -w /work "$IMG" sh -c "$*";;', '-v "$R/.git/objects:/base/objects" "${MNT[@]}" -w /work "$IMG" sh -c "$*";;', ':ro on base objects mount (roles)', ['A1']),
 'M02': (K, 'MNT=(-v "$W:/work:$m" -v "$W/.git:/work/.git:ro"', 'MNT=(-v "$W:/work:$m" -v "$W/.git:/work/.git"', ':ro on pointer file bind', ['A2']),
 'M03': (K, 'HARDEN=(--rm --network none ', 'HARDEN=(--rm ', '--network none', ['N1']),
 'M04': (K, 'GITENV=(-e HOME=/tmp ', 'GITENV=(-e "GH_TOKEN=${GH_TOKEN:-}" -e "GITHUB_TOKEN=${GITHUB_TOKEN:-}" -e HOME=/tmp ', 'token passed with -e NAME=value', ['N2']),
 'M05': (K, 'reset_shadow(){ # plain', 'reset_shadow(){ return 0; # plain', 'reset_shadow', ['A12']),
 'M06': (K, '-e "GIT_CONFIG_PARAMETERS=\'core.hooksPath\'=\'/dev/null\' \'core.fsmonitor\'=\'false\'"', '', 'GIT_CONFIG_PARAMETERS', ['A12b']),
 'M07': (K, 'grep -ivxE \'setup/readme\\.md|setup/testing\\.md\' "$P/.gatehome/paths" | grep -iE "$FORBID_PREFIX|$FORBID_NAME" && fail', 'grep -iE "^$" "$P/.gatehome/paths" && fail', 'gate: forbidden paths', ['A4', 'A4b', 'A4c', 'A17', 'A18', 'A18b']),
 'M08': (K, 'grep -iE "$FORBID_PREFIX|', 'grep -E "$FORBID_PREFIX|', 'gate: case-insensitive match', ['A4c']),
 'M09': (K, '[ -z "$sym" ] ||', 'true ||', 'gate: symlink rule', ['A5']),
 'M10': (K, '[ "$sz" -le "$MAX_BUNDLE" ] || fail', 'true || fail', 'gate: bundle size', ['A6']),
 'M11': (K, '[ "$lines" -le "$MAX_LINES" ] || fail', 'true || fail', 'gate: line limit', ['A6b']),
 'M12': (K, 'then fail "refs in bundle must be', 'then : "refs in bundle must be', 'gate: exactly one ref', ['A7', 'A7b']),
 'M13': (K, '[ "$pre" = "$M" ] || fail', 'true || fail', 'gate: prerequisite == main', ['A8b']),
 'M14': (K, '[ "$(hgit -C "$G" merge-base main "$I")" = "$M" ] || fail', 'true || fail', 'gate: merge-base == main', []),
 'M15': (K, '[ "$pre" = "$M" ] || fail', 'true || fail', 'gate: prerequisite AND merge-base (M15 also applies M14)', ['A8', 'A8b']),
 'M16': (K, 'else fail "foreign-owned files: $bad"; fi', 'fi', 'gate: ownership', ['A11-detect']),
 'M17': (K, 'hgit -C "$G" fsck --no-dangling "$I" >/dev/null || fail "fetch/fsck"', 'true', 'gate: fsck received commits', ['A13']),
 'M18': (K, '[ -z "$gl" ] ||', 'true ||', 'gate: gitlink rule', ['A14']),
 'M19': (K, '[ "$nf" -le "$MAX_FILES" ] || fail', 'true || fail', 'gate: file-count limit', ['A6c']),
 'M20': (K, '[ -z "$badid" ] || fail', 'true || fail', 'gate: agent identity', ['A15']),
 'M21': (K, 'hgit -C "$G" bundle verify -q "$F" || fail "bundle verify"', 'true', 'gate: bundle verify', []),
 'M22': (K, '--network none --user "$UIDGID" ', '--network none ', '--user uid:gid', ['A11']),
 'M23': (K, '--cap-drop ALL ', '', '--cap-drop ALL', ['H1']),
 'M24': (K, '--security-opt no-new-privileges\n', '\n', 'no-new-privileges', ['H1']),
 'M25': (K, '  --read-only --tmpfs', '  --tmpfs', '--read-only', ['H4']),
 'M26': (K, '--pids-limit "${PIDS:-128}" ', '', '--pids-limit', ['H2']),
 'M27': (K, '--memory "${MEM:-512m}" ', '', '--memory', ['H3']),
 'M28': (K, ' --cpus "${CPUS:-1}")', ')', '--cpus', ['H5']),
 'M29': (K, 'repo-gc|repo-prune) tasks_active &&', 'repo-gc|repo-prune) false &&', 'gc guard (no-op)', ['A10']),
 'M30': (K, 'if tasks_active && ! git -C "$R" merge-base', 'if false && ! git -C "$R" merge-base', 'set-main fast-forward guard', ['A10b']),
 'M31': (K, 'push origin $I:refs/heads/agent/$T', 'push --all origin', 'push stub single refspec', ['A16']),
 'M32': (K, 'work_mounts(){ local m=$1', 'work_mounts(){ local m=rw', 'reviewer ro mounts', ['A9']),
 'M33': (K, 'git config gc.pruneExpire never; ', '', 'gc.pruneExpire=never in repo', []),
 'M34': (K, '&&\n    echo /base/objects > "$S/objects/info/alternates" ) ||', ') ||', 'reset_shadow alternates rewrite (caught since A19: file is unlinked first)', ['A4', 'A13']),

 'M35': (K, 'grep -ivxE \'setup/readme\\.md|setup/testing\\.md\' "$P/.gatehome/paths" | grep -iE "$FORBID_PREFIX|$FORBID_NAME"', 'hgit -C "$G" diff --raw --no-renames main $I | awk \'{print $NF}\' | grep -iE "$FORBID_PREFIX|$FORBID_NAME"', 'A17: NUL-safe path parsing (back to awk $NF on --raw)', ['A17', 'A17b', 'A17c']),
 'M36': (K, "FORBID_NAME='(^|/)(", "FORBID_NAME='^(", 'A18: rule names matched anywhere (anchored to root only)', ['A18', 'A18b']),
 'M37': (K, "FORBID_PREFIX='^(\\.github|setup|scripts)/|(^|/)\\.pi/|(^|/)\\.agents/'", "FORBID_PREFIX='^(\\.github)/|(^|/)\\.pi/'", 'A18b: prefixes setup/ scripts/ .agents/ at any depth', ['A18b']),
 'M38': (K, 'for f in config objects/info/alternates', 'for f in objects/info/alternates', 'A19: unlink config before write (+ noclobber removed)', ['A19'], [('( set -C   #', '(   #')]),
 'M39': (K, 'if [ -L "$d" ] ||', 'if false && [ -L "$d" ] ||', 'A19b: refuse symlinked shadow dirs', ['A19b']),
 'M40': (K, 'grep -iE "$DOTGIT" "$P/.gatehome/paths" && fail', 'false && fail', 'A20: nested .git path rule', []),
 'M41': (K, 'grep -iE "$DOTGIT" "$P/.gatehome/paths" && fail', 'false && fail', 'A20: nested .git rule + fetch fsck (unmask)', ['A20'], [('-c fetch.fsckObjects=true -c transfer.fsckObjects=true ', '')]),
 'M42': (K, 'show "main:$TEST_ENTRY"', 'show "$I:$TEST_ENTRY"', 'A21: test entrypoint pinned to main', ['A21']),
 'M43': (K, '--min-parents=2 "main..$I")" ] ||', '--min-parents=2 "main..$I")" ] || true ||', 'A22b: reject merge commits', ['A22b']),
 'M44': (K, '--max-parents=0 "main..$I")" ] ||', '--max-parents=0 "main..$I")" ] || true ||', 'A22: reject orphan/root commits', []),
 'M45': ('lib/visibility.py', 'return "ro"  # developer-tests-ro', 'return "rw"  # developer-tests-ro', 'drop read-only on tests', ['V-A2']),
 'M46': ('lib/visibility.py', 'apply_overlay = True  # deny-overlay-on', 'apply_overlay = False  # deny-overlay-on', 'skip the deny', ['V-A20']),
 'M47': (K, '  # Whole-tree fallback is not used.\n  :', '  MNT+=(-v "$W:/work:rw")', 'restore the whole-tree fallback', ['V-A17']),
 'M48': ('lib/visibility.py', 'raise PolicyError("deny_narrow", ".keel/deny.local", rec.line, rec.value)  # narrow-refused', 'rules[:] = [r for r in rules if not (r.kind == "name" and fold_key(r.value) == fold_key(rec.value))]  # narrow-refused', 'narrow the deny base', ['V-A19']),
 'M49': ('lib/visibility.py', '.casefold()  # fold-nfc-case', '  # fold-nfc-case', 'break casefold matching', ['V-A15']),
 'M50': ('lib/visibility.py', 'unicodedata.normalize("NFC", text).casefold()', 'text.casefold()', 'break NFC matching', ['V-A16']),
 'M51': ('lib/visibility.py', 'return _redact_impl(text, env)  # redaction-on', 'return text, 0  # redaction-on', 'disable log redaction', ['V-A24']),
 'M52': ('lib/visibility.py', 'same_fs = False  # developer-same-fs', 'same_fs = True  # developer-same-fs', 'make developer tests writable on the same filesystem as src', ['V-A10-hardlink']),
 'M53': ('lib/egress.sh', 'net_internal=true  # egress-internal', 'net_internal=false  # egress-internal', 'role network is not internal', ['E-A2']),
 'M54': ('lib/egress.sh', "developer) printf '%s\\n' egress;;  # developer-egress", "developer) printf '%s\\n' open;;  # developer-egress", 'developer uses the open bridge', ['E-A2']),
 'M55': ('lib/egress.sh', "critic) printf '%s\\n' none;;  # critic-none", "critic) printf '%s\\n' egress;;  # critic-none", 'critic joins egress', ['E-A3']),
 'M56': ('lib/egress.sh', "qa|researcher) printf '%s\\n' none;;  # qa-researcher-none", "qa|researcher) printf '%s\\n' egress;;  # qa-researcher-none", 'qa and researcher join egress', ['E-A4', 'E-A7']),
 'M57': ('lib/egress.py', 'return True  # egress-log-on', 'return False  # egress-log-on', 'disable denial log', ['E-H3']),
 'M58': ('lib/egress.py', 'return "hostport"  # egress-log-hostport', 'return "url"  # egress-log-hostport', 'log the full url', ['E-H3']),
 'M59': ('lib/egress.py', 'return decide_exact(entries, host)  # egress-exact', 'return True  # egress-exact', 'allow every host', ['E-A1', 'E-A17']),
 'M60': ('lib/egress.py', 'return decide_port(entries, host, port, kind)  # egress-ports', 'return True  # egress-ports', 'allow every port', ['E-A12']),
 'M61': ('lib/egress_proxy.py', 'use_connect_target = True  # connect-target-acl', 'use_connect_target = False  # connect-target-acl', 'authorize CONNECT from the Host header', ['E-A13']),
 'M62': ('lib/egress_proxy.py', 'follow_redirects = False  # redirect-recheck', 'follow_redirects = True  # redirect-recheck', 'follow redirects inside the proxy', ['E-A14']),
 'M63': ('lib/egress_proxy.py', 'ADMIN_HOST = "127.0.0.1"  # proxy-admin-local', 'ADMIN_HOST = "0.0.0.0"  # proxy-admin-local', 'admin port on the role network', ['E-A8']),
 'M64': ('lib/egress.sh', 'dns_forward=off  # dns-forward-off', 'dns_forward=on  # dns-forward-off', 'forward external DNS', ['E-A9']),
 'M65': ('lib/egress.sh', 'ipv6_off=1  # egress-ipv6-off', 'ipv6_off=0  # egress-ipv6-off', 'enable ipv6 in the role', ['E-A10']),
 'M66': ('lib/egress.sh', 'egress_fail_closed=1  # egress-fail-closed', 'egress_fail_closed=0  # egress-fail-closed', 'launch when the proxy is down', ['E-A16']),
 'M67': (K, 'use_none=1  # proto-network-none', 'use_none=0  # proto-network-none', 'proto drops network none', ['N1']),
 'M68': ('lib/egress.py', 'return clean_host(host)  # egress-sanitize', 'return host  # egress-sanitize', 'log the raw host', ['E-A15']),
 'M69': (K, 'secret_env_gate=1  # secret-env-gate', 'secret_env_gate=0  # secret-env-gate', 'role starts with a denylisted name set', ['S-A1']),
 'M70': ('lib/visibility.py', 'return _scan_patterns(text)  # pattern-scan', 'return []  # pattern-scan', 'drop format-pattern redaction', ['S-A2']),
 'M71': ('lib/visibility.py', 'except Exception as err:  # mounts-internal-log\n        internal = PolicyError("mounts_internal", "emit_mounts", 0, type(err).__name__)', 'except Exception:  # mounts-internal-log\n        return 0', 'swallow a mount error', ['S-A3']),
 'M72': ('lib/visibility.py', '    "KEEL_SECRET",\n)', '    "NOT_A_SECRET",\n)', 'drop KEEL_SECRET from the name denylist', ['S-A4']),
 'M73': (K, 'secret_scan=1  # secret-scan', 'secret_scan=0  # secret-scan', 'skip the secret scan', ['SEC-03']),
 'M74': (K, '--ignore-gitleaks-allow ', '', 'honor inline allow comments', ['SEC-04']),
 'M75': (K, '.gitleaks.toml|.gitleaksignore) continue;;  # harness-owned-ignore', '.gitleaks.toml|.gitleaksignore) ;;  # harness-owned-ignore', 'load a product ignore file', ['SEC-05']),
}
M['M15'] = (K, M['M13'][1], M['M13'][2], M['M15'][3], M['M15'][4])  # applied together with M14 below
GREEN = re.compile(r'^(BLOCKED|CONTAINED|PARTIAL|N/A)')

def cleanup_ns(mid):
    ns = mid.lower()
    docker = os.environ.get('DOCKER', 'docker').split()
    subprocess.run(docker + ['rm', '-f', 'keel-proxy-' + ns, 'keel-mock-' + ns], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(docker + ['network', 'rm', 'keel-egress-' + ns, 'keel-out-' + ns], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def run(mid):
    f, old, new, what, exp = M[mid][:5]
    d = tempfile.mkdtemp(prefix=f'mut-{mid}-', dir=os.path.expanduser('~'))
    src = os.path.join(d, 'p')
    os.makedirs(os.path.join(src, 'tests', 'harness'))
    shutil.copy2(os.path.join(SETUP, 'keel.sh'), os.path.join(src, 'keel.sh'))
    shutil.copy2(os.path.join(SETUP, 'gitleaks.toml'), os.path.join(src, 'gitleaks.toml'))
    shutil.copytree(os.path.join(SETUP, 'lib'), os.path.join(src, 'lib'))
    shutil.copytree(os.path.join(SETUP, 'allow'), os.path.join(src, 'allow'))
    shutil.copytree(os.path.join(SETUP, 'deny'), os.path.join(src, 'deny'))
    shutil.copytree(os.path.join(SETUP, 'egress'), os.path.join(src, 'egress'))
    shutil.copy2(os.path.join(HARNESS, 'test-attacks.sh'), os.path.join(src, 'tests', 'harness', 'test-attacks.sh'))
    shutil.copy2(os.path.join(HARNESS, 'test-egress.sh'), os.path.join(src, 'tests', 'harness', 'test-egress.sh'))
    shutil.copy2(os.path.join(HARNESS, 'h3-verdict.sh'), os.path.join(src, 'tests', 'harness', 'h3-verdict.sh'))
    shutil.copy2(os.path.join(HARNESS, 'visibility-suite.sh'), os.path.join(src, 'tests', 'harness', 'visibility-suite.sh'))
    p = os.path.join(src, f); s = open(p).read()
    edits = [(old, new)] + list(M[mid][5] if len(M[mid]) > 5 else []) + ([(M['M14'][1], M['M14'][2])] if mid == 'M15' else [])
    env = dict(os.environ, KEEL_ROOT=os.path.join(d, 'k'), KEEL_NS=mid)
    try:
        for o, n in edits:
            if s.count(o) != 1:
                return mid, what, exp, None, f'mutation did not apply ({s.count(o)} matches)'
            s = s.replace(o, n)
        open(p, 'w').write(s)
        try:
            out = subprocess.run(['bash', os.path.join(src, 'tests', 'harness', 'test-attacks.sh')], env=env, capture_output=True, text=True, timeout=900).stdout
        except subprocess.TimeoutExpired:
            return mid, what, exp, None, 'timeout'
        open(os.path.join(HARNESS, 'logs', f'mutation-{mid}.log'), 'w').write(out)
        res = dict(re.findall(r'^RESULT ([^:]+): (.*)$', out, re.M))
        red = sorted(k for k, v in res.items() if not GREEN.match(v))
        return mid, what, exp, red, res
    finally:
        cleanup_ns(mid)
        subprocess.run(['sudo', 'rm', '-rf', d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == '__main__':
    ids = sys.argv[1:] or sorted(M)
    os.makedirs(os.path.join(HARNESS, 'logs'), exist_ok=True)
    with cf.ThreadPoolExecutor(int(os.environ.get('JOBS', '3'))) as ex:
        rows = list(ex.map(run, ids))
    bad = 0
    print('| ID | protection removed | expected red | went red | caught |')
    print('|---|---|---|---|---|')
    for mid, what, exp, red, res in rows:
        if red is None: print(f'| {mid} | {what} | {",".join(exp)} | ERROR: {res} | ERROR |'); bad += 1; continue
        ok = set(exp) <= set(red) if exp else True
        tag = ('yes' if exp else ('masked (expected)' if not red else 'yes (extra)')) if ok else 'NO'
        if not ok: bad += 1
        print(f'| {mid} | {what} | {",".join(exp) or "(none: masked)"} | {",".join(red) or "-"} | {tag} |')
    sys.exit(1 if bad else 0)
