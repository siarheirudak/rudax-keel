#!/usr/bin/env python3
"""Happy and attack cases for mutant selection, grading, and full-run state."""
import base64
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mutate
import mutant_defs as md
import mutant_files as mf
import mutate_shards as ms

ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
SELECT_CASES = (
    "S-H1", "S-H2", "S-H3", "S-H4", "S-H6", "S-H7", "S-H7b", "S-H8", "S-H9",
    "S-A1", "S-A2", "S-A3", "S-A4", "S-A7", "S-A8", "S-A9", "S-A10", "S-A11",
    "S-A12", "S-A13", "S-A15", "S-A16", "S-A17", "S-A18", "S-A20", "S-A21",
    "S-A22", "S-A23", "S-A27", "S-A32", "S-A33",
)
SHARD_CASES = (
    "S-H5", "S-A5", "S-A6", "S-A14", "S-A19", "S-A24", "S-A25", "S-A26",
    "S-A28", "S-A29", "S-A30", "S-A31", "S-A34", "S-A35", "S-A36",
    "H1", "H2", "H3", "H4",
    "A1", "A2", "A3", "A4", "A5", "A6",
)


def state_mod():
    path = os.path.join(HERE, "mutate-full-state.py")
    spec = importlib.util.spec_from_file_location("mutate_full_state", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def mini(ids, exp=None):
    table = {}
    suites = {}
    for mid in ids:
        table[mid] = ("keel.sh", "old-" + mid, "new-" + mid, "what", list(exp or ["A1"]))
        suites[mid] = "test-attacks.sh"
    return md.Defs({
        "M": table,
        "SUITE_OF": suites,
        "EXTRA_EDITS": {},
        "COPY_LIST": ["keel.sh"],
        "CI_IDS": list(ids),
        "OFFLINE_IDS": [],
        "FULL_ONLY": [],
        "EXPECTED_MASKED": {},
    })


def _run(branch="main"):
    return {
        "id": 1,
        "path": ".github/workflows/mutate-full.yml",
        "event": "schedule",
        "status": "completed",
        "conclusion": "failure",
        "head_branch": branch,
        "head_sha": "a" * 40,
        "job_name": "mutants",
    }


def case_s_h1():
    main = mini(["M01"])
    fresh = ["M201", "M202", "M203", "M204", "M205", "M206"]
    pr = mini(["M01"] + fresh)
    found = md.new_ids(main.ids, pr.ids)
    plan = md.build_plan([], found, [], False, sorted(pr.ids, key=md.id_key))
    return found == set(fresh) and plan == sorted(fresh, key=md.id_key)


def case_s_h2():
    status, ids = mf.select_mutants(["setup/keel.sh"])
    return status == "some" and "M03" in ids and "M51" not in ids


def case_s_h3():
    _status, ids = mf.select_mutants(["setup/lib/visibility.py"])
    return "M45" in ids and "M94" in ids


def case_s_h4():
    return mf.select_mutants(["docs/status.md"]) == ("skip", [])


def case_s_h5():
    ids = ["M%02d" % n for n in range(1, 14)]
    shards = ms.assign_shards(ids, 4)
    flat = [mid for group in shards for mid in group]
    return (
        len(shards) == 4
        and sorted(flat) == sorted(ids)
        and len(flat) == len(set(flat))
    )


def case_s_h6():
    st = state_mod()
    daily = "17 18 * * *"
    same = st.fresh_decision("schedule", daily, "abc", "abc", False) == "skip"
    moved = st.fresh_decision("schedule", daily, "abc", "def", False) == "run"
    weekly = st.fresh_decision("schedule", st.WEEKLY_CRON, "abc", "abc", False) == "run"
    return same and moved and weekly


def case_s_h7():
    st = state_mod()
    run = _run()
    plan = md.build_plan(["M03"], [], [], st.is_red([run], {}, "main"), ["M01", "M03"])
    return plan == ["M01", "M03"]


def case_s_h7b():
    st = state_mod()
    failure = _run()
    cancelled = dict(failure, id=2, conclusion="cancelled")
    return st.is_red([cancelled, failure], {}, "main") is True


def case_s_h8():
    ordered = sorted(mutate.M, key=lambda mid: int(mid[1:]))
    listed = mf.CI_IDS + mf.OFFLINE_IDS + mf.FULL_ONLY
    masked = mutate.verdict_tag([], []) == "masked (expected)"
    return ordered == sorted(listed, key=lambda mid: int(mid[1:])) and masked


def case_s_h9():
    st = state_mod()
    quiet = st.run_should_fail(["M02"], "ci+offline", mf.CI_IDS, mf.OFFLINE_IDS, True) is False
    loud = st.run_should_fail(["M02"], "all", mf.CI_IDS, mf.OFFLINE_IDS, False) is True
    return quiet and loud


def case_s_a1():
    _status, ids = mf.select_mutants(["setup/keel.sh"])
    return "M03" in ids


def case_s_a2():
    samples = [
        "M = {name: 1}\n",
        "M = dict(a=1)\n",
        "M = {}\nM = {}\n",
        "K = 'keel.sh'\nM = {'M01': (evil, 'a', 'b', 'c', [])}\n",
    ]
    for sample in samples:
        try:
            md.parse_literals(sample)
        except md.DefsError:
            continue
        return False
    return True


def case_s_a3():
    main = mini(["M01"])
    pr = mini(["M01"])
    pr.M["M01"] = ("keel.sh", "old-M01", "noop", "what", ["A1"])
    modified = md.modified_ids(main, pr)
    plan = md.build_plan([], [], modified, False, ["M01"])
    return modified == {"M01"} and plan == ["M01"]


def case_s_a4():
    return md.removed_ids(["M01", "M02"], ["M01"]) == ["M02"]


def case_s_a5():
    missing = ms.bind_shard(["M01", "M02"], ["M01"], "success")
    duplicate = ms.bind_shard(["M01"], ["M01", "M01"], "success")
    foreign = ms.bind_shard(["M01"], ["M01", "M02"], "success")
    return missing is False and duplicate is False and foreign is False


def case_s_a6():
    failed = ms.bind_shard(["M01"], ["M01"], "failure")
    cancelled = ms.bind_shard(["M01"], ["M01"], "cancelled")
    return failed is False and cancelled is False


def case_s_a7():
    return mf.select_mutants(["setup/lib/new_helper.py"]) == ("full", list(mf.CI_IDS))


def case_s_a8():
    found = mf.scan_text("setup/lib/egress_proxy.py", "import egress\nimport visibility\n")
    missing = found != ("setup/lib/egress.py",)
    dynamic = mf.scan_text("setup/lib/egress.py", "import importlib\nimportlib.import_module('z')\n")
    live = True
    if os.path.isfile(os.path.join(mf._repo_root(), "setup", "keel.sh")):
        live = mf.scan_repo() == {key: tuple(value) for key, value in mf.DEPENDS.items()}
    return missing and dynamic is None and live


def case_s_a9():
    defs = md.load_mutate(open(os.path.join(HERE, "mutate.py"), encoding="utf-8").read())
    clean = md.duplicate_errors(defs, md.FROZEN_DUPLICATES) == []
    grown = md.FROZEN_DUPLICATES + (("M01", "M02"),)
    dirty = md.duplicate_errors(defs, grown) == ["known list"]
    return clean and dirty


def case_s_a10():
    absent = md.meta_errors({}, ["M139"], lambda _mid: "")
    twice = md.meta_errors({"M139": ("plan-forced", "mechanism")}, ["M139"], lambda _mid: "plan-forced plan-forced")
    real = md.meta_errors(mf.META, list(mutate.M), _meta_text)
    return "M139" in absent and "M139" in twice and real == []


def _strip_catalogue(text):
    kept = []
    skip = False
    for line in text.splitlines(True):
        if line.startswith("META ="):
            skip = True
        if skip:
            if line.startswith("}"):
                skip = False
            continue
        kept.append(line)
    return "".join(kept)


def _meta_text(mid):
    pieces = []
    for rel in mf.FILES[mid]:
        path = os.path.join(ROOT, rel)
        if os.path.isfile(path):
            pieces.append(_strip_catalogue(open(path, encoding="utf-8").read()))
    return pieces


def case_s_a11():
    st = state_mod()
    return st.fresh_decision("schedule", "17 18 * * *", "abc", "abc", True) == "run"


def case_s_a12():
    return md.unknown_suites({"M120": "weaker.sh"}, mf.SUITES) == ["M120"]


def case_s_a13():
    st = state_mod()
    failure = _run()
    skipped = dict(failure, id=3, conclusion="success", head_sha="c" * 40)
    states = {3: {"mode": "skip"}}
    return st.is_red([skipped, failure], states, "main") is True


def case_s_a14():
    hostile = (
        "K = 'keel.sh'\n"
        "def judge(*_a, **_k):\n    return [], {}\n"
        "M = {'M01': (K, 'a', 'b', 'c', ['A1'])}\n"
        "SUITE_OF = {'M01': 'test-attacks.sh'}\n"
        "EXTRA_EDITS = {}\n"
        "COPY_LIST = []\n"
    )
    parsed = md.load_mutate(hostile)
    tag, _detail = ms.grade_stdout(["A1"], "RESULT A1: BLOCKED\n")
    return tag == "NO" and parsed.suite("M01") == "test-attacks.sh"


def case_s_a15():
    main = mini(["M120"])
    main.suite_of["M120"] = "test-step5.sh"
    pr = mini(["M120"])
    pr.suite_of["M120"] = "test-attacks.sh"
    by_suite = md.modified_ids(main, pr) == {"M120"}
    main = mini(["M120"])
    pr = mini(["M120"])
    pr.extra["M120"] = ["M14"]
    by_extra = md.modified_ids(main, pr) == {"M120"}
    plan = md.build_plan([], [], {"M120"}, False, ["M120"])
    return by_suite and by_extra and plan == ["M120"]


def case_s_a16():
    main = mini(["M01", "M02"])
    pr = mini(["M01", "M02"])
    pr.copy = []
    return md.modified_ids(main, pr) == {"M01", "M02"}


def case_s_a17():
    st = state_mod()
    failure = _run()
    push = dict(failure, id=4, event="push", conclusion="success", head_sha="d" * 40)
    return st.is_red([push, failure], {}, "main") is True


def case_s_a18():
    return md.classification_errors(["M01", "M999"], ["M01"], [], []) == ["M999"]


def case_s_a19():
    handle = tempfile.NamedTemporaryFile(delete=False)
    handle.write(b"abc")
    handle.close()
    try:
        good = ms.verify_sha256(handle.name, ms.sha256_file(handle.name))
        bad = ms.verify_sha256(handle.name, "0" * 64)
    finally:
        os.unlink(handle.name)
    return good and not bad


def case_s_a20():
    main = mini(["M01"])
    pr = mini(["M01"])
    pr.M["M01"] = ("keel.sh", "old-M01", "new-M01", "what", [])
    try:
        md.grade_exp("M01", main, pr, {})
    except md.DefsError:
        return True
    return False


def case_s_a21():
    main = mini(["M01"])
    pr = mini(["M01", "M201"])
    pr.M["M201"] = ("keel.sh", "a", "b", "what", [])
    try:
        md.grade_exp("M201", main, pr, {})
    except md.DefsError:
        return True
    return False


def case_s_a22():
    main = mini(["M01"], ["A1", "A2"])
    pr = mini(["M01"], ["A1"])
    try:
        md.grade_exp("M01", main, pr, {})
    except md.DefsError:
        return True
    return False


def case_s_a23():
    main = mini(["M01"])
    pr = mini(["M01", "M999"])
    pr.ci = ["M01"]
    errors = md.coverage_errors(main, pr, mf.SUITES, {})
    return "M999" in errors


def case_s_a24():
    return (
        ms.artifact_names_ok(["plan", "raw-0", "evil"], ["0"]) is False
        and ms.artifact_names_ok(["raw-9"], ["0"]) is False
    )


def case_s_a25():
    path = ms.zip_violations([{"name": "../x", "mode": "file", "size": 1}])
    absolute = ms.zip_violations([{"name": "/tmp/x", "mode": "file", "size": 1}])
    link = ms.zip_violations([{"name": "a", "mode": "symlink", "size": 1}])
    size = ms.zip_violations([{"name": "a", "mode": "file", "size": ms.MAX_FILE_BYTES + 1}])
    try:
        ms.parse_result_text("x" * (ms.MAX_LINE + 1))
        line = False
    except ms.ShardError:
        line = True
    return "path" in path and "path" in absolute and "symlink" in link and "size" in size and line


def case_s_a26():
    return ms.main_moved("before", "after") is True and ms.main_moved("same", "same") is False


def case_s_a27():
    st = state_mod()
    run = dict(_run(), conclusion="success", job_name="mutants")
    missing = st.is_real_green(run, None, "main")
    skipped = st.is_real_green(run, {"mode": "skip"}, "main")
    return missing is False and skipped is False


def case_s_a28():
    needle = "    timeout-minutes: 45 # shard-timeout"
    for rel in (".github/workflows/mutate-pr.yml", ".github/workflows/mutate-full.yml"):
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        if text.count(needle) != 1:
            return False
        if "actions/cache" in text:
            return False
    return True


def case_s_a29():
    if ms.accept_entry("120000", "abc", "abc"):
        return False
    if ms.accept_entry("160000", "abc", "abc"):
        return False
    if ms.accept_entry("100644", "abc", "def"):
        return False
    repo = tempfile.mkdtemp(prefix="tree-")
    dest = tempfile.mkdtemp(prefix="out-")
    try:
        subprocess.check_call(["git", "init", "-q"], cwd=repo)
        subprocess.check_call(["git", "-C", repo, "config", "user.email", "t@x"])
        subprocess.check_call(["git", "-C", repo, "config", "user.name", "t"])
        os.makedirs(os.path.join(repo, "setup"))
        payload = "hello $Format:%H$\n"
        open(os.path.join(repo, "setup", "keel.sh"), "w", encoding="utf-8").write(payload)
        open(os.path.join(repo, ".gitattributes"), "w", encoding="utf-8").write(
            "setup/keel.sh export-ignore\nsetup/keel.sh export-subst\n"
        )
        subprocess.check_call(["git", "-C", repo, "add", ".gitattributes", "setup/keel.sh"])
        subprocess.check_call(["git", "-C", repo, "commit", "-qm", "base"])
        sha = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
        ms.materialize_tree(repo, sha, dest)
        got = open(os.path.join(dest, "setup", "keel.sh"), encoding="utf-8").read()
        if got != payload:
            return False
        os.symlink("keel.sh", os.path.join(repo, "setup", "link.sh"))
        subprocess.check_call(["git", "-C", repo, "add", "setup/link.sh"])
        subprocess.check_call(["git", "-C", repo, "commit", "-qm", "link"])
        sha = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
        linked = tempfile.mkdtemp(prefix="link-")
        try:
            ms.materialize_tree(repo, sha, linked)
        except ms.ShardError:
            return True
        return False
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)


