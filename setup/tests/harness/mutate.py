#!/usr/bin/env python3
"""Mutation audit: remove one protection at a time in a temp copy and rerun its suite.
Usage: DOCKER="sudo docker" python3 setup/tests/harness/mutate.py [ID ...]"""
import os, py_compile, re, shutil, subprocess, sys, tempfile, concurrent.futures as cf
HARNESS = os.path.dirname(os.path.abspath(__file__))
SETUP = os.path.abspath(os.path.join(HARNESS, os.pardir, os.pardir))
K = 'keel.sh'
# id: (file, old, new, protection removed, expected red check IDs ([] = known masked by another layer))
M = {
 'M01': (K, 'crun -v "$R/.git/objects:/base/objects:ro" "${MNT[@]}" -w /work "$IMG" sh -c "$*"', 'crun -v "$R/.git/objects:/base/objects" "${MNT[@]}" -w /work "$IMG" sh -c "$*"', ':ro on base objects mount (roles)', ['A1']),
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
 'M76': ('lib/egress.py', '            entries.append(item)\n    return entries  # allow-entries', '            entries.append(item)\n    entries.append(("example.com", None))  # allow-extra-host\n    return entries  # allow-entries', 'allowlist accepts example.com', ['E-A1']),
 'M77': ('lib/egress.sh', '$DOCKER run "${args[@]}" "${GITENV[@]}" "$@"  # role-env-explicit', '$DOCKER run "${args[@]}" "${GITENV[@]}" -e "GH_TOKEN=${GH_TOKEN:-}" -e "GITHUB_TOKEN=${GITHUB_TOKEN:-}" -e "KEEL_SECRET=${KEEL_SECRET:-}" "$@"  # role-env-explicit', 'role container receives secret names', ['S-H1']),
 'M78': ('tests/harness/attack-results.sh', 'NOT BLOCKED|', '', 'treat NOT BLOCKED as pass', ['CHK-1']),
 'M79': ('check.sh', 'mode_check=1 # script-mode', 'mode_check=0 # script-mode', 'script mode check disabled', ['MODE-A1']),
 'M80': ('lib/runtime.sh', 'rootless_token=0 # rootless-token', 'rootless_token=1 # rootless-token', 'classify every daemon as rootless', ['R-A1']),
 'M81': ('lib/runtime.sh', 'launch_refuse=1 # runtime-refuse', 'launch_refuse=0 # runtime-refuse', 'skip the rootful launch refuse', ['R-A1']),
 'M82': (K, '--cap-drop ALL ', '', 'drop cap-drop ALL', ['H1']),
 'M83': (K, '--security-opt no-new-privileges\n', '\n', 'drop no-new-privileges', ['H1']),
 'M84': (K, '  --read-only --tmpfs', '  --tmpfs', 'drop read-only', ['H4']),
 'M85': (K, '--memory-swap "${MEM:-512m}" ', '', 'drop the swap pin', ['H3']),
 'M86': ('lib/runtime.sh', 'disk_gate=1 # disk-gate', 'disk_gate=0 # disk-gate', 'skip the free-space gate', ['R-A4']),
 'M87': ('lib/runtime.sh', 'sandbox_flags=1 # chromium-sandbox', 'sandbox_flags=0 # chromium-sandbox', 'allow sandbox-off chromium argv', ['R-A5']),
 'M88': ('lib/runtime.sh', 'userns_is_rootless=0 # userns-not-rootless', 'userns_is_rootless=1 # userns-not-rootless', 'treat userns remap as rootless', ['R-A7']),
 'M89': ('keel-doctor.sh', 'env05_level=CRITICAL # env05-level', 'env05_level=RECOMMENDED # env05-level', 'downgrade the isolation check', ['R-A1']),
 'M90': ('tests/harness/doctor-score.sh', 'score_exact=1 # doctor-score-exact', 'score_exact=0 # doctor-score-exact', 'accept any not-ready doctor', ['R-A8']),
 'M91': (K, 'launch_guard(){ keel_require_runtime || exit $?; } # launch-guard', 'launch_guard(){ return 0; } # launch-guard', 'drop the launch runtime check', ['R-A9']),
 'M92': ('tests/harness/mutant-result.py', 'sha_bind = 1  # mutant-sha-bind', 'sha_bind = 0  # mutant-sha-bind', 'accept a mutant run for a different sha', ['M-A1']),
 'M93': ('scripts/check-gate.sh', 'bind_mutants=1 # mutant-result-bind', 'bind_mutants=0 # mutant-result-bind', 'drop the mutant result check', ['M-A4']),
 'M94': ('lib/pi_launch.py', '"no_extensions": True,  # pi-flag-ne', '"no_extensions": False,  # pi-flag-ne', 'drop -ne', ['PI-A-ext']),
 'M95': ('lib/pi_launch.py', '"no_prompts": True,  # pi-flag-np', '"no_prompts": False,  # pi-flag-np', 'drop -np', ['PI-A-prompts']),
 'M96': ('lib/pi_launch.py', '"no_context": False,  # pi-flag-nc', '"no_context": True,  # pi-flag-nc', 'insert -nc', ['PI-H-context-on']),
 'M97': ('lib/pi_launch.py', 'return True  # pi-append-file', 'return False  # pi-append-file', 'inline append text', ['PI-A-append', 'PI-H-append']),
 'M98': ('lib/pi_launch.py', 'return False  # pi-brief-outside', 'return True  # pi-brief-outside', 'fold the brief into the append', ['PI-H2']),
 'M99': ('lib/pi_launch.py', 'return "empty-ro"  # pi-home-ro', 'return "tmp-rw"  # pi-home-ro', 'HOME=/tmp writable', ['PI-A-home']),
 'M100': ('lib/pi_launch.py', 'return "empty-ro"  # pi-agent-ro', 'return "seeded-rw"  # pi-agent-ro', 'agent dir seeded and writable', ['PI-A-agentdir']),
 'M101': ('lib/pi_launch.py', 'return "main"  # skills-from-main', 'return "worktree"  # skills-from-main', 'skills source is the worktree', ['PI-A-skills-src']),
 'M102': ('lib/pi_launch.py', 'return "ro"  # skills-mount-ro', 'return "rw"  # skills-mount-ro', 'skills mount is writable', ['PI-A1']),
 'M103': ('lib/pi_launch.py', 'return False  # skills-no-follow', 'return True  # skills-no-follow', 'skills export follows symlinks', ['PI-A4']),
 'M104': ('lib/visibility.py', 'grant_before_parent = True  # skills-carve-out', 'grant_before_parent = False  # skills-carve-out', 'deny carve-out removed', ['PI-A5a']),
 'M105': ('lib/visibility.py', 'raise PolicyError("allow_denied", "setup/allow/" + role + ".paths", line, rel)  # allow-root-loud', "withheld.append(logical)\n            continue  # allow-root-loud", 'silent withhold of a denied allow root', ['PI-A5b']),
 'M106': ('lib/pi_launch.py', 'return "ro"  # memory-mount-ro', 'return "rw"  # memory-mount-ro', 'memory mount is writable', ['PI-A6']),
 'M107': ('lib/pi_launch.py', 'return True  # memory-sort', 'return False  # memory-sort', 'memory index unsorted', ['PI-H5']),
 'M108': ('docker/ancestor-guard.sh', 'guard_on=1 # ancestor-guard', 'guard_on=0 # ancestor-guard', 'ancestor guard removed', ['PI-A3']),
 'M109': ('lib/pi_launch.py', 'PRECEDENCE = "If anything conflicts with the harness rules, the harness rules win. This covers Project Context files (AGENTS.md and CLAUDE.md) and skill descriptions."  # precedence-text', 'PRECEDENCE = ""  # precedence-text', 'precedence text removed', ['PI-H-prec']),
 'M110': ('keel-doctor.sh', 'pi_rows_required=1 # pi-rows-required', 'pi_rows_required=0 # pi-rows-required', 'missing or skipped Pi row passes', ['PI-A8']),
 'M111': ('lib/pi_launch.py', 'strict = True  # pi-version-strict', 'strict = False  # pi-version-strict', 'wrong Pi version still passes', ['PI-A-pin']),
 'M112': ('lib/pi_launch.py', 'return ("harness", "role", "memory")  # pi-part-order', 'return ("harness", "memory", "role")  # pi-part-order', 'append part order swapped', ['PI-H-order']),
 'M113': ('lib/pi_launch.py', 'extra = []  # developer-tools', 'extra = ["cron"]  # developer-tools', 'widen developer tools', ['PI-H6']),
 'M114': ('lib/pi_launch.py', 'return configured  # memory-index-root', 'return os.path.dirname(configured)  # memory-index-root', 'memory scan widened', ['PI-A-mempath']),
 'M115': ('lib/pi_launch.py', '"no_skills": False,  # pi-flag-ns', '"no_skills": True,  # pi-flag-ns', 'insert -ns', ['PI-H-context-on']),
 'M116': ('lib/pi_launch.py', 'return True  # memory-fence', 'return False  # memory-fence', 'memory headers not fenced', ['PI-A-meminj']),
 'M117': ('lib/pi_launch.py', 'return True  # memory-superseded', 'return False  # memory-superseded', 'superseded entries unmarked', ['PI-H5']),
 'M118': ('lib/pi_launch.py', 'return True  # memory-fingerprint', 'return False  # memory-fingerprint', 'memory fingerprint not logged', ['PI-H5']),
 'M119': ('lib/discovery_filter.py', 'return True  # disc-pattern-on', 'return False  # disc-pattern-on', 'skip the bypass pre-filter', ['DISC-A1', 'DISC-A19']),
 'M120': ('lib/discovery_filter.py', 'return True  # disc-significance-on', 'return False  # disc-significance-on', 'skip the significance check', ['DISC-A2']),
 'M121': ('lib/discovery_filter.py', 'return True  # disc-path-check', 'return False  # disc-path-check', 'accept a path outside the tree', ['DISC-A3']),
 'M122': ('lib/discovery_filter.py', 'return True  # disc-size-cap', 'return False  # disc-size-cap', 'drop the candidate size cap', ['DISC-A4']),
 'M123': ('lib/pi_launch.py', 'return []  # disc-no-candidate-scan', 'return [os.path.join(os.path.dirname(memory_dir), "candidates")]  # disc-no-candidate-scan', 'index scans candidates', ['DISC-H4']),
 'M124': ('lib/discovery_filter.py', 'return True  # disc-symlink-refuse', 'return False  # disc-symlink-refuse', 'follow a candidate symlink', ['DISC-A6']),
 'M125': ('lib/discovery_filter.py', 'return True  # disc-no-queue', 'return False  # disc-no-queue', 'keep a proposed queue', ['DISC-A7']),
 'M126': ('lib/discovery_filter.py', 'return True  # disc-audit-redact', 'return False  # disc-audit-redact', 'write secret values into the audit', ['DISC-A8']),
 'M127': ('lib/discovery_filter.py', 'return True  # disc-schema-on', 'return False  # disc-schema-on', 'skip the schema check', ['DISC-A15']),
 'M128': ('lib/visibility.py', 'return "ro"  # discovery-memory-ro', 'return "rw"  # discovery-memory-ro', 'accepted memory mount is writable', ['DISC-A5', 'DISC-A11']),
 'M129': ('keel-doctor.sh', 'local disc_rows_required=1 # disc-rows-required', 'local disc_rows_required=0 # disc-rows-required', 'skip a failed discovery row', ['DISC-A12']),
 'M130': ('lib/discovery_judge.py', 'return True  # disc-judge-enabled', 'return False  # disc-judge-enabled', 'promote without the judge', ['DISC-A16', 'DISC-A17', 'DISC-A18']),
 'M131': ('lib/discovery_judge.py', 'return True  # disc-fail-closed', 'return False  # disc-fail-closed', 'judge errors fail open', ['DISC-A16', 'DISC-A17', 'DISC-A18']),
 'M132': ('lib/discovery_filter.py', 'return True  # disc-audit-failures', 'return False  # disc-audit-failures', 'drop the audit line on reject', ['DISC-A1', 'DISC-A16', 'DISC-A17']),
 'M133': ('lib/discovery_judge.py', 'return True  # disc-judge-host', 'return False  # disc-judge-host', 'judge destination check widened', ['DISC-A20']),
 'M134': ('lib/discovery_filter.py', 'return True  # disc-promote-order', 'return False  # disc-promote-order', 'promote before the iteration ends', ['DISC-A13']),
 'M135': ('lib/discovery_filter.py', 'return True  # disc-critical-d2', 'return False  # disc-critical-d2', 'critical candidate skips D2', ['DISC-H11']),
 'M136': ('lib/discovery_judge.py', 'isolated = True  # disc-judge-isolated', 'isolated = False  # disc-judge-isolated', 'a role can reach the judge', ['DISC-A21']),
 'M137': ('lib/discovery_judge.py', 'return marker  # disc-stub-ci-only', 'return True  # disc-stub-ci-only', 'stub allowed outside CI', ['DISC-A22']),
 'M138': ('lib/discovery_judge.py', 'return True  # disc-noul-strict', 'return False  # disc-noul-strict', 'loose Decisions JSON parse', ['DISC-A18']),
 'M139': ('tests/harness/mutant_defs.py', 'include_forced = True  # plan-forced', 'include_forced = False  # plan-forced', 'drop forced ids from the plan', ['S-H1', 'S-A3']),
 'M140': ('tests/harness/mutant_defs.py', 'use_main = True  # new-against-main', 'use_main = False  # new-against-main', 'new ids compared with the pull request', ['S-H1']),
 'M141': ('tests/harness/mutant_defs.py', 'compare_values = True  # compare-values', 'compare_values = False  # compare-values', 'modified compares keys only', ['S-A3']),
 'M142': ('tests/harness/mutant_defs.py', 'reject_computed = True  # parser-computed', 'reject_computed = False  # parser-computed', 'parser accepts computed keys', ['S-A2']),
 'M143': ('tests/harness/mutant_defs.py', 'reject_second = True  # parser-second', 'reject_second = False  # parser-second', 'parser accepts a second M assignment', ['S-A2']),
 'M144': ('tests/harness/mutant_defs.py', 'reject_names = True  # parser-names', 'reject_names = False  # parser-names', 'parser accepts an unknown name', ['S-A2']),
 'M145': ('tests/harness/mutant_defs.py', 'reject_removed = True  # reject-removed', 'reject_removed = False  # reject-removed', 'removed ids are allowed', ['S-A4']),
 'M146': ('tests/harness/mutant_defs.py', 'compare_suite = True  # compare-suite', 'compare_suite = False  # compare-suite', 'suite and extra edits are not modifications', ['S-A15']),
 'M147': ('tests/harness/mutant_defs.py', 'copy_widens = True  # copy-widens', 'copy_widens = False  # copy-widens', 'copy list changes do not widen', ['S-A16']),
 'M148': ('tests/harness/mutant_defs.py', 'reject_unknown_suite = True  # suite-known', 'reject_unknown_suite = False  # suite-known', 'unknown suite name accepted', ['S-A12']),
 'M149': ('tests/harness/mutant_files.py', 'unmapped_full = True  # unmapped-full', 'unmapped_full = False  # unmapped-full', 'unmapped setup path skips', ['S-A7']),
 'M150': ('tests/harness/mutant_files.py', 'use_depends = True  # depends-on', 'use_depends = False  # depends-on', 'dependents are ignored', ['S-H3']),
 'M151': ('tests/harness/mutant_files.py', 'dynamic_unresolved = True  # dynamic-unresolved', 'dynamic_unresolved = False  # dynamic-unresolved', 'dynamic imports look resolved', ['S-A8']),
 'M152': ('tests/harness/mutate_shards.py', 'keep_last = True  # shard-last', 'keep_last = False  # shard-last', 'round-robin drops the last id', ['S-H5']),
 'M153': ('tests/harness/mutate_shards.py', 'require_all_ids = True  # shard-complete', 'require_all_ids = False  # shard-complete', 'missing shard ids are accepted', ['S-A5']),
 'M154': ('tests/harness/mutate_shards.py', 'reject_foreign = True  # shard-foreign', 'reject_foreign = False  # shard-foreign', 'foreign shard ids are accepted', ['S-A5']),
 'M155': ('tests/harness/mutate_shards.py', 'require_success = True  # shard-success', 'require_success = False  # shard-success', 'shard result is ignored', ['S-A6']),
 'M156': ('tests/harness/mutate-full-state.py', 'skip_noise = True  # skip-noise', 'skip_noise = False  # skip-noise', 'cancelled and skip runs count as green', ['S-H7b', 'S-A13']),
 'M157': ('tests/harness/mutate-full-state.py', 'filter_runs = True  # filter-runs', 'filter_runs = False  # filter-runs', 'full-run filter is ignored', ['S-A17']),
 'M158': ('tests/harness/mutant_defs.py', 'check_classification = True  # class-check', 'check_classification = False  # class-check', 'classification check is off', ['S-A18']),
 'M159': ('tests/harness/mutate-full-state.py', 'fail_open = True  # fresh-api-run', 'fail_open = False  # fresh-api-run', 'freshness API error skips', ['S-A11']),
 'M160': ('tests/harness/mutant_defs.py', 'check_duplicates = True  # duplicate-def', 'check_duplicates = False  # duplicate-def', 'duplicate check is off', ['S-A9']),
 'M161': ('tests/harness/mutant_defs.py', '    use_exp = main_exp  # exp-from-main', '    use_exp = pr_exp  # exp-from-main', 'expected attacks come from the pull request', ['S-A20', 'S-A22']),
 'M162': ('tests/harness/mutant_defs.py', 'reject_new_masked = True  # new-masked', 'reject_new_masked = False  # new-masked', 'new empty exp is accepted', ['S-A21']),
 'M163': ('tests/harness/mutant_defs.py', 'run_coverage_safety = True  # coverage-safety', 'run_coverage_safety = False  # coverage-safety', 'coverage checks skipped', ['S-A23']),
 'M164': ('tests/harness/mutate_shards.py', '    names_ok = set(names) <= allowed  # artifact-allow', '    names_ok = True  # artifact-allow', 'artifact names are not checked', ['S-A24']),
 'M165': ('tests/harness/mutate_shards.py', 'check_main_moved = True  # main-moved', 'check_main_moved = False  # main-moved', 'selector movement is ignored', ['S-A26']),
 'M166': ('tests/harness/mutate-full-state.py', 'trust_state = True  # trust-state', 'trust_state = False  # trust-state', 'green is decided by the job name', ['S-A27']),
 'M167': ('tests/harness/mutate_shards.py', 'enforce_size = True  # extract-size', 'enforce_size = False  # extract-size', 'extract size cap is off', ['S-A25']),
 'M168': ('tests/harness/mutate_shards.py', 'enforce_paths = True  # extract-path', 'enforce_paths = False  # extract-path', 'extract paths are not checked', ['S-A25']),
 'M169': ('tests/harness/mutate_shards.py', 'enforce_symlink = True  # extract-symlink', 'enforce_symlink = False  # extract-symlink', 'extract symlinks are allowed', ['S-A25']),
 'M170': ('tests/harness/mutate_shards.py', 'enforce_line = True  # line-cap', 'enforce_line = False  # line-cap', 'result line cap is off', ['S-A25']),
 'M171': ('.github/workflows/mutate-pr.yml', '    timeout-minutes: 45 # shard-timeout', '    timeout-minutes: 0 # shard-timeout', 'shard timeout removed', ['S-A28']),
 'M172': ('tests/harness/mutate_shards.py', 'timeout_is_fail = True  # timeout-not-success', 'timeout_is_fail = False  # timeout-not-success', 'timed out shard counts as success', ['S-A34', 'S-A6']),
 'M173': ('tests/harness/mutate_shards.py', 'check_baseline = True  # baseline-check', 'check_baseline = False  # baseline-check', 'baseline check is off', ['S-A30', 'S-A31']),
 'M174': ('tests/harness/mutate_shards.py', 'check_tree_entries = True  # tree-entry-check', 'check_tree_entries = False  # tree-entry-check', 'tree entry checks are off', ['S-A29']),
 'M175': ('.github/workflows/mutate-pr.yml', '    permissions: # shard-readonly\n      contents: read', '    permissions: # shard-readonly\n      actions: write\n      contents: read', 'shard job can write actions', ['S-A35']),
}
SUITE_OF = {
    'M01': 'test-attacks.sh',
    'M02': 'test-attacks.sh',
    'M03': 'test-attacks.sh',
    'M04': 'test-attacks.sh',
    'M05': 'test-attacks.sh',
    'M06': 'test-attacks.sh',
    'M07': 'test-attacks.sh',
    'M08': 'test-attacks.sh',
    'M09': 'test-attacks.sh',
    'M10': 'test-attacks.sh',
    'M11': 'test-attacks.sh',
    'M12': 'test-attacks.sh',
    'M13': 'test-attacks.sh',
    'M14': 'test-attacks.sh',
    'M15': 'test-attacks.sh',
    'M16': 'test-attacks.sh',
    'M17': 'test-attacks.sh',
    'M18': 'test-attacks.sh',
    'M19': 'test-attacks.sh',
    'M20': 'test-attacks.sh',
    'M21': 'test-attacks.sh',
    'M22': 'test-attacks.sh',
    'M23': 'test-attacks.sh',
    'M24': 'test-attacks.sh',
    'M25': 'test-attacks.sh',
    'M26': 'test-attacks.sh',
    'M27': 'test-attacks.sh',
    'M28': 'test-attacks.sh',
    'M29': 'test-attacks.sh',
    'M30': 'test-attacks.sh',
    'M31': 'test-attacks.sh',
    'M32': 'test-attacks.sh',
    'M33': 'test-attacks.sh',
    'M34': 'test-attacks.sh',
    'M35': 'test-attacks.sh',
    'M36': 'test-attacks.sh',
    'M37': 'test-attacks.sh',
    'M38': 'test-attacks.sh',
    'M39': 'test-attacks.sh',
    'M40': 'test-attacks.sh',
    'M41': 'test-attacks.sh',
    'M42': 'test-attacks.sh',
    'M43': 'test-attacks.sh',
    'M44': 'test-attacks.sh',
    'M45': 'test-attacks.sh',
    'M46': 'test-attacks.sh',
    'M47': 'test-attacks.sh',
    'M48': 'test-attacks.sh',
    'M49': 'test-attacks.sh',
    'M50': 'test-attacks.sh',
    'M51': 'test-attacks.sh',
    'M52': 'test-attacks.sh',
    'M53': 'test-attacks.sh',
    'M54': 'test-attacks.sh',
    'M55': 'test-attacks.sh',
    'M56': 'test-attacks.sh',
    'M57': 'test-attacks.sh',
    'M58': 'test-attacks.sh',
    'M59': 'test-attacks.sh',
    'M60': 'test-attacks.sh',
    'M61': 'test-attacks.sh',
    'M62': 'test-attacks.sh',
    'M63': 'test-attacks.sh',
    'M64': 'test-attacks.sh',
    'M65': 'test-attacks.sh',
    'M66': 'test-attacks.sh',
    'M67': 'test-attacks.sh',
    'M68': 'test-attacks.sh',
    'M69': 'test-attacks.sh',
    'M70': 'test-attacks.sh',
    'M71': 'test-attacks.sh',
    'M72': 'test-attacks.sh',
    'M73': 'test-attacks.sh',
    'M74': 'test-attacks.sh',
    'M75': 'test-attacks.sh',
    'M76': 'test-attacks.sh',
    'M77': 'test-attacks.sh',
    'M78': 'test-attack-results.sh',
    'M79': 'test-attacks.sh',
    'M80': 'test-runtime.sh',
    'M81': 'test-runtime.sh',
    'M82': 'test-attacks.sh',
    'M83': 'test-attacks.sh',
    'M84': 'test-attacks.sh',
    'M85': 'test-attacks.sh',
    'M86': 'test-runtime.sh',
    'M87': 'test-runtime.sh',
    'M88': 'test-runtime.sh',
    'M89': 'test-runtime.sh',
    'M90': 'test-runtime.sh',
    'M91': 'test-runtime.sh',
    'M92': 'test-mutant-result.sh',
    'M93': 'test-mutant-result.sh',
    'M94': 'test-step4.sh',
    'M95': 'test-step4.sh',
    'M96': 'test-step4.sh',
    'M97': 'test-step4.sh',
    'M98': 'test-step4.sh',
    'M99': 'test-step4.sh',
    'M100': 'test-step4.sh',
    'M101': 'test-step4.sh',
    'M102': 'test-step4.sh',
    'M103': 'test-step4.sh',
    'M104': 'test-step4.sh',
    'M105': 'test-step4.sh',
    'M106': 'test-step4.sh',
    'M107': 'test-step4.sh',
    'M108': 'test-step4.sh',
    'M109': 'test-step4.sh',
    'M110': 'test-step4.sh',
    'M111': 'test-step4.sh',
    'M112': 'test-step4.sh',
    'M113': 'test-step4.sh',
    'M114': 'test-step4.sh',
    'M115': 'test-step4.sh',
    'M116': 'test-step4.sh',
    'M117': 'test-step4.sh',
    'M118': 'test-step4.sh',
    'M119': 'test-step5.sh',
    'M120': 'test-step5.sh',
    'M121': 'test-step5.sh',
    'M122': 'test-step5.sh',
    'M123': 'test-step5.sh',
    'M124': 'test-step5.sh',
    'M125': 'test-step5.sh',
    'M126': 'test-step5.sh',
    'M127': 'test-step5.sh',
    'M128': 'test-step5.sh',
    'M129': 'test-step5.sh',
    'M130': 'test-step5.sh',
    'M131': 'test-step5.sh',
    'M132': 'test-step5.sh',
    'M133': 'test-step5.sh',
    'M134': 'test-step5.sh',
    'M135': 'test-step5.sh',
    'M136': 'test-step5.sh',
    'M137': 'test-step5.sh',
    'M138': 'test-step5.sh',
    'M139': 'test-mutant-select.py',
    'M140': 'test-mutant-select.py',
    'M141': 'test-mutant-select.py',
    'M142': 'test-mutant-select.py',
    'M143': 'test-mutant-select.py',
    'M144': 'test-mutant-select.py',
    'M145': 'test-mutant-select.py',
    'M146': 'test-mutant-select.py',
    'M147': 'test-mutant-select.py',
    'M148': 'test-mutant-select.py',
    'M149': 'test-mutant-select.py',
    'M150': 'test-mutant-select.py',
    'M151': 'test-mutant-select.py',
    'M156': 'test-mutant-select.py',
    'M157': 'test-mutant-select.py',
    'M158': 'test-mutant-select.py',
    'M159': 'test-mutant-select.py',
    'M160': 'test-mutant-select.py',
    'M161': 'test-mutant-select.py',
    'M162': 'test-mutant-select.py',
    'M163': 'test-mutant-select.py',
    'M166': 'test-mutant-select.py',
    'M152': 'test-mutate-shards.sh',
    'M153': 'test-mutate-shards.sh',
    'M154': 'test-mutate-shards.sh',
    'M155': 'test-mutate-shards.sh',
    'M164': 'test-mutate-shards.sh',
    'M165': 'test-mutate-shards.sh',
    'M167': 'test-mutate-shards.sh',
    'M168': 'test-mutate-shards.sh',
    'M169': 'test-mutate-shards.sh',
    'M170': 'test-mutate-shards.sh',
    'M171': 'test-mutate-shards.sh',
    'M172': 'test-mutate-shards.sh',
    'M173': 'test-mutate-shards.sh',
    'M174': 'test-mutate-shards.sh',
    'M175': 'test-mutate-shards.sh',
}
EXTRA_EDITS = {
    'M15': ['M14'],
}
COPY_LIST = [
    'keel.sh',
    'check.sh',
    'gitleaks.toml',
    'keel-doctor.sh',
    'lib',
    'allow',
    'deny',
    'egress',
    'pi',
    'docker',
    'tools',
    'chrome/chromium-argv.sh',
    'tests/harness/attack-results.sh',
    'tests/harness/doctor-score.sh',
    'tests/harness/fixtures',
    'tests/harness/h3-verdict.sh',
    'tests/harness/harness-keel.sh',
    'tests/harness/mutant-result.py',
    'tests/harness/mutant_defs.py',
    'tests/harness/mutant_files.py',
    'tests/harness/mutate-full-state.py',
    'tests/harness/mutate-issue.py',
    'tests/harness/mutate-plan.sh',
    'tests/harness/mutate.py',
    'tests/harness/mutate_shards.py',
    'tests/harness/pi-oracle.mjs',
    'tests/harness/pi-record.sh',
    'tests/harness/resolve-mutant-target.py',
    'tests/harness/run-tests.sh',
    'tests/harness/speed_cases.py',
    'tests/harness/runtime-stub.sh',
    'tests/harness/step4_check.py',
    'tests/harness/step5_check.py',
    'tests/harness/test-attack-results.sh',
    'tests/harness/test-attacks.sh',
    'tests/harness/test-egress.sh',
    'tests/harness/test-mutant-result.sh',
    'tests/harness/test-mutant-select.py',
    'tests/harness/test-mutate-parse.py',
    'tests/harness/test-mutate-plan.sh',
    'tests/harness/test-mutate-schedule.sh',
    'tests/harness/test-mutate-shards.sh',
    'tests/harness/test-runtime.sh',
    'tests/harness/test-step4.sh',
    'tests/harness/test-step5.sh',
    'tests/harness/visibility-suite.sh',
]

