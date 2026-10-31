#!/usr/bin/env python3
"""Folder allowlists, the unified deny, and the launch log.

The harness is the only writer of .keel/logs. Roles do not receive that
directory. A project deny file can add paths. It cannot remove a base entry.
"""

import base64
import datetime
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCHABLE = (
    "orchestrator",
    "architect",
    "tester",
    "developer",
    "auditor",
    "skills_auditor",
    "critic",
    "design_reviewer",
    "verifier",
    "qa",
    "researcher",
)

# tests is listed rw here so the read-only override below is the one switch.
MODES = {
    "orchestrator": {"briefs": "rw", "docs": "ro", "tests": "ro", ".keel/decisions": "rw"},
    "architect": {"briefs": "ro", "docs": "ro", ".keel/decisions": "ro"},
    "tester": {"src": "ro", "docs": "ro", "tests": "rw"},
    "developer": {"src": "rw", "docs": "rw", "tests": "rw"},
    "auditor": {"src": "ro", "docs": "ro"},
    "skills_auditor": {"skills-draft": "ro", "skill-review": "ro"},
    "critic": {"plans": "ro"},
    "design_reviewer": {"docs": "ro"},
    "verifier": {"findings": "ro"},
    "qa": {"qa-stub": "ro"},
    "researcher": {"research-stub": "ro"},
}

SECRET_ENV = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "BOT_GH_TOKEN",
    "GITHUB_PAT",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "API_KEY",
    "API_TOKEN",
    "NPM_TOKEN",
    "PYPI_TOKEN",
    "PASSWORD",
    "OPENAI_API_KEY",
    "KEEL_SECRET",
)

TOKEN_RE = re.compile(r"(?:ghp_|github_pat_|gho_|ghu_|ghs_|ghr_|sk-|xox[baprs]-|AKIA)[A-Za-z0-9_\-]{20,}")
KEY_RE = re.compile(r"-----BEGIN [A-Z ]{0,40}KEY-----.*?-----END [A-Z ]{0,40}KEY-----", re.S)
PASSWORD_RE = re.compile(r"(?i)(?:password|passwd|pwd)\s*[:=]\s*\S+")
UNKNOWN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9+/_\-]{32,}={0,2}(?![A-Za-z0-9])")
GLOB_CHARS = set("*?[]")
PLACEHOLDER = "[REDACTED:{0}]"
TYPES = ("token", "key", "password", "env", "unknown")


class PolicyError(Exception):
    def __init__(self, code, file, line, detail=""):
        self.code = code
        self.file = file
        self.line = line
        self.detail = detail
        super().__init__(code)


class Rec(object):
    def __init__(self, kind, value, line, roles=()):
        self.kind = kind
        self.value = value
        self.line = line
        self.roles = tuple(roles)


def fold_key(text):
    return unicodedata.normalize("NFC", text).casefold()  # fold-nfc-case


def clean_rel(raw, file, line):
    if not isinstance(raw, str) or raw == "" or "\x00" in raw or "\\" in raw:
        raise PolicyError("allow_malformed", file, line, raw)
    text = unicodedata.normalize("NFC", raw.strip())
    while text.endswith("/"):
        text = text[:-1]
    if text == "" or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise PolicyError("allow_escape", file, line, raw)
    if any(ch in text for ch in GLOB_CHARS):
        raise PolicyError("allow_glob", file, line, raw)
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PolicyError("allow_escape", file, line, raw)
    return text


def parse_allow(text, file):
    roots = []
    seen = set()
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line == "" or line.startswith("#"):
            continue
        if " " in line or "\t" in line:
            raise PolicyError("allow_malformed", file, n, line)
        rel = clean_rel(line, file, n)
        key = fold_key(rel)
        if key in seen:
            continue
        seen.add(key)
        roots.append((rel, n))
    if not roots:
        raise PolicyError("allow_empty", file, 0, "")
    return roots


def _plain_or_special(line, file, n, allow_special):
    if any(ch in line for ch in GLOB_CHARS):
        code = "deny_local_glob" if not allow_special else "deny_base_malformed"
        raise PolicyError(code, file, n, line)
    if line.startswith("- ") or line.startswith("!") or line.startswith("drop "):
        value = line.split(None, 1)[1].strip() if " " in line else ""
        if not allow_special:
            raise PolicyError("deny_narrow", file, n, value)
        raise PolicyError("deny_base_malformed", file, n, line)
    return None


