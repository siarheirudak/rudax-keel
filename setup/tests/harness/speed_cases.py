#!/usr/bin/env python3
"""Happy and attack cases for mutant selection, grading, and full-run state."""
import base64
import importlib.util
import io
import json
import os
import re
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
    "S-P1", "S-P2", "S-P3", "S-P4", "S-P5", "S-P6", "S-P7", "S-P8", "S-P9",
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
        line = "RESULT A1: BLOCKED"
        _write_tar(tar_path, _shard_files([mid], _STUB_REL, _stub_suite(line)))
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
        return line in got and line in base
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


def _no(detail):
    print(detail, file=sys.stderr)
    return False


def _shard_script(rel):
    text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    job = _workflow_jobs(text).get("shard") or ""
    lines = job.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "run: |":
            continue
        base = len(line) - len(line.lstrip(" "))
        body = []
        for nxt in lines[index + 1:]:
            if nxt.strip() and (len(nxt) - len(nxt.lstrip(" "))) <= base:
                break
            body.append(nxt)
        if "run-shard" not in "\n".join(body):
            continue
        indent = min(len(item) - len(item.lstrip(" ")) for item in body if item.strip())
        return "\n".join(item[indent:] if len(item) >= indent else item for item in body)
    return ""


def _resolve_job(rel):
    text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    return _workflow_jobs(text).get("resolve-plan") or ""


def case_s_p1():
    """Both workflows keep one read-only run-shard lifecycle and upload k=0..7."""
    scripts = []
    for rel in (".github/workflows/mutate-pr.yml", ".github/workflows/mutate-full.yml"):
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        jobs = _workflow_jobs(text)
        shard = jobs.get("shard") or ""
        if _permission_map(shard) != {"contents": "read"}:
            return _no("permission " + rel)
        if "actions/cache" in text or "actions/cache" in shard:
            return _no("cache " + rel)
        if "GH_TOKEN" in shard or "GITHUB_TOKEN" in shard or "NPM_TOKEN" in shard:
            return _no("token " + rel)
        script = _shard_script(rel)
        if "env -i" not in script or "run-shard" not in script:
            return _no("entrypoint " + rel)
        if '"PATH=$PATH"' not in script:
            return _no("path " + rel)
        if "/usr/bin:/bin" in script:
            return _no("replaced path " + rel)
        if 'NODE_PATH=$NODE_PATH' not in script or 'KEEL_PI_BIN=$KEEL_PI_BIN' not in script:
            return _no("forward " + rel)
        if '"KEEL_CI=1"' not in script:
            return _no("keel ci " + rel)
        if "docker build" in script or "gitleaks-install" in script or "npm install" in script:
            return _no("yaml provision " + rel)
        if "if: always()" not in shard:
            return _no("always " + rel)
        if "raw-out/shard-status.json" not in shard or "raw-out/baseline-*" not in shard:
            return _no("raw paths " + rel)
        if "raw-out/work" in shard:
            return _no("work upload " + rel)
        for line in shard.splitlines():
            if line.strip() == "path: raw-out":
                return _no("broad raw " + rel)
        if "fromJSON(needs.resolve-plan.outputs.matrix)" not in shard:
            return _no("matrix " + rel)
        if 'JOBS: "3"' not in shard:
            return _no("jobs " + rel)
        plan_job = _resolve_job(rel)
        cursor = 0
        for key in range(8):
            marker = "name: tree-%d" % key
            gate = "hashFiles('plan-out/tree-%d.tar.gz')" % key
            found = plan_job.find(marker, cursor)
            if found < 0 or gate not in plan_job:
                return _no("tree %d %s" % (key, rel))
            cursor = found + len(marker)
        if "ea165f8d65b6e75b540449e92b4886f43607fa02" not in plan_job:
            return _no("pin " + rel)
        scripts.append(script)
    if scripts[0] != scripts[1]:
        return _no("lifecycle drift")
    return True


def _source_pins():
    run = open(os.path.join(ROOT, "setup/tests/harness/run-tests.sh"), encoding="utf-8").read()
    installer = open(os.path.join(ROOT, "setup/gitleaks-install.sh"), encoding="utf-8").read()
    image = open(os.path.join(ROOT, "setup/docker/keel-pi.Dockerfile"), encoding="utf-8").read()
    pi = open(os.path.join(ROOT, "setup/lib/pi_launch.py"), encoding="utf-8").read()
    gitleaks_ver = "8.30.1"
    pi_ver = "0.73.1"
    if gitleaks_ver not in installer or "sha256sum -c" not in installer:
        return None
    if "gitleaks-install.sh" not in run:
        return None
    if pi_ver not in run or pi_ver not in image or ('PI_PIN = "%s"' % pi_ver) not in pi:
        return None
    package = "@mariozechner/pi-coding-agent@%s" % pi_ver
    if package not in run:
        return None
    keys = (
        "$DOCKER info",
        "gitleaks-install.sh",
        "keel-git.Dockerfile",
        "keel-proxy.Dockerfile",
        "keel-pi.Dockerfile",
        package,
    )
    try:
        positions = [run.index(key) for key in keys]
    except ValueError:
        return None
    if positions != sorted(positions):
        return None
    return gitleaks_ver, pi_ver, package


def _flat_commands(cmds):
    return "\n".join(" ".join(argv) for argv in cmds)


