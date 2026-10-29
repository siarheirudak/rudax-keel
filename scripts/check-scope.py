#!/usr/bin/env python3
"""Fail when a pull request mixes process files with anything else.

Process files are .github/**, scripts/**, and setup/** at the root, and
.pi/** and .agents/** at any depth.
Two paths are ordinary docs, matched as the whole path and ignoring case:
setup/README.md and setup/TESTING.md. A different path with the same
basename, such as setup/a/README.md, is still a process file. These names
are process files anywhere in the tree, including under setup/, and the
match ignores case: CODEOWNERS, AGENTS.md, AGENTS.override.md, CLAUDE.md,
and .shellcheckrc. CLAUDE.md is the fallback context file Pi Agent loads.
scripts/ is included because CI runs those checks from the pull request,
including scripts/tests/. A docs file counts only when it is itself an
agent-rule file. tests/ is not a process path. Labels are not read and
are not permission.

Paths are normalised before classification. Leading and trailing
whitespace is removed, a leading ./ is stripped, backslashes become
slashes, duplicate slashes collapse, and the path is Unicode NFC. A path
that is still ambiguous counts as a process file.

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
import unicodedata
import urllib.error
import urllib.request

ROOT_PREFIXES = (".github/", "setup/", "scripts/")
# (^|/)prefix, at any depth. Matched without regard to case.
NESTED_DIR_PREFIXES = (".pi/", ".agents/")
AGENT_RULE_NAMES = {
    "AGENTS.md",
    "AGENTS.override.md",
    "CLAUDE.md",
    "CODEOWNERS",
    ".shellcheckrc",
}
FILE_CAP = 3000
# Whole path, not the basename. Case is folded only for this allowlist.
SETUP_DOC_PATHS = {
    "setup/readme.md",
    "setup/testing.md",
}


def canonical_path(path):
    """Return one relative path, or None when the path is still ambiguous."""
    if not isinstance(path, str) or path == "" or "\x00" in path:
        return None
    text = unicodedata.normalize("NFC", path).strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    while text.startswith("./"):
        text = text[2:]
    if text == "" or text == "." or text.startswith("/"):
        return None
    parts = text.split("/")
    if any(part in ("", ".", "..") or ":" in part for part in parts):
        return None
    return text


def is_process(path):
    canonical = canonical_path(path)
    if canonical is None:
        return True
    name = canonical.rsplit("/", 1)[-1].casefold()
    for rule in AGENT_RULE_NAMES:
        if name == rule.casefold():
            return True
    if canonical.casefold() in SETUP_DOC_PATHS:
        return False
    folded = canonical.casefold()
    for prefix in ROOT_PREFIXES:
        if folded.startswith(prefix.casefold()):
            return True
    for prefix in NESTED_DIR_PREFIXES:
        needle = prefix.casefold()
        if folded.startswith(needle) or ("/" + needle) in folded:
            return True
    return False


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

    classified = [
        ("setup/README.md", False),
        ("setup/readme.md", False),
        ("setup/TESTING.md", False),
        ("setup/testing.md", False),
        ("setup/tests/NOTES.md", True),
        ("setup/apply-github-rules.sh", True),
        ("setup/common.sh", True),
        ("setup/rulesets/protect-main.json", True),
        ("setup/rulesets/require-checks.json", True),
        ("setup/tests/test-fake-gh.sh", True),
        ("setup/tests/mock-gh.py", True),
        ("setup/tests/harness/run-tests.sh", True),
        ("setup/AGENTS.md", True),
        ("setup/agents.md", True),
        ("setup/a/README.md", True),
        ("setup/notes.md", True),
        ("setup/x.sh", True),
        ("setup/a/AGENTS.md", True),
        ("setup/CLAUDE.md", True),
        ("setup/CODEOWNERS", True),
        ("setup/AGENTS.override.md", True),
        (".github/workflows/scope.yml", True),
        (".github/README.md", True),
        (".GitHub/workflows/checks.yml", True),
        ("scripts/check-scope.py", True),
        ("scripts/NOTES.md", True),
        ("scripts/tests/test_md_links.py", True),
        (".pi/SYSTEM.md", True),
        (".pi/extensions/x.ts", True),
        (".pi/mcp.json", True),
        (".Pi/SYSTEM.md", True),
        (".agents/skills/a/SKILL.md", True),
        (".Agents/skills/a/SKILL.md", True),
        ("apps/.agents/skills/x/SKILL.md", True),
        ("apps/.Agents/skills/x/SKILL.md", True),
        ("pkg/.pi/SYSTEM.md", True),
        ("pkg/.Pi/SYSTEM.md", True),
        ("not.pi/SYSTEM.md", False),
        (" setup/README.md ", False),
        (" pkg/.pi/SYSTEM.md ", True),
        ("sub/AGENTS.override.md", True),
        ("sub/agents.override.md", True),
        ("sub/claude.md", True),
        ("sub/CLAUDE.md", True),
        ("README.md", False),
        ("docs/why.md", False),
        ("docs/AGENTS.md", True),
        ("docs/agents.md", True),
        ("tests/test_app.py", False),
        ("./setup/README.md", False),
        ("setup\\README.md", False),
        ("setup//README.md", False),
        (".//setup/README.md", False),
        ("./setup/keel.sh", True),
        ("setup\\keel.sh", True),
        ("Setup/keel.sh", True),
        ("Setup/README.md", False),
        ("Setup/TESTING.md", False),
        (".mcp.json", False),
        ("src/app.py", False),
        ("", True),
        ("setup/../README.md", True),
        ("/etc/passwd", True),
        (".github/workflows/caf\u0065\u0301.yml", True),
    ]
    for path, expected in classified:
        if is_process(path) != expected:
            print(
                "self-test mismatch path={0} process={1} expected={2}".format(
                    path, is_process(path), expected
                ),
                file=sys.stderr,
            )
            print(
                "how to fix: fix the process-file classifier in scripts/check-scope.py",
                file=sys.stderr,
            )
            return 1
    angstrom = "docs/\u212b.md"
    if canonical_path(angstrom) != unicodedata.normalize("NFC", angstrom):
        print("self-test mismatch: path was not Unicode NFC", file=sys.stderr)
        print(
            "how to fix: fix the process-file classifier in scripts/check-scope.py",
            file=sys.stderr,
        )
        return 1
    if is_process(angstrom):
        print("self-test mismatch: NFC path was classified as a process file", file=sys.stderr)
        print(
            "how to fix: fix the process-file classifier in scripts/check-scope.py",
            file=sys.stderr,
        )
        return 1

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
        ([entry(".pi/SYSTEM.md"), entry("src/main.go")], 2, "main", "main", True, "src/main.go"),
        ([entry(".pi/extensions/x.ts")], 1, "main", "main", False, ""),
        (
            [entry(".agents/skills/a/SKILL.md"), entry("README.md")],
            2,
            "main",
            "main",
            True,
            "README.md",
        ),
        ([entry("sub/AGENTS.override.md")], 1, "main", "main", False, ""),
        (
            [entry("sub/claude.md"), entry("docs/why.md")],
            2,
            "main",
            "main",
            True,
            "sub/claude.md",
        ),
        ([entry(".mcp.json"), entry("README.md")], 2, "main", "main", False, ""),
        (
            [entry(".pi/mcp.json"), entry("README.md")],
            2,
            "main",
            "main",
            True,
            "README.md",
        ),
        ([entry(".shellcheckrc")], 1, "main", "main", False, ""),
        (
            [entry("./setup/README.md"), entry("README.md")],
            2,
            "main",
            "main",
            False,
            "",
        ),
        (
            [entry("setup\\README.md"), entry("docs/why.md")],
            2,
            "main",
            "main",
            False,
            "",
        ),
        (
            [entry("setup//README.md"), entry("README.md")],
            2,
            "main",
            "main",
            False,
            "",
        ),
        (
            [entry("./setup/keel.sh"), entry("README.md")],
            2,
            "main",
            "main",
            True,
            "./setup/keel.sh",
        ),
        (
            [entry("setup/../README.md"), entry("README.md")],
            2,
            "main",
            "main",
            True,
            "setup/../README.md",
        ),
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
            [entry("setup/README.md"), entry("README.md")],
            2,
            "main",
            "main",
            False,
            "",
        ),
        (
            [entry("setup/TESTING.md"), entry("docs/why.md")],
            2,
            "main",
            "main",
            False,
            "",
        ),
        (
            [entry("setup/README.md"), entry("setup/apply-github-rules.sh")],
            2,
            "main",
            "main",
            True,
            "setup/README.md",
        ),
        (
            [entry("setup/AGENTS.md"), entry("setup/README.md")],
            2,
            "main",
            "main",
            True,
            "setup/AGENTS.md",
        ),
        (
            [entry("setup/CLAUDE.md"), entry("docs/why.md")],
            2,
            "main",
            "main",
            True,
            "setup/CLAUDE.md",
        ),
        (
            [entry("setup/rulesets/require-checks.json"), entry("README.md")],
            2,
            "main",
            "main",
            True,
            "README.md",
        ),
        (
            [entry("setup/tests/test-fake-gh.sh"), entry("tests/test_app.py")],
            2,
            "main",
            "main",
            True,
            "tests/test_app.py",
        ),
        (
            [entry("scripts/NOTES.md"), entry("README.md")],
            2,
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
            False,
            "",
        ),
        (
            [entry("docs/was-setup.sh", "setup/apply-github-rules.sh")],
            1,
            "main",
            "main",
            True,
            "setup/apply-github-rules.sh",
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
