#!/usr/bin/env python3
"""Decide whether keel-gate may pass the mutant requirement for this commit.

A pull request that selects mutants needs a successful workflow_dispatch of
.github/workflows/mutate-pr.yml on the default branch, titled with this head
SHA, whose recorded plan contains every mutant the gate requires.
Comments, artifacts, and environment variables are not a result.
A diff that selects no mutants and changes no mutant definitions does not
need a run.
"""
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mutant_defs as md
import mutant_files as mf  # noqa: E402
import mutate_shards as ms

WORKFLOW_PATH = ".github/workflows/mutate-pr.yml"
SHA_RE = re.compile(r"[0-9a-f]{40}")
REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
MUTANT_ID_RE = re.compile(r"^M[0-9]{2,}$")
DIGEST_RE = re.compile(r"[0-9a-fA-F]{64}")
sha_bind = 1  # mutant-sha-bind
require_plan = 1  # plan-cover
use_defs = 1  # defs-required
redirect_guard = 1  # redirect-guard
one_plan = 1  # one-plan
check_head = 1  # checkout-head

API_HOST = "api.github.com"
MAX_REDIRECTS = 4
MAX_MATCHING_RUNS = 20
CATALOG_CAP = 1048576
ZIP_COMPRESSED_CAP = 1048576
ZIP_UNCOMPRESSED_CAP = 1048576
BODY_CAP = 1048576
MISSING_ID_CAP = 12
SAVED_OPTS = ("--expect-head", "--base", "--run", "--list", "--zip")


def title_for(sha):
    return "mutants " + sha


def pr_number(ref):
    """Pull request number from the runner ref. Other refs are not a pull request."""
    match = re.fullmatch(r"refs/pull/([0-9]+)/merge", ref or "")
    if not match:
        return None
    return match.group(1)


def pull_head_sha(pull):
    """Head SHA from the pull request record. The merge commit is not the head."""
    if not isinstance(pull, dict):
        return ""
    sha = ((pull.get("head") or {}).get("sha") or "").strip()
    if not SHA_RE.fullmatch(sha):
        return ""
    return sha


def run_matches(head_sha, run, default_branch):
    """True when this workflow run is the trusted result for head_sha."""
    if not isinstance(run, dict):
        return False
    if run.get("event") != "workflow_dispatch":
        return False
    if (run.get("head_branch") or "") != default_branch:
        return False
    if run.get("conclusion") != "success":
        return False
    if (run.get("path") or "") != WORKFLOW_PATH:
        return False
    title = run.get("display_title") or ""
    if sha_bind != 1:
        prefix = "mutants "
        return title.startswith(prefix) and SHA_RE.fullmatch(title[len(prefix):]) is not None
    return title == title_for(head_sha)


def _auth_header_name(name):
    lowered = (name or "").lower()
    return lowered == "authorization" or lowered.endswith("-authorization") or lowered == "cookie"


class _GuardedRedirect(urllib.request.HTTPRedirectHandler):
    """Follow only https redirects, and attach no request header on later hops."""

    max_redirections = MAX_REDIRECTS
    max_repeats = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if redirect_guard != 1:
            return urllib.request.HTTPRedirectHandler.redirect_request(
                self, req, fp, code, msg, headers, newurl
            )
        parts = urllib.parse.urlsplit(newurl)
        if parts.scheme != "https" or not parts.hostname:
            raise urllib.error.HTTPError(req.full_url, code, "redirect", headers, fp)
        if parts.username or parts.password:
            raise urllib.error.HTTPError(req.full_url, code, "redirect", headers, fp)
        host = parts.hostname
        if parts.port:
            host = "%s:%s" % (host, parts.port)
        clean = urllib.parse.urlunsplit((parts.scheme, host, parts.path, parts.query, ""))
        return urllib.request.Request(clean, method="GET")


def _request(repo, token, path):
    if not REPO_RE.fullmatch(repo or ""):
        raise RuntimeError("bad repository")
    if not token:
        raise RuntimeError("token missing")
    if not path.startswith("/") or "://" in path or "@" in path:
        raise RuntimeError("bad path")
    url = "https://" + API_HOST + "/repos/" + repo + path
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname != API_HOST:
        raise RuntimeError("bad path")
    if token in url:
        raise RuntimeError("bad path")
    return urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "rudax-keel-mutants",
        },
        method="GET",
    )


def _open(step, req):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _GuardedRedirect)
    try:
        return opener.open(req, timeout=30)
    except urllib.error.HTTPError as err:
        code = getattr(err, "code", None)
        raise RuntimeError("%s: %s" % (step, code)) from None
    except Exception:
        raise RuntimeError("%s: network error" % step) from None


def _read_limited(resp, cap):
    try:
        data = resp.read(cap + 1)
    finally:
        resp.close()
    if len(data) > cap:
        return None
    return data


def _fetch_json(repo, token, path, step, missing_ok=False):
    req = _request(repo, token, path)
    try:
        resp = _open(step, req)
    except RuntimeError as err:
        if missing_ok and str(err).endswith(": 404"):
            return None
        raise
    data = _read_limited(resp, BODY_CAP)
    if data is None:
        raise RuntimeError("%s: network error" % step)
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise RuntimeError("%s: network error" % step) from None


def _fetch_bytes(repo, token, path, step):
    req = _request(repo, token, path)
    resp = _open(step, req)
    data = _read_limited(resp, ZIP_COMPRESSED_CAP)
    if data is None:
        raise RuntimeError("%s: network error" % step)
    return data


def _fetch_runs(repo, token, default_branch):
    runs = []
    for page in range(1, 6):
        path = (
            "/actions/workflows/mutate-pr.yml/runs"
            "?event=workflow_dispatch&status=success&branch=%s&per_page=100&page=%d"
            % (default_branch, page)
        )
        # No workflow file on the default branch yet means there is no run.
        payload = _fetch_json(repo, token, path, "run list", missing_ok=True)
        if payload is None:
            return []
        if not isinstance(payload, dict):
            raise RuntimeError("run list: network error")
        batch = payload.get("workflow_runs") or []
        if not isinstance(batch, list):
            raise RuntimeError("run list: network error")
        runs.extend(batch)
        if len(batch) < 100:
            break
    return runs


