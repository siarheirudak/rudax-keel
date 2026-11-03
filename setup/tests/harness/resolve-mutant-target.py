#!/usr/bin/env python3
"""Resolve the commit named by a maintainer dispatch. Prints sha and base."""
import json
import os
import re
import sys
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


def main():
    repo = os.environ.get("REPO", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    pr = os.environ.get("PR", "").strip()
    sha = os.environ.get("SHA", "").strip()
    default_branch = os.environ.get("DEFAULT_BRANCH", "main").strip() or "main"
    if not REPO_RE.fullmatch(repo):
        print("mutants: bad repository", file=sys.stderr)
        return 1
    if not REF_RE.fullmatch(default_branch) or ".." in default_branch:
        print("mutants: bad default branch", file=sys.stderr)
        return 1
    if pr and not PR_RE.fullmatch(pr):
        print("mutants: bad pull request number", file=sys.stderr)
        return 1
    if sha and not SHA_RE.fullmatch(sha):
        print("mutants: bad sha", file=sys.stderr)
        return 1
    if not pr and not sha:
        print("mutants: pass a pull request number or a sha", file=sys.stderr)
        return 1
    base = default_branch
    if pr:
        if not token:
            print("mutants: token missing", file=sys.stderr)
            return 1
        pull = api(repo, token, "/pulls/" + pr)
        head = ((pull.get("head") or {}).get("sha") or "").strip()
        base = ((pull.get("base") or {}).get("ref") or default_branch).strip()
        if not SHA_RE.fullmatch(head):
            print("mutants: pull request has no head sha", file=sys.stderr)
            return 1
        if sha and sha != head:
            print("mutants: sha does not match the pull request head", file=sys.stderr)
            return 1
        sha = head
    if not REF_RE.fullmatch(base) or ".." in base or base.startswith("-"):
        print("mutants: bad base branch", file=sys.stderr)
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