def _contract_ok(cmds, baseline, gitleaks_ver, pi_ver, package):
    flat = _flat_commands(cmds)
    keys = (
        "gitleaks-install.sh",
        "keel-git.Dockerfile",
        "keel-proxy.Dockerfile",
        "keel-pi.Dockerfile",
        package,
    )
    try:
        positions = [flat.index(key) for key in keys]
    except ValueError:
        return False
    if positions != sorted(positions):
        return False
    if gitleaks_ver not in flat or pi_ver not in flat:
        return False
    if flat.index("docker info") > flat.index("gitleaks-install.sh"):
        return False
    bash_cmds = [argv for argv in cmds if argv[:1] == ["bash"]]
    installer = os.path.join(baseline, "setup", "gitleaks-install.sh")
    if bash_cmds != [["bash", installer]]:
        return False
    for argv in cmds:
        if argv[:3] != ["docker", "build", "-q"]:
            continue
        dockerfile = argv[argv.index("-f") + 1]
        context = argv[-1]
        if not dockerfile.startswith(baseline + os.sep) or not context.startswith(baseline + os.sep):
            return False
        if os.path.dirname(dockerfile) != context:
            return False
    return True


def case_s_p2():
    pins = _source_pins()
    if pins is None:
        return _no("source pins")
    gitleaks_ver, pi_ver, package = pins
    baseline = "/validated/baseline"
    home = "/runner/home"
    needed = set()
    for suite in mf.SUITES:
        needed |= ms.SUITE_NEEDS[suite]
    cmds = ms.provision_commands(baseline, needed, home, pi_present=False)
    if not _contract_ok(cmds, baseline, gitleaks_ver, pi_ver, package):
        return _no("contract")
    pin = json.loads(json.dumps(cmds))
    pin[2][0] = pin[2][0].replace(gitleaks_ver, "8.30.2")
    if _contract_ok(pin, baseline, gitleaks_ver, pi_ver, package):
        return _no("bad pin accepted")
    swapped = json.loads(json.dumps(cmds))
    git_at = next(i for i, argv in enumerate(swapped) if "keel-git.Dockerfile" in " ".join(argv))
    proxy_at = next(i for i, argv in enumerate(swapped) if "keel-proxy.Dockerfile" in " ".join(argv))
    swapped[git_at], swapped[proxy_at] = swapped[proxy_at], swapped[git_at]
    if _contract_ok(swapped, baseline, gitleaks_ver, pi_ver, package):
        return _no("bad order accepted")
    wrong_path = json.loads(json.dumps(cmds))
    wrong_path[git_at][wrong_path[git_at].index("-f") + 1] = "/checkout-main-sentinel/keel-git.Dockerfile"
    if _contract_ok(wrong_path, baseline, gitleaks_ver, pi_ver, package):
        return _no("bad path accepted")
    wrong_setup = json.loads(json.dumps(cmds))
    wrong_setup[1][1] = os.path.join(baseline, "setup", "other-install.sh")
    if _contract_ok(wrong_setup, baseline, gitleaks_ver, pi_ver, package):
        return _no("bad setup accepted")
    return True


def _env_stub():
    return b"""#!/bin/bash
if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  printf 'RESULT A1: ERROR\\n'
  exit 1
fi
node -e 'require("probe-pkg/package.json")' || exit 1
test -x "$KEEL_PI_BIN" || exit 1
printf 'NS=%s\\n' "$KEEL_NS"
printf 'NODE_PATH=%s\\n' "$NODE_PATH"
printf 'KEEL_PI_BIN=%s\\n' "$KEEL_PI_BIN"
printf 'PATH=%s\\n' "$PATH"
if [ -n "${GH_TOKEN:-}${GITHUB_TOKEN:-}${NPM_TOKEN:-}${KEEL_SECRET:-}${GITHUB_ENV:-}${DOCKER_AUTH_CONFIG:-}" ]; then
  printf 'LEAK=1\\n'
fi
printf 'RESULT A1: BLOCKED\\n'
"""


