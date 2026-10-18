#!/usr/bin/env python3
"""Fail when a pull request mixes process files with anything else.

Process files are .github/**, setup/**, scripts/**, .cursor/**, .claude/**,
and these names anywhere in the tree: CODEOWNERS, AGENTS.md, CLAUDE.md,
CLAUDE.local.md, .cursorrules, .windsurfrules, .clinerules, .mcp.json, and
.shellcheckrc. scripts/ is included because CI runs those checks from the
pull request, including scripts/tests/. A docs file counts only when it is
itself an agent-rule file. tests/ is not a process path. Labels are not read
and are not permission.

A rename counts both the new path and previous_filename. One process path
and one other path is a mix, including when they are the two names of one
rename. The pull request base must be the repository default branch. The
file list must match pull_request.changed_files, and a pull request with
3000 or more changed files fails closed because the API list stops there.

The GitHub job downloads this file from the pull request base and does not
check out the pull request. --self-test checks the classifier with no network.
"""

import json
import os
import sys
import urllib.error
import urllib.request

PROCESS_PREFIXES = (".github/", "setup/", "scripts/", ".cursor/", ".claude/")
AGENT_RULE_NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "CLAUDE.local.md",
    "CODEOWNERS",
    ".cursorrules",
    ".windsurfrules",
    ".clinerules",
    ".mcp.json",
    ".shellcheckrc",
}
FILE_CAP = 3000


def is_process(path):
    name = path.rsplit("/", 1)[-1]
    if name in AGENT_RULE_NAMES:
        return True
    return path.startswith(PROCESS_PREFIXES)


def classify(paths):
    process = [path for path in paths if is_process(path)]
    other = [path for path in paths if not is_process(path)]
    return process, other


def names_of(entry):
    names = []
    filename = entry.get("filename") or ""
    previous = entry.get("previous_filename") or ""
    if filename:
        names.append(filename)
    if previous and previous not in names:
        names.append(previous)
    return names


def evaluate(entries, changed_files, base_ref, default_branch):
    """Return (failed, message). Message is empty when the pull request passes."""
    if not default_branch or base_ref != default_branch:
        shown = base_ref or "(missing)"
        return True, (
            "how to fix: this pull request targets "
            + shown
            + "; retarget it onto the default branch "
            + (default_branch or "(unknown)")
        )
    listed = len(entries)
    if (
        not isinstance(changed_files, int)
        or changed_files >= FILE_CAP
        or listed != changed_files
    ):
        reported = changed_files if isinstance(changed_files, int) else "(missing)"
        return True, (
            "how to fix: GitHub reported "
            + str(reported)
            + " changed files but the API list has "
            + str(listed)
            + "; the list stops at 3000, so split the pull request"
        )
    paths = []
    for entry in entries:
        paths.extend(names_of(entry))
    process, other = classify(paths)
    if process and other:
        return True, (
            "how to fix: this pull request mixes process files ("
            + ", ".join(process)
            + ") with other files ("
            + ", ".join(other)
            + "); put the process changes in their own pull request"
        )
    return False, ""