GREEN = re.compile(r'^(BLOCKED|CONTAINED|PARTIAL|N/A)')
PARSE_ERROR = 'mutated file does not parse'
EMPTY_RESULT = 'empty RESULT'

def apply_edits(text, edits):
    """Replace each old string once. Zero or many matches is an invalid mutant."""
    for old, new in edits:
        count = text.count(old)
        if count != 1:
            return None, 'mutation did not apply (%s matches)' % count
        text = text.replace(old, new, 1)
    return text, None

def mutated_file_parses(path):
    """True when the applied file is syntactically valid for its language."""
    if path.endswith('.py'):
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError:
            return False
        return True
    if path.endswith('.sh'):
        proc = subprocess.run(
            ['bash', '-n', path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0
    return True

def collect_results(out):
    return dict(re.findall(r'^RESULT ([^:]+): (.*)$', out or '', re.M))

def red_from_results(res):
    return sorted(k for k, v in res.items() if not GREEN.match(v))

def judge(_exp, out, applied_error=None, parse_failed=False):
    """Return (red, detail). red is None when the mutant is invalid.

    An apply miss, a file that does not parse, or a RESULT dict with no lines
    is an error. An empty expected list does not turn a missing RESULT into a pass.
    """
    if applied_error:
        return None, applied_error
    if parse_failed:
        return None, PARSE_ERROR
    res = collect_results(out)
    if not res:
        return None, EMPTY_RESULT
    return red_from_results(res), res

def verdict_tag(exp, red):
    if red is None:
        return 'ERROR'
    ok = set(exp) <= set(red) if exp else True
    if not ok:
        return 'NO'
    if exp:
        return 'yes'
    if not red:
        return 'masked (expected)'
    return 'yes (extra)'

def cleanup_ns(mid):
    ns = mid.lower()
    docker = os.environ.get('DOCKER', 'docker').split()
    try:
        subprocess.run(docker + ['rm', '-f', 'keel-proxy-' + ns, 'keel-mock-' + ns], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(docker + ['network', 'rm', 'keel-egress-' + ns, 'keel-out-' + ns], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return

def copy_listed(setup_root, dest, paths):
    for rel in paths:
        src_path = os.path.join(setup_root, rel)
        dst_path = os.path.join(dest, rel)
        if not os.path.exists(src_path):
            raise SystemExit('copy list missing %s' % rel)
        parent = os.path.dirname(dst_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if os.path.isdir(src_path):
            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)

def edit_pairs(mid, table=None, extras=None):
    table = table or M
    extras = EXTRA_EDITS if extras is None else extras
    pairs_by_file = {}
    specs = [mid] + list(extras.get(mid) or [])
    for sid in specs:
        spec = table[sid]
        pairs = [(spec[1], spec[2])]
        if len(spec) > 5:
            pairs.extend(list(spec[5]))
        pairs_by_file.setdefault(spec[0], []).extend(pairs)
    return pairs_by_file

def target_rels(mid):
    rels = [M[mid][0]]
    try:
        import mutant_files as mf
    except ImportError:
        return rels
    for path in mf.FILES.get(mid, []):
        rel = path[len('setup/'):] if path.startswith('setup/') else path
        if rel not in rels:
            rels.append(rel)
    return rels

def place_for(rel, temp_root, src):
    if rel.startswith('scripts/') or rel.startswith('.github/'):
        return os.path.join(temp_root, rel)
    return os.path.join(src, rel)

def fill_repo(repo, temp_root, src):
    """Repo layout around the setup snapshot, including workflow files."""
    setup_root = os.path.join(repo, 'setup')
    for dirpath, dirnames, filenames in os.walk(setup_root):
        dirnames[:] = [name for name in dirnames if name != '__pycache__']
        rel_dir = os.path.relpath(dirpath, setup_root)
        for name in filenames:
            rel = name if rel_dir == '.' else os.path.join(rel_dir, name)
            dest = os.path.join(src, rel)
            if os.path.lexists(dest):
                continue
            parent = os.path.dirname(dest)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copy2(os.path.join(dirpath, name), dest)
    link = os.path.join(temp_root, 'setup')
    if not os.path.lexists(link):
        os.symlink('p', link)
    for top in ('.github', 'scripts'):
        origin = os.path.join(repo, top)
        if not os.path.isdir(origin):
            continue
        for dirpath, dirnames, filenames in os.walk(origin):
            dirnames[:] = [name for name in dirnames if name != '__pycache__']
            rel_dir = os.path.relpath(dirpath, origin)
            for name in filenames:
                rel = name if rel_dir == '.' else os.path.join(rel_dir, name)
                dest = os.path.join(temp_root, top, rel)
                if os.path.lexists(dest):
                    continue
                parent = os.path.dirname(dest)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                shutil.copy2(os.path.join(dirpath, name), dest)

def run(mid):
    _f, _old, _new, what, exp = M[mid][:5]
    d = tempfile.mkdtemp(prefix='mut-%s-' % mid, dir=os.path.expanduser('~'))
    src = os.path.join(d, 'p')
    os.makedirs(src, exist_ok=True)
    repo = os.path.dirname(SETUP)
    copy_listed(SETUP, src, COPY_LIST)
    fill_repo(repo, d, src)
    env = dict(os.environ, KEEL_ROOT=os.path.join(d, 'k'), KEEL_NS=mid)
    try:
        applied_error = None
        touched = []
        for rel, pairs in edit_pairs(mid).items():
            for dest_rel in target_rels(mid) if rel == M[mid][0] else [rel]:
                path = place_for(dest_rel, d, src)
                if not os.path.isfile(path):
                    origin = os.path.join(repo, dest_rel) if dest_rel.startswith(('scripts/', '.github/')) else os.path.join(SETUP, dest_rel)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    if os.path.isfile(origin):
                        shutil.copy2(origin, path)
                if not os.path.isfile(path):
                    applied_error = 'mutation did not apply (missing %s)' % dest_rel
                    break
                text = open(path, encoding='utf-8').read()
                if text.count(pairs[0][0]) != 1 and dest_rel != rel:
                    continue
                updated, err = apply_edits(text, pairs)
                if err or updated is None:
                    applied_error = err
                    break
                open(path, 'w', encoding='utf-8').write(updated)
                touched.append(path)
            if applied_error:
                break
        out = ''
        if applied_error:
            red, detail = judge(exp, out, applied_error, False)
            return mid, what, exp, red, detail
        if any(not mutated_file_parses(path) for path in touched):
            red, detail = judge(exp, out, None, True)
            return mid, what, exp, red, detail
        script = SUITE_OF[mid]
        suite_path = os.path.join(src, 'tests', 'harness', script)
        runner = 'python3' if script.endswith('.py') else 'bash'
        try:
            out = subprocess.run([runner, suite_path], env=env, capture_output=True, text=True, timeout=900).stdout
        except subprocess.TimeoutExpired:
            return mid, what, exp, None, 'timeout'
        open(os.path.join(HARNESS, 'logs', 'mutation-%s.log' % mid), 'w').write(out)
        red, detail = judge(exp, out, None, False)
        return mid, what, exp, red, detail
    finally:
        cleanup_ns(mid)
        subprocess.run(['sudo', 'rm', '-rf', d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _print_rows(rows):
    bad = 0
    print('| ID | protection removed | expected red | went red | caught |')
    print('|---|---|---|---|---|')
    for mid, what, exp, red, res in rows:
        if red is None:
            print('| %s | %s | %s | ERROR: %s | ERROR |' % (mid, what, ','.join(exp), res))
            bad += 1
            continue
        tag = verdict_tag(exp, red)
        if tag == 'NO':
            bad += 1
        print('| %s | %s | %s | %s | %s |' % (mid, what, ','.join(exp) or '(none: masked)', ','.join(red) or '-', tag))
    return bad

def build_cmd(argv):
    """Apply pull-request literals with this file's editor. The pull-request file is data."""
    import mutant_defs as defs
    defs_path = argv[argv.index('--defs') + 1]
    tree = argv[argv.index('--tree') + 1]
    out = argv[argv.index('--out') + 1]
    source = open(defs_path, encoding='utf-8').read()
    parsed = defs.load_mutate(source)
    os.makedirs(out, exist_ok=True)
    ids = [arg for arg in argv if arg.startswith('M')]
    if not ids:
        ids = sorted(parsed.ids, key=defs.id_key)
    for mid in ids:
        dest = os.path.join(out, mid)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(tree, dest)
        for rel, pairs in edit_pairs(mid, parsed.M, parsed.extra).items():
            path = os.path.join(dest, rel if rel.startswith(('scripts/', '.github/')) else os.path.join('setup', rel))
            text = open(path, encoding='utf-8').read()
            updated, err = apply_edits(text, pairs)
            if err or updated is None:
                raise SystemExit('%s %s' % (mid, err or 'apply'))
            open(path, 'w', encoding='utf-8').write(updated)
    return 0

def grade_cmd(argv):
    """Grade captured stdout with this file's judge. Definitions are not executed."""
    import json
    import mutant_defs as defs
    raw = argv[argv.index('grade') + 1]
    plan_path = argv[argv.index('grade') + 2]
    plan = json.load(open(plan_path, encoding='utf-8'))
    bad = 0
    for mid, exp in plan['exp'].items():
        stdout = open(os.path.join(raw, mid + '.txt'), encoding='utf-8').read()
        red, detail = judge(exp, stdout, None, False)
        tag = verdict_tag(exp, red)
        if tag in ('NO', 'ERROR'):
            bad += 1
        print('RESULT %s: %s' % (mid, tag))
    return 1 if bad else 0

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'build':
        sys.exit(build_cmd(sys.argv))
    if len(sys.argv) > 1 and sys.argv[1] == 'grade':
        sys.exit(grade_cmd(sys.argv))
    ids = sys.argv[1:] or sorted(M)
    os.makedirs(os.path.join(HARNESS, 'logs'), exist_ok=True)
    # Setting: threads for a local mutant batch.
    with cf.ThreadPoolExecutor(int(os.environ.get('JOBS', '3'))) as ex:
        rows = list(ex.map(run, ids))
    sys.exit(1 if _print_rows(rows) else 0)
