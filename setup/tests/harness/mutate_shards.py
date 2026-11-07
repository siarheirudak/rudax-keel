#!/usr/bin/env python3
"""Shard plan, tree materialisation, and trusted aggregate."""
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import mutate
import mutant_defs as md
import mutant_files as mf

# Setting: shard fan-out. Tune from measured runs.
SHARD_CAP = 8
# Setting: reject an archive entry or a RESULT line above these sizes.
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_LINE = 8192
SELECTOR_FILES = (
    "setup/tests/harness/mutant_files.py",
    "setup/tests/harness/mutate.py",
    "setup/tests/harness/mutant_defs.py",
    "setup/tests/harness/mutate_shards.py",
    "setup/tests/harness/mutate-full-state.py",
)

keep_last = True  # shard-last
require_all_ids = True  # shard-complete
reject_foreign = True  # shard-foreign
require_success = True  # shard-success
check_main_moved = True  # main-moved
enforce_size = True  # extract-size
enforce_paths = True  # extract-path
enforce_symlink = True  # extract-symlink
enforce_line = True  # line-cap
timeout_is_fail = True  # timeout-not-success
check_baseline = True  # baseline-check
check_tree_entries = True  # tree-entry-check


class ShardError(Exception):
    pass


# Pins match run-tests.sh, setup/gitleaks-install.sh, and the pi image.
GITLEAKS_VERSION = "8.30.1"
PI_VERSION = "0.73.1"
PI_PACKAGE = "@mariozechner/pi-coding-agent@" + PI_VERSION
DIAG_RECORD_MAX = 4096
DIAG_RECORD_CAP = 128
DIAG_TOTAL_MAX = 64 * 1024
DIAG_LIST_MAX = 20
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ID_RE = re.compile(r"^M[0-9]+$")
SHARD_RE = re.compile(r"^[0-9]+$")
PREREQ_CATEGORIES = frozenset((
    "docker_missing",
    "docker_daemon",
    "gitleaks_install",
    "gitleaks_version",
    "image_build",
    "image_missing",
    "image_version",
    "node_missing",
    "npm_missing",
    "pi_install",
    "pi_version",
    "pi_resolve",
    "absent",
    "map",
    "prereq",
    "timeout",
    "transport",
    "incomplete",
))
BASELINE_REASONS = frozenset((
    "absent",
    "unreadable",
    "decode",
    "line",
    "empty",
    "duplicate",
    "conflict",
    "incomplete",
    "parser",
    "status",
    "timeout",
))
TAG_DISPLAY = frozenset((
    "BLOCKED",
    "CONTAINED",
    "PARTIAL",
    "NA",
    "NOT_BLOCKED",
    "WRONG_REASON",
    "ERROR",
    "OTHER",
))
_TAG_NORMALIZE = {
    "BLOCKED": "BLOCKED",
    "CONTAINED": "CONTAINED",
    "PARTIAL": "PARTIAL",
    "N/A": "NA",
    "NOT BLOCKED": "NOT_BLOCKED",
    "WRONG REASON": "WRONG_REASON",
    "ERROR": "ERROR",
}
# One row per trusted suite. Images include transitive role dependencies.
SUITE_NEEDS = {
    "test-attacks.sh": frozenset(("docker", "gitleaks", "image_git", "image_proxy")),
    "test-attack-results.sh": frozenset(),
    "test-mutant-result.sh": frozenset(),
    "test-runtime.sh": frozenset(("docker",)),
    "test-step4.sh": frozenset(("docker", "image_git", "image_pi", "host_pi")),
    "test-step5.sh": frozenset(),
    "test-step6.sh": frozenset(("docker", "image_git")),
    "test-egress.sh": frozenset(("docker", "image_git", "image_proxy")),
    "visibility-suite.sh": frozenset(("docker", "image_git", "image_proxy")),
    "test-mutant-select.py": frozenset(),
    "test-mutate-shards.sh": frozenset(),
}
_IMAGE_FILES = (
    ("image_git", "keel-git"),
    ("image_proxy", "keel-proxy"),
    ("image_pi", "keel-pi"),
)


class PrereqError(ShardError):
    def __init__(self, category, suites, ids):
        self.category = category if category in PREREQ_CATEGORIES else "prereq"
        self.suites = list(suites)
        self.ids = list(ids)
        ShardError.__init__(self, "prereq")


def assign_shards(ids, cap=SHARD_CAP):
    ordered = sorted(ids, key=md.id_key)
    if not keep_last and ordered:
        ordered = ordered[:-1]
    count = min(cap, len(ordered)) if ordered else 0
    shards = [[] for _ in range(count)]
    for index, mid in enumerate(ordered):
        shards[index % count].append(mid)
    return shards


def result_ok(result):
    if not require_success:
        return True
    if result == "success":
        return True
    if result in ("timed_out", "cancelled") and not timeout_is_fail:
        return True
    return False


def bind_shard(expected, seen, shard_result):
    if not result_ok(shard_result):
        return False
    if len(seen) != len(set(seen)):
        return False
    if require_all_ids and set(expected) - set(seen):
        return False
    if reject_foreign and set(seen) - set(expected):
        return False
    return True


def allowed_artifact_names(shard_keys):
    names = {"plan"}
    for key in shard_keys:
        names.add("raw-%s" % key)
        names.add("tree-%s" % key)
    return names


def artifact_names_ok(names, shard_keys):
    allowed = allowed_artifact_names(shard_keys)
    names_ok = set(names) <= allowed  # artifact-allow
    if not names_ok:
        return False
    if len(list(names)) != len(set(names)):
        return False
    return True


def skipped_shard_ok(shard_result, plan_skip):
    """A skipped shard is success only when the trusted plan says skip."""
    if shard_result != "skipped":
        return False
    return bool(plan_skip)


def bad_zip_path(name):
    if name.startswith("/") or name.startswith("\\"):
        return True
    parts = name.replace("\\", "/").split("/")
    return any(part == ".." for part in parts)


def zip_violations(entries):
    """entries: list of dicts name, mode, size. mode is 'file' or 'symlink'."""
    bad = []
    total = sum(item["size"] for item in entries)
    if enforce_size and (total > MAX_ARCHIVE_BYTES or any(item["size"] > MAX_FILE_BYTES for item in entries)):
        bad.append("size")
    if enforce_paths and any(bad_zip_path(item["name"]) for item in entries):
        bad.append("path")
    if enforce_symlink and any(item["mode"] == "symlink" for item in entries):
        bad.append("symlink")
    return bad


def parse_result_text(text):
    if enforce_line:
        for line in text.splitlines():
            if len(line) > MAX_LINE:
                raise ShardError("line")
    return mutate.collect_results(text)