def case_s_a30():
    bad, missing = ms.baseline_bad_ids(
        ["M01", "M02"],
        {"M01": "suite", "M02": "suite"},
        {"M01": ["A1"], "M02": ["A2"]},
        {"suite": "RESULT A1: NOT BLOCKED\nRESULT A2: BLOCKED\n"},
    )
    return bad == ["M01"] and missing is False


def case_s_a31():
    _bad, missing = ms.baseline_bad_ids(
        ["M01"],
        {"M01": "suite"},
        {"M01": ["A1"]},
        {},
    )
    return missing is True


def case_s_a32():
    return md.counts_used(mf.RED_COUNTS, "all") == "ci+offline" and md.counts_used("ci+offline", "all") == "ci+offline"


def case_s_a33():
    st = state_mod()
    run = dict(_run(), conclusion="success")
    expired = st.is_real_green(run, {"expired": True, "mode": "run", "full_plan": True, "green_all": True}, "main")
    mode = st.fresh_decision("schedule", "17 18 * * *", "abc", None, False)
    return expired is False and mode == "run"


def case_s_a34():
    return ms.result_ok("timed_out") is False and ms.bind_shard(["M01"], ["M01"], "timed_out") is False


def _workflow_jobs(text):
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == "jobs:":
            start = index + 1
            break
    if start is None:
        return {}
    jobs = {}
    name = None
    buf = []
    for line in lines[start:]:
        if (
            line.startswith("  ")
            and not line.startswith("   ")
            and line.rstrip().endswith(":")
            and not line.strip().startswith("#")
        ):
            if name is not None:
                jobs[name] = "\n".join(buf)
            name = line.strip()[:-1]
            buf = [line]
        elif name is not None:
            buf.append(line)
    if name is not None:
        jobs[name] = "\n".join(buf)
    return jobs