def parse_deny_local(text, file):
    rules = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line == "" or line.startswith("#"):
            continue
        if line.startswith("- ") or line.startswith("!") or line.startswith("drop "):
            value = line.split(None, 1)[1].strip()
            rules.append(Rec("drop", value, n))
            continue
        if any(ch in line for ch in GLOB_CHARS):
            raise PolicyError("deny_local_glob", file, n, line)
        if " " in line or "\t" in line:
            raise PolicyError("deny_local_malformed", file, n, line)
        rules.append(Rec("path", clean_rel(line, file, n), n))
    return rules


def parse_deny_base(text, file):
    rules = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line == "" or line.startswith("#"):
            continue
        if line.startswith("- ") or line.startswith("!") or line.startswith("drop "):
            raise PolicyError("deny_base_malformed", file, n, line)
        if any(ch in line for ch in GLOB_CHARS):
            raise PolicyError("deny_base_malformed", file, n, line)
        if line.startswith("name "):
            value = line[5:].strip()
            if value == "" or "/" in value or any(ch in value for ch in GLOB_CHARS):
                raise PolicyError("deny_base_malformed", file, n, line)
            rules.append(Rec("name", value, n))
            continue
        if line.startswith("path "):
            rules.append(Rec("path", clean_rel(line[5:].strip(), file, n), n))
            continue
        if line.startswith("except "):
            try:
                roles_part, path_part = line[len("except "):].split(" path ", 1)
            except ValueError:
                raise PolicyError("deny_base_malformed", file, n, line)
            roles = tuple(part.strip() for part in roles_part.split(",") if part.strip())
            if not roles:
                raise PolicyError("deny_base_malformed", file, n, line)
            rules.append(Rec("except", clean_rel(path_part.strip(), file, n), n, roles))
            continue
        if " " in line or "\t" in line:
            raise PolicyError("deny_base_malformed", file, n, line)
        rules.append(Rec("path", clean_rel(line, file, n), n))
    require_base(rules, file)
    return rules


def require_base(rules, file):
    names = {fold_key(r.value) for r in rules if r.kind == "name"}
    paths = {fold_key(r.value) for r in rules if r.kind == "path"}
    needed = {
        "name:.env": ".env" in names,
        "path:.keel/logs": fold_key(".keel/logs") in paths,
        "path:.keel/runs": fold_key(".keel/runs") in paths,
        "path:.keel/deny.local": fold_key(".keel/deny.local") in paths,
    }
    missing = [key for key, ok in needed.items() if not ok]
    decisions = [r for r in rules if r.kind == "except" and fold_key(r.value) == fold_key(".keel/decisions")]
    allowed = {"orchestrator", "architect"}
    if not decisions or any(role not in allowed for role in decisions[0].roles) or set(decisions[0].roles) != allowed:
        missing.append("except:.keel/decisions")
    if missing:
        raise PolicyError("deny_base_narrow", file, 0, ",".join(missing))


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise PolicyError("allow_unreadable", path, 0, exc.errno and "unreadable" or "unreadable")


def load_base(harness):
    path = os.path.join(harness, "deny", "base")
    if not os.path.lexists(path):
        raise PolicyError("deny_base_missing", "setup/deny/base", 0, "")
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PolicyError("deny_base_symlink", "setup/deny/base", 0, "")
    real = os.path.realpath(path)
    root = os.path.realpath(harness)
    if not real.startswith(root + os.sep):
        raise PolicyError("deny_base_symlink", "setup/deny/base", 0, "")
    return parse_deny_base(read_text(path), "setup/deny/base")


def snapshot_path(keel, task):
    if task == "" or "/" in task or task in (".", "..") or ".." in task.split("/"):
        raise PolicyError("allow_escape", "task", 0, task)
    return os.path.join(keel, task + ".deny")


def load_project_deny(work, keel, task):
    """Read .keel/deny.local once per task. Later edits are ignored."""
    live = os.path.join(work, ".keel", "deny.local")
    snap = snapshot_path(keel, task)
    if os.path.isfile(snap) and not os.path.islink(snap):
        text = read_text(snap)
        return parse_deny_local(text, ".keel/deny.local")
    if os.path.lexists(live) and os.path.islink(live):
        raise PolicyError("deny_local_malformed", ".keel/deny.local", 0, "symlink")
    text = ""
    if os.path.isfile(live):
        text = read_text(live)
    rules = parse_deny_local(text, ".keel/deny.local")
    os.makedirs(os.path.dirname(snap), exist_ok=True)
    tmp = snap + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, snap)
    return rules