def _plan_line(repo=None, base=None, bytecode_off=False):
    env = None
    if repo or base or bytecode_off:
        env = os.environ.copy()
        if bytecode_off:
            env["PYTHONDONTWRITEBYTECODE"] = "1"
        if repo:
            env["KEEL_MUTATE_REPO"] = repo
        if base:
            env["KEEL_MUTATE_BASE"] = base
            env.pop("GITHUB_BASE_REF", None)
    proc = subprocess.run(
        ["bash", os.path.join(HERE, "mutate-plan.sh")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return None
    line = proc.stdout.strip().splitlines()
    return line[-1] if line else ""


def _selector_ids(line):
    if line == mf.SKIP_LINE:
        return set()
    if line == mf.FULL_LINE:
        return set(mf.CI_IDS)
    prefix = "RESULT mutate: run "
    if isinstance(line, str) and line.startswith(prefix):
        parts = line[len(prefix):].split()
        if parts and all(MUTANT_ID_RE.fullmatch(part) for part in parts):
            return set(parts)
    return None


def _blob(repo, rev, rel):
    listed = ms._git(repo, "ls-tree", "-z", rev, "--", rel)
    item = listed.split(b"\0", 1)[0] if listed else b""
    if not item or b"\t" not in item:
        raise RuntimeError("catalog")
    meta, _path_b = item.split(b"\t", 1)
    mode, kind, oid = meta.decode("ascii").split(" ")
    if kind != "blob" or mode in ("120000", "160000"):
        raise RuntimeError("catalog")
    blob = ms._git(repo, "cat-file", "blob", oid)
    if len(blob) > CATALOG_CAP:
        raise RuntimeError("catalog")
    return blob.decode("utf-8")


def _defs_at(repo, rev):
    try:
        found = md.parse_literals(_blob(repo, rev, "setup/tests/harness/mutate.py"))
        found.update(md.parse_literals(_blob(repo, rev, "setup/tests/harness/mutant_files.py")))
        if not isinstance(found.get("M"), dict):
            return None
        return md.Defs(found)
    except Exception:
        return None


def _def_delta(base_defs, head_defs):
    return set(md.new_ids(base_defs.ids, head_defs.ids)), set(md.modified_ids(base_defs, head_defs))


def _required(selector_ids, new, modified):
    if use_defs != 1:
        return set(selector_ids)
    return set(selector_ids) | set(new) | set(modified)


def required_at_head(repo, base_sha):
    """Ids required for the checkout at HEAD compared with base_sha."""
    line = _plan_line(repo=repo, base=base_sha, bytecode_off=True)
    if line is None:
        raise RuntimeError("selection")
    selector = _selector_ids(line)
    if selector is None:
        raise RuntimeError("selection")
    base_defs = _defs_at(repo, base_sha)
    head_defs = _defs_at(repo, "HEAD")
    if base_defs is None or head_defs is None:
        raise RuntimeError("catalog")
    new, modified = _def_delta(base_defs, head_defs)
    return _required(selector, new, modified)


def _second_parent(repo):
    try:
        raw = ms._git(repo, "rev-parse", "--verify", "--quiet", "HEAD^2")
    except Exception:
        return ""
    sha = raw.decode().strip()
    if not SHA_RE.fullmatch(sha):
        return ""
    return sha


def _reject_dupes(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate")
        obj[key] = value
    return obj


def _bad_const(_name):
    raise ValueError("number")


def _strict_plan(text):
    try:
        data = json.loads(text, object_pairs_hook=_reject_dupes, parse_constant=_bad_const)
    except (ValueError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("skip") is not False:
        return None
    ids = data.get("ids")
    if not isinstance(ids, list) or len(ids) != len(set(ids)):
        return None
    if not all(isinstance(item, str) and MUTANT_ID_RE.fullmatch(item) for item in ids):
        return None
    main_sha = data.get("main_sha")
    if not isinstance(main_sha, str) or not main_sha:
        return None
    return data


def _read_plan(blob):
    if not isinstance(blob, (bytes, bytearray)) or len(blob) > ZIP_COMPRESSED_CAP:
        return None
    try:
        archive = zipfile.ZipFile(io.BytesIO(bytes(blob)))
    except zipfile.BadZipFile:
        return None
    try:
        infos = archive.infolist()
        if len(infos) != 1:
            return None
        info = infos[0]
        name = info.filename
        if name != "plan.json" or "/" in name or "\\" in name or name.endswith("/"):
            return None
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(unix_mode) or stat.S_ISDIR(unix_mode):
            return None
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            return None
        if info.file_size > ZIP_UNCOMPRESSED_CAP or info.compress_size > ZIP_COMPRESSED_CAP:
            return None
        raw = archive.open(info, "r")
        try:
            data = raw.read(ZIP_UNCOMPRESSED_CAP + 1)
        finally:
            raw.close()
    except Exception:
        return None
    finally:
        archive.close()
    if len(data) > ZIP_UNCOMPRESSED_CAP:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        return None
    return _strict_plan(text)


def _digest_word(entry, blob):
    if not isinstance(entry, dict) or "digest" not in entry or entry.get("digest") is None:
        return "digest not given", True
    digest = entry.get("digest")
    if not isinstance(digest, str):
        return "digest", False
    value = digest[len("sha256:"):] if digest.startswith("sha256:") else digest
    if not DIGEST_RE.fullmatch(value):
        return "digest", False
    actual = hashlib.sha256(bytes(blob)).hexdigest()
    if value.lower() != actual:
        return "digest", False
    return "digest matches", True


def _pick_entry(entries, run_id):
    if not isinstance(entries, list):
        return None, "shape"
    if one_plan != 1:
        if not entries or not isinstance(entries[0], dict):
            return None, "no plan"
        return entries[0], ""
    chosen = []
    foreign = False
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("name") != "plan":
            continue
        if entry.get("expired") is True:
            continue
        owner = entry.get("workflow_run")
        owner_id = owner.get("id") if isinstance(owner, dict) else None
        if owner_id != run_id:
            foreign = True
            continue
        chosen.append(entry)
    if len(chosen) != 1:
        if foreign and not chosen:
            return None, "foreign artifact"
        return None, "no plan"
    return chosen[0], ""


def _plan_from_parts(entries, run_id, blob, check_digest):
    entry, reason = _pick_entry(entries, run_id)
    if entry is None:
        return None, reason
    if not isinstance(blob, (bytes, bytearray)):
        return None, "no plan"
    digest_word = "digest not given"
    if check_digest:
        digest_word, ok = _digest_word(entry, blob)
        if not ok:
            return None, digest_word
    plan = _read_plan(blob)
    if plan is None:
        return None, "shape"
    return plan, digest_word


def _plan_covers(plan, required):
    if require_plan != 1:
        return True
    if not isinstance(plan, dict):
        return False
    ids = plan.get("ids")
    if not isinstance(ids, list) or plan.get("skip") is not False:
        return False
    return set(required) <= set(ids)


def _missing_ids(plan, required):
    have = set(plan.get("ids") or []) if isinstance(plan, dict) else set()
    return set(required) - have


def _show_ids(ids):
    ordered = sorted(ids, key=lambda item: (len(item), item))
    shown = ordered[:MISSING_ID_CAP]
    text = " ".join(shown)
    if len(ordered) > MISSING_ID_CAP:
        text += " ..."
    return text


def _bind(head_sha, checkout_sha, runs, required, load, default_branch="main"):
    """Return (status, detail). load(run) returns (plan, word) or (None, reason)."""
    if check_head == 1:
        if not checkout_sha:
            return "parent", None
        if head_sha != checkout_sha:
            return "mismatch", None
    inspected = 0
    for run in runs or []:
        if not run_matches(head_sha, run, default_branch):
            continue
        inspected += 1
        if inspected > MAX_MATCHING_RUNS:
            break
        plan, word = load(run)
        if plan is None or not _plan_covers(plan, required):
            continue
        return "bound", (run, plan, word)
    return "missing", None


def _runs_newest(runs):
    def key(run):
        if isinstance(run, dict) and isinstance(run.get("id"), int):
            return run["id"]
        return -1

    return sorted(runs or [], key=key, reverse=True)


def _artifact_id(entry):
    value = entry.get("id") if isinstance(entry, dict) else None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None


def _load_remote(repo, token, run):
    run_id = run.get("id") if isinstance(run, dict) else None
    if not isinstance(run_id, int) or run_id < 1:
        return None, "no plan"
    payload = _fetch_json(
        repo, token, "/actions/runs/%d/artifacts?per_page=100" % run_id, "artifact list"
    )
    if not isinstance(payload, dict):
        raise RuntimeError("artifact list: network error")
    entries = payload.get("artifacts")
    if not isinstance(entries, list):
        raise RuntimeError("artifact list: network error")
    total = payload.get("total_count")
    if isinstance(total, int) and total > len(entries):
        raise RuntimeError("artifact list: network error")
    entry, _reason = _pick_entry(entries, run_id)
    if entry is None:
        return None, "no plan"
    artifact = _artifact_id(entry)
    if artifact is None:
        return None, "no plan"
    blob = _fetch_bytes(repo, token, "/actions/artifacts/%d/zip" % artifact, "artifact download")
    return _plan_from_parts(entries, run_id, blob, False)


def _how(kind):
    if kind == "mismatch" or kind == "parent":
        return "how to fix: re-run the checks for the current head"
    return "how to fix: dispatch mutate-pr again for this head"


def _fail_line(sha, kind, required):
    if kind == "mismatch":
        print("mutants: head changed %s" % sha, file=sys.stderr)
    elif kind == "parent":
        print("mutants: checkout head missing %s" % sha, file=sys.stderr)
    else:
        print("mutants: missing %s: %s" % (sha, _show_ids(required)), file=sys.stderr)
    print(_how(kind), file=sys.stderr)


def _gate_repo():
    return os.environ.get("KEEL_MUTATE_REPO") or os.getcwd()


def _gate_main():
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event != "pull_request":
        print("mutants: not a pull request")
        return 0
    repo = _gate_repo()
    line = _plan_line()
    if line is None:
        print("mutants: selection failed", file=sys.stderr)
        return 1
    selector = _selector_ids(line)
    if selector is None:
        print("mutants: selection failed", file=sys.stderr)
        return 1
    base = os.environ.get("KEEL_MUTATE_BASE") or os.environ.get("GATE_PR_BASE_SHA") or ""
    base_defs = _defs_at(repo, base) if base else None
    head_defs = _defs_at(repo, "HEAD")
    if base_defs is None or head_defs is None:
        print("mutants: selection failed", file=sys.stderr)
        return 1
    new, modified = _def_delta(base_defs, head_defs)
    required = _required(selector, new, modified)
    if not required:
        print("mutants: not required")
        return 0
    checkout = _second_parent(repo) if check_head == 1 else "unchecked"
    if check_head == 1 and not checkout:
        print("mutants: checkout head missing", file=sys.stderr)
        print(_how("parent"), file=sys.stderr)
        return 1
    number = pr_number(os.environ.get("GITHUB_REF", ""))
    if not number:
        print("mutants: pull request ref missing", file=sys.stderr)
        return 1
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    default_branch = os.environ.get("DEFAULT_BRANCH") or "main"
    if not token:
        print("mutants: token missing", file=sys.stderr)
        return 1
    try:
        pull = _fetch_json(gh_repo, token, "/pulls/" + number, "run record")
    except RuntimeError as err:
        print("mutants: %s" % err, file=sys.stderr)
        return 1
    sha = pull_head_sha(pull)
    if not sha:
        print("mutants: head sha missing", file=sys.stderr)
        return 1
    if check_head == 1 and sha != checkout:
        _fail_line(sha, "mismatch", required)
        return 1
    try:
        runs = _runs_newest(_fetch_runs(gh_repo, token, default_branch))
    except RuntimeError as err:
        print("mutants: %s" % err, file=sys.stderr)
        return 1

    def load(run):
        return _load_remote(gh_repo, token, run)

    try:
        status, detail = _bind(sha, checkout or sha, runs, required, load, default_branch)
    except RuntimeError as err:
        print("mutants: %s" % err, file=sys.stderr)
        return 1
    if status == "bound":
        run, plan, _word = detail
        print(
            "mutants: bound %s run %s %s covers %d of %d"
            % (sha, run.get("id"), plan.get("main_sha"), len(required), len(required))
        )
        return 0
    _fail_line(sha, "missing", required)
    return 1


def _saved_error(text):
    print(text, file=sys.stderr)
    return 1


def _parse_saved(argv):
    if not argv:
        return None
    if argv == ["--self-test"]:
        return None
    names = set(SAVED_OPTS)
    if argv[0] != "--check-saved-run":
        return _saved_error("mutants: bad arguments")
    rest = argv[1:]
    if len(rest) != 10:
        return _saved_error("mutants: bad arguments")
    seen = {}
    index = 0
    while index < len(rest):
        key = rest[index]
        if key not in names or key in seen or index + 1 >= len(rest):
            return _saved_error("mutants: bad arguments")
        value = rest[index + 1]
        if value.startswith("--"):
            return _saved_error("mutants: bad arguments")
        seen[key] = value
        index += 2
    if set(seen) != names:
        return _saved_error("mutants: bad arguments")
    if not SHA_RE.fullmatch(seen["--expect-head"]) or not SHA_RE.fullmatch(seen["--base"]):
        return _saved_error("mutants: bad arguments")
    return seen


def _saved_status():
    repo = os.getcwd()
    try:
        head = ms._git(repo, "rev-parse", "HEAD").decode().strip()
        dirty = ms._git(repo, "status", "--porcelain=v1", "--untracked-files=normal")
    except Exception:
        return "", "checkout"
    return head, "dirty tree" if dirty.strip() else ""


def _read_capped(path, cap):
    try:
        with open(path, "rb") as handle:
            data = handle.read(cap + 1)
    except OSError:
        return None
    if len(data) > cap:
        return None
    return data


def _saved_missing(reason):
    print("missing: %s" % reason)
    return 1


def _saved_run(opts):
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    expect = opts["--expect-head"]
    base = opts["--base"]
    head, problem = _saved_status()
    if problem == "checkout":
        return _saved_missing("checkout")
    if head != expect:
        return _saved_missing("head mismatch")
    if problem:
        return _saved_missing(problem)
    run_blob = _read_capped(opts["--run"], BODY_CAP)
    list_blob = _read_capped(opts["--list"], BODY_CAP)
    zip_blob = _read_capped(opts["--zip"], ZIP_COMPRESSED_CAP)
    if run_blob is None or list_blob is None or zip_blob is None:
        return _saved_missing("shape")
    try:
        run = json.loads(run_blob.decode("utf-8"))
        listed = json.loads(list_blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _saved_missing("shape")
    if not isinstance(run, dict) or not isinstance(listed, dict):
        return _saved_missing("shape")
    if not run_matches(expect, run, "main"):
        return _saved_missing("run does not match")
    entries = listed.get("artifacts")
    if not isinstance(entries, list):
        return _saved_missing("no plan")
    try:
        required = required_at_head(os.getcwd(), base)
    except RuntimeError:
        return _saved_missing("shape")
    plan, word = _plan_from_parts(entries, run.get("id"), zip_blob, True)
    if plan is None:
        return _saved_missing(word or "no plan")
    if not _plan_covers(plan, required):
        missing = _missing_ids(plan, required)
        return _saved_missing("under-cover " + _show_ids(missing))
    k = len(required)
    n = len(plan.get("ids") or [])
    print(
        "%s %s %s %s %s covers %d of %d, plan %d %s"
        % (
            expect,
            run.get("display_title") or "",
            run.get("conclusion") or "",
            run.get("id"),
            plan.get("main_sha"),
            k,
            k,
            n,
            word,
        )
    )
    return 0


def _sample(sha, **overrides):
    run = {
        "id": 1,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "conclusion": "success",
        "path": WORKFLOW_PATH,
        "display_title": title_for(sha),
    }
    run.update(overrides)
    return run


def _plan_obj(ids, main_sha):
    return {"ids": list(ids), "skip": False, "main_sha": main_sha}


def self_test():
    """Happy path, plan coverage, and the saved-run mode. No network."""
    sha = "0123456789abcdef0123456789abcdef01234567"
    old = "fedcba9876543210fedcba9876543210fedcba98"
    harness = ["setup/keel.sh"]
    docs = ["docs/status.md"]
    good = [_sample(sha)]
    fail = 0

    def res(name, ok, detail):
        nonlocal fail
        if ok:
            print("RESULT %s: BLOCKED (%s)" % (name, detail))
        else:
            fail = 1
            print("RESULT %s: NOT BLOCKED (%s)" % (name, detail))

    def live_decision(event, live, changed, runs, default_branch="main"):
        if event != "pull_request":
            return "push"
        status, _ids = mf.select_mutants(list(changed))
        if status == "skip":
            return "skip"
        if not SHA_RE.fullmatch(live or ""):
            return "bad-sha"
        if any(run_matches(live, run, default_branch) for run in runs or []):
            return "bound"
        return "missing"

    bound = live_decision("pull_request", sha, harness, good)
    skipped = live_decision("pull_request", sha, docs, [])
    ref_ok = pr_number("refs/pull/35/merge") == "35" and pr_number("refs/heads/main") is None
    head_ok = pull_head_sha({"head": {"sha": sha}, "merge_commit_sha": old}) == sha
    res(
        "M-H1",
        bound == "bound" and skipped == "skip" and ref_ok and head_ok,
        "head sha bound; docs diff needs no run",
    )

    stale = live_decision("pull_request", sha, harness, [_sample(old)])
    res("M-A1", stale == "missing", "stale sha stays red")

    missing = live_decision("pull_request", sha, harness, [])
    bad = live_decision("pull_request", "not-a-sha", harness, good)
    res("M-A2", missing == "missing" and bad == "bad-sha", "missing run stays red")

    spoofs = [
        _sample(sha, event="pull_request"),
        _sample(sha, head_branch="feature"),
        _sample(sha, path=".github/workflows/mutate-full.yml"),
        _sample(sha, conclusion="failure"),
        _sample(sha, display_title="mutants passed"),
        _sample(sha, display_title=title_for(sha) + " extra"),
    ]
    spoofed = all(live_decision("pull_request", sha, harness, [run]) == "missing" for run in spoofs)
    ignored = live_decision(
        "pull_request",
        sha,
        harness,
        [{"comment": "mutants " + sha, "artifacts": [{"name": "mutant-sha"}]}],
    )
    res("M-A3", spoofed and ignored == "missing", "untrusted result stays red")

    main_sha = "a" * 40
    required = {"M01", "M02"}
    calls = {"n": 0}

    def covering(run):
        calls["n"] += 1
        if run.get("id") == 3:
            return _plan_obj(["M01"], main_sha), "digest not given"
        return _plan_obj(["M01", "M02"], main_sha), "digest not given"

    one = _bind(sha, sha, [_sample(sha, id=8)], required, covering)
    two = _bind(sha, sha, [_sample(sha, id=3), _sample(sha, id=2)], required, covering)
    line_ok = one[0] == "bound" and "covers %d of %d" % (len(required), len(required))
    older_ok = two[0] == "bound" and two[1][0]["id"] == 2
    res("M-H2", bool(line_ok) and older_ok, "covering plan binds, including an older run")

    def lacking(run):
        calls["n"] += 1
        return _plan_obj(["M01"], main_sha), "digest not given"

    lack = _bind(sha, sha, [_sample(sha, id=4)], required, lacking)
    lack_ids = _missing_ids(lack[1][0] if lack[0] == "bound" else _plan_obj(["M01"], main_sha), required)

    def no_plan(run):
        calls["n"] += 1
        return None, "no plan"

    none = _bind(sha, sha, [_sample(sha, id=5)], required, no_plan)
    res(
        "M-A5",
        lack[0] == "missing" and "M02" in lack_ids and none[0] == "missing",
        "a plan that omits a required id stays red",
    )

    res("M-A6", _case_definitions(), "new and changed definitions are required")
    res("M-A7", _case_redirects(), "redirect hops stay on https without the request header")
    res("M-A8", _case_shapes(), "a plan archive of the wrong shape covers nothing")
    quiet = {"n": 0}

    def boom(run):
        quiet["n"] += 1
        raise RuntimeError("run record: 500")

    docs_required = _required(set(), set(), set())
    empty_required = _required(set(), set(), set())
    ignored = _case_gate_ignores(boom, quiet)
    res(
        "M-A10",
        docs_required == set() and empty_required == set() and ignored and quiet["n"] == 0,
        "gate mode ignores saved files",
    )
    saved_ok, saved_detail = _case_saved()
    res("M-H3", saved_ok, saved_detail)
    res("M-A11", _case_saved_misses(), "saved run mismatches stay red")
    res("M-A9", _case_heads(), "the live head must match the checkout head")
    return 1 if fail else 0


def _case_definitions():
    """Selector skip plus one changed id, and a definition that is only added."""
    base = md.Defs({
        "M": {"M01": ["keel.sh", "old", "new", "what", ["A1"]]},
        "SUITE_OF": {"M01": "test-attacks.sh"},
        "EXTRA_EDITS": {},
        "COPY_LIST": ["keel.sh"],
    })
    changed = md.Defs({
        "M": {"M01": ["keel.sh", "old", "other", "what", ["A1"]]},
        "SUITE_OF": {"M01": "test-attacks.sh"},
        "EXTRA_EDITS": {},
        "COPY_LIST": ["keel.sh"],
    })
    added = md.Defs({
        "M": {
            "M01": ["keel.sh", "old", "new", "what", ["A1"]],
            "M02": ["keel.sh", "old2", "new2", "what", ["A1"]],
        },
        "SUITE_OF": {"M01": "test-attacks.sh", "M02": "test-attacks.sh"},
        "EXTRA_EDITS": {},
        "COPY_LIST": ["keel.sh"],
    })
    new_c, mod_c = _def_delta(base, changed)
    exact = _required(set(), new_c, mod_c)
    if exact != {"M01"}:
        return False
    plan = _plan_obj([], "b" * 40)
    if _plan_covers(plan, exact):
        return False
    if "M01" not in _missing_ids(plan, exact):
        return False
    new_a, mod_a = _def_delta(base, added)
    widened = _required(set(), new_a, mod_a)
    if "M02" not in widened:
        return False
    if _plan_covers(_plan_obj(["M01"], "b" * 40), widened):
        return False
    return True


def _case_redirects():
    import http.client
    from email.message import Message

    token = "zz-sample-value"
    body_marker = "BODYMARKER"
    storage = "https://objects.example.test/marker-place"
    seen = []
    script = {"items": []}

    https_type = http.client.HTTPSConnection
    real_request = http.client.HTTPConnection.request
    real_getresponse = http.client.HTTPConnection.getresponse

    def fake_request(self, method, selector, _data=None, headers=None, *, encode_chunked=False):
        scheme = "https" if isinstance(self, https_type) else "http"
        seen.append({
            "scheme": scheme,
            "host": self.host,
            "selector": selector,
            "headers": dict(headers or {}),
            "method": method,
        })

    def fake_getresponse(self):
        item = script["items"].pop(0)
        msg = Message()
        for key, value in item.get("headers", {}).items():
            msg[key] = value
        return _FakeResp(item["code"], msg, item.get("body", b""))

    class _FakeResp(object):
        def __init__(self, code, headers, body):
            self.code = code
            self.status = code
            self.reason = "status"
            self._headers = headers
            self._body = body

        def info(self):
            return self._headers

        def read(self, n=-1):
            if n is None or n < 0 or n >= len(self._body):
                data = self._body
                self._body = b""
                return data
            data = self._body[:n]
            self._body = self._body[n:]
            return data

        def close(self):
            return None

    http.client.HTTPConnection.request = fake_request
    http.client.HTTPConnection.getresponse = fake_getresponse
    try:
        return _redirect_scenarios(token, body_marker, storage, seen, script)
    finally:
        http.client.HTTPConnection.request = real_request
        http.client.HTTPConnection.getresponse = real_getresponse


def _header_problem(headers, token):
    for key, value in headers.items():
        if _auth_header_name(key):
            return True
        if token in str(value):
            return True
    return False


def _redirect_scenarios(token, body_marker, storage, seen, script):
    import contextlib

    repo = "owner/repo"

    def play(items, step, path):
        seen.clear()
        script["items"] = list(items)
        out = io.StringIO()
        err = io.StringIO()
        caught = None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                resp = _open(step, _request(repo, token, path))
                if resp is not None:
                    resp.read()
                    resp.close()
            except RuntimeError as err_run:
                caught = str(err_run)
        return caught, out.getvalue() + err.getvalue(), list(seen)

    def hop(code, location, body=b"{}"):
        return {"code": code, "headers": {"Location": location}, "body": body}

    def ok():
        return {"code": 200, "headers": {}, "body": b"{}"}

    api = "https://api.github.com/repos/owner/repo/actions/artifacts/7/zip"
    cross = "https://objects.example.test/one"
    same = "https://api.github.com/repos/owner/repo/elsewhere"
    down = "http://objects.example.test/one"
    second = "https://objects.example.test/two"
    scenarios = [
        ("artifact download", "/actions/artifacts/7/zip", [hop(302, cross), ok()], False),
        ("artifact download", "/actions/artifacts/7/zip", [hop(302, same), ok()], False),
        ("artifact download", "/actions/artifacts/7/zip", [hop(302, down)], True),
        ("artifact download", "/actions/artifacts/7/zip", [hop(302, cross), hop(302, second), ok()], False),
    ]
    for step, path, items, must_fail in scenarios:
        caught, text, rows = play(items, step, path)
        if not rows:
            return False
        first = rows[0]
        if first["scheme"] != "https" or not str(first["host"]).startswith(API_HOST):
            return False
        if "Bearer " + token not in str(first["headers"].get("Authorization", "")):
            return False
        if must_fail:
            if caught is None or len(rows) != 1:
                return False
        else:
            if caught is not None or len(rows) != len(items):
                return False
            for row in rows[1:]:
                if row["scheme"] != "https":
                    return False
                if _header_problem(row["headers"], token):
                    return False
                if token in row["selector"] or token in str(row["host"]):
                    return False
        if token in text or storage in text or body_marker in text:
            return False
        if api not in (first["scheme"] + "://" + str(first["host"]).split(":")[0] + first["selector"]):
            if "/actions/artifacts/7/zip" not in first["selector"]:
                return False
    caught, text, rows = play(
        [{
            "code": 403,
            "headers": {"Location": storage},
            "body": body_marker.encode("utf-8"),
        }],
        "artifact list",
        "/actions/runs/1/artifacts?per_page=100",
    )
    if caught != "artifact list: 403":
        return False
    if token in text or storage in text or body_marker in text or "Location" in text:
        return False
    if len(rows) != 1:
        return False
    return True


def _zip_bytes(obj, name="plan.json", method=zipfile.ZIP_DEFLATED, extra=()):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        info = zipfile.ZipInfo(name)
        info.compress_type = method
        payload = obj if isinstance(obj, (bytes, bytearray)) else json.dumps(obj).encode("utf-8")
        archive.writestr(info, payload)
        for extra_name, extra_obj in extra:
            archive.writestr(extra_name, json.dumps(extra_obj))
    return buf.getvalue()


def _covers(blob, entries, run_id=9):
    plan, _word = _plan_from_parts(entries, run_id, blob, False)
    if plan is None:
        return False
    return _plan_covers(plan, set(plan["ids"]))


def _entry(run_id=9, expired=False):
    return {
        "id": 7,
        "name": "plan",
        "expired": expired,
        "workflow_run": {"id": run_id},
    }


def _case_shapes():
    good = _plan_obj(["M01"], "c" * 40)
    blob = _zip_bytes(good)
    one = [_entry()]
    if not _covers(blob, one):
        return False
    if _covers(blob, []):
        return False
    if _covers(blob, [_entry(), _entry(run_id=9)]):
        return False
    if _covers(blob, [_entry(expired=True)]):
        return False
    if _covers(b"x" * (ZIP_COMPRESSED_CAP + 1), one):
        return False
    huge = {"ids": ["M01"], "skip": False, "main_sha": "c" * 40, "pad": "p" * (ZIP_UNCOMPRESSED_CAP + 8)}
    if _covers(_zip_bytes(huge), one):
        return False
    if _covers(_zip_bytes(good, extra=(("other.json", {"a": 1}),)), one):
        return False
    if _covers(_zip_bytes(good, name="dir/plan.json"), one):
        return False
    if _covers(_zip_bytes(good, name="plan.json/"), one):
        return False
    link = _zip_bytes(good)
    # A stored symlink is not a regular entry. Rebuild with the symlink bit set.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        info = zipfile.ZipInfo("plan.json")
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b"elsewhere")
    if _covers(buf.getvalue(), one):
        return False
    if _covers(_zip_bytes(good, method=zipfile.ZIP_BZIP2), one):
        return False
    if _covers(_zip_bytes(b"{", ), one):
        return False
    dup = b'{"ids": ["M01"], "ids": ["M02"], "skip": false, "main_sha": "%s"}' % (b"c" * 40)
    if _covers(_zip_bytes(dup), one):
        return False
    if _covers(_zip_bytes({"ids": ["M01"], "skip": False, "main_sha": "c" * 40, "n": float("nan")}), one):
        return False
    if _covers(_zip_bytes(["M01"]), one):
        return False
    if _covers(_zip_bytes({"ids": ["M01"], "skip": True, "main_sha": "c" * 40}), one):
        return False
    if _covers(_zip_bytes({"ids": ["M01", "M01"], "skip": False, "main_sha": "c" * 40}), one):
        return False
    if _covers(_zip_bytes({"ids": ["nope"], "skip": False, "main_sha": "c" * 40}), one):
        return False
    lied = bytearray(_zip_bytes(good))
    local = lied.find(b"PK\x03\x04")
    central = lied.find(b"PK\x01\x02")
    if local < 0 or central < 0:
        return False
    huge = (ZIP_UNCOMPRESSED_CAP + 50).to_bytes(4, "little")
    lied[local + 22:local + 26] = huge
    lied[central + 24:central + 28] = huge
    if _covers(bytes(lied), one):
        return False
    return True


def _case_gate_ignores(boom, quiet):
    import contextlib
    import tempfile

    real_plan = _plan_line
    real_defs = _defs_at
    real_open = _open
    base = md.Defs({
        "M": {"M01": ["keel.sh", "old", "new", "what", ["A1"]]},
        "SUITE_OF": {"M01": "test-attacks.sh"},
        "EXTRA_EDITS": {},
        "COPY_LIST": ["keel.sh"],
    })

    def skip_line(repo=None, base=None, bytecode_off=False):
        return mf.SKIP_LINE

    def same_defs(repo, rev):
        return base

    def counting(step, req):
        quiet["n"] += 1
        raise RuntimeError("run record: 500")

    folder = tempfile.mkdtemp(prefix="saved-")
    keys = (
        "CHECK_SAVED_RUN",
        "EXPECT_HEAD",
        "BASE",
        "RUN",
        "LIST",
        "ZIP",
    )
    previous = {key: os.environ.get(key) for key in keys}
    cwd = os.getcwd()
    try:
        for name in ("run.json", "list.json", "plan.zip"):
            with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                handle.write("{}\n")
        os.chdir(folder)
        for present in (False, True):
            quiet["n"] = 0
            globals()["_plan_line"] = skip_line
            globals()["_defs_at"] = same_defs
            globals()["_open"] = counting
            if present:
                os.environ["CHECK_SAVED_RUN"] = "1"
                os.environ["EXPECT_HEAD"] = "ab" * 20
                os.environ["BASE"] = "cd" * 20
                os.environ["RUN"] = os.path.join(folder, "run.json")
                os.environ["LIST"] = os.path.join(folder, "list.json")
                os.environ["ZIP"] = os.path.join(folder, "plan.zip")
            else:
                for key in keys:
                    os.environ.pop(key, None)
            os.environ["GITHUB_EVENT_NAME"] = "pull_request"
            os.environ["KEEL_MUTATE_BASE"] = "b" * 40
            held_out = io.StringIO()
            with contextlib.redirect_stdout(held_out):
                code = _gate_main()
            if code != 0 or quiet["n"] != 0:
                return False
        bad_forms = [
            ["--check-saved-run"],
            ["--expect-head", "ab" * 20],
            ["--check-saved-run", "--expect-head", "zz", "--base", "ab" * 20,
             "--run", "r", "--list", "l", "--zip", "z"],
            ["--check-saved-run", "--expect-head", "ab" * 20, "--expect-head", "ab" * 20,
             "--base", "cd" * 20, "--run", "r", "--list", "l", "--zip", "z"],
            ["--check-saved-run", "--nope", "1", "--expect-head", "ab" * 20,
             "--base", "cd" * 20, "--run", "r", "--list", "l"],
            ["--self-test", "--check-saved-run"],
        ]
        for argv in bad_forms:
            err = io.StringIO()
            old = sys.stderr
            sys.stderr = err
            try:
                code = main(argv)
            finally:
                sys.stderr = old
            if code == 0 or not err.getvalue().strip():
                return False
        return True
    finally:
        globals()["_plan_line"] = real_plan
        globals()["_defs_at"] = real_defs
        globals()["_open"] = real_open
        os.chdir(cwd)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        os.environ.pop("GITHUB_EVENT_NAME", None)
        os.environ.pop("KEEL_MUTATE_BASE", None)
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def _git(repo, *args):
    proc = subprocess.run(
        ["git", "-C", repo, "-c", "user.email=dev@example.com", "-c", "user.name=Dev",
         "-c", "commit.gpgsign=false", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git")
    return proc.stdout.strip()


def _case_saved():
    import contextlib
    import shutil
    import tempfile

    repo = tempfile.mkdtemp(prefix="saved-run-")
    folder = None
    try:
        _git(repo, "init", "-q", "-b", "main")
        harness = os.path.join(repo, "setup", "tests", "harness")
        os.makedirs(harness)
        for name in ("mutate.py", "mutant_files.py"):
            src = os.path.join(HERE, name)
            with open(src, "rb") as handle:
                data = handle.read()
            with open(os.path.join(harness, name), "wb") as handle:
                handle.write(data)
        keel = os.path.join(repo, "setup", "keel.sh")
        os.makedirs(os.path.dirname(keel), exist_ok=True)
        with open(keel, "w", encoding="utf-8") as handle:
            handle.write("old\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "base")
        base = _git(repo, "rev-parse", "HEAD")
        _git(repo, "checkout", "-q", "-b", "pr")
        with open(keel, "w", encoding="utf-8") as handle:
            handle.write("new\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "pr")
        head = _git(repo, "rev-parse", "HEAD")
        _git(repo, "checkout", "-q", "main")
        held = os.environ.get("GITHUB_ACTIONS"), os.environ.get("DEFAULT_BRANCH")
        os.environ.pop("GITHUB_ACTIONS", None)
        os.environ["DEFAULT_BRANCH"] = "main"
        try:
            quiet = io.StringIO()
            with contextlib.redirect_stdout(quiet):
                code, info = ms.decide_plan(repo, head, "main")
        finally:
            if held[0] is None:
                os.environ.pop("GITHUB_ACTIONS", None)
            else:
                os.environ["GITHUB_ACTIONS"] = held[0]
            if held[1] is None:
                os.environ.pop("DEFAULT_BRANCH", None)
            else:
                os.environ["DEFAULT_BRANCH"] = held[1]
        if code != 0 or not info or not info.get("plan"):
            return False, "planner produced no plan"
        _git(repo, "checkout", "-q", "--detach", head)
        plan = {
            "ids": list(info["plan"]),
            "skip": False,
            "main_sha": info["main_sha"],
        }
        blob = _zip_bytes(plan)
        digest = hashlib.sha256(blob).hexdigest()
        run = _sample(head, id=4242)
        folder = tempfile.mkdtemp(prefix="saved-in-")
        listed = {
            "artifacts": [{
                "id": 7,
                "name": "plan",
                "expired": False,
                "digest": "sha256:" + digest,
                "workflow_run": {"id": 4242},
            }]
        }
        paths = _write_saved(folder, run, listed, blob)
        first = _invoke_saved(repo, head, base, paths)
        if first[0] != 0 or head not in first[1] or "covers " not in first[1] or "digest matches" not in first[1]:
            return False, "first saved run"
        second = _invoke_saved(repo, head, base, paths)
        if second[0] != 0 or second[1] != first[1]:
            return False, "second saved run"
        if _pycache(repo):
            return False, "bytecode cache"
        listed["artifacts"][0]["digest"] = None
        paths = _write_saved(folder, run, listed, blob)
        third = _invoke_saved(repo, head, base, paths)
        if third[0] != 0 or "digest not given" not in third[1]:
            return False, "null digest"
        if _pycache(repo):
            return False, "bytecode cache"
        k = third[1].split("covers ", 1)[-1].split(" ", 1)[0]
        return True, "saved run covers %s and ignores a null digest" % k
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        if folder:
            shutil.rmtree(folder, ignore_errors=True)


def _pycache(root):
    for dirpath, dirnames, _filenames in os.walk(root):
        if "__pycache__" in dirnames:
            return True
        if dirpath.endswith("__pycache__"):
            return True
    return False


def _write_saved(folder, run, listed, blob):
    run_path = os.path.join(folder, "run.json")
    list_path = os.path.join(folder, "list.json")
    zip_path = os.path.join(folder, "plan.zip")
    with open(run_path, "w", encoding="utf-8") as handle:
        json.dump(run, handle)
    with open(list_path, "w", encoding="utf-8") as handle:
        json.dump(listed, handle)
    with open(zip_path, "wb") as handle:
        handle.write(blob)
    return run_path, list_path, zip_path


def _invoke_saved(repo, head, base, paths):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_EVENT_NAME"):
        env.pop(key, None)
    proc = subprocess.run(
        [
            sys.executable, "-B", os.path.join(HERE, "mutant-result.py"),
            "--check-saved-run",
            "--expect-head", head,
            "--base", base,
            "--run", paths[0],
            "--list", paths[1],
            "--zip", paths[2],
        ],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _case_saved_misses():
    import shutil
    import tempfile

    repo = tempfile.mkdtemp(prefix="saved-miss-")
    folder = None
    try:
        _git(repo, "init", "-q", "-b", "main")
        harness = os.path.join(repo, "setup", "tests", "harness")
        os.makedirs(harness)
        for name in ("mutate.py", "mutant_files.py"):
            with open(os.path.join(HERE, name), "rb") as handle:
                data = handle.read()
            with open(os.path.join(harness, name), "wb") as handle:
                handle.write(data)
        with open(os.path.join(repo, "setup", "TESTING.md"), "w", encoding="utf-8") as handle:
            handle.write("doc\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "base")
        base = _git(repo, "rev-parse", "HEAD")
        head = base
        plan = _plan_obj(["M01"], base)
        blob = _zip_bytes(plan)
        digest = hashlib.sha256(blob).hexdigest()
        run = _sample(head, id=11)
        folder = tempfile.mkdtemp(prefix="saved-in-")
        good_list = {
            "artifacts": [{
                "id": 7,
                "name": "plan",
                "expired": False,
                "digest": "sha256:" + digest,
                "workflow_run": {"id": 11},
            }]
        }
        cases = []
        bare = dict(good_list)
        bare["artifacts"] = []
        cases.append(bare)
        titled = _sample(head, id=11, display_title="mutants " + ("ab" * 20))
        cases_run = [titled]
        failed = _sample(head, id=11, conclusion="failure")
        cases_run.append(failed)
        pushed = _sample(head, id=11, event="push")
        cases_run.append(pushed)
        branched = _sample(head, id=11, head_branch="other")
        cases_run.append(branched)
        other_path = _sample(head, id=11, path=".github/workflows/mutate-full.yml")
        cases_run.append(other_path)
        foreign = json.loads(json.dumps(good_list))
        foreign["artifacts"][0]["workflow_run"] = {"id": 99}
        bad_digest = json.loads(json.dumps(good_list))
        bad_digest["artifacts"][0]["digest"] = "sha256:" + ("ab" * 32)
        malformed = json.loads(json.dumps(good_list))
        malformed["artifacts"][0]["digest"] = "sha256:zz"
        for listed in (bare, foreign, bad_digest, malformed):
            paths = _write_saved(folder, run, listed, blob)
            code, out, _err = _invoke_saved(repo, head, base, paths)
            if code == 0 or not out.startswith("missing:"):
                return False
        for item in cases_run:
            paths = _write_saved(folder, item, good_list, blob)
            code, out, _err = _invoke_saved(repo, head, base, paths)
            if code == 0 or "run does not match" not in out:
                return False
        code, out, _err = _invoke_saved(repo, "ab" * 20, base, _write_saved(folder, run, good_list, blob))
        if code == 0 or "head mismatch" not in out:
            return False
        stray = os.path.join(harness, "stray.py")
        with open(stray, "w", encoding="utf-8") as handle:
            handle.write("x = 1\n")
        code, out, _err = _invoke_saved(repo, head, base, _write_saved(folder, run, good_list, blob))
        os.remove(stray)
        if code == 0 or "dirty tree" not in out:
            return False
        return True
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        if folder:
            shutil.rmtree(folder, ignore_errors=True)


def _case_heads():
    sha = "11" * 20
    other = "22" * 20
    required = {"M01"}
    run = _sample(sha, id=6)
    other_run = _sample(other, id=7)

    def load(item):
        return _plan_obj(["M01"], "e" * 40), "digest not given"

    mismatch = _bind(sha, other, [run, other_run], required, load)
    parent = _bind(sha, "", [run], required, load)
    if mismatch[0] != "mismatch" or parent[0] != "parent":
        return False
    # A covering run for either sha still does not bind.
    return mismatch[1] is None and parent[1] is None


def mutants_satisfied(head_sha, runs, default_branch="main"):
    for run in runs or []:
        if run_matches(head_sha, run, default_branch):
            return True
    return False


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--self-test"]:
        return self_test()
    if not argv:
        return _gate_main()
    parsed = _parse_saved(argv)
    if not isinstance(parsed, dict):
        return 1
    return _saved_run(parsed)


if __name__ == "__main__":
    sys.exit(main())
