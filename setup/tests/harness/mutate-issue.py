#!/usr/bin/env python3
"""Open or comment on one issue when the scheduled full mutant set fails."""
import json
import os
import sys
import urllib.parse
import urllib.request

TITLE = "Full mutant set failed"


def matching_issue(issues, title):
    numbers = []
    for item in issues:
        if item.get("title") != title:
            continue
        if "pull_request" in item:
            continue
        number = item.get("number")
        if isinstance(number, int):
            numbers.append(number)
    return numbers


def self_test():
    issues = [
        {"number": 1, "title": TITLE, "pull_request": {}},
        {"number": 4, "title": "other"},
        {"number": 9, "title": TITLE},
    ]
    if matching_issue(issues, TITLE) != [9]:
        raise SystemExit("issue match failed")
    if matching_issue([], TITLE) != []:
        raise SystemExit("empty match failed")
    print("mutate issue: one open issue")


def _request(token, method, path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com" + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "keel-mutate-full",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def open_issues(token, repo):
    found = []
    page = 1
    while page <= 10:
        batch = _request(
            token,
            "GET",
            "/repos/%s/issues?state=open&per_page=100&page=%d" % (repo, page),
        )
        if not isinstance(batch, list):
            raise SystemExit("issue list failed")
        found.extend(batch)
        if len(batch) < 100:
            return found
        page += 1
    raise SystemExit("too many open issues to scan")


def file_issue(token, repo, run_url):
    numbers = matching_issue(open_issues(token, repo), TITLE)
    body = "Full mutant set failed.\n\n%s\n" % run_url
    if numbers:
        _request(
            token,
            "POST",
            "/repos/%s/issues/%d/comments" % (repo, min(numbers)),
            {"body": body},
        )
        return
    _request(
        token,
        "POST",
        "/repos/%s/issues" % repo,
        {"title": TITLE, "body": body},
    )


def main(argv):
    if argv[1:2] == ["--self-test"]:
        self_test()
        return 0
    token = os.environ.get("GH_TOKEN") or ""
    repo = os.environ.get("REPO") or ""
    run_url = os.environ.get("RUN_URL") or ""
    if not token or not repo or not run_url:
        print("ERROR: mutate issue: missing GH_TOKEN, REPO, or RUN_URL", file=sys.stderr)
        return 1
    if urllib.parse.urlparse(run_url).scheme not in ("https", "http"):
        print("ERROR: mutate issue: run url rejected", file=sys.stderr)
        return 1
    file_issue(token, repo, run_url)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