def _permission_map(job):
    """Return the shard permission map, or None when the block is missing."""
    lines = job.splitlines()
    for index, line in enumerate(lines):
        code = line.split("#", 1)[0].strip()
        if code == "permissions: write-all":
            return {"write-all": "write-all"}
        if code != "permissions:":
            continue
        base = len(line) - len(line.lstrip(" "))
        found = {}
        for nxt in lines[index + 1:]:
            if not nxt.strip() or nxt.strip().startswith("#"):
                continue
            indent = len(nxt) - len(nxt.lstrip(" "))
            if indent <= base:
                break
            body = nxt.split("#", 1)[0].strip()
            if ":" not in body:
                return {"bad": "bad"}
            key, value = body.split(":", 1)
            found[key.strip()] = value.strip().strip("\"'")
        return found
    return None


def _other_job_fetches_tree(name, job):
    if name == "shard":
        return False
    if "run-shard" in job:
        return True
    lines = job.splitlines()
    downloading = False
    for line in lines:
        stripped = line.strip()
        if "download-artifact" in line:
            downloading = True
            continue
        if not downloading:
            continue
        if stripped.startswith("name:") and "tree-" in stripped:
            return True
        if stripped.startswith("- "):
            downloading = "download-artifact" in line
    return False


def _clean_entries(job):
    """Lines inside the shard job's run-shard clean=(...) list."""
    entries = []
    capture = False
    for line in job.splitlines():
        stripped = line.strip()
        if stripped.startswith("clean=("):
            capture = True
            continue
        if not capture:
            continue
        if stripped == ")":
            break
        entries.append(stripped)
    return entries


