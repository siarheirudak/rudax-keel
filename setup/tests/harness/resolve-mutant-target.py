#!/usr/bin/env python3
"""Resolve the commit named by a maintainer dispatch. Prints sha and base."""
import json
import os
import re
import sys
import urllib.error
import urllib.request

SHA_RE = re.compile(r"[0-9a-f]{40}")
PR_RE = re.compile(r"[0-9]+")
REF_RE = re.compile(r"[A-Za-z0-9._/-]+")
REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def api(repo, token, path):
    req = urllib.request.Request(
        "https://api.github.com/repos/" + repo + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "rudax-keel-mutants",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def resolve_fields(repo, pr, sha, default_branch, pull=None, token_present=False):
    """Return (sha, base, error). error is None when the inputs are usable."""
    if not REPO_RE.fullmatch(repo or ""):
        return None, None, "bad repository"
    if not REF_RE.fullmatch(default_branch or "") or ".." in (default_branch or ""):
        return None, None, "bad default branch"
    if pr and not PR_RE.fullmatch(pr):
        return None, None, "bad pull request number"
    if sha and not SHA_RE.fullmatch(sha):
        return None, None, "bad sha"
    if not pr and not sha:
        return None, None, "pass a pull request number or a sha"
    base = default_branch
    if pr:
        if not token_present:
            return None, None, "token missing"
        head = ""
        if isinstance(pull, dict):
            head = ((pull.get("head") or {}).get("sha") or "").strip()
            base = ((pull.get("base") or {}).get("ref") or default_branch).strip()
        if not SHA_RE.fullmatch(head):
            return None, None, "pull request has no head sha"
        if sha and sha != head:
            return None, None, "sha does not match the pull request head"
        sha = head
    if not REF_RE.fullmatch(base) or ".." in base or base.startswith("-"):
        return None, None, "bad base branch"
    return sha, base, None


def self_test():
    sha = "0123456789abcdef0123456789abcdef01234567"
    other = "fedcba9876543210fedcba9876543210fedcba98"
    cases = [
        ("o/r", "", "zz", "main", None, False, "bad sha"),
        ("o/r", "", "", "main", None, False, "pass a pull request number or a sha"),
        ("bad repo", "", sha, "main", None, False, "bad repository"),
        ("o/r", "x", "", "main", None, True, "bad pull request number"),
        ("o/r", "4", "", "main", None, False, "token missing"),
        ("o/r", "4", sha, "main", {"head": {"sha": other}, "base": {"ref": "main"}}, True, "sha does not match the pull request head"),
        ("o/r", "4", "", "main", {"head": {"sha": "nope"}, "base": {"ref": "main"}}, True, "pull request has no head sha"),
        ("o/r", "4", "", "main", {"head": {"sha": sha}, "base": {"ref": "../x"}}, True, "bad base branch"),
    ]
    for repo, pr, got, default, pull, token, expect in cases:
        _sha, _base, err = resolve_fields(repo, pr, got, default, pull, token)
        if err != expect:
            print("mutants: %s != %s" % (err, expect), file=sys.stderr)
            return 1
    out, base, err = resolve_fields("o/r", "", sha, "main", None, False)
    if err or out != sha or base != "main":
        print("mutants: sha-only resolve failed", file=sys.stderr)
        return 1
    out, base, err = resolve_fields(
        "o/r", "4", "", "main", {"head": {"sha": sha}, "base": {"ref": "develop"}}, True
    )
    if err or out != sha or base != "develop":
        print("mutants: pull resolve failed", file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--self-test"]:
        return self_test()
    repo = os.environ.get("REPO", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    pr = os.environ.get("PR", "").strip()
    sha = os.environ.get("SHA", "").strip()
    default_branch = os.environ.get("DEFAULT_BRANCH", "main").strip() or "main"
    pull = None
    if pr and token and REPO_RE.fullmatch(repo) and PR_RE.fullmatch(pr):
        try:
            pull = api(repo, token, "/pulls/" + pr)
        except urllib.error.HTTPError as err:
            print("mutants: pull request lookup failed (%s)" % err.code, file=sys.stderr)
            return 1
        except urllib.error.URLError:
            print("mutants: pull request lookup failed", file=sys.stderr)
            return 1
    sha, base, err = resolve_fields(repo, pr, sha, default_branch, pull, bool(token))
    if err:
        print("mutants: %s" % err, file=sys.stderr)
        return 1
    text = "sha=%s\nbase=%s\n" % (sha, base)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