def merge_deny(base_rules, local_rules):
    rules = list(base_rules)
    for rec in local_rules:
        if rec.kind == "drop":
            raise PolicyError("deny_narrow", ".keel/deny.local", rec.line, rec.value)  # narrow-refused
        rules.append(rec)
    return rules


def mode_for(role, root):
    table = MODES.get(role, {})
    key = fold_key(root)
    mode = "ro"
    for name, value in table.items():
        if fold_key(name) == key:
            mode = value
            break
    if role == "developer" and key == fold_key("tests"):
        return "ro"  # developer-tests-ro
    return mode


def is_denied(rel, role, rules):
    folded = fold_key(rel)
    base = folded.rsplit("/", 1)[-1]
    for rec in rules:
        if rec.kind == "name" and base == fold_key(rec.value):
            return True
        if rec.kind == "path":
            path = fold_key(rec.value)
            if folded == path or folded.startswith(path + "/"):
                return True
        if rec.kind == "except":
            if role in rec.roles:
                continue
            path = fold_key(rec.value)
            if folded == path or folded.startswith(path + "/"):
                return True
    return False


def env_type(name):
    upper = name.upper()
    if "PASSWORD" in upper or "PASSWD" in upper or upper == "PASSWORD":
        return "password"
    if "TOKEN" in upper:
        return "token"
    if "KEY" in upper:
        return "key"
    return "env"


def secret_values(env):
    found = []
    for name in SECRET_ENV:
        value = env.get(name, "")
        if isinstance(value, str) and len(value) >= 12:
            found.append((value, env_type(name)))
    found.sort(key=lambda item: len(item[0]), reverse=True)
    return found


def _replace_span(text, start, end, kind, count):
    return text[:start] + PLACEHOLDER.format(kind), text[end:], count + 1


def _redact_impl(text, env):
    if not isinstance(text, str) or text == "":
        return text, 0
    count = 0
    pending = text
    done = ""
    values = secret_values(env)
    encoded = []
    for value, kind in values:
        try:
            raw = base64.b64encode(value.encode("utf-8")).decode("ascii")
        except Exception:
            continue
        if len(raw) >= 16:
            encoded.append((raw, kind))
    while pending:
        best = None  # start, end, kind

        def consider(start, end, kind):
            nonlocal best
            if start < 0 or end <= start:
                return
            if best is None or start < best[0] or (start == best[0] and (end - start) > (best[1] - best[0])):
                best = (start, end, kind)

        for value, kind in values:
            at = pending.find(value)
            if at >= 0:
                consider(at, at + len(value), kind)
        for raw, kind in encoded:
            at = pending.find(raw)
            if at >= 0:
                consider(at, at + len(raw), kind)
        match = TOKEN_RE.search(pending)
        if match:
            consider(match.start(), match.end(), "token")
        match = KEY_RE.search(pending)
        if match:
            consider(match.start(), match.end(), "key")
        match = PASSWORD_RE.search(pending)
        if match:
            consider(match.start(), match.end(), "password")
        match = UNKNOWN_RE.search(pending)
        if match and "REDACTED" not in match.group(0):
            consider(match.start(), match.end(), "unknown")
        if best is None:
            done += pending
            break
        start, end, kind = best
        done += pending[:start] + PLACEHOLDER.format(kind)
        pending = pending[end:]
        count += 1
        if count > 1000:
            raise PolicyError("redaction_failed", ".keel/logs/launch.jsonl", 0, "too many")
    return done, count


def apply_redaction(text, env):
    return _redact_impl(text, env)  # redaction-on


def redact_obj(value, env):
    if isinstance(value, str):
        return apply_redaction(value, env)
    if isinstance(value, list):
        total = 0
        out = []
        for item in value:
            new, n = redact_obj(item, env)
            out.append(new)
            total += n
        return out, total
    if isinstance(value, dict):
        total = 0
        out = {}
        for key, item in value.items():
            new, n = redact_obj(item, env)
            out[key] = new
            total += n
        return out, total
    return value, 0