def case_s_a35():
    for rel in (".github/workflows/mutate-pr.yml", ".github/workflows/mutate-full.yml"):
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        jobs = _workflow_jobs(text)
        shard = jobs.get("shard")
        if shard is None:
            return False
        if _permission_map(shard) != {"contents": "read"}:
            return False
        if "run-shard" not in shard:
            return False
        clean = _clean_entries(shard)
        if not any("PLAN_B64=" in item for item in clean):
            return False
        if '"K=$K"' not in clean:
            return False
        for name, job in jobs.items():
            if _other_job_fetches_tree(name, job):
                return False
    return True


def _redirected_request(old, new, headers):
    import urllib.request
    req = urllib.request.Request(old, headers=dict(headers), method="GET")
    return ms.NoForeignAuthRedirect().redirect_request(req, None, 302, "Found", {}, new)


def case_s_a36():
    """Auth stays on api.github.com and is dropped on a storage redirect."""
    import urllib.request
    headers = {
        "Authorization": "Bearer secret",
        "Proxy-Authorization": "Basic x",
        "Cookie": "session=1",
        "Accept": "application/vnd.github+json",
        "User-Agent": "rudax-keel-mutants",
    }
    origin = "https://api.github.com/repos/a/b/actions/artifacts/1/zip"
    cross = _redirected_request(origin, "https://objects.githubusercontent.com/artifact.zip", headers)
    same = _redirected_request(origin, "https://api.github.com/repos/a/b/actions/artifacts/1/zip?redirected=1", headers)
    if cross is None or same is None:
        return False
    cross_names = {key.lower() for key in cross.headers}
    if "authorization" in cross_names or "proxy-authorization" in cross_names or "cookie" in cross_names:
        return False
    if "accept" not in cross_names:
        return False
    if same.get_header("Authorization") != "Bearer secret":
        return False
    if same.get_header("Proxy-authorization") != "Basic x":
        return False
    if same.get_header("Cookie") != "session=1":
        return False
    recorded = {}
    real_open = urllib.request.OpenerDirector.open

    def fake_open(self, fullurl, data=None, timeout=None):
        recorded["handlers"] = [type(item) for item in self.handlers]
        recorded["auth"] = fullurl.get_header("Authorization") if hasattr(fullurl, "get_header") else None
        raise RuntimeError("no-network")

    urllib.request.OpenerDirector.open = fake_open
    try:
        try:
            ms.github_bytes("https://api.github.com/repos/a/b/actions/artifacts/9/zip", "sekrit")
        except RuntimeError as err:
            if str(err) != "no-network":
                return False
        else:
            return False
    finally:
        urllib.request.OpenerDirector.open = real_open
    if recorded.get("auth") != "Bearer sekrit":
        return False
    if ms.NoForeignAuthRedirect not in recorded.get("handlers", []):
        return False
    state = state_mod()
    seen = {}
    old_api = state._api_json
    old_bytes = ms.github_bytes

    def fake_api(_url, _token):
        return {
            "artifacts": [{
                "name": "state",
                "expired": False,
                "archive_download_url": "https://api.github.com/repos/o/r/actions/artifacts/9/zip",
            }],
        }

    def fake_bytes(url, token, timeout=60):
        seen["url"] = url
        seen["token"] = token
        raise RuntimeError("no-network")

    state._api_json = fake_api
    ms.github_bytes = fake_bytes
    try:
        try:
            state.fetch_one_state("o/r", "sekrit", 9)
        except RuntimeError as err:
            if str(err) != "no-network":
                return False
        else:
            return False
    finally:
        state._api_json = old_api
        ms.github_bytes = old_bytes
    return (
        seen.get("url") == "https://api.github.com/repos/o/r/actions/artifacts/9/zip"
        and seen.get("token") == "sekrit"
    )


def _push_env(updates):
    old = {}
    for key, value in updates.items():
        old[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return old


def _pop_env(old):
    for key, value in old.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _plan_b64(plan):
    return base64.b64encode(json.dumps(plan).encode("utf-8")).decode("ascii")


def _write_tar(path, files):
    """files: archive name -> bytes. Names stay inside the archive."""
    with tarfile.open(path, "w:gz") as tar:
        for name, blob in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(blob)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(blob))


def _stub_suite(line):
    return ("#!/bin/bash\nprintf '%s\\n'\n" % line).encode("utf-8")


def _shard_files(ids, script_rel, script, extra=None):
    files = {script_rel: script}
    for mid in ids:
        files["ids/%s/setup/keel.sh" % mid] = b"changed\n"
    if extra:
        files.update(extra)
    return files