def case_s_p3():
    """NODE_PATH and KEEL_PI_BIN cross env -i and run_suite. Token-like names do not."""
    root = tempfile.mkdtemp(prefix="env-")
    try:
        bin_dir = os.path.join(root, "bin")
        node_path = os.path.join(root, "modules")
        os.makedirs(os.path.join(node_path, "probe-pkg"))
        os.makedirs(bin_dir)
        open(os.path.join(node_path, "probe-pkg", "package.json"), "w", encoding="utf-8").write("{}\n")
        node = os.path.join(bin_dir, "node")
        open(node, "w", encoding="utf-8").write(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "code = sys.argv[sys.argv.index('-e') + 1] if '-e' in sys.argv else ''\n"
            "root = os.environ.get('NODE_PATH', '').split(':')[0]\n"
            "raise SystemExit(0 if os.path.isfile(os.path.join(root, 'probe-pkg', 'package.json')) and 'probe-pkg' in code else 1)\n"
        )
        os.chmod(node, 0o755)
        npm = os.path.join(bin_dir, "npm")
        open(npm, "w", encoding="utf-8").write("#!/bin/sh\nexit 0\n")
        os.chmod(npm, 0o755)
        pi_bin = os.path.join(root, "pi")
        open(pi_bin, "w", encoding="utf-8").write("#!/bin/sh\nexit 0\n")
        os.chmod(pi_bin, 0o755)
        poisoned = {
            "GH_TOKEN": "CANARY_GH_TOKEN",
            "GITHUB_TOKEN": "CANARY_GITHUB_TOKEN",
            "NPM_TOKEN": "CANARY_NPM_TOKEN",
            "KEEL_SECRET": "CANARY_KEEL_SECRET",
            "DOCKER_AUTH_CONFIG": "CANARY_DOCKER_AUTH",
        }
        work = os.path.join(root, "direct")
        os.makedirs(os.path.join(work, "setup", "tests", "harness"))
        script = os.path.join(work, "setup", "tests", "harness", "test-mutate-shards.sh")
        open(script, "wb").write(_env_stub())
        old = _push_env(dict(poisoned, PATH=bin_dir + ":" + os.environ.get("PATH", "")))
        try:
            stdout, code = ms.run_suite(
                work,
                "test-mutate-shards.sh",
                "base",
                {"NODE_PATH": node_path, "KEEL_PI_BIN": pi_bin},
            )
            text = stdout.decode("utf-8")
            if code != 0 or "NODE_PATH=%s" % node_path not in text or "KEEL_PI_BIN=%s" % pi_bin not in text:
                return _no("direct child %s %s" % (code, text))
            if "LEAK=1" in text or "CANARY_" in text:
                return _no("direct leak")
            stdout, code = ms.run_suite(
                work,
                "test-mutate-shards.sh",
                "M201",
                {"NODE_PATH": node_path, "KEEL_PI_BIN": pi_bin},
            )
            mutant = stdout.decode("utf-8")
            if code != 0 or "NS=M201" not in mutant or "CANARY_" in mutant:
                return _no("mutant child")
            env = ms.allowlisted_env({"NODE_PATH": node_path, "KEEL_PI_BIN": pi_bin})
            if any(key.startswith("GH") or "TOKEN" in key or key.startswith("KEEL_SECRET") for key in env):
                return _no("allowlist keys")
        finally:
            _pop_env(old)

        tar_path = os.path.join(root, "tree.tar.gz")
        _write_tar(tar_path, _shard_files(["M201"], _STUB_REL, _env_stub()))
        digest = ms.sha256_file(tar_path)
        plan = {
            "ids": ["M201"],
            "shards": {"0": ["M201"]},
            "suite": {"M201": "test-mutate-shards.sh"},
            "exp": {"M201": ["A1"]},
            "skip": False,
            "sha256": {"0": digest},
            "full_plan": False,
            "red_counts": "ci+offline",
        }
        workdir = os.path.join(root, "flow")
        os.makedirs(os.path.join(workdir, "shard-in"))
        os.symlink(os.path.join(ROOT, "setup"), os.path.join(workdir, "setup"))
        shutil.copy(tar_path, os.path.join(workdir, "shard-in", "tree-0.tar.gz"))
        script_path = os.path.join(root, "run.sh")
        open(script_path, "w", encoding="utf-8").write(_shard_script(".github/workflows/mutate-pr.yml") + "\n")
        flow_env = dict(os.environ)
        flow_env.update(poisoned)
        flow_env.update({
            "PATH": bin_dir + ":" + os.environ.get("PATH", ""),
            "PLAN_B64": _plan_b64(plan),
            "K": "0",
            "JOBS": "3",
            "NODE_PATH": node_path,
            "KEEL_PI_BIN": pi_bin,
            "HOME": os.environ.get("HOME", root),
            "TMPDIR": root,
        })
        proc = subprocess.run(
            ["bash", script_path],
            cwd=workdir,
            env=flow_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return _no("workflow env %s %s" % (proc.returncode, proc.stderr[-500:]))
        base = open(os.path.join(workdir, "raw-out", "baseline-test-mutate-shards.sh"), encoding="utf-8").read()
        got = open(os.path.join(workdir, "raw-out", "M201.txt"), encoding="utf-8").read()
        for label, body in (("base", base), ("mutant", got)):
            if "NODE_PATH=%s" % node_path not in body or "KEEL_PI_BIN=%s" % pi_bin not in body:
                return _no("workflow missing forward " + label)
            if bin_dir not in body.split("PATH=", 1)[-1]:
                return _no("workflow path " + label)
            if "LEAK=1" in body or "CANARY_" in body:
                return _no("workflow leak " + label)
        if "NS=base" not in base or "NS=M201" not in got:
            return _no("workflow namespaces")
        return True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _restore_runner(saved):
    ms._run_allowlisted = saved


def case_s_p4():
    if set(ms.SUITE_NEEDS) != set(mf.SUITES):
        return _no("suite map")
    expects = {
        "test-attacks.sh": {"docker", "gitleaks", "image_git", "image_proxy"},
        "test-attack-results.sh": set(),
        "test-mutant-result.sh": set(),
        "test-runtime.sh": {"docker"},
        "test-step4.sh": {"docker", "image_git", "image_pi", "host_pi"},
        "test-step5.sh": set(),
        "test-step6.sh": {"docker", "image_git"},
        "test-egress.sh": {"docker", "image_git", "image_proxy"},
        "visibility-suite.sh": {"docker", "image_git", "image_proxy"},
        "test-mutant-select.py": set(),
        "test-mutate-shards.sh": set(),
    }
    for suite, need in expects.items():
        if set(ms.SUITE_NEEDS[suite]) != need:
            return _no("row " + suite)
    if "image_proxy" not in ms.union_needs(["test-attacks.sh", "visibility-suite.sh"]):
        return _no("transitive proxy")
    if ms.union_needs(["test-step5.sh"]) or ms.union_needs(["test-mutate-shards.sh"]):
        return _no("empty union")
    partial = dict(ms.SUITE_NEEDS)
    partial.pop("test-step5.sh")
    try:
        ms.union_needs(["test-attacks.sh"], partial)
        return _no("partial map accepted")
    except ms.ShardError as err:
        if str(err) != "prereq":
            return _no("partial map error")
    try:
        ms.union_needs(["missing.sh"])
        return _no("unknown suite accepted")
    except ms.ShardError:
        pass
    runtime = ms.provision_commands("/baseline", ms.union_needs(["test-runtime.sh"]), "/home")
    if runtime != [["docker", "info"]]:
        return _no("runtime commands %s" % runtime)

    calls = []
    saved = ms._run_allowlisted

    def spy(argv, env):
        calls.append(list(argv))
        if "GH_TOKEN" in env or "NPM_TOKEN" in env:
            return 9, ""
        if argv[:2] == ["node", "-e"]:
            return 0, ""
        if argv[-1:] == ["version"]:
            return 0, "8.30.1\n"
        return 0, ""

    root = tempfile.mkdtemp(prefix="need-")
    ms._run_allowlisted = spy
    try:
        step5 = os.path.join(root, "step5")
        os.makedirs(step5)
        tar_path = os.path.join(step5, "tree.tar.gz")
        out_dir = os.path.join(step5, "out")
        script = "baseline/setup/tests/harness/test-step5.sh"
        _write_tar(tar_path, _shard_files(["M201"], script, _stub_suite("RESULT A1: BLOCKED")))
        old = _push_env({"K": "0", "GH_TOKEN": "CANARY_GH_TOKEN", "NPM_TOKEN": "CANARY_NPM_TOKEN"})
        try:
            rc = ms.cmd_run_shard(
                tar_path,
                ms.sha256_file(tar_path),
                out_dir,
                {"M201": "test-step5.sh"},
                ["M201"],
                {"M201": ["A1"]},
            )
        finally:
            _pop_env(old)
        if rc != 0 or calls:
            return _no("step5 called provision %s %s" % (rc, calls))
        if not os.path.isfile(os.path.join(out_dir, "M201.txt")):
            return _no("step5 mutant missing")

        calls[:] = []
        home = os.path.join(root, "home")
        pi_dir = os.path.join(home, ".cache", "keel", "pi-0.73.1", "node_modules")
        os.makedirs(os.path.join(pi_dir, ".bin"))
        os.makedirs(os.path.join(pi_dir, "@mariozechner", "pi-coding-agent"))
        pi_bin = os.path.join(pi_dir, ".bin", "pi")
        open(pi_bin, "w", encoding="utf-8").write("#!/bin/sh\n")
        os.chmod(pi_bin, 0o755)
        open(os.path.join(pi_dir, "@mariozechner", "pi-coding-agent", "package.json"), "w", encoding="utf-8").write(
            '{"version":"0.73.1"}\n'
        )
        base = os.path.join(root, "base")
        docker = os.path.join(base, "setup", "docker")
        os.makedirs(docker)
        for name in ("keel-git", "keel-pi"):
            open(os.path.join(docker, name + ".Dockerfile"), "w", encoding="utf-8").write("FROM scratch\n")
        old = _push_env({
            "KEEL_PI_BIN": "/untrusted/pi",
            "NODE_PATH": "/untrusted/modules",
            "KEEL_PI_DIR": "/untrusted/pi-dir",
            "GH_TOKEN": "CANARY_GH_TOKEN",
        })
        try:
            verified = ms.provision_selected(base, ["test-step4.sh"], {"test-step4.sh": ["M10"]}, home=home)
        finally:
            _pop_env(old)
        if verified.get("KEEL_PI_BIN") != pi_bin:
            return _no("pi bin not superseded")
        if not verified.get("NODE_PATH", "").startswith(pi_dir):
            return _no("node path")
        if "/untrusted/modules" not in verified.get("NODE_PATH", ""):
            return _no("inherited node path dropped")
        joined = " ".join(" ".join(argv) for argv in calls)
        if "/untrusted/pi-dir" in joined or "/untrusted/pi " in joined:
            return _no("external pi path used")
        if base not in joined or "keel-git.Dockerfile" not in joined:
            return _no("baseline image path missing")
        node_calls = [argv for argv in calls if argv[:2] == ["node", "-e"]]
        if not node_calls or "0.73.1" not in node_calls[-1][-1]:
            return _no("pi probe")

        calls[:] = []

        def missing_docker(argv, env):
            calls.append(list(argv))
            if argv[:2] == ["docker", "info"]:
                return 127, ""
            return 0, ""

        ms._run_allowlisted = missing_docker
        bad = os.path.join(root, "bad")
        os.makedirs(bad)
        tar_path = os.path.join(bad, "tree.tar.gz")
        out_dir = os.path.join(bad, "out")
        files = _shard_files(
            ["M11"],
            "baseline/setup/tests/harness/test-step6.sh",
            _stub_suite("RESULT A1: BLOCKED"),
        )
        files["baseline/setup/docker/keel-git.Dockerfile"] = b"FROM scratch\n"
        _write_tar(tar_path, files)
        suite_calls = []
        real_suite = ms.run_suite

        def suite_spy(*args, **kwargs):
            suite_calls.append(args)
            return real_suite(*args, **kwargs)

        ms.run_suite = suite_spy
        old = _push_env({"K": "2"})
        try:
            rc = ms.cmd_run_shard(
                tar_path,
                ms.sha256_file(tar_path),
                out_dir,
                {"M11": "test-step6.sh"},
                ["M11"],
                {"M11": ["A1"]},
            )
        finally:
            _pop_env(old)
            ms.run_suite = real_suite
        if rc == 0 or suite_calls:
            return _no("missing docker still ran")
        err = open(os.path.join(out_dir, "shard-status.json"), encoding="utf-8").read()
        if "docker_missing" not in err:
            return _no("docker category")
        return True
    finally:
        _restore_runner(saved)
        shutil.rmtree(root, ignore_errors=True)


def _tar_with(path, members):
    with tarfile.open(path, "w:gz") as tar:
        for spec in members:
            info = tarfile.TarInfo(name=spec["name"])
            kind = spec.get("kind", "file")
            if kind == "file":
                blob = spec.get("blob", b"")
                info.size = len(blob)
                info.mode = 0o644
                info.type = tarfile.REGTYPE
                tar.addfile(info, io.BytesIO(blob))
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = spec.get("link", "x")
                tar.addfile(info)
            elif kind == "fifo":
                info.type = tarfile.FIFOTYPE
                tar.addfile(info)


def case_s_p5():
    """Invalid archives never provision, and builds use the extracted tree."""
    root = tempfile.mkdtemp(prefix="order-")
    calls = []
    saved = ms._run_allowlisted
    real_suite = ms.run_suite

    def spy(argv, env):
        calls.append(("prov", list(argv)))
        return 0, "8.30.1\n"

    def suite_spy(*args, **kwargs):
        calls.append(("suite", args[1] if len(args) > 1 else ""))
        return b"RESULT A1: BLOCKED\n", 0

    ms._run_allowlisted = spy
    ms.run_suite = suite_spy
    try:
        out_dir = os.path.join(root, "out")
        os.makedirs(out_dir)
        tar_path = os.path.join(root, "bad-path.tar.gz")
        _tar_with(tar_path, [{"name": "../escape", "blob": b"x"}])
        try:
            ms.cmd_run_shard(
                tar_path, ms.sha256_file(tar_path), out_dir,
                {"M201": "test-step6.sh"}, ["M201"], {"M201": ["A1"]},
            )
            return _no("path accepted")
        except ms.ShardError as err:
            if str(err) != "path" or calls:
                return _no("path provision %s" % err)
        tar_path = os.path.join(root, "link.tar.gz")
        _tar_with(tar_path, [{"name": "baseline/link", "kind": "symlink"}])
        try:
            ms.cmd_run_shard(
                tar_path, ms.sha256_file(tar_path), out_dir,
                {"M201": "test-mutate-shards.sh"}, ["M201"], {"M201": []},
            )
            return _no("link accepted")
        except ms.ShardError as err:
            if str(err) != "symlink" or calls:
                return _no("link provision")
        tar_path = os.path.join(root, "fifo.tar.gz")
        _tar_with(tar_path, [{"name": "baseline/fifo", "kind": "fifo"}])
        try:
            ms.cmd_run_shard(
                tar_path, ms.sha256_file(tar_path), out_dir,
                {"M201": "test-mutate-shards.sh"}, ["M201"], {"M201": []},
            )
            return _no("fifo accepted")
        except ms.ShardError as err:
            if str(err) != "type" or calls:
                return _no("fifo provision")
        tar_path = os.path.join(root, "ids.tar.gz")
        _tar_with(tar_path, [
            {"name": "baseline/setup/tests/harness/test-mutate-shards.sh", "blob": b"#!/bin/bash\n"},
            {"name": "ids/M202/setup/keel.sh", "blob": b"x\n"},
        ])
        try:
            ms.cmd_run_shard(
                tar_path, ms.sha256_file(tar_path), out_dir,
                {"M201": "test-mutate-shards.sh", "M202": "test-mutate-shards.sh"},
                ["M201"], {"M201": []},
            )
            return _no("id bind accepted")
        except ms.ShardError as err:
            if str(err) != "shard" or calls:
                return _no("bind provision")
        try:
            ms.cmd_run_shard(tar_path, "0" * 64, out_dir, {"M201": "test-mutate-shards.sh"}, ["M201"])
            return _no("digest accepted")
        except SystemExit as err:
            if err.code != "sha256" or calls:
                return _no("digest provision")
        try:
            ms.cmd_run_shard(
                tar_path, ms.sha256_file(tar_path), out_dir,
                {"M202": "../../x.sh"}, ["M202"], {"M202": ["A1"]},
            )
            return _no("suite accepted")
        except ms.ShardError as err:
            if str(err) != "suite" or calls:
                return _no("suite provision")

        checkout = os.path.join(root, "checkout-main-sentinel")
        os.makedirs(os.path.join(checkout, "setup", "docker"))
        open(os.path.join(checkout, "setup", "docker", "keel-git.Dockerfile"), "w", encoding="utf-8").write(
            "FROM scratch\n# SENTINEL_MAIN\n"
        )
        tar_path = os.path.join(root, "good.tar.gz")
        good_out = os.path.join(root, "out-good")
        _tar_with(tar_path, [
            {"name": "baseline/setup/docker/keel-git.Dockerfile", "blob": b"FROM scratch\n# BASELINE_TREE\n"},
            {"name": "baseline/setup/tests/harness/test-step6.sh", "blob": _stub_suite("RESULT A1: BLOCKED")},
            {"name": "ids/M11/setup/keel.sh", "blob": b"changed\n"},
        ])
        cwd = os.getcwd()
        os.chdir(checkout)
        try:
            rc = ms.cmd_run_shard(
                tar_path, ms.sha256_file(tar_path), good_out,
                {"M11": "test-step6.sh"}, ["M11"], {"M11": ["A1"]},
            )
        finally:
            os.chdir(cwd)
        if rc != 0:
            return _no("good shard %s" % rc)
        blob = " ".join(" ".join(item[1]) for item in calls if item[0] == "prov")
        if "checkout-main-sentinel" in blob or "SENTINEL_MAIN" in blob:
            return _no("checkout dockerfile used")
        if "keel-git.Dockerfile" not in blob or "/baseline/" not in blob and "baseline/setup/docker" not in blob:
            return _no("baseline dockerfile missing %s" % blob)
        if not any(item[0] == "suite" for item in calls):
            return _no("suite did not run")
        if calls[0][0] != "prov":
            return _no("provision after suite")
        return True
    finally:
        ms._run_allowlisted = saved
        ms.run_suite = real_suite
        shutil.rmtree(root, ignore_errors=True)


def _pairs(mid, names):
    return [(mid, list(names))]


def case_s_p6():
    suite = "test-step6.sh"
    missing = ms.classify_baseline("2", suite, _pairs("M224", ["S6-H8"]), None, 0)
    if missing["kind"] != "missing" or missing["red_expected"] or missing["reason"] != "absent":
        return _no("missing")
    if missing["ids"] != ["M224"]:
        return _no("missing ids")
    decode = ms.classify_baseline("2", suite, _pairs("M224", ["S6-H8"]), b"\xff", 0)
    if decode["kind"] != "unparseable" or decode["reason"] != "decode" or decode["red_expected"]:
        return _no("decode")
    long_line = "RESULT S6-H8: BLOCKED\n" + ("x" * (ms.MAX_LINE + 1))
    lined = ms.classify_baseline("2", suite, _pairs("M224", ["S6-H8"]), long_line, 0)
    if lined["kind"] != "unparseable" or lined["reason"] != "line":
        return _no("line")
    empty = ms.classify_baseline("2", suite, _pairs("M224", []), "", 0)
    if empty["kind"] != "unparseable" or empty["reason"] != "empty":
        return _no("empty")
    incomplete = ms.classify_baseline(
        "2", suite, _pairs("M224", ["S6-H8", "S6-H9"]), "RESULT S6-H8: BLOCKED\n", 0
    )
    if incomplete["kind"] != "unparseable" or incomplete["missing_expected"] != ["S6-H9"]:
        return _no("incomplete")
    duplicate = ms.classify_baseline(
        "2", suite, _pairs("M224", ["S6-H8"]),
        "RESULT S6-H8: BLOCKED\nRESULT S6-H8: BLOCKED\n", 0,
    )
    conflict = ms.classify_baseline(
        "2", suite, _pairs("M224", ["S6-H8"]),
        "RESULT S6-H8: BLOCKED\nRESULT S6-H8: NOT BLOCKED\n", 0,
    )
    if duplicate["reason"] != "duplicate" or conflict["reason"] != "conflict":
        return _no("records")
    if duplicate["red_expected"] or conflict["red_expected"]:
        return _no("unsafe red")
    bad = ms.classify_baseline(
        "2", suite,
        [("M224", ["S6-H8"]), ("M225", ["S6-H8"]), ("M226", ["OTHER"])],
        "RESULT S6-H8: NOT BLOCKED\nRESULT OTHER: BLOCKED\nRESULT CANARY_NAME: NOT BLOCKED\n",
        0,
    )
    if bad["kind"] != "BAD" or bad["ids"] != ["M224", "M225"] or bad["red_expected"] != ["S6-H8"]:
        return _no("bad ids %s" % bad)
    if bad["tags"] != ["NOT_BLOCKED"] or bad["extra_red_count"] != 1:
        return _no("bad tags")
    rendered = ms.format_finding(bad)
    if "CANARY_NAME" in rendered or "shard=2" not in rendered or "test-step6.sh" not in rendered:
        return _no("render %s" % rendered)
    masked = ms.classify_baseline("0", "test-step5.sh", _pairs("M14", []), None, 0)
    if masked["kind"] != "missing":
        return _no("masked waived")
    usable = ms.classify_baseline(
        "0", "test-step5.sh", _pairs("M14", []), "RESULT EXTRA: NOT BLOCKED\n", 0
    )
    if usable is not None:
        return _no("extra red changed policy")

    plan = {
        "ids": ["M224", "M225"],
        "shards": {"0": ["M224"], "1": ["M225"]},
        "suite": {"M224": suite, "M225": suite},
        "exp": {"M224": ["S6-H8"], "M225": ["S6-H8"]},
        "skip": False,
        "full_plan": True,
        "red_counts": "ci+offline",
    }

    def write(raw):
        _raw_id(os.path.join(raw, "raw-0"), "M224", "RESULT S6-H8: NOT BLOCKED\n", suite, "RESULT S6-H8: NOT BLOCKED\n")
        _raw_id(os.path.join(raw, "raw-1"), "M225", "RESULT S6-H8: NOT BLOCKED\n", suite, "RESULT S6-H8: BLOCKED\n")

    rc, text = _grade(plan, write)
    if rc == 0 or "kind=BAD" not in text or "shard=0" not in text:
        return _no("mask %s %s" % (rc, text))
    if "shard=1" in text and "kind=BAD" in text.split("shard=1")[0]:
        pass
    saved = ms.check_baseline
    ms.check_baseline = False
    try:
        quiet = ms.baseline_bad_ids(["M01"], {"M01": "s"}, {"M01": ["A1"]}, {})
        rc_off, text_off = _grade(plan, write)
    finally:
        ms.check_baseline = saved
    if quiet != ([], False) or rc_off != 0 or "kind=BAD" in text_off:
        return _no("flag off %s %s %s" % (quiet, rc_off, text_off))
    return True


def case_s_p7():
    canary = "CANARY_SECRET_VALUE"
    suite = "test-step6.sh"
    body = (
        canary + "\n"
        "\x1b[31mred\x1b[0m\n"
        "::error file=secret::" + canary + "\n"
        "::add-mask::" + canary + "\n"
        "RESULT S6-H8: NOT BLOCKED\n"
        + ("Y" * (ms.MAX_LINE + 50))
    )
    script = (
        "#!/bin/bash\npython3 - << 'PY'\n"
        "print(%r)\nprint('\\x1b[31m')\nprint(%r)\nprint('RESULT S6-H8: NOT BLOCKED')\n"
        "print('Y' * %d)\nPY\n"
    ) % (canary, "::error file=secret::" + canary, ms.MAX_LINE + 50)
    finding = ms.classify_baseline("2", suite, _pairs("M224", ["S6-H8"]), body, 0)
    rendered = ms.render_findings([finding])
    if canary in rendered or "\x1b" in rendered or "::" in rendered or "Y" * 80 in rendered:
        return _no("render leaked")
    if finding["reason"] != "line":
        return _no("long line kind")
    injected = ms.classify_baseline(
        "0\n::warning::" + canary,
        suite,
        _pairs("M224", ["S6-H8"]),
        "RESULT S6-H8: NOT BLOCKED " + canary + "\n::warning::" + canary + "\n",
        0,
    )
    line = ms.format_finding(injected)
    if canary in line or "\n" in line or "::" in line or "tags=[OTHER]" not in line:
        return _no("injection %s" % line)
    ids = ["M%d" % n for n in range(1, 26)] + ["bad id"]
    wide = ms._finding("BAD", "1", suite, ids, red_expected=["A1"] * 25, tags=["NOT_BLOCKED"])
    wide_line = ms.format_finding(wide)
    if "ids_total=26" not in wide_line or "bad id" in wide_line or "M21" in wide_line:
        return _no("id bound %s" % wide_line)
    many = [
        ms._finding("missing", "0", "test-step5.sh", ["M1"], reason="absent")
        for _ in range(150)
    ]
    bounded = ms.render_findings(many)
    if "records_total=150" not in bounded or "records_omitted=" not in bounded or "truncated" not in bounded:
        return _no("record bound")
    if bounded.count("kind=missing") > ms.DIAG_RECORD_CAP:
        return _no("too many lines")
    huge = ms.bound_diagnostic_text([canary + ("x" * 5000)], 1)
    if canary in huge or "truncated=record" not in huge:
        return _no("byte bound")
    root = tempfile.mkdtemp(prefix="san-")
    try:
        tar_path = os.path.join(root, "tree.tar.gz")
        out_dir = os.path.join(root, "out")
        files = _shard_files(["M224"], "baseline/setup/tests/harness/test-step6.sh", script.encode("utf-8"))
        files["baseline/setup/docker/keel-git.Dockerfile"] = b"FROM scratch\n"
        _write_tar(tar_path, files)
        saved = ms._run_allowlisted
        ms._run_allowlisted = lambda argv, env: (0, "8.30.1\n")
        old = _push_env({"K": "2"})
        buf = io.StringIO()
        err = sys.stderr
        sys.stderr = buf
        try:
            rc = ms.cmd_run_shard(
                tar_path, ms.sha256_file(tar_path), out_dir,
                {"M224": suite}, ["M224"], {"M224": ["S6-H8"]},
            )
        finally:
            sys.stderr = err
            _pop_env(old)
            ms._run_allowlisted = saved
        console = buf.getvalue()
        status = open(os.path.join(out_dir, "shard-status.json"), encoding="utf-8").read()
        if rc == 0 or canary in console or canary in status or "\x1b" in console or "::" in console:
            return _no("status leaked")
        if os.path.isfile(os.path.join(out_dir, "M224.txt")):
            return _no("mutant ran on bad baseline")
        return True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _grade(plan, write_raw, updates=None):
    raw = tempfile.mkdtemp(prefix="grade-")
    cwd = os.getcwd()
    buf = io.StringIO()
    old_err = sys.stderr
    try:
        write_raw(raw)
        os.chdir(ROOT)
        env = {
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
        }
        if updates:
            env.update(updates)
        old = _push_env(env)
        sys.stderr = buf
        try:
            return ms.cmd_aggregate(), buf.getvalue()
        finally:
            sys.stderr = old_err
            _pop_env(old)
            os.chdir(cwd)
    finally:
        if sys.stderr is buf:
            sys.stderr = old_err
        shutil.rmtree(raw, ignore_errors=True)


def case_s_p8():
    root = tempfile.mkdtemp(prefix="pre-")
    try:
        marker = os.path.join(root, "mutant-ran")
        script = (
            "#!/bin/bash\n"
            "if [ \"$KEEL_NS\" != base ]; then printf ran > '%s'; fi\n"
            "printf 'RESULT A1: NOT BLOCKED\\n'\n" % marker
        ).encode("utf-8")
        tar_path = os.path.join(root, "tree.tar.gz")
        out_dir = os.path.join(root, "out")
        _write_tar(tar_path, _shard_files(["M201"], _STUB_REL, script))
        buf = io.StringIO()
        err = sys.stderr
        sys.stderr = buf
        old = _push_env({"K": "0", "TMPDIR": root})
        try:
            rc = ms.cmd_run_shard(
                tar_path, ms.sha256_file(tar_path), out_dir,
                {"M201": "test-mutate-shards.sh"}, ["M201"], {"M201": ["A1"]},
            )
        finally:
            sys.stderr = err
            _pop_env(old)
        console = buf.getvalue()
        if rc == 0 or os.path.exists(marker) or "kind=BAD" not in console:
            return _no("preflight %s %s" % (rc, console))
        if not os.path.isfile(os.path.join(out_dir, "baseline-test-mutate-shards.sh")):
            return _no("baseline artifact")
        if os.path.isfile(os.path.join(out_dir, "M201.txt")):
            return _no("mutant artifact")

        suite = "test-mutate-shards.sh"
        plan = {
            "ids": ["M201"],
            "shards": {"0": ["M201"]},
            "suite": {"M201": suite},
            "exp": {"M201": ["A1"]},
            "skip": False,
            "full_plan": True,
            "red_counts": "ci+offline",
        }

        def green(raw):
            _raw_id(os.path.join(raw, "raw-0"), "M201", "RESULT A1: NOT BLOCKED\n", suite, "RESULT A1: BLOCKED\n")

        rc, text = _grade(plan, green, {"SHARD_RESULT": "failure"})
        if rc == 0 or "shard result failure" not in text:
            return _no("latched shard %s %s" % (rc, text))

        def missing_both(raw):
            os.makedirs(os.path.join(raw, "raw-0"))

        rc, text = _grade(plan, missing_both)
        if rc == 0 or text.find("kind=missing") < 0 or text.find("kind=missing") > text.find("binding"):
            return _no("order %s" % text)

        def status_lie(raw):
            folder = os.path.join(raw, "raw-0")
            _raw_id(folder, "M201", "RESULT A1: NOT BLOCKED\n", suite, "RESULT A1: NOT BLOCKED\n")
            open(os.path.join(folder, "shard-status.json"), "w", encoding="utf-8").write('{"ok": true}\n')

        rc, text = _grade(plan, status_lie)
        if rc == 0 or "kind=BAD" not in text:
            return _no("status trust")

        saved_json = ms._github_json

        def boom(*_args, **_kwargs):
            raise RuntimeError("CANARY_SECRET_URL")

        ms._github_json = boom
        try:
            rc, text = _grade(plan, green, {"GH_TOKEN": "t", "REPO": "o/r", "RUN_ID": "1"})
        finally:
            ms._github_json = saved_json
        if rc == 0 or "category=transport" not in text or "CANARY_SECRET_URL" in text:
            return _no("transport %s %s" % (rc, text))

        both = {
            "ids": ["M201", "M202"],
            "shards": {"0": ["M201", "M202"]},
            "suite": {"M201": suite, "M202": suite},
            "exp": {"M201": ["A1"], "M202": ["A1"]},
            "skip": False,
            "full_plan": False,
            "red_counts": "ci+offline",
        }

        def write_both(raw):
            folder = os.path.join(raw, "raw-0")
            _raw_id(folder, "M201", "RESULT A1: NOT BLOCKED\n", suite, "RESULT A1: BLOCKED\n")
            open(os.path.join(folder, "M202.txt"), "w", encoding="utf-8").write("RESULT A1: NOT BLOCKED\n")

        rc, _text = _grade(both, write_both)
        if rc != 0:
            return _no("complete grade %s" % rc)
        return True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_s_p9():
    ids = ["M%d" % n for n in range(1, 159)]
    shards = ms.assign_shards(ids)
    if [len(group) for group in shards] != [20, 20, 20, 20, 20, 20, 19, 19]:
        return _no("cap8 sizes")
    flat = [mid for group in shards for mid in group]
    if sorted(flat, key=lambda mid: int(mid[1:])) != ids or len(flat) != len(set(flat)):
        return _no("cap8 coverage")
    if ms.assign_shards([], 8) != []:
        return _no("empty")
    if len(ms.assign_shards(["M1", "M2"], 8)) != 2:
        return _no("short")
    four = ms.assign_shards(ids, 4)
    if [len(group) for group in four] != [40, 40, 39, 39]:
        return _no("cap4")
    keys = [str(index) for index in range(8)]
    names = ["plan"] + ["raw-%s" % key for key in keys] + ["tree-%s" % key for key in keys]
    if not ms.artifact_names_ok(names, keys):
        return _no("keys 0..7")
    if ms.artifact_names_ok(names + ["raw-8"], keys) or ms.artifact_names_ok(names + ["tree-9"], keys):
        return _no("foreign key")
    if ms.artifact_names_ok(names + ["raw-0"], keys):
        return _no("duplicate artifact")
    for rel in (".github/workflows/mutate-pr.yml", ".github/workflows/mutate-full.yml"):
        job = _resolve_job(rel)
        for key in keys:
            if "name: tree-%s" % key not in job:
                return _no("upload " + key)
    return True


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
    "S-P1": case_s_p1,
    "S-P2": case_s_p2,
    "S-P3": case_s_p3,
    "S-P4": case_s_p4,
    "S-P5": case_s_p5,
    "S-P6": case_s_p6,
    "S-P7": case_s_p7,
    "S-P8": case_s_p8,
    "S-P9": case_s_p9,
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