def warn_once(keel):
    stamp = os.path.join(keel, ".keel", "logs", ".public-warning")
    if os.path.isfile(stamp):
        return
    os.makedirs(os.path.dirname(stamp), exist_ok=True)
    sys.stderr.write(
        "warning: if this product repository is public, files committed under "
        ".keel/decisions/ are public. This harness does not store task decisions.\n"
    )
    with open(stamp, "w", encoding="utf-8") as handle:
        handle.write("once\n")


def still_secret(line, env):
    for value, _kind in secret_values(env):
        if value in line:
            return True
    if TOKEN_RE.search(line):
        return True
    return False


def write_log(keel, record, env):
    """Append one JSONL record. This is the only log writer."""
    warn_once(keel)
    redacted, count = redact_obj(record, env)
    if isinstance(redacted, dict):
        redacted["redactions"] = count
    else:
        raise PolicyError("redaction_failed", ".keel/logs/launch.jsonl", 0, "")
    line = json.dumps(redacted, ensure_ascii=True, separators=(",", ":"))
    if still_secret(line, env) or "\n" in line:
        safe = {
            "ts": record.get("ts", ""),
            "event": "refuse",
            "role": record.get("role", ""),
            "reason_code": "redaction_failed",
            "file": ".keel/logs/launch.jsonl",
            "line": 0,
            "detail": "",
            "mounted_roots": [],
            "denied_withheld": [],
            "redactions": count,
        }
        line = json.dumps(safe, ensure_ascii=True, separators=(",", ":"))
        if still_secret(line, env):
            raise PolicyError("redaction_failed", ".keel/logs/launch.jsonl", 0, "")
    path = os.path.join(keel, ".keel", "logs", "launch.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        raise PolicyError("log_write_failed", ".keel/logs/launch.jsonl", 0, "")
    return redacted


def now_ts():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fixture_detail(keel):
    if os.environ.get("KEEL_REDACT_FIXTURE") != "1":
        return ""
    path = os.path.join(keel, ".keel", "redact-fixture")
    if os.path.isfile(path) and not os.path.islink(path):
        return read_text(path)
    return ""


def log_refuse(keel, role, err, env, detail=""):
    extra = fixture_detail(keel)
    if extra:
        detail = (detail + "\n" + extra).strip()
    record = {
        "ts": now_ts(),
        "event": "refuse",
        "role": role,
        "reason_code": err.code,
        "file": err.file,
        "line": err.line,
        "detail": detail or err.detail,
        "mounted_roots": [],
        "denied_withheld": [],
    }
    write_log(keel, record, env)


def log_ok(keel, role, roots, withheld, env, detail=""):
    extra = fixture_detail(keel)
    if extra:
        detail = (detail + "\n" + extra).strip()
    record = {
        "ts": now_ts(),
        "event": "launch_ok",
        "role": role,
        "reason_code": "",
        "file": "",
        "line": 0,
        "detail": detail,
        "mounted_roots": roots,
        "denied_withheld": withheld,
    }
    write_log(keel, record, env)


def load_allow(harness, role):
    rel = os.path.join("setup", "allow", role + ".paths")
    path = os.path.join(harness, "allow", role + ".paths")
    if role not in LAUNCHABLE or not os.path.lexists(path):
        raise PolicyError("unknown_role", rel, 0, role)
    if os.path.islink(path) or not os.path.isfile(path):
        raise PolicyError("allow_unreadable", rel, 0, "")
    return parse_allow(read_text(path), rel)


def archive_base(repo, sha, dest):
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "archive", "--format=tar", sha],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise PolicyError("tester_base_missing", sha, 0, str(exc.errno or ""))
    if proc.returncode != 0:
        raise PolicyError("tester_base_missing", sha, 0, "archive")
    tar = subprocess.run(["tar", "-x", "-C", dest], input=proc.stdout, check=False)
    if tar.returncode != 0:
        raise PolicyError("tester_base_missing", sha, 0, "tar")


def prepare_source(role, work, repo, keel, task):
    if role != "tester":
        return work, []
    base_file = os.path.join(keel, task + ".base")
    if not os.path.isfile(base_file):
        raise PolicyError("tester_base_missing", task + ".base", 0, "")
    sha = read_text(base_file).strip()
    if len(sha) < 7:
        raise PolicyError("tester_base_missing", task + ".base", 0, "")
    dest = os.path.join(keel, ".keel", "runs", task, "base")
    archive_base(repo, sha, dest)
    return dest, []