_STUB_REL = "baseline/setup/tests/harness/test-mutate-shards.sh"
_STUB_LINE = "RESULT A1: NOT BLOCKED"


def _with_raw(plan, write_raw):
    """Run aggregate against a temp raw dir. Restores the process environment."""
    raw = tempfile.mkdtemp(prefix="raw-")
    cwd = os.getcwd()
    try:
        write_raw(raw)
        os.chdir(ROOT)
        old = _push_env({
            "PLAN_B64": _plan_b64(plan),
            "SHARD_RESULT": "success",
            "SELECTOR": ms.selector_hash(ROOT),
            "RAW_DIR": raw,
            "STATE_PATH": os.path.join(raw, "state.json"),
            "GH_TOKEN": None,
            "REPO": None,
            "RUN_ID": None,
            "GITHUB_OUTPUT": None,
            "HEAD_SHA": None,
        })
        try:
            return ms.cmd_aggregate()
        finally:
            _pop_env(old)
            os.chdir(cwd)
    finally:
        shutil.rmtree(raw, ignore_errors=True)


def _raw_id(folder, mid, stdout, suite, baseline):
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, mid + ".txt"), "w", encoding="utf-8").write(stdout)
    open(os.path.join(folder, "baseline-" + suite), "w", encoding="utf-8").write(baseline)


def _run_main_shard(plan, tar_path, out_dir):
    old = _push_env({
        "PLAN_B64": _plan_b64(plan),
        "K": "0",
        "TAR": tar_path,
        "SHA256": ms.sha256_file(tar_path),
        "RAW_DIR": out_dir,
        "GITHUB_OUTPUT": None,
    })
    try:
        return ms.main(["mutate_shards.py", "run-shard"])
    finally:
        _pop_env(old)


def _resolve_fixture():
    """Main defs plus a pull-request id whose suite is on the main list."""
    repo = tempfile.mkdtemp(prefix="resolve-")
    plan_dir = tempfile.mkdtemp(prefix="plan-")
    main_src = (
        "K = 'keel.sh'\n"
        "M = {'M01': ('keel.sh', 'old-M01', 'new-M01', 'what', ['A1'])}\n"
        "SUITE_OF = {'M01': 'test-attacks.sh'}\n"
        "EXTRA_EDITS = {}\n"
        "COPY_LIST = ['keel.sh']\n"
        "CI_IDS = ['M01']\n"
        "OFFLINE_IDS = []\n"
        "FULL_ONLY = []\n"
    )
    pr_src = (
        "K = 'keel.sh'\n"
        "M = {\n"
        " 'M01': ('keel.sh', 'old-M01', 'new-M01-b', 'what', ['A1']),\n"
        " 'M201': ('keel.sh', 'old-M201', 'new-M201', 'what', ['A9']),\n"
        "}\n"
        "SUITE_OF = {'M01': 'test-attacks.sh', 'M201': 'test-step6.sh'}\n"
        "EXTRA_EDITS = {}\n"
        "COPY_LIST = ['keel.sh']\n"
        "CI_IDS = ['M01', 'M201']\n"
        "OFFLINE_IDS = []\n"
        "FULL_ONLY = []\n"
    )
    try:
        subprocess.check_call(["git", "init", "-q", "-b", "main"], cwd=repo)
        subprocess.check_call(["git", "-C", repo, "config", "user.email", "t@x"])
        subprocess.check_call(["git", "-C", repo, "config", "user.name", "t"])
        subprocess.check_call(["git", "-C", repo, "config", "commit.gpgsign", "false"])
        harness = os.path.join(repo, "setup", "tests", "harness")
        os.makedirs(harness)
        open(os.path.join(repo, "setup", "keel.sh"), "w", encoding="utf-8").write("old-M01\nold-M201\n")
        for name in (
            "mutant_files.py",
            "mutant_defs.py",
            "mutate_shards.py",
            "mutate-full-state.py",
        ):
            open(os.path.join(harness, name), "w", encoding="utf-8").write("\n")
        open(os.path.join(harness, "mutate.py"), "w", encoding="utf-8").write(main_src)
        subprocess.check_call(["git", "-C", repo, "add", "."])
        subprocess.check_call(["git", "-C", repo, "commit", "-qm", "base"])
        subprocess.check_call(["git", "-C", repo, "checkout", "-q", "-b", "pr"])
        open(os.path.join(harness, "mutate.py"), "w", encoding="utf-8").write(pr_src)
        subprocess.check_call(["git", "-C", repo, "add", "setup/tests/harness/mutate.py"])
        subprocess.check_call(["git", "-C", repo, "commit", "-qm", "pr"])
        pr_sha = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
        subprocess.check_call(["git", "-C", repo, "checkout", "-q", "main"])
        output = os.path.join(plan_dir, "github_output")
        open(output, "w", encoding="utf-8").close()
        old = _push_env({
            "PLAN_DIR": plan_dir,
            "PLAN_ALL": None,
            "GH_TOKEN": None,
            "REPO": None,
            "GITHUB_OUTPUT": output,
        })
        try:
            rc = ms.cmd_resolve(repo, pr_sha, "main")
        finally:
            _pop_env(old)
        payload = json.loads(open(os.path.join(plan_dir, "plan.json"), encoding="utf-8").read())
        return rc, payload
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        shutil.rmtree(plan_dir, ignore_errors=True)


def case_h1():
    rc, payload = _resolve_fixture()
    if rc != 0:
        return False
    if "M201" in mutate.M or "M201" in mutate.SUITE_OF:
        return False
    return (
        payload["suite"].get("M201") == "test-step6.sh"
        and payload["exp"].get("M201") == ["A9"]
        and "M201" in payload["ids"]
    )