def main_moved(before, after):
    if not check_main_moved:
        return False
    return before != after


def accept_entry(mode, digest, oid):
    if not check_tree_entries:
        return True
    if mode in ("120000", "160000"):
        return False
    return digest == oid


def git_blob_digest(blob):
    header = ("blob %d\0" % len(blob)).encode("ascii")
    return hashlib.sha1(header + blob).hexdigest()


def _git(repo, *args):
    cmd = ["git", "-C", repo, "-c", "core.hooksPath=/dev/null", *args]
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_COUNT"] = "0"
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
    if proc.returncode != 0:
        raise ShardError(proc.stderr.decode("utf-8", "replace").strip() or "git")
    return proc.stdout


def materialize_tree(repo, sha, dest):
    """Build dest from ls-tree and cat-file. No checkout, archive, or filters."""
    raw = _git(repo, "ls-tree", "-r", "-z", sha)
    os.makedirs(dest, exist_ok=True)
    for item in raw.split(b"\0"):
        if not item:
            continue
        meta, path_b = item.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split(" ")
        path = path_b.decode("utf-8")
        if kind == "commit" or mode in ("120000", "160000"):
            if not accept_entry(mode, "", oid):
                raise ShardError("entry " + path)
            continue
        if kind != "blob":
            raise ShardError("entry " + path)
        blob = _git(repo, "cat-file", "blob", oid)
        digest = git_blob_digest(blob)
        if not accept_entry(mode, digest, oid):
            raise ShardError("hash " + path)
        target = os.path.join(dest, path)
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(blob)
        if mode == "100755":
            os.chmod(target, 0o755)


def selector_hash(root):
    digest = hashlib.sha256()
    for rel in SELECTOR_FILES:
        path = os.path.join(root, rel)
        digest.update(rel.encode("utf-8"))
        with open(path, "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()


def _at(table, mid):
    if callable(table):
        return table(mid)
    return table[mid]


def baseline_bad_ids(ids, suite_of, exp_of, baselines):
    if not check_baseline:
        return [], False
    bad = []
    missing = False
    for mid in ids:
        suite = _at(suite_of, mid)
        if suite not in baselines or baselines[suite] is None:
            missing = True
            continue
        try:
            red = set(mutate.red_from_results(parse_result_text(baselines[suite])))
        except ShardError:
            missing = True
            continue
        if any(name in red for name in _at(exp_of, mid)):
            bad.append(mid)
    return bad, missing


def grade_stdout(exp, stdout):
    try:
        text = stdout if isinstance(stdout, str) else stdout.decode("utf-8", "replace")
        parsed = parse_result_text(text)
    except ShardError as err:
        return "ERROR", str(err)
    # judge() re-parses. A long-line failure is already returned.
    red, detail = mutate.judge(exp, text, None, False)
    if red is None:
        return "ERROR", detail
    # Re-check the cap result was the same set of lines.
    if mutate.red_from_results(parsed) != red:
        return "ERROR", "parse"
    return mutate.verdict_tag(exp, red), detail


def tag_fails(tag):
    return tag in ("NO", "ERROR")


def resolve_plan(changed, main, pr, red, known_suites, select):
    errors = md.coverage_errors(main, pr, known_suites, main.masked)
    if errors:
        raise md.DefsError("coverage " + ",".join(str(item) for item in errors))
    fresh = md.new_ids(main.ids, pr.ids)
    changed_ids = md.modified_ids(main, pr)
    gone = md.removed_ids(main.ids, pr.ids)
    if gone:
        raise md.DefsError("removed " + " ".join(gone))
    _status, old = select(list(changed))
    if isinstance(old, tuple):
        old = old[1]
    ordered = sorted(main.ids | pr.ids, key=md.id_key)
    plan = md.build_plan(old, fresh, changed_ids, red, ordered)
    print("mutants: total %d, new %d, modified %d" % (len(plan), len(fresh), len(changed_ids)))
    return plan


def inspect_zip(blob):
    if enforce_size and len(blob) > MAX_ARCHIVE_BYTES:
        raise ShardError("size")
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as err:
        raise ShardError("zip") from err
    entries = []
    for info in archive.infolist():
        mode = "file"
        unix = info.external_attr >> 16
        if stat.S_ISLNK(unix):
            mode = "symlink"
        entries.append({"name": info.filename, "mode": mode, "size": info.file_size})
    bad = zip_violations(entries)
    if bad:
        raise ShardError(",".join(bad))
    return archive


def safe_extract(blob, dest):
    archive = inspect_zip(blob)
    os.makedirs(dest, exist_ok=True)
    for info in archive.infolist():
        archive.extract(info, dest)
    return dest


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path, expected):
    return sha256_file(path) == expected


def repo_rel(m_file):
    if m_file.startswith("scripts/") or m_file.startswith(".github/"):
        return m_file
    return "setup/" + m_file


def apply_def_edits(dest_root, defs, mid):
    """Apply one id's literals onto a materialised tree. No suite code runs."""
    rels = [defs.M[mid][0]]
    for other in defs.extras(mid):
        if other in defs.M:
            rels.append(defs.M[other][0])
    file_edits = {}
    specs = [mid] + [other for other in defs.extras(mid) if other in defs.M]
    for sid in specs:
        spec = defs.M[sid]
        pairs = [(spec[1], spec[2])]
        if len(spec) > 5:
            pairs.extend(spec[5])
        file_edits.setdefault(spec[0], []).extend(pairs)
    for path in mf.FILES.get(mid, []):
        rel = path[len("setup/"):] if path.startswith("setup/") else path
        if rel not in file_edits:
            file_edits[rel] = file_edits[defs.M[mid][0]]
    for rel, pairs in file_edits.items():
        path = os.path.join(dest_root, repo_rel(rel))
        if not os.path.isfile(path):
            raise ShardError("%s missing %s" % (mid, rel))
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        if rel != defs.M[mid][0] and text.count(pairs[0][0]) != 1:
            continue
        updated, err = mutate.apply_edits(text, pairs)
        if err or updated is None:
            raise ShardError("%s %s" % (mid, err or "apply"))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(updated)