def consider_link(path, root, work, role, rules):
    raw = os.readlink(path)
    if raw.startswith("/") or raw.startswith("\\"):
        raise PolicyError("symlink_escape", rel_of(path, work), 0, "")
    joined = os.path.normpath(os.path.join(os.path.dirname(path), raw))
    root_real = os.path.realpath(root) if os.path.isdir(root) else os.path.abspath(root)
    # Compare without resolving the link itself.
    if not (joined == os.path.abspath(root) or joined.startswith(os.path.abspath(root) + os.sep)):
        raise PolicyError("symlink_escape", rel_of(path, work), 0, "")
    target_rel = rel_of(joined, work) if joined.startswith(os.path.abspath(work)) else rel_of(path, work)
    if is_denied(target_rel, role, rules) or is_denied(rel_of(path, work), role, rules):
        raise PolicyError("symlink_escape", rel_of(path, work), 0, "")


def rel_of(path, work):
    rel = os.path.relpath(path, work)
    return rel.replace(os.sep, "/")


def scan_tree(host_root, work, role, rules, masks, withheld):
    if os.path.islink(host_root):
        raise PolicyError("symlink_escape", rel_of(host_root, work), 0, "")
    for dirpath, dirnames, filenames in os.walk(host_root, followlinks=False):
        entries = list(dirnames) + list(filenames)
        keep = []
        for name in dirnames:
            path = os.path.join(dirpath, name)
            rel = rel_of(path, work)
            if os.path.islink(path):
                consider_link(path, host_root, work, role, rules)
                continue
            if is_denied(rel, role, rules):
                masks.append((path, rel, "dir"))
                withheld.append(rel)
                continue
            keep.append(name)
        dirnames[:] = keep
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = rel_of(path, work)
            if os.path.islink(path):
                consider_link(path, host_root, work, role, rules)
                continue
            if not os.path.isfile(path):
                continue
            if is_denied(rel, role, rules):
                if os.stat(path).st_nlink > 1:
                    raise PolicyError("hardlink_withheld", rel, 0, "")
                masks.append((path, rel, "file"))
                withheld.append(rel)


def build_mounts(role, work, harness, keel, task, repo, env):
    roots = load_allow(harness, role)
    base = load_base(harness)
    local = load_project_deny(work, keel, task)
    rules = merge_deny(base, local)
    # deny-overlay-on
    apply_overlay = True  # deny-overlay-on
    if not apply_overlay:
        rules = [rec for rec in rules if rec.kind == "keep-none"]
    source, _absent = prepare_source(role, work, repo, keel, task)
    runs = os.path.join(keel, ".keel", "runs", task)
    os.makedirs(runs, exist_ok=True)
    empty_file = os.path.join(runs, "empty-file")
    empty_dir = os.path.join(runs, "empty-dir")
    if not os.path.exists(empty_file):
        with open(empty_file, "w", encoding="utf-8"):
            pass
    os.makedirs(empty_dir, exist_ok=True)
    mounts = []
    mounted = []
    withheld = []
    absent = []
    for rel, line in roots:
        folded = fold_key(rel)
        logical = rel
        host = os.path.join(source, *rel.split("/"))
        container = "/work/" + rel
        if folded == fold_key(".keel/decisions"):
            host = os.path.join(source, ".keel", "decisions", task)
            container = "/work/.keel/decisions/" + task
            logical = ".keel/decisions/" + task
        mode = mode_for(role, rel)
        if is_denied(logical, role, rules) or is_denied(rel, role, rules):
            withheld.append(logical)
            continue
        if not os.path.isdir(host) or os.path.islink(host):
            if role == "tester" and rel != "tests":
                absent.append(rel)
                continue
            if role == "tester" and rel == "tests":
                os.makedirs(host, exist_ok=True)
            elif mode == "rw" and folded == fold_key(".keel/decisions"):
                os.makedirs(host, exist_ok=True)
            else:
                raise PolicyError("allow_not_dir", "setup/allow/" + role + ".paths", line, rel)
        if not os.path.isdir(host):
            raise PolicyError("allow_not_dir", "setup/allow/" + role + ".paths", line, rel)
        # Separate binds keep tests and src on different mounts, so a hardlink cannot cross them.
        same_fs = False  # developer-same-fs
        if role == "developer" and same_fs:
            if not mounts:
                mounts.append((source, "/work", "rw"))
            mounted.append(logical)
            continue
        mounts.append((host, container, mode))
        mounted.append(logical)
        local_masks = []
        local_withheld = []
        base_for_rel = source if role == "tester" else work
        scan_tree(host, base_for_rel, role, rules, local_masks, local_withheld)
        for host_path, rel_path, kind in local_masks:
            if kind == "dir":
                mounts.append((empty_dir, "/work/" + rel_path, "ro"))
            else:
                mounts.append((empty_file, "/work/" + rel_path, "ro"))
        withheld.extend(local_withheld)
    if role != "tester" and not mounted:
        raise PolicyError("allow_empty", "setup/allow/" + role + ".paths", 0, "")
    detail = ""
    if absent:
        detail = "absent " + ",".join(absent)
    return mounts, mounted, withheld, detail