def case_h2():
    if "M201" in mutate.SUITE_OF or "M201" in mutate.M:
        return False
    mid = "M201"
    suite = "test-mutate-shards.sh"
    root = tempfile.mkdtemp(prefix="h2-")
    try:
        tar_path = os.path.join(root, "tree.tar.gz")
        out_dir = os.path.join(root, "out")
        _write_tar(tar_path, _shard_files([mid], _STUB_REL, _stub_suite(_STUB_LINE)))
        plan = {
            "ids": [mid],
            "shards": {"0": [mid]},
            "suite": {mid: suite},
            "exp": {mid: ["A1"]},
            "skip": False,
        }
        if _run_main_shard(plan, tar_path, out_dir) != 0:
            return False
        got = open(os.path.join(out_dir, mid + ".txt"), encoding="utf-8").read()
        base = open(os.path.join(out_dir, "baseline-" + suite), encoding="utf-8").read()
        return _STUB_LINE in got and _STUB_LINE in base
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_h3():
    mid = "M201"
    suite = "test-mutate-shards.sh"
    if mid in mutate.M or mid in mutate.SUITE_OF:
        return False
    plan = {
        "ids": [mid],
        "shards": {"0": [mid]},
        "suite": {mid: suite},
        "exp": {mid: ["A1"]},
        "skip": False,
        "full_plan": False,
        "red_counts": "ci+offline",
    }
    seen = {}
    real = ms.grade_stdout

    def spy(exp, stdout):
        seen["exp"] = list(exp)
        return real(exp, stdout)

    ms.grade_stdout = spy
    try:
        def write(raw):
            _raw_id(
                os.path.join(raw, "raw-0"),
                mid,
                "RESULT A1: NOT BLOCKED\n",
                suite,
                "RESULT A1: BLOCKED\n",
            )

        rc = _with_raw(plan, write)
    finally:
        ms.grade_stdout = real
    graded, _detail = real(["A1"], "RESULT A1: NOT BLOCKED\n")
    return rc == 0 and seen.get("exp") == ["A1"] and graded == "yes" and ms.plan_suite(plan, mid) == suite


def case_h4():
    _rc, payload = _resolve_fixture()
    if payload["suite"].get("M01") != "test-attacks.sh":
        return False
    if payload["exp"].get("M01") != ["A1"]:
        return False
    mid = "M152"
    suite = mutate.SUITE_OF[mid]
    exp = list(mutate.M[mid][4])
    plan = {
        "ids": [mid],
        "shards": {"0": [mid]},
        "suite": {mid: suite},
        "exp": {mid: exp},
        "skip": False,
        "full_plan": False,
        "red_counts": "ci+offline",
    }
    if ms.plan_suite(plan, mid) != suite or ms.plan_exp(plan, mid) != exp:
        return False
    killed = "RESULT %s: NOT BLOCKED\n" % exp[0]
    quiet = "RESULT %s: BLOCKED\n" % exp[0]
    baseline = "RESULT %s: BLOCKED\n" % exp[0]

    def write_killed(raw):
        _raw_id(os.path.join(raw, "raw-0"), mid, killed, suite, baseline)

    def write_quiet(raw):
        _raw_id(os.path.join(raw, "raw-0"), mid, quiet, suite, baseline)

    new_killed = _with_raw(plan, write_killed)
    new_quiet = _with_raw(plan, write_quiet)
    tag_killed, _detail = ms.grade_stdout(exp, killed)
    tag_quiet, _detail = ms.grade_stdout(exp, quiet)
    old_killed = 0 if not ms.tag_fails(tag_killed) else 1
    old_quiet = 0 if not ms.tag_fails(tag_quiet) else 1
    return new_killed == old_killed == 0 and new_quiet == old_quiet == 1


def case_a1():
    main = mini(["M01"])
    pr = mini(["M01", "M201"])
    pr.suite_of["M201"] = "not-a-suite.sh"
    try:
        ms.resolve_plan([], main, pr, False, mf.SUITES, lambda _names: ("skip", []))
    except md.DefsError as err:
        text = str(err)
        return text.startswith("coverage") and "M201" in text
    return False