def self_test():
    def entry(name, previous=None):
        item = {"filename": name}
        if previous:
            item["previous_filename"] = previous
        return item

    many = [entry("f{}.txt".format(index)) for index in range(FILE_CAP)]
    cases = [
        ([entry("README.md")], 1, "main", "main", False, ""),
        ([entry(".github/workflows/checks.yml")], 1, "main", "main", False, ""),
        (
            [entry(".github/workflows/checks.yml"), entry("README.md")],
            2,
            "main",
            "main",
            True,
            "README.md",
        ),
        ([entry("tests/test_app.py"), entry("README.md")], 2, "main", "main", False, ""),
        (
            [entry("setup/apply-github-rules.sh"), entry("docs/why.md")],
            2,
            "main",
            "main",
            True,
            "docs/why.md",
        ),
        ([entry("AGENTS.md")], 1, "main", "main", False, ""),
        (
            [entry("docs/CLAUDE.md"), entry("docs/why.md")],
            2,
            "main",
            "main",
            True,
            "docs/CLAUDE.md",
        ),
        ([entry("scripts/check.sh")], 1, "main", "main", False, ""),
        ([entry("scripts/check.sh"), entry("README.md")], 2, "main", "main", True, "README.md"),
        ([entry("CODEOWNERS")], 1, "main", "main", False, ""),
        ([entry(".cursor/rules.md"), entry("src/main.go")], 2, "main", "main", True, "src/main.go"),
        ([entry(".cursorrules")], 1, "main", "main", False, ""),
        ([entry(".windsurfrules"), entry("src/app.py")], 2, "main", "main", True, ".windsurfrules"),
        ([entry("docs/.clinerules")], 1, "main", "main", False, ""),
        ([entry(".mcp.json")], 1, "main", "main", False, ""),
        ([entry("CLAUDE.local.md"), entry("README.md")], 2, "main", "main", True, "CLAUDE.local.md"),
        ([entry(".shellcheckrc")], 1, "main", "main", False, ""),
        ([entry("scripts/tests/test_md_links.py")], 1, "main", "main", False, ""),
        (
            [entry("scripts/tests/test_md_links.py"), entry("README.md")],
            2,
            "main",
            "main",
            True,
            "README.md",
        ),
        (
            [entry(".github/README-from-product.md", "README.md")],
            1,
            "main",
            "main",
            True,
            "README.md",
        ),
        (
            [entry("docs/was-setup.md", "setup/README.md")],
            1,
            "main",
            "main",
            True,
            "setup/README.md",
        ),
        ([entry(".github/b.yml", ".github/a.yml")], 1, "main", "main", False, ""),
        ([entry("docs/b.md", "README.md")], 1, "main", "main", False, ""),
        ([entry("README.md")], 2, "main", "main", True, "3000"),
        (many, FILE_CAP, "main", "main", True, "3000"),
        ([entry("README.md")], 1, "other", "main", True, "other"),
        ([entry("README.md")], 1, "main", "", True, "unknown"),
        ([entry("README.md")], None, "main", "main", True, "missing"),
    ]
    for entries, changed, base, default, should_fail, needle in cases:
        failed, message = evaluate(entries, changed, base, default)
        if failed != should_fail or (needle and needle not in message):
            print(
                "self-test mismatch entries={0} failed={1} message={2}".format(
                    entries, failed, message
                ),
                file=sys.stderr,
            )
            print(
                "how to fix: fix the process-file classifier in scripts/check-scope.py",
                file=sys.stderr,
            )
            return 1
        if failed and not message.startswith("how to fix:"):
            print("self-test message missing how to fix", file=sys.stderr)
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
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "rudax-keel-scope",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        print(
            "how to fix: GitHub API returned HTTP {0} while reading the pull request; retry when it succeeds".format(
                exc.code
            ),
            file=sys.stderr,
        )
    except (urllib.error.URLError, json.JSONDecodeError, ValueError):
        print(
            "how to fix: could not read the pull request from the GitHub API; retry when the network works",
            file=sys.stderr,
        )
    return None


def pull_request_files(repo, number, token):
    files = []
    page = 1
    while True:
        url = (
            "https://api.github.com/repos/{0}/pulls/{1}/files?per_page=100&page={2}".format(
                repo, number, page
            )
        )
        batch = api_json(url, token)
        if batch is None:
            return None
        if not isinstance(batch, list):
            print(
                "how to fix: GitHub returned an unexpected file list; retry when the API succeeds",
                file=sys.stderr,
            )
            return None
        if not batch:
            break
        files.extend(batch)
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
    event_base = os.environ.get("BASE_REF", "")
    pull = api_json("https://api.github.com/repos/{0}/pulls/{1}".format(repo, number), token)
    if pull is None:
        return 1
    info = api_json("https://api.github.com/repos/{0}".format(repo), token)
    if info is None:
        return 1
    base_ref = (pull.get("base") or {}).get("ref") or ""
    if event_base and event_base != base_ref:
        print(
            "how to fix: the event base {0} does not match the pull request base {1}; re-run the check".format(
                event_base, base_ref or "(missing)"
            ),
            file=sys.stderr,
        )
        return 1
    entries = pull_request_files(repo, number, token)
    if entries is None:
        return 1
    failed, message = evaluate(
        entries,
        pull.get("changed_files"),
        base_ref,
        info.get("default_branch") or "",
    )
    if failed:
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
