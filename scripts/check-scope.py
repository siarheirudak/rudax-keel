#!/usr/bin/env python3
"""Fail when a pull request mixes process files with anything else.

Process files are .github/**, setup/**, scripts/**, CODEOWNERS, AGENTS.md,
CLAUDE.md, .cursor/**, and .claude/**. scripts/ is included because CI runs
those checks from the pull request. A docs file counts only when it is itself
an agent-rule file (AGENTS.md or CLAUDE.md). tests/ is not a process path.
Labels are not read and are not permission.

The GitHub job downloads this file from the default branch and does not
check out the pull request. --self-test checks the classifier with no network.
"""

import json
import os
import sys
import urllib.request

PROCESS_PREFIXES = (".github/", "setup/", "scripts/", ".cursor/", ".claude/")
AGENT_RULE_NAMES = {"AGENTS.md", "CLAUDE.md", "CODEOWNERS"}


def is_process(path):
    name = path.rsplit("/", 1)[-1]
    if name in AGENT_RULE_NAMES:
        return True
    return path.startswith(PROCESS_PREFIXES)


def classify(paths):
    process = [path for path in paths if is_process(path)]
    other = [path for path in paths if not is_process(path)]
    return process, other


def fail(process, other):
    print(
        "how to fix: this pull request mixes process files ("
        + ", ".join(process)
        + ") with other files ("
        + ", ".join(other)
        + "); put the process changes in their own pull request",
        file=sys.stderr,
    )
    return 1


def self_test():
    cases = [
        (["README.md"], False),
        ([".github/workflows/checks.yml"], False),
        ([".github/workflows/checks.yml", "README.md"], True),
        (["tests/test_app.py", "README.md"], False),
        (["setup/apply-github-rules.sh", "docs/why.md"], True),
        (["AGENTS.md"], False),
        (["docs/CLAUDE.md", "docs/why.md"], True),
        (["scripts/check.sh"], False),
        (["scripts/check.sh", "README.md"], True),
        (["CODEOWNERS"], False),
        ([".cursor/rules.md", "src/main.go"], True),
    ]
    for paths, should_fail in cases:
        process, other = classify(paths)
        mixed = bool(process and other)
        if mixed != should_fail:
            print(f"self-test mismatch {paths}: mixed={mixed}", file=sys.stderr)
            print(
                "how to fix: fix the process-file classifier in scripts/check-scope.py",
                file=sys.stderr,
            )
            return 1
    return 0


def api_json(url, token):
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "rudax-keel-scope",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def pull_request_files(repo, number, token):
    files = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/pulls/{number}/files?per_page=100&page={page}"
        batch = api_json(url, token)
        if not batch:
            break
        files.extend(item["filename"] for item in batch)
        if len(batch) < 100:
            break
        page += 1
    return files


def main():
    if "--self-test" in sys.argv[1:]:
        return self_test()
    repo = os.environ["REPO"]
    number = os.environ["PR_NUMBER"]
    token = os.environ["GH_TOKEN"]
    paths = pull_request_files(repo, number, token)
    process, other = classify(paths)
    if process and other:
        return fail(process, other)
    return 0


if __name__ == "__main__":
    sys.exit(main())
