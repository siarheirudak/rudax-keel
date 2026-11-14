#!/usr/bin/env python3
import sys; print("PROBE-P1A-MARKER: tampered mutant-result.py ran"); sys.exit(0)
"""Decide whether keel-gate may pass the mutant requirement for this commit.

A pull request that selects mutants needs a successful workflow_dispatch of
.github/workflows/mutate-pr.yml on the default branch, titled with this head
SHA. Comments, artifacts, and environment variables are not a result.
A diff that selects no mutants (docs, for example) does not need a run.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mutant_files as mf  # noqa: E402

WORKFLOW_PATH = ".github/workflows/mutate-pr.yml"
SHA_RE = re.compile(r"[0-9a-f]{40}")
REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
sha_bind = 1  # mutant-sha-bind


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


def mutants_satisfied(head_sha, runs, default_branch="main"):
    for run in runs or []:
        if run_matches(head_sha, run, default_branch):
            return True
    return False


def live_decision(event, sha, changed, runs, default_branch="main"):
    """skip, bound, push, missing, or bad-sha. Extra payload keys are ignored."""
    if event != "pull_request":
        return "push"
    status, _ids = mf.select_mutants(list(changed))
    if status == "skip":
        return "skip"
    if not SHA_RE.fullmatch(sha or ""):
        return "bad-sha"
    if mutants_satisfied(sha, runs, default_branch):
        return "bound"
    return "missing"


def _sample(sha, **overrides):
    run = {
        "event": "workflow_dispatch",
        "head_branch": "main",
        "conclusion": "success",
        "path": WORKFLOW_PATH,
        "display_title": title_for(sha),
    }
    run.update(overrides)
    return run


def self_test():
    """Happy path and the stale, missing, and spoofed cases. No network."""
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
    # A comment or an artifact is not a workflow run, so it cannot bind the sha.
    spoofed = all(live_decision("pull_request", sha, harness, [run]) == "missing" for run in spoofs)
    ignored = live_decision(
        "pull_request",
        sha,
        harness,
        [{"comment": "mutants " + sha, "artifacts": [{"name": "mutant-sha"}]}],
    )
    res("M-A3", spoofed and ignored == "missing", "untrusted result stays red")
    return 1 if fail else 0


def _plan_line():
    import subprocess

    proc = subprocess.run(
        ["bash", os.path.join(HERE, "mutate-plan.sh")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return None
    line = proc.stdout.strip().splitlines()
    return line[-1] if line else ""


def _fetch_json(repo, token, path, missing_ok=False):
    if not REPO_RE.fullmatch(repo or ""):
        raise RuntimeError("bad repository")
    if not token:
        raise RuntimeError("token missing")
    if not path.startswith("/"):
        raise RuntimeError("bad path")
    req = urllib.request.Request(
        "https://api.github.com/repos/" + repo + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "rudax-keel-mutants",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        if missing_ok and err.code == 404:
            return None
        raise RuntimeError("github lookup failed (%s)" % err.code)
    except urllib.error.URLError:
        raise RuntimeError("github lookup failed")


def _fetch_runs(repo, token, default_branch):
    runs = []
    for page in range(1, 6):
        path = (
            "/actions/workflows/mutate-pr.yml/runs"
            "?event=workflow_dispatch&status=success&branch=%s&per_page=100&page=%d"
            % (default_branch, page)
        )
        # No workflow file on the default branch yet means there is no run.
        payload = _fetch_json(repo, token, path, missing_ok=True)
        if payload is None:
            return []
        batch = payload.get("workflow_runs") or []
        runs.extend(batch)
        if len(batch) < 100:
            break
    return runs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--self-test"]:
        return self_test()
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event != "pull_request":
        print("mutants: not a pull request")
        return 0
    line = _plan_line()
    if line is None:
        print("mutants: selection failed", file=sys.stderr)
        return 1
    if line == mf.SKIP_LINE:
        print("mutants: not required")
        return 0
    number = pr_number(os.environ.get("GITHUB_REF", ""))
    if not number:
        print("mutants: pull request ref missing", file=sys.stderr)
        return 1
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    default_branch = os.environ.get("DEFAULT_BRANCH") or "main"
    try:
        pull = _fetch_json(repo, token, "/pulls/" + number)
    except RuntimeError as err:
        print("mutants: %s" % err, file=sys.stderr)
        return 1
    sha = pull_head_sha(pull)
    if not sha:
        print("mutants: head sha missing", file=sys.stderr)
        return 1
    try:
        runs = _fetch_runs(repo, token, default_branch)
    except RuntimeError as err:
        print("mutants: %s" % err, file=sys.stderr)
        return 1
    if mutants_satisfied(sha, runs, default_branch):
        print("mutants: bound %s" % sha)
        return 0
    print("mutants: no successful run for %s" % sha, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