def case_a2():
    mid = "M201"
    suite = "evil.sh"
    plan = {
        "ids": [mid],
        "shards": {"0": [mid]},
        "suite": {mid: suite},
        "exp": {mid: ["A1"]},
        "skip": False,
        "full_plan": False,
        "red_counts": "ci+offline",
    }
    try:
        ms.plan_suite(plan, mid)
        return False
    except ms.ShardError as err:
        if str(err) != "suite":
            return False
    root = tempfile.mkdtemp(prefix="a2-")
    try:
        tar_path = os.path.join(root, "tree.tar.gz")
        out_dir = os.path.join(root, "out")
        script = "baseline/setup/tests/harness/" + suite
        _write_tar(tar_path, _shard_files([mid], script, _stub_suite(_STUB_LINE)))
        try:
            _run_main_shard(plan, tar_path, out_dir)
            return False
        except ms.ShardError as err:
            if str(err) != "suite":
                return False

        def write(raw):
            _raw_id(
                os.path.join(raw, "raw-0"),
                mid,
                "RESULT A1: NOT BLOCKED\n",
                suite,
                "RESULT A1: BLOCKED\n",
            )

        try:
            _with_raw(plan, write)
            return False
        except ms.ShardError as err:
            return str(err) == "suite"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_a3():
    mid = "M03"
    suite = mutate.SUITE_OF[mid]
    exp = list(mutate.M[mid][4])
    missing_suite = {
        "ids": [mid],
        "shards": {"0": [mid]},
        "suite": {},
        "exp": {mid: exp},
        "skip": False,
        "full_plan": False,
        "red_counts": "ci+offline",
    }
    missing_exp = {
        "ids": [mid],
        "shards": {"0": [mid]},
        "suite": {mid: suite},
        "exp": {},
        "skip": False,
        "full_plan": False,
        "red_counts": "ci+offline",
    }
    try:
        ms.plan_suite(missing_suite, mid)
        return False
    except ms.ShardError as err:
        if str(err) != "plan":
            return False
    try:
        ms.plan_exp(missing_exp, mid)
        return False
    except ms.ShardError as err:
        if str(err) != "plan":
            return False
    root = tempfile.mkdtemp(prefix="a3-")
    try:
        tar_path = os.path.join(root, "tree.tar.gz")
        out_dir = os.path.join(root, "out")
        script = "baseline/setup/tests/harness/" + suite
        line = "RESULT %s: NOT BLOCKED" % exp[0]
        _write_tar(tar_path, _shard_files([mid], script, _stub_suite(line)))
        try:
            _run_main_shard(missing_suite, tar_path, out_dir)
            return False
        except ms.ShardError as err:
            if str(err) != "plan":
                return False
        if os.path.isfile(os.path.join(out_dir, mid + ".txt")):
            return False

        def write(raw):
            _raw_id(
                os.path.join(raw, "raw-0"),
                mid,
                line + "\n",
                suite,
                "RESULT %s: BLOCKED\n" % exp[0],
            )

        try:
            rc = _with_raw(missing_exp, write)
        except ms.ShardError as err:
            return str(err) == "plan"
        return rc != 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_a4():
    keep = "M201"
    extra = "M202"
    suite = "test-mutate-shards.sh"
    root = tempfile.mkdtemp(prefix="a4-")
    try:
        tar_path = os.path.join(root, "tree.tar.gz")
        out_dir = os.path.join(root, "out")
        _write_tar(
            tar_path,
            _shard_files([keep, extra], _STUB_REL, _stub_suite(_STUB_LINE)),
        )
        try:
            ms.cmd_run_shard(
                tar_path,
                ms.sha256_file(tar_path),
                out_dir,
                {keep: suite, extra: suite},
                [keep],
            )
            return False
        except ms.ShardError as err:
            if str(err) != "shard":
                return False
        plan = {
            "ids": [keep],
            "shards": {"0": [keep]},
            "suite": {keep: suite},
            "exp": {keep: ["A1"]},
            "skip": False,
        }
        try:
            _run_main_shard(plan, tar_path, out_dir)
            return False
        except ms.ShardError:
            return True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_a5():
    root = tempfile.mkdtemp(prefix="a5-")
    try:
        tar_path = os.path.join(root, "tree.tar.gz")
        out_dir = os.path.join(root, "out")
        _write_tar(tar_path, _shard_files(["M201"], _STUB_REL, _stub_suite(_STUB_LINE)))
        try:
            ms.cmd_run_shard(
                tar_path,
                "0" * 64,
                out_dir,
                {"M201": "test-mutate-shards.sh"},
                ["M201"],
            )
        except SystemExit as err:
            direct = err.code == "sha256"
        else:
            return False
        plan = {
            "ids": ["M201"],
            "shards": {"0": ["M201"]},
            "suite": {"M201": "test-mutate-shards.sh"},
            "exp": {"M201": ["A1"]},
            "skip": False,
        }
        old = _push_env({
            "PLAN_B64": _plan_b64(plan),
            "K": "0",
            "TAR": tar_path,
            "SHA256": "0" * 64,
            "RAW_DIR": out_dir,
            "GITHUB_OUTPUT": None,
        })
        try:
            ms.main(["mutate_shards.py", "run-shard"])
        except SystemExit as err:
            return direct and err.code == "sha256"
        else:
            return False
        finally:
            _pop_env(old)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_a6():
    mid = "M201"
    suite = "../../x.sh"
    plan = {
        "ids": [mid],
        "shards": {"0": [mid]},
        "suite": {mid: suite},
        "exp": {mid: ["A1"]},
        "skip": False,
        "full_plan": False,
        "red_counts": "ci+offline",
    }
    try:
        ms.plan_suite(plan, mid)
        return False
    except ms.ShardError as err:
        if str(err) != "suite":
            return False
    root = tempfile.mkdtemp(prefix="a6-")
    try:
        tar_path = os.path.join(root, "tree.tar.gz")
        out_dir = os.path.join(root, "out")
        sentinel = b"#!/bin/bash\necho RAN > setup/ran-marker\necho 'RESULT A1: NOT BLOCKED'\n"
        files = _shard_files([mid], "baseline/setup/tests/harness/ignored.sh", b"#!/bin/bash\n")
        files["baseline/setup/x.sh"] = sentinel
        _write_tar(tar_path, files)
        try:
            ms.cmd_run_shard(
                tar_path,
                ms.sha256_file(tar_path),
                out_dir,
                {mid: suite},
                [mid],
            )
            return False
        except ms.ShardError as err:
            if str(err) != "suite":
                return False
        marker = os.path.join(out_dir, "work", "baseline", "setup", "ran-marker")
        if os.path.exists(marker):
            return False

        def write(raw):
            folder = os.path.join(raw, "raw-0")
            os.makedirs(folder, exist_ok=True)
            open(os.path.join(folder, mid + ".txt"), "w", encoding="utf-8").write(
                "RESULT A1: NOT BLOCKED\n"
            )

        try:
            _with_raw(plan, write)
            return False
        except ms.ShardError as err:
            return str(err) == "suite"
    finally:
        shutil.rmtree(root, ignore_errors=True)