def emit_mounts(args, env):
    try:
        mounts, roots, withheld, detail = build_mounts(
            args.role, args.work, args.harness, args.keel, args.task, args.repo, env
        )
        log_ok(args.keel, args.role, roots, withheld, env, detail)
    except PolicyError as err:
        try:
            log_refuse(args.keel, args.role, err, env)
        except PolicyError as nested:
            sys.stderr.write("REFUSE\t{0}\t{1}\t{2}\n".format(nested.code, nested.file, nested.line))
            return 1
        sys.stdout.write("REFUSE\t{0}\t{1}\t{2}\n".format(err.code, err.file, err.line))
        return 1
    for host, container, mode in mounts:
        sys.stdout.write("MOUNT\t{0}\t{1}\t{2}\n".format(host, container, mode))
    return 0


def doctor(harness):
    errors = []
    try:
        load_base(harness)
    except PolicyError as err:
        errors.append("{0} {1}:{2}".format(err.code, err.file, err.line))
    for role in LAUNCHABLE:
        try:
            load_allow(harness, role)
        except PolicyError as err:
            errors.append("{0} {1}:{2} {3}".format(err.code, err.file, err.line, err.detail))
    return errors


def cmd_doctor(args):
    errors = doctor(args.harness)
    if errors:
        for line in errors:
            sys.stderr.write(line + "\n")
        return 1
    sys.stdout.write("visibility ok\n")
    return 0