def pack_shard(baseline, ids, defs, dest_tar):
    """One baseline tree plus the mutated file bytes for each id."""
    os.makedirs(os.path.dirname(dest_tar), exist_ok=True)
    with tarfile.open(dest_tar, "w:gz") as tar:
        tar.add(baseline, arcname="baseline")
        for mid in ids:
            overlay = os.path.join(os.path.dirname(dest_tar), "overlay-" + mid)
            if os.path.isdir(overlay):
                subprocess.run(["rm", "-rf", overlay], check=False)
            subprocess.run(["cp", "-a", baseline, overlay], check=True)
            apply_def_edits(overlay, defs, mid)
            # Store only paths whose bytes differ, under ids/<mid>/.
            for dirpath, _dirs, files in os.walk(overlay):
                for name in files:
                    full = os.path.join(dirpath, name)
                    rel = os.path.relpath(full, overlay)
                    base = os.path.join(baseline, rel)
                    with open(full, "rb") as handle:
                        blob = handle.read()
                    same = False
                    if os.path.isfile(base):
                        with open(base, "rb") as handle:
                            same = handle.read() == blob
                    if same:
                        continue
                    data = blob
                    info = tarfile.TarInfo(name="ids/%s/%s" % (mid, rel))
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            subprocess.run(["rm", "-rf", overlay], check=False)


def self_test():
    ids = ["M%02d" % n for n in range(1, 14)]
    shards = assign_shards(ids, 4)
    flat = [mid for group in shards for mid in group]
    if sorted(flat) != sorted(ids) or len(flat) != len(set(flat)) or len(shards) != 4:
        return "round-robin"
    if SHARD_CAP != 8 or len(assign_shards(["M%02d" % n for n in range(1, 17)])) != 8:
        return "cap"
    if not bind_shard(["M01"], ["M01"], "success"):
        return "bind success"
    if bind_shard(["M01", "M02"], ["M01"], "success"):
        return "missing id accepted"
    if bind_shard(["M01"], ["M01", "M01"], "success"):
        return "duplicate accepted"
    if bind_shard(["M01"], ["M01", "M02"], "success"):
        return "foreign id accepted"
    if bind_shard(["M01"], ["M01"], "failure"):
        return "failed shard accepted"
    if bind_shard(["M01"], ["M01"], "cancelled"):
        return "cancelled shard accepted"
    if bind_shard(["M01"], ["M01"], "timed_out"):
        return "timed out shard accepted"
    if artifact_names_ok(["plan", "raw-0", "tree-0", "evil"], ["0"]):
        return "extra artifact accepted"
    if skipped_shard_ok("skipped", True) is not True or skipped_shard_ok("skipped", False) is not False:
        return "skipped shard"
    if artifact_names_ok(["raw-9"], ["0"]):
        return "raw-9 accepted"
    sample = [{"name": "../x", "mode": "file", "size": 1}]
    if "path" not in zip_violations(sample):
        return "dotdot allowed"
    sample = [{"name": "/tmp/x", "mode": "file", "size": 1}]
    if "path" not in zip_violations(sample):
        return "absolute path allowed"
    sample = [{"name": "a", "mode": "symlink", "size": 1}]
    if "symlink" not in zip_violations(sample):
        return "symlink allowed"
    sample = [{"name": "a", "mode": "file", "size": MAX_FILE_BYTES + 1}]
    if "size" not in zip_violations(sample):
        return "size cap off"
    try:
        parse_result_text("RESULT A1: BLOCKED\n" + ("x" * (MAX_LINE + 1)))
    except ShardError:
        pass
    else:
        return "line cap off"
    if not main_moved("a", "b"):
        return "main move ignored"
    if accept_entry("120000", "abc", "abc"):
        return "symlink entry accepted"
    if accept_entry("100644", "abc", "def"):
        return "hash mismatch accepted"
    bad, missing = baseline_bad_ids(
        ["M01", "M02"],
        {"M01": "s", "M02": "s"},
        {"M01": ["A1"], "M02": ["A2"]},
        {"s": "RESULT A1: NOT BLOCKED\nRESULT A2: BLOCKED\n"},
    )
    if bad != ["M01"] or missing:
        return "baseline ids %s missing %s" % (bad, missing)
    bad, missing = baseline_bad_ids(
        ["M01"],
        {"M01": "s"},
        {"M01": ["A1"]},
        {},
    )
    if not missing:
        return "missing baseline accepted"
    return ""


def emit_output(name, value):
    text = str(value)
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        print("%s=%s" % (name, text))
        return
    delim = "KEEL%s" % hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("%s<<%s\n%s\n%s\n" % (name, delim, text, delim))