CASES = {
    "S-H1": case_s_h1,
    "S-H2": case_s_h2,
    "S-H3": case_s_h3,
    "S-H4": case_s_h4,
    "S-H5": case_s_h5,
    "S-H6": case_s_h6,
    "S-H7": case_s_h7,
    "S-H7b": case_s_h7b,
    "S-H8": case_s_h8,
    "S-H9": case_s_h9,
    "S-A1": case_s_a1,
    "S-A2": case_s_a2,
    "S-A3": case_s_a3,
    "S-A4": case_s_a4,
    "S-A5": case_s_a5,
    "S-A6": case_s_a6,
    "S-A7": case_s_a7,
    "S-A8": case_s_a8,
    "S-A9": case_s_a9,
    "S-A10": case_s_a10,
    "S-A11": case_s_a11,
    "S-A12": case_s_a12,
    "S-A13": case_s_a13,
    "S-A14": case_s_a14,
    "S-A15": case_s_a15,
    "S-A16": case_s_a16,
    "S-A17": case_s_a17,
    "S-A18": case_s_a18,
    "S-A19": case_s_a19,
    "S-A20": case_s_a20,
    "S-A21": case_s_a21,
    "S-A22": case_s_a22,
    "S-A23": case_s_a23,
    "S-A24": case_s_a24,
    "S-A25": case_s_a25,
    "S-A26": case_s_a26,
    "S-A27": case_s_a27,
    "S-A28": case_s_a28,
    "S-A29": case_s_a29,
    "S-A30": case_s_a30,
    "S-A31": case_s_a31,
    "S-A32": case_s_a32,
    "S-A33": case_s_a33,
    "S-A34": case_s_a34,
    "S-A35": case_s_a35,
    "S-A36": case_s_a36,
    "H1": case_h1,
    "H2": case_h2,
    "H3": case_h3,
    "H4": case_h4,
    "A1": case_a1,
    "A2": case_a2,
    "A3": case_a3,
    "A4": case_a4,
    "A5": case_a5,
    "A6": case_a6,
}


def report(names):
    bad = []
    pending = list(names)
    for name in names:
        pending.pop(0)
        try:
            ok = CASES[name]()
        except Exception:
            print("RESULT %s: ERROR" % name)
            for rest in pending:
                print("RESULT %s: ERROR" % rest)
            bad.append(name)
            bad.extend(pending)
            return bad
        print("RESULT %s: %s" % (name, "BLOCKED" if ok else "NOT BLOCKED"))
        if not ok:
            bad.append(name)
    return bad


def prove(suite):
    """Apply each mutant for this suite and require its cases to go red."""
    wanted = SELECT_CASES if suite == "select" else SHARD_CASES
    failures = []
    for mid, spec in sorted(mutate.M.items(), key=lambda item: int(item[0][1:])):
        if int(mid[1:]) < 139:
            continue
        if mutate.SUITE_OF[mid] not in ("test-mutant-select.py", "test-mutate-shards.sh"):
            continue
        if mutate.SUITE_OF[mid] == "test-mutant-select.py" and suite != "select":
            continue
        if mutate.SUITE_OF[mid] == "test-mutate-shards.sh" and suite != "shards":
            continue
        tmp = tempfile.mkdtemp(prefix="prove-")
        try:
            for name in os.listdir(HERE):
                if name.endswith(".py"):
                    shutil.copy(os.path.join(HERE, name), os.path.join(tmp, name))
            needs_workflows = any(rel.startswith(".github/") for rel in mf.FILES[mid])
            if needs_workflows:
                wf_src = os.path.join(ROOT, ".github", "workflows")
                wf_dst = os.path.join(tmp, "repo", ".github", "workflows")
                os.makedirs(wf_dst, exist_ok=True)
                for name in os.listdir(wf_src):
                    if name.endswith((".yml", ".yaml")):
                        shutil.copy(os.path.join(wf_src, name), os.path.join(wf_dst, name))
            for rel in mf.FILES[mid]:
                src = os.path.join(ROOT, rel)
                if not os.path.isfile(src):
                    continue
                if rel.startswith(".github/"):
                    dest_root = os.path.join(tmp, "repo")
                    dest = os.path.join(dest_root, rel)
                else:
                    dest = os.path.join(tmp, os.path.basename(rel))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy(src, dest)
                text = open(dest, encoding="utf-8").read()
                updated, err = mutate.apply_edits(text, [(spec[1], spec[2])])
                if err or updated is None:
                    if rel.startswith(".github/") and text.count(spec[1]) == 0:
                        continue
                    failures.append("%s apply %s" % (mid, err))
                    break
                open(dest, "w", encoding="utf-8").write(updated)
            else:
                env = dict(os.environ)
                if any(rel.startswith(".github/") for rel in mf.FILES[mid]):
                    env["SPEED_ROOT"] = os.path.join(tmp, "repo")
                for case in spec[4]:
                    if case not in wanted and case not in CASES:
                        failures.append("%s unknown %s" % (mid, case))
                        continue
                    proc = subprocess.run(
                        [sys.executable, os.path.join(tmp, "speed_cases.py"), "--case", case],
                        cwd=tmp,
                        env=env,
                        capture_output=True,
                        text=True,
                    )
                    if "NOT BLOCKED" not in proc.stdout:
                        failures.append("%s %s\n%s%s" % (mid, case, proc.stdout, proc.stderr))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return failures


def main(argv):
    if argv[1:2] == ["--case"]:
        # Honour SPEED_ROOT so a mutated workflow tree can be checked.
        global ROOT
        if os.environ.get("SPEED_ROOT"):
            ROOT = os.environ["SPEED_ROOT"]
        name = argv[2]
        try:
            ok = CASES[name]()
        except Exception:
            print("RESULT %s: ERROR" % name)
            return 0
        print("RESULT %s: %s" % (name, "BLOCKED" if ok else "NOT BLOCKED"))
        return 0
    suite = "select"
    if argv[1:2] == ["--suite"]:
        suite = argv[2]
    names = SELECT_CASES if suite == "select" else SHARD_CASES
    bad = report(names)
    proved = prove(suite)
    if bad or proved:
        print("speed cases failed", bad, proved, file=sys.stderr)
        return 1
    print("speed cases: %s holds" % suite)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