def self_test():
    import tempfile
    env = {
        "GH_TOKEN": "ghp_" + ("A" * 36),
        "KEEL_SECRET": "envonlysecretvalue123456",
        "API_KEY": "short",
    }
    token = env["GH_TOKEN"]
    red, n = apply_redaction("see " + token + " end", env)
    assert red == "see [REDACTED:token] end", red
    assert n == 1
    assert token not in red
    assert not red.startswith("ghp_") and "AAAA" not in red
    env_red, n_env = apply_redaction("value " + env["KEEL_SECRET"], env)
    assert env_red == "value [REDACTED:env]", env_red
    pw, n_pw = apply_redaction("password=hunter2hunter2hunter2", env)
    assert pw == "[REDACTED:password]", pw
    unknown, n_u = apply_redaction("Zz9unknownSecretValue1234567890abcd", env)
    assert unknown == "[REDACTED:unknown]", unknown
    blob = base64.b64encode(token.encode("utf-8")).decode("ascii")
    b64, n_b = apply_redaction("blob " + blob, env)
    assert blob not in b64 and "[REDACTED:token]" in b64, b64
    multi = "line-one\n" + token + "\nline-three"
    multi_red, _n = apply_redaction(multi, env)
    assert token not in multi_red and "[REDACTED:token]" in multi_red
    # count is replacement events
    both, n_both = apply_redaction(token + " " + env["KEEL_SECRET"], env)
    assert n_both == 2, n_both
    assert token not in both and env["KEEL_SECRET"] not in both

    # casefold and NFC
    assert fold_key("SRC/.ENV") == fold_key("src/.env")
    nfd = "cafe\u0301"
    nfc = unicodedata.normalize("NFC", nfd)
    assert fold_key(nfd) == fold_key(nfc)

    file = "mem.paths"
    try:
        parse_allow("# only\n\n", file)
        raise SystemExit("empty allow was accepted")
    except PolicyError as err:
        assert err.code == "allow_empty"
    try:
        parse_allow("src/*\n", file)
        raise SystemExit("glob accepted")
    except PolicyError as err:
        assert err.code == "allow_glob"
    try:
        parse_allow("/etc\n", file)
        raise SystemExit("absolute accepted")
    except PolicyError as err:
        assert err.code == "allow_escape"
    try:
        parse_allow("src/../../etc\n", file)
        raise SystemExit("dotdot accepted")
    except PolicyError as err:
        assert err.code == "allow_escape"
    roots = parse_allow("# c\n\nsrc\nSRC\n", file)
    assert len(roots) == 1, roots

    base = """# keel-deny-base
name .env
path .keel/logs
path .keel/runs
path .keel/deny.local
except orchestrator,architect path .keel/decisions
except skills_auditor path .agents
"""
    rules = parse_deny_base(base, "setup/deny/base")
    try:
        parse_deny_base("name .env\n", "setup/deny/base")
        raise SystemExit("narrow base accepted")
    except PolicyError as err:
        assert err.code == "deny_base_narrow"
    local = parse_deny_local("src/customer.txt\n", ".keel/deny.local")
    merged = merge_deny(rules, local)
    assert is_denied("src/.ENV", "developer", merged)
    assert is_denied("src/customer.txt", "developer", merged)
    assert not is_denied(".keel/decisions/task-1/d1.md", "orchestrator", merged)
    assert is_denied(".keel/decisions/task-1/d1.md", "developer", merged)
    assert is_denied(".keel/decisions/task-1/d1.md", "tester", merged)
    assert is_denied(".keel/decisions/task-1/d1.md", "auditor", merged)
    assert is_denied(".agents/skills/a", "auditor", merged)
    assert not is_denied(".agents/skills/a", "skills_auditor", merged)
    try:
        merge_deny(rules, parse_deny_local("- .env\n", ".keel/deny.local"))
        raise SystemExit("drop accepted")
    except PolicyError as err:
        assert err.code == "deny_narrow"
    try:
        parse_deny_local("src/*\n", ".keel/deny.local")
        raise SystemExit("deny glob accepted")
    except PolicyError as err:
        assert err.code == "deny_local_glob"
    assert mode_for("developer", "tests") == "ro"
    assert mode_for("developer", "src") == "rw"
    assert mode_for("tester", "tests") == "rw"

    tmp = tempfile.mkdtemp(prefix="vis-self-")
    try:
        harness = os.path.join(tmp, "h")
        os.makedirs(os.path.join(harness, "allow"))
        os.makedirs(os.path.join(harness, "deny"))
        with open(os.path.join(harness, "deny", "base"), "w", encoding="utf-8") as handle:
            handle.write(base)
        for role, body in {
            "developer": "src\ndocs\ntests\n",
            "orchestrator": "briefs\ndocs\ntests\n.keel/decisions\n",
            "architect": "briefs\ndocs\n.keel/decisions\n",
            "tester": "src\ndocs\ntests\n",
            "auditor": "src\ndocs\n",
            "skills_auditor": "skills-draft\nskill-review\n",
            "critic": "plans\n",
            "design_reviewer": "docs\n",
            "verifier": "findings\n",
            "qa": "qa-stub\n",
            "researcher": "research-stub\n",
        }.items():
            with open(os.path.join(harness, "allow", role + ".paths"), "w", encoding="utf-8") as handle:
                handle.write(body)
        assert doctor(harness) == []
        os.symlink(os.path.join(harness, "deny", "base"), os.path.join(tmp, "linkbase"))
        # replace base with a symlink
        base_path = os.path.join(harness, "deny", "base")
        os.rename(base_path, base_path + ".real")
        os.symlink(base_path + ".real", base_path)
        try:
            load_base(harness)
            raise SystemExit("symlink base accepted")
        except PolicyError as err:
            assert err.code == "deny_base_symlink", err.code
        os.remove(base_path)
        os.rename(base_path + ".real", base_path)

        work = os.path.join(tmp, "work")
        keel = os.path.join(tmp, "keel")
        os.makedirs(os.path.join(work, "src"))
        os.makedirs(os.path.join(work, "docs"))
        os.makedirs(os.path.join(work, "tests"))
        os.makedirs(os.path.join(work, ".keel"))
        with open(os.path.join(work, "src", ".env"), "w", encoding="utf-8") as handle:
            handle.write("SECRET\n")
        with open(os.path.join(work, ".keel", "deny.local"), "w", encoding="utf-8") as handle:
            handle.write("src/customer.txt\n")
        mounts, roots, withheld, _detail = build_mounts(
            "developer", work, harness, keel, "task-1", work, env
        )
        assert "src" in roots and "tests" in roots
        assert any(item[2] == "ro" and item[1] == "/work/tests" for item in mounts)
        assert any(item[1] == "/work/src/.env" and item[2] == "ro" for item in mounts)
        assert "src/.env" in withheld
        # second load ignores a removed project deny
        os.remove(os.path.join(work, ".keel", "deny.local"))
        with open(os.path.join(work, "src", "customer.txt"), "w", encoding="utf-8") as handle:
            handle.write("cust\n")
        _m2, _r2, withheld2, _d2 = build_mounts(
            "developer", work, harness, keel, "task-1", work, env
        )
        assert "src/customer.txt" in withheld2

        log_ok(keel, "developer", ["src"], ["src/.env"], env, token)
        logged = open(os.path.join(keel, ".keel", "logs", "launch.jsonl"), encoding="utf-8").read()
        assert token not in logged
        assert "[REDACTED:token]" in logged
        last = json.loads(logged.strip().splitlines()[-1])
        assert last["redactions"] >= 1
        assert last["event"] == "launch_ok"
        fix = os.path.join(keel, ".keel", "redact-fixture")
        with open(fix, "w", encoding="utf-8") as handle:
            handle.write(token + "\nFIXTURE-RECORD\n")
        os.environ.pop("KEEL_REDACT_FIXTURE", None)
        log_ok(keel, "developer", ["src"], [], env, "")
        quiet = json.loads(open(os.path.join(keel, ".keel", "logs", "launch.jsonl"), encoding="utf-8").read().strip().splitlines()[-1])
        assert quiet["redactions"] == 0, quiet
        assert token not in quiet["detail"]
        assert "FIXTURE-RECORD" not in quiet["detail"]
        os.environ["KEEL_REDACT_FIXTURE"] = "1"
        try:
            log_ok(keel, "developer", ["src"], [], env, "")
            fed = json.loads(open(os.path.join(keel, ".keel", "logs", "launch.jsonl"), encoding="utf-8").read().strip().splitlines()[-1])
            assert fed["redactions"] >= 1, fed
            assert token not in fed["detail"]
            assert "[REDACTED:token]" in fed["detail"]
            assert "FIXTURE-RECORD" in fed["detail"]
        finally:
            os.environ.pop("KEEL_REDACT_FIXTURE", None)
            os.remove(fix)
    finally:
        shutil.rmtree(tmp)
    print("visibility self-test ok")
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        sys.stderr.write("usage: visibility.py self-test | doctor --harness H | mounts --role R --work W --harness H --keel P --task T --repo R | refuse --code C --role R ...\n")
        return 2
    cmd = argv[1]
    if cmd == "self-test":
        return self_test()
    args = parse_args(argv[2:])
    if cmd == "doctor":
        return cmd_doctor(args)
    if cmd == "refuse":
        err = PolicyError(args.code or "unknown_role", args.file or "", int(args.line or 0), "")
        try:
            log_refuse(args.keel, args.role, err, os.environ)
        except PolicyError:
            return 1
        sys.stdout.write("REFUSE\t{0}\t{1}\t{2}\n".format(err.code, err.file, err.line))
        return 1
    if cmd == "mounts":
        return emit_mounts(args, os.environ)
    sys.stderr.write("unknown command\n")
    return 2


def parse_args(argv):
    class Args(object):
        pass
    out = Args()
    out.role = ""
    out.work = ""
    out.harness = ""
    out.keel = ""
    out.task = "task-1"
    out.repo = ""
    out.code = ""
    out.file = ""
    out.line = "0"
    i = 0
    while i < len(argv):
        key = argv[i]
        if i + 1 >= len(argv):
            break
        val = argv[i + 1]
        if key == "--role":
            out.role = val
        elif key == "--work":
            out.work = val
        elif key == "--harness":
            out.harness = val
        elif key == "--keel":
            out.keel = val
        elif key == "--task":
            out.task = val
        elif key == "--repo":
            out.repo = val
        elif key == "--code":
            out.code = val
        elif key == "--file":
            out.file = val
        elif key == "--line":
            out.line = val
        i += 2
    return out


if __name__ == "__main__":
    sys.exit(main(sys.argv))