def _load_state():
    import importlib.util
    path = os.path.join(_HERE, "mutate-full-state.py")
    spec = importlib.util.spec_from_file_location("mutate_full_state", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def combined_defs(mutate_src, files_src):
    found = md.parse_literals(mutate_src)
    found.update(md.parse_literals(files_src))
    return md.Defs(found)


def git_text(repo, sha, rel):
    return _git(repo, "show", "%s:%s" % (sha, rel)).decode("utf-8")


def cmd_resolve(repo, sha, base_ref):
    import json
    main_sha = _git(repo, "rev-parse", base_ref).decode().strip()
    base = _git(repo, "merge-base", main_sha, sha).decode().strip()
    names = [line for line in _git(repo, "diff", "--name-only", base, sha).decode().splitlines() if line]
    main = combined_defs(
        open(os.path.join(repo, "setup/tests/harness/mutate.py"), encoding="utf-8").read(),
        open(os.path.join(repo, "setup/tests/harness/mutant_files.py"), encoding="utf-8").read(),
    )
    pr = combined_defs(
        git_text(repo, sha, "setup/tests/harness/mutate.py"),
        git_text(repo, sha, "setup/tests/harness/mutant_files.py"),
    )
    red = False
    token = os.environ.get("GH_TOKEN") or ""
    gh_repo = os.environ.get("REPO") or ""
    if token and gh_repo:
        try:
            state = _load_state()
            runs = [state.normalize_run(item) for item in state.fetch_runs(gh_repo, token)]
            states = {}
            for run in runs:
                if run.get("conclusion") == "success":
                    states[run["id"]] = {"missing": True, "mode": "skip"}
            red = state.is_red(runs, states, os.environ.get("DEFAULT_BRANCH") or "main")
        except Exception:
            red = True
    if os.environ.get("PLAN_ALL") == "1":
        plan = sorted(main.ids, key=md.id_key)
        print("mutants: total %d, new 0, modified 0" % len(plan))
        suite_defs = main
    else:
        plan = resolve_plan(names, main, pr, red, mf.SUITES, mf.select_mutants)
        suite_defs = pr
    shards = assign_shards(plan)
    graded = {}
    suites = {}
    known_suites = set(mf.SUITES)
    for mid in plan:
        suite = suite_defs.suite(mid)
        if suite not in known_suites:  # plan-suite-assert
            raise md.DefsError("suite")
        suites[mid] = suite
        graded[mid] = md.grade_exp(mid, main, pr, main.masked) if mid in pr.M else list(mutate.M[mid][4])
    payload = {
        "ids": plan,
        "shards": {str(index): group for index, group in enumerate(shards)},
        "exp": graded,
        "suite": suites,
        "main_sha": main_sha,
        "selector": selector_hash(repo),
        "skip": not plan,
        "full_plan": os.environ.get("PLAN_ALL") == "1",
        "red_counts": mf.RED_COUNTS,
    }
    out_dir = os.environ.get("PLAN_DIR") or os.path.join(repo, ".plan")
    os.makedirs(out_dir, exist_ok=True)
    if plan:
        tree = os.path.join(out_dir, "tree")
        if os.path.isdir(tree):
            subprocess.run(["rm", "-rf", tree], check=False)
        materialize_tree(repo, sha, tree)
        hashes = {}
        for index, group in enumerate(shards):
            tar_path = os.path.join(out_dir, "tree-%d.tar.gz" % index)
            pack_shard(tree, group, pr, tar_path)
            hashes[str(index)] = sha256_file(tar_path)
        payload["sha256"] = hashes
    else:
        payload["sha256"] = {}
    import base64
    blob = json.dumps(payload, sort_keys=True)
    open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8").write(blob)
    emit_output("plan_b64", base64.b64encode(blob.encode("utf-8")).decode("ascii"))
    emit_output("matrix", json.dumps({"k": list(payload["shards"])}))
    emit_output("skip", "true" if payload["skip"] else "false")
    emit_output("main_sha", main_sha)
    emit_output("selector", payload["selector"])
    return 0


def union_needs(suites, table=None):
    """Union of requirements for these suites. Unknown rows fail closed."""
    table = SUITE_NEEDS if table is None else table
    if set(table) != set(mf.SUITES):
        raise ShardError("prereq")
    needed = set()
    for suite in suites:
        if suite not in table:
            raise ShardError("prereq")
        needed |= set(table[suite])
    return needed


def _affected(suites, ids_by_suite, requirement):
    names = [suite for suite in suites if requirement in SUITE_NEEDS.get(suite, ())]
    ids = []
    for suite in names:
        ids.extend(ids_by_suite.get(suite, []))
    return names, ids


def allowlisted_env(extra=None):
    """Clean child environment. Not a copy of the parent process environment."""
    env = {
        "HOME": os.environ.get("HOME", ""),
        "PATH": os.environ.get("PATH", ""),
        "USER": os.environ.get("USER", "runner"),
        "LOGNAME": os.environ.get("LOGNAME") or os.environ.get("USER", "runner"),
        "SHELL": os.environ.get("SHELL", "/bin/bash"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "KEEL_CI": "1",
    }
    if os.environ.get("DOCKER_HOST"):
        env["DOCKER_HOST"] = os.environ["DOCKER_HOST"]
    if extra:
        for key in ("NODE_PATH", "KEEL_PI_BIN"):
            if extra.get(key):
                env[key] = extra[key]
    return env


def suite_forward_from_env():
    found = {}
    for key in ("NODE_PATH", "KEEL_PI_BIN"):
        if os.environ.get(key):
            found[key] = os.environ[key]
    return found


def _pi_dir(home):
    return os.path.join(home, ".cache", "keel", "pi-" + PI_VERSION)


def _gitleaks_bin(home):
    return os.path.join(home, ".cache", "keel", "gitleaks-" + GITLEAKS_VERSION, "gitleaks")


def _pi_host_script(home):
    path = os.path.join(
        _pi_dir(home),
        "node_modules",
        "@mariozechner",
        "pi-coding-agent",
        "package.json",
    )
    return (
        "try{"
        "const p=JSON.parse(require('fs').readFileSync("
        + json.dumps(path)
        + ",'utf8'));"
        "if(p===null||typeof p!=='object'||Array.isArray(p)||typeof p.version!=='string')process.exit(3);"
        "if(p.version!=="
        + json.dumps(PI_VERSION)
        + ")process.exit(1);"
        "}catch(e){process.exit(3)}"
    )


def _pi_image_script():
    return (
        "const p=require('/usr/local/lib/node_modules/@mariozechner/pi-coding-agent/package.json');"
        "if(p.version!=='%s')process.exit(1)" % PI_VERSION
    )


def _docker_build(tag, docker_dir):
    return [
        "docker", "build", "-q", "-t", tag,
        "-f", os.path.join(docker_dir, tag + ".Dockerfile"),
        docker_dir,
    ]


def provision_commands(baseline, needed, home, pi_present=False):
    """Ordered provisioning commands. Paths are rooted at the validated baseline."""
    base = os.path.abspath(baseline)
    docker_dir = os.path.join(base, "setup", "docker")
    cmds = []
    if "docker" in needed:
        cmds.append(["docker", "info"])
    if "gitleaks" in needed:
        cmds.append(["bash", os.path.join(base, "setup", "gitleaks-install.sh")])
        cmds.append([_gitleaks_bin(home), "version"])
    for requirement, tag in _IMAGE_FILES:
        if requirement not in needed:
            continue
        cmds.append(_docker_build(tag, docker_dir))
        cmds.append(["docker", "image", "inspect", tag])
        if tag == "keel-pi":
            cmds.append([
                "docker", "run", "--rm", "--network", "none",
                "--entrypoint", "node", "keel-pi", "-e", _pi_image_script(),
            ])
    if "host_pi" in needed:
        cmds.append(["node", "--version"])
        cmds.append(["npm", "--version"])
        if not pi_present:
            cmds.append([
                "npm", "install", "--prefix", _pi_dir(home), "--silent", PI_PACKAGE,
            ])
        cmds.append(["node", "-e", _pi_host_script(home)])
    return cmds


def command_requirement(argv):
    if argv[:2] == ["docker", "info"]:
        return "docker"
    if argv[:1] == ["bash"] and argv[-1].endswith("gitleaks-install.sh"):
        return "gitleaks"
    if len(argv) >= 2 and argv[1] == "version" and "gitleaks" in os.path.basename(argv[0]):
        return "gitleaks"
    if argv[:3] == ["docker", "build", "-q"] or argv[:3] == ["docker", "image", "inspect"]:
        blob = " ".join(argv)
        if "keel-proxy" in blob:
            return "image_proxy"
        if "keel-pi" in blob:
            return "image_pi"
        if "keel-git" in blob:
            return "image_git"
    if argv[:2] == ["docker", "run"]:
        return "image_pi"
    if argv[:1] in (["node"], ["npm"]):
        return "host_pi"
    return "prereq"


def _category_for(argv, code):
    requirement = command_requirement(argv)
    if requirement == "docker":
        return "docker_missing" if code == 127 else "docker_daemon"
    if requirement == "gitleaks":
        if argv[:1] == ["bash"]:
            return "gitleaks_install"
        return "gitleaks_version"
    if requirement == "image_git" or requirement == "image_proxy" or requirement == "image_pi":
        if argv[:2] == ["docker", "run"]:
            return "image_version"
        if argv[:3] == ["docker", "image", "inspect"]:
            return "image_missing"
        return "image_build"
    if requirement == "host_pi":
        if argv[:1] == ["node"] and code == 127:
            return "node_missing"
        if argv[:1] == ["npm"] and code == 127:
            return "npm_missing"
        if argv[:1] == ["npm"]:
            return "pi_install"
        if argv[:2] == ["node", "-e"]:
            return "pi_version" if code == 1 else "pi_resolve"
        return "pi_resolve"
    return "prereq"


def _run_allowlisted(argv, env):
    try:
        proc = subprocess.run(
            argv,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=900,
            check=False,
        )
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    out = proc.stdout.decode("utf-8", "replace") if proc.stdout else ""
    return proc.returncode, out


def _require_tested_file(path, suites, ids):
    if not os.path.isfile(path):
        raise PrereqError("absent", suites, ids)


def provision_selected(baseline, suites, ids_by_suite, home=None):
    """Install only the selected suites' prerequisites. Return verified pi paths."""
    if set(SUITE_NEEDS) != set(mf.SUITES):
        raise PrereqError("map", list(suites), [])
    needed = union_needs(suites)
    if not needed:
        return {}
    home = home or os.environ.get("HOME") or ""
    base = os.path.abspath(baseline)
    if "gitleaks" in needed:
        names, ids = _affected(suites, ids_by_suite, "gitleaks")
        _require_tested_file(os.path.join(base, "setup", "gitleaks-install.sh"), names, ids)
    for requirement, tag in _IMAGE_FILES:
        if requirement not in needed:
            continue
        names, ids = _affected(suites, ids_by_suite, requirement)
        _require_tested_file(
            os.path.join(base, "setup", "docker", tag + ".Dockerfile"),
            names,
            ids,
        )
    pi_bin = os.path.join(_pi_dir(home), "node_modules", ".bin", "pi")
    pi_present = os.access(pi_bin, os.X_OK)
    verified = {}
    host_env = None
    if "host_pi" in needed:
        node_path = os.path.join(_pi_dir(home), "node_modules")
        inherited = os.environ.get("NODE_PATH") or ""
        if inherited:
            node_path = node_path + ":" + inherited
        verified = {"NODE_PATH": node_path, "KEEL_PI_BIN": pi_bin}
        host_env = allowlisted_env(verified)
    env = allowlisted_env()
    for argv in provision_commands(base, needed, home, pi_present=pi_present):
        requirement = command_requirement(argv)
        names, ids = _affected(suites, ids_by_suite, requirement)
        cmd_env = host_env if argv[:2] == ["node", "-e"] and host_env else env
        code, out = _run_allowlisted(argv, cmd_env)
        if code != 0:
            raise PrereqError(_category_for(argv, code), names, ids)
        if command_requirement(argv) == "gitleaks" and argv[-1:] == ["version"]:
            if GITLEAKS_VERSION not in out:
                raise PrereqError("gitleaks_version", names, ids)
    if "host_pi" in needed and not os.access(pi_bin, os.X_OK):
        names, ids = _affected(suites, ids_by_suite, "host_pi")
        raise PrereqError("pi_version", names, ids)
    return verified


def normalize_tag(raw):
    return _TAG_NORMALIZE.get((raw or "").strip(), "OTHER")


def _result_records(text):
    if enforce_line:
        for line in text.splitlines():
            if len(line) > MAX_LINE:
                raise ShardError("line")
    found = {}
    order = []
    for line in text.splitlines():
        match = re.match(r"^RESULT ([^:]+): (.*)$", line)
        if not match:
            continue
        name, tag = match.group(1), match.group(2)
        if name in found:
            if found[name] != tag:
                raise ShardError("conflict")
            raise ShardError("duplicate")
        found[name] = tag
        order.append((name, tag))
    return order


def _finding(kind, shard, suite, ids, reason="", red_expected=None, missing_expected=None, tags=None, extra_red_count=0):
    return {
        "kind": kind,
        "shard": str(shard),
        "suite": suite,
        "ids": list(ids),
        "reason": reason,
        "red_expected": list(red_expected or []),
        "missing_expected": list(missing_expected or []),
        "tags": list(tags or []),
        "extra_red_count": extra_red_count,
    }


def classify_baseline(shard, suite, id_exps, text, returncode=0):
    """Classify one (shard, suite) baseline. None means the baseline is usable."""
    ids = [mid for mid, _exp in id_exps]
    if isinstance(text, dict) and text.get("unreadable"):
        return _finding("missing", shard, suite, ids, reason="unreadable")
    if text is None:
        return _finding("missing", shard, suite, ids, reason="absent")
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            return _finding("unparseable", shard, suite, ids, reason="decode")
    if returncode == 124:
        return _finding("unparseable", shard, suite, ids, reason="timeout")
    if returncode not in (0, None):
        return _finding("unparseable", shard, suite, ids, reason="status")
    try:
        records = _result_records(text)
    except ShardError as err:
        reason = str(err) if str(err) in BASELINE_REASONS else "parser"
        return _finding("unparseable", shard, suite, ids, reason=reason)
    usable = [(name, tag) for name, tag in records if NAME_RE.fullmatch(name)]
    if not records or not usable:
        reason = "empty" if not records else "parser"
        return _finding("unparseable", shard, suite, ids, reason=reason)
    by_name = dict(usable)
    union = []
    for _mid, exp in id_exps:
        for name in exp:
            if name not in union:
                union.append(name)
    expected_valid = [name for name in union if NAME_RE.fullmatch(name)]
    missing = [name for name in expected_valid if name not in by_name]
    red_names = []
    tags = []
    for name in expected_valid:
        if name not in by_name:
            continue
        tag = by_name[name]
        if mutate.GREEN.match(tag.strip()):
            continue
        red_names.append(name)
        norm = normalize_tag(tag)
        if norm not in tags:
            tags.append(norm)
    extra_red = [
        name for name, tag in usable
        if name not in expected_valid and not mutate.GREEN.match(tag.strip())
    ]
    if missing:
        affected = [
            mid for mid, exp in id_exps
            if any(name in missing for name in exp)
        ] or ids
        return _finding(
            "unparseable", shard, suite, affected, reason="incomplete",
            red_expected=red_names, missing_expected=missing, tags=tags,
            extra_red_count=len(extra_red),
        )
    if red_names:
        affected = [
            mid for mid, exp in id_exps
            if any(name in red_names for name in exp)
        ]
        return _finding(
            "BAD", shard, suite, affected, red_expected=red_names, tags=tags,
            extra_red_count=len(extra_red),
        )
    return None


def _cap_list(values, pattern, limit):
    valid = [item for item in values if pattern.fullmatch(str(item))]
    shown = valid[:limit]
    return shown, len(list(values)) - len(shown), len(list(values))


def format_finding(item):
    kind = item.get("kind")
    if kind not in ("missing", "unparseable", "BAD"):
        return "baseline truncated=record"
    shard = item.get("shard") if SHARD_RE.fullmatch(str(item.get("shard") or "")) else "-"
    suite = item.get("suite") if item.get("suite") in mf.SUITES else "-"
    shown_ids, ids_omitted, ids_total = _cap_list(item.get("ids") or [], ID_RE, DIAG_LIST_MAX)
    shown_reds, reds_omitted, _reds_total = _cap_list(item.get("red_expected") or [], NAME_RE, DIAG_LIST_MAX)
    shown_missing, missing_omitted, _missing_total = _cap_list(
        item.get("missing_expected") or [], NAME_RE, DIAG_LIST_MAX
    )
    tags = [tag for tag in (item.get("tags") or []) if tag in TAG_DISPLAY][:DIAG_LIST_MAX]
    reason = item.get("reason") if item.get("reason") in BASELINE_REASONS else ""
    parts = [
        "baseline",
        "kind=%s" % kind,
        "shard=%s" % shard,
        "suite=%s" % suite,
        "ids=[%s]" % ",".join(shown_ids),
    ]
    if ids_omitted:
        parts.append("ids_omitted=%d" % ids_omitted)
        parts.append("ids_total=%d" % ids_total)
    parts.append("red_expected=[%s]" % ",".join(shown_reds))
    names_omitted = reds_omitted
    if kind == "unparseable":
        parts.append("missing_expected=[%s]" % ",".join(shown_missing))
        names_omitted += missing_omitted
    if names_omitted:
        parts.append("names_omitted=%d" % names_omitted)
    if tags:
        parts.append("tags=[%s]" % ",".join(tags))
    if reason:
        parts.append("reason=%s" % reason)
    line = " ".join(parts)
    if len(line.encode("utf-8")) > DIAG_RECORD_MAX:
        return "baseline kind=%s shard=%s suite=%s truncated=record ids_total=%d" % (
            kind, shard, suite, ids_total
        )
    return line


def render_prereq(category, suites, ids):
    if category not in PREREQ_CATEGORIES:
        category = "prereq"
    shown_suites = [suite for suite in suites if suite in mf.SUITES][:DIAG_LIST_MAX]
    suites_omitted = len(list(suites)) - len(shown_suites)
    shown_ids, ids_omitted, ids_total = _cap_list(ids, ID_RE, DIAG_LIST_MAX)
    parts = [
        "prereq",
        "category=%s" % category,
        "suites=[%s]" % ",".join(shown_suites),
        "ids=[%s]" % ",".join(shown_ids),
    ]
    if suites_omitted:
        parts.append("suites_omitted=%d" % suites_omitted)
        parts.append("suites_total=%d" % len(list(suites)))
    if ids_omitted:
        parts.append("ids_omitted=%d" % ids_omitted)
        parts.append("ids_total=%d" % ids_total)
    line = " ".join(parts)
    if len(line.encode("utf-8")) > DIAG_RECORD_MAX:
        line = "prereq category=%s truncated=record ids_total=%d" % (category, ids_total)
    return line


def bound_diagnostic_text(lines, total_records):
    kept = []
    used = 0
    for line in lines:
        raw = line
        if len(raw.encode("utf-8")) > DIAG_RECORD_MAX:
            raw = "baseline truncated=record"
        extra = len(raw.encode("utf-8")) + (1 if kept else 0)
        if len(kept) >= DIAG_RECORD_CAP or used + extra > DIAG_TOTAL_MAX:
            break
        kept.append(raw)
        used += extra
    omitted = total_records - len(kept)
    if omitted > 0:
        footer = "baseline truncated records_omitted=%d records_total=%d" % (omitted, total_records)
        if len(kept) >= DIAG_RECORD_CAP:
            kept[-1] = footer
            omitted = total_records - (DIAG_RECORD_CAP - 1)
            kept[-1] = "baseline truncated records_omitted=%d records_total=%d" % (omitted, total_records)
        else:
            kept.append(footer)
    return "\n".join(kept)


def render_findings(findings):
    lines = [format_finding(item) for item in findings]
    return bound_diagnostic_text(lines, len(findings))


def _status_finding(item):
    line = format_finding(item)
    return {"line": line}


def write_shard_status(path, payload):
    phase = payload.get("phase")
    if phase not in ("start", "provision", "baseline", "mutant", "done", "failed"):
        phase = "failed"
    safe = {"ok": bool(payload.get("ok")), "phase": phase}
    category = payload.get("category")
    if category in PREREQ_CATEGORIES:
        safe["category"] = category
    findings = payload.get("findings") or []
    if findings:
        safe["findings"] = [_status_finding(item) for item in findings[:DIAG_RECORD_CAP]]
        safe["records_total"] = len(findings)
    blob = json.dumps(safe, sort_keys=True)
    if len(blob.encode("utf-8")) > DIAG_TOTAL_MAX:
        blob = json.dumps({"ok": False, "phase": "failed", "truncated": True}, sort_keys=True)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(blob)


def read_baseline_blob(path):
    if not os.path.lexists(path) or os.path.islink(path) or not os.path.isfile(path):
        if os.path.lexists(path):
            return {"unreadable": True}
        return None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return {"unreadable": True}


def run_suite(tree, suite, namespace, forwarded=None):
    script = os.path.join(tree, "setup", "tests", "harness", suite)
    runner = "python3" if suite.endswith(".py") else "bash"
    picked = forwarded if forwarded is not None else suite_forward_from_env()
    env = allowlisted_env(picked)
    env["KEEL_NS"] = namespace
    try:
        proc = subprocess.run(
            [runner, script],
            cwd=tree,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=900,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return b"", 124
    except OSError:
        return b"", 127
    return proc.stdout or b"", proc.returncode


def safe_untar(tar_path, dest):
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            name = member.name
            if name.startswith("/") or ".." in name.split("/"):
                raise ShardError("path")
            if member.issym() or member.islnk():
                raise ShardError("symlink")
            if not member.isdir() and not member.isreg():
                raise ShardError("type")
        tar.extractall(dest, members=members)


def plan_suite(plan, mid):
    """Suite for one id from the trusted plan. No main-table fallback."""
    if not isinstance(plan, dict):
        raise ShardError("plan")
    suites = plan.get("suite")
    if not isinstance(suites, dict) or mid not in suites:  # plan-suite-key
        raise ShardError("plan")
    suite = suites[mid]
    if suite not in mf.SUITES:  # plan-suite-known
        raise ShardError("suite")
    return suite


def plan_exp(plan, mid):
    """Expected attacks for one id from the trusted plan. No main-table fallback."""
    if not isinstance(plan, dict):
        raise ShardError("plan")
    exps = plan.get("exp")
    if not isinstance(exps, dict) or mid not in exps:  # plan-exp-key
        raise ShardError("plan")
    exp = exps[mid]
    if not isinstance(exp, (list, tuple)) or not all(isinstance(item, str) for item in exp):
        raise ShardError("plan")
    return list(exp)


def _emit_prereq(status_path, err):
    text = render_prereq(err.category, err.suites, err.ids)
    print(text, file=sys.stderr)
    write_shard_status(status_path, {"ok": False, "phase": "failed", "category": err.category})


def cmd_run_shard(tar_path, expected_sha, out_dir, suites, group, expected=None):
    os.makedirs(out_dir, exist_ok=True)
    status_path = os.path.join(out_dir, "shard-status.json")
    write_shard_status(status_path, {"ok": False, "phase": "start"})
    if not isinstance(group, list) or not group:
        raise ShardError("plan")
    if not verify_sha256(tar_path, expected_sha):
        raise SystemExit("sha256")
    work = os.path.join(out_dir, "work")
    safe_untar(tar_path, work)
    baseline = os.path.abspath(os.path.join(work, "baseline"))
    ids_root = os.path.join(work, "ids")
    ids = sorted(os.listdir(ids_root), key=md.id_key) if os.path.isdir(ids_root) else []
    # An id stored in the tar that the plan suite map does not name fails closed.
    for mid in ids:
        if mid not in suites:
            raise ShardError("plan")
    # Tar ids must equal this shard group.
    if not bind_shard(list(group), ids, "success"):  # shard-bind
        raise ShardError("shard")
    for mid in group:
        if mid not in suites:
            raise ShardError("plan")
        if suites[mid] not in mf.SUITES:
            raise ShardError("suite")
    if expected is None:
        expected = {mid: [] for mid in group}
    for mid in group:
        if mid not in expected:
            raise ShardError("plan")
        exp = expected[mid]
        if not isinstance(exp, (list, tuple)) or not all(isinstance(item, str) for item in exp):
            raise ShardError("plan")
    selected = []
    ids_by_suite = {}
    for mid in group:
        suite = suites[mid]
        if suite not in ids_by_suite:
            selected.append(suite)
        ids_by_suite.setdefault(suite, []).append(mid)
    try:
        verified = provision_selected(baseline, selected, ids_by_suite)
    except PrereqError as err:
        _emit_prereq(status_path, err)
        return 1
    forward = suite_forward_from_env()
    if verified:
        forward.update(verified)
    write_shard_status(status_path, {"ok": False, "phase": "baseline"})
    shard_key = os.environ.get("K") or "0"
    findings = []
    for suite in selected:
        stdout, code = run_suite(baseline, suite, "base", forward)
        open(os.path.join(out_dir, "baseline-" + suite), "wb").write(stdout or b"")
        pairs = [(mid, list(expected.get(mid) or [])) for mid in ids_by_suite[suite]]
        finding = classify_baseline(shard_key, suite, pairs, stdout, code)
        if finding and check_baseline:
            findings.append(finding)
    if findings:
        rendered = render_findings(findings)
        if rendered:
            print(rendered, file=sys.stderr)
        write_shard_status(status_path, {"ok": False, "phase": "failed", "findings": findings})
        return 1
    for mid in group:
        suite = suites[mid]
        parent = tempfile.mkdtemp(prefix="id-")
        dest = os.path.join(parent, "tree")
        subprocess.check_call(["cp", "-a", baseline, dest])
        overlay = os.path.join(ids_root, mid)
        for dirpath, _dirs, files in os.walk(overlay):
            for name in files:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, overlay)
                target = os.path.join(dest, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(full, target)
        stdout, code = run_suite(dest, suite, mid, forward)
        open(os.path.join(out_dir, mid + ".txt"), "wb").write(stdout or b"")
        subprocess.run(["rm", "-rf", parent], check=False)
        if code == 124:
            print("failure category=timeout", file=sys.stderr)
            write_shard_status(status_path, {"ok": False, "phase": "failed", "category": "timeout"})
            return 1
    write_shard_status(status_path, {"ok": True, "phase": "done"})
    return 0


def _github_json(url, token):
    import urllib.request
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "rudax-keel-mutants",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json_loads(resp.read().decode("utf-8"))


def json_loads(text):
    import json
    return json.loads(text)


def _safe_shard_key(key):
    return key if SHARD_RE.fullmatch(str(key)) else "-"


def _failure_state(plan):
    state = {
        "mode": "run",
        "full_plan": bool(plan.get("full_plan")),
        "green_all": False,
        "bootstrap_overdue": False,
        "head_sha": os.environ.get("HEAD_SHA") or "",
    }
    out = os.environ.get("STATE_PATH") or "state.json"
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(state, handle)


def _baseline_findings(plan, folders):
    if not check_baseline:
        return []
    findings = []
    for key, group in plan["shards"].items():
        if not isinstance(group, list):
            raise ShardError("plan")
        folder = folders.get(key) or ""
        by_suite = {}
        for mid in group:
            suite = plan_suite(plan, mid)
            exp = plan_exp(plan, mid)
            by_suite.setdefault(suite, []).append((mid, exp))
        for suite, pairs in by_suite.items():
            path = os.path.join(folder, "baseline-" + suite) if folder else ""
            blob = read_baseline_blob(path) if path else None
            finding = classify_baseline(key, suite, pairs, blob, 0)
            if finding:
                findings.append(finding)
    return findings


def cmd_aggregate():
    import base64
    plan = json.loads(base64.b64decode(os.environ["PLAN_B64"]))
    shard_result = os.environ.get("SHARD_RESULT") or "success"
    # plan_b64 is resolve-plan's job output. A skipped shard is success only
    # when that trusted output says the plan itself is a skip.
    if shard_result == "skipped":
        if skipped_shard_ok(shard_result, plan.get("skip")):
            return 0
        print("shard skipped without a skip plan", file=sys.stderr)
        return 1
    if plan.get("skip"):
        return 0
    known_results = frozenset(("success", "failure", "cancelled", "timed_out", "skipped"))
    shown_result = shard_result if shard_result in known_results else "failure"
    failed = False
    notes = []
    if not result_ok(shard_result):
        failed = True
        notes.append("shard result %s" % shown_result)
    if main_moved(os.environ.get("SELECTOR") or "", selector_hash(os.getcwd())):
        failed = True
        notes.append("selector files moved")
    token = os.environ.get("GH_TOKEN") or ""
    repo = os.environ.get("REPO") or ""
    run_id = os.environ.get("RUN_ID") or ""
    raw_dirs = {}
    if token and repo and run_id:
        try:
            listed = _github_json(
                "https://api.github.com/repos/%s/actions/runs/%s/artifacts?per_page=100" % (repo, run_id),
                token,
            )
            artifacts = listed.get("artifacts") or []
            names = [item["name"] for item in artifacts]
            if not artifact_names_ok(names, list(plan["shards"])):
                failed = True
                notes.append("artifact name rejected")
                artifacts = []
            else:
                missing_raw = [
                    key for key in plan["shards"]
                    if ("raw-%s" % key) not in names
                ]
                if missing_raw:
                    failed = True
                    notes.append("failure category=incomplete")
            for item in artifacts:
                # tree-* is the shard input. The aggregate never reads that content.
                if item["name"].startswith("tree-") or not item["name"].startswith("raw-"):
                    continue
                if not artifact_names_ok([item["name"]], list(plan["shards"])):
                    continue
                try:
                    blob_resp = _github_bytes(item["archive_download_url"], token)
                    dest = os.path.join(os.environ.get("RAW_DIR") or "raw", item["name"])
                    safe_extract(blob_resp, dest)
                    raw_dirs[item["name"][4:]] = dest
                except Exception:
                    failed = True
                    notes.append("failure category=transport")
        except Exception:
            failed = True
            notes.append("failure category=transport")
    folders = {}
    for key in plan["shards"]:
        folders[key] = raw_dirs.get(key) or os.path.join(os.environ.get("RAW_DIR") or "raw", "raw-" + key)
    findings = _baseline_findings(plan, folders)
    rendered = render_findings(findings)
    if rendered:
        print(rendered, file=sys.stderr)
        failed = True
    for note in notes:
        print(note, file=sys.stderr)
    failures = []
    graded = []
    for key, group in plan["shards"].items():
        folder = folders[key]
        seen = []
        for mid in group:
            path = os.path.join(folder, mid + ".txt")
            if os.path.isfile(path) and not os.path.islink(path):
                seen.append(mid)
        if not bind_shard(group, seen, "success"):
            print("shard %s binding" % _safe_shard_key(key), file=sys.stderr)
            failed = True
            continue
        if failed:
            continue
        for mid in group:
            # A missing or unknown plan suite fails closed before this id is graded.
            plan_suite(plan, mid)
            exp = plan_exp(plan, mid)
            stdout = open(os.path.join(folder, mid + ".txt"), encoding="utf-8").read()
            tag, _detail = grade_stdout(exp, stdout)
            graded.append(mid)
            if tag_fails(tag):
                failures.append(mid)
    if failed:
        _failure_state(plan)
        return 1
    if set(graded) != set(plan["ids"]):
        _failure_state(plan)
        return 1
    state_mod = _load_state()
    blocking = state_mod.blocking_ids(failures, plan.get("red_counts") or mf.RED_COUNTS, mf.CI_IDS, mf.OFFLINE_IDS)
    overdue = False
    if plan.get("full_plan") and failures and token and repo:
        try:
            runs = [state_mod.normalize_run(item) for item in state_mod.fetch_runs(repo, token)]
            branch = os.environ.get("DEFAULT_BRANCH") or "main"
            overdue = state_mod.bootstrap_overdue(runs, {}, branch, mf.BOOTSTRAP_FULL_RUNS)
        except Exception:
            overdue = False
    state = {
        "mode": "run",
        "full_plan": bool(plan.get("full_plan")),
        "green_all": not failures and bool(plan.get("full_plan")),
        "bootstrap_overdue": overdue,
        "head_sha": os.environ.get("HEAD_SHA") or "",
    }
    out = os.environ.get("STATE_PATH") or "state.json"
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    if plan.get("full_plan"):
        print("bootstrap-overdue: does not feed red state")
    if state["bootstrap_overdue"]:
        print("bootstrap overdue")
    return 1 if blocking else 0


def _request_host(url):
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def _auth_header(name):
    lowered = name.lower()
    return lowered == "authorization" or lowered.endswith("-authorization") or lowered == "cookie"


class NoForeignAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Drop auth headers when a redirect leaves the original host.

    An artifact zip redirects to signed storage. That host rejects a
    forwarded Authorization header.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        if _request_host(req.full_url) != _request_host(newurl):
            for key in list(new.headers):
                if _auth_header(key):  # redirect-auth
                    new.remove_header(key)
        return new


def github_bytes(url, token, timeout=60):
    """Download one GitHub URL. Auth is removed when a redirect changes host."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "rudax-keel-mutants",
        },
    )
    opener = urllib.request.build_opener(NoForeignAuthRedirect)
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def _github_bytes(url, token):
    return github_bytes(url, token)


def main(argv):
    if argv[1:2] == ["--self-test"]:
        err = self_test()
        if err:
            print(err, file=sys.stderr)
            return 1
        print("mutate shards: self-test holds")
        return 0
    if argv[1:2] == ["run-shard"]:
        import base64
        import json
        out_dir = os.environ.get("RAW_DIR") or "raw"
        os.makedirs(out_dir, exist_ok=True)
        write_shard_status(os.path.join(out_dir, "shard-status.json"), {"ok": False, "phase": "start"})
        blob = os.environ.get("PLAN_B64") or ""
        key = os.environ.get("K")
        if not blob or not key:
            raise ShardError("plan")
        try:
            plan = json.loads(base64.b64decode(blob))
        except Exception as err:
            raise ShardError("plan") from err
        if not isinstance(plan, dict):
            raise ShardError("plan")
        shards = plan.get("shards")
        if not isinstance(shards, dict) or key not in shards:
            raise ShardError("plan")
        group = shards[key]
        if not isinstance(group, list) or not group:
            raise ShardError("plan")
        suites = {}
        expected = {}
        for mid in group:
            suites[mid] = plan_suite(plan, mid)
            expected[mid] = plan_exp(plan, mid)
        return cmd_run_shard(
            os.environ["TAR"],
            os.environ["SHA256"],
            os.environ.get("RAW_DIR") or "raw",
            suites,
            group,
            expected,
        )
    if argv[1:2] == ["aggregate"]:
        return cmd_aggregate()
    if argv[1:2] == ["resolve"]:
        repo = os.environ.get("REPO_ROOT") or os.getcwd()
        sha = os.environ.get("SHA") or ""
        base_ref = os.environ.get("BASE_REF") or "origin/main"
        if not sha:
            print("missing SHA", file=sys.stderr)
            return 2
        return cmd_resolve(repo, sha, base_ref)
    print("usage: mutate_shards.py --self-test | resolve", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
