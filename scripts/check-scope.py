#!/usr/bin/env python3
"""Fail when a pull request mixes workflow, process, and code changes.

Workflow paths are .github/workflows and .github/actions at the repository
root, including those two paths themselves. Process paths are any other
.github path, setup/ and scripts/ at the root, .keel/ at the root, .pi/ and
.agents/ at any depth, a path that is exactly .keel, setup, scripts, or
.github, a path whose final component is exactly .pi or .agents, and the
root .gitattributes and .gitmodules files.
Two paths are ordinary docs, matched as the whole path and ignoring case:
setup/README.md and setup/TESTING.md. A different path with the same
basename, such as setup/a/README.md, is still a process file. These names
are process files anywhere in the tree, including under setup/, and the
match ignores case: CODEOWNERS, AGENTS.md, AGENTS.override.md, CLAUDE.md,
and .shellcheckrc. CLAUDE.md is the fallback context file Pi Agent loads.
scripts/ is included because CI runs those checks from the pull request,
including scripts/tests/. A docs file counts only when it is itself an
agent-rule file. tests/ is not a process path. Only the `workflow` label is
read, when this check runs, to match the kind. A label grants nothing.

Paths are normalised before classification. Leading and trailing
whitespace is removed, a leading ./ is stripped, backslashes become
slashes, duplicate slashes collapse, and the path is Unicode NFC. A path
that is still ambiguous counts as a process file.

A rename counts both the new path and previous_filename. More than one
kind is a mix, including when the two names of one rename differ in kind.
The pull request base must be the repository default branch. The file list
must match pull_request.changed_files, and a pull request with 3000 or
more changed files fails closed because the API list stops there.
On success the check prints kind: code, kind: process, kind: workflow, or
kind: none.

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
ROOT_GIT_PATHS = {
    ".gitattributes",
    ".gitmodules",
}
BARE_DIR_NAMES = {
    ".keel",
    "setup",
    "scripts",
    ".github",
}
BARE_FINAL_NAMES = {
    ".pi",
    ".agents",
}
ADD_WORKFLOW_LABEL = (
    "how to fix: add the workflow label to this pull request, then re-run this check"
)
REMOVE_WORKFLOW_LABEL = (
    "how to fix: remove the workflow label from this pull request, then re-run this check"
)
LABEL_SHAPE_MESSAGE = (
    "how to fix: the pull request labels are missing or malformed;"
    " retry when each label has a name"
)

workflow_kind = True  # workflow-kind
keel_process = True  # keel-process
workflow_label = True  # workflow-label
label_only_workflow = True  # label-only-workflow
one_kind = True  # one-kind
rename_both = True  # rename-both
workflow_case = True  # workflow-case
default_base = True  # default-base
file_count = True  # file-count
labels_shape = True  # labels-shape
workflow_actions = True  # workflow-actions
bare_names = True  # bare-names


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


def _workflow_match(canonical):
    """True when the canonical path is workflow kind."""
    if not workflow_kind:
        return False
    text = canonical.casefold() if workflow_case else canonical
    prefixes = [".github/workflows/"]
    exact = [".github/workflows"]
    if workflow_actions:
        prefixes.append(".github/actions/")
        exact.append(".github/actions")
    for prefix in prefixes:
        needle = prefix.casefold() if workflow_case else prefix
        if text.startswith(needle):
            return True
    for item in exact:
        needle = item.casefold() if workflow_case else item
        if text == needle:
            return True
    return False


def kind_of(path):
    """Return workflow, process, or code. An ambiguous path is process."""
    canonical = canonical_path(path)
    if canonical is None:
        return "process"
    if _workflow_match(canonical):
        return "workflow"
    folded = canonical.casefold()
    name = folded.rsplit("/", 1)[-1]
    for rule in AGENT_RULE_NAMES:
        if name == rule.casefold():
            return "process"
    if folded in SETUP_DOC_PATHS:
        return "code"
    for prefix in ROOT_PREFIXES:
        if folded.startswith(prefix.casefold()):
            return "process"
    for prefix in NESTED_DIR_PREFIXES:
        needle = prefix.casefold()
        if folded.startswith(needle) or ("/" + needle) in folded:
            return "process"
    if keel_process and folded.startswith(".keel/"):
        return "process"
    if bare_names and (folded in BARE_DIR_NAMES or name in BARE_FINAL_NAMES):
        return "process"
    if folded in ROOT_GIT_PATHS:
        return "process"
    return "code"


def names_of(entry):
    names = []
    filename = entry.get("filename") or ""
    previous = entry.get("previous_filename") or ""
    if filename:
        names.append(filename)
    if rename_both and previous and previous not in names:
        names.append(previous)
    return names


def _mix_message(groups):
    parts = []
    for label in ("code", "process", "workflow"):
        rows = groups[label]
        if rows:
            parts.append(label + " (" + ", ".join(rows) + ")")
    return (
        "how to fix: this pull request mixes "
        + " and ".join(parts)
        + "; split into one pull request per kind"
    )


def carries_workflow_label(names):
    for name in names:
        if isinstance(name, str) and name.casefold() == "workflow":
            return True
    return False


def read_label_names(pull):
    """Return label names, or None when the pull request payload is malformed."""
    if not isinstance(pull, dict) or "labels" not in pull:
        return [] if not labels_shape else None
    raw = pull.get("labels")
    if not isinstance(raw, list):
        return [] if not labels_shape else None
    names = []
    for item in raw:
        if not isinstance(item, dict):
            return [] if not labels_shape else None
        name = item.get("name")
        if not isinstance(name, str):
            return [] if not labels_shape else None
        names.append(name)
    return names


def evaluate(entries, changed_files, base_ref, default_branch, labels):
    """Return (failed, message, kind). Message is empty when the pull request passes."""
    if default_base and (not default_branch or base_ref != default_branch):
        shown = base_ref or "(missing)"
        return True, (
            "how to fix: this pull request targets "
            + shown
            + "; retarget it onto the default branch "
            + (default_branch or "(unknown)")
        ), ""
    listed = len(entries)
    if file_count and (
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
        ), ""
    paths = []
    for entry in entries:
        paths.extend(names_of(entry))
    groups = {"code": [], "process": [], "workflow": []}
    for path in paths:
        groups[kind_of(path)].append(path)
    present = [label for label in ("code", "process", "workflow") if groups[label]]
    if len(present) > 1:
        if one_kind:
            return True, _mix_message(groups), ""
        return False, "", present[0]
    kind = present[0] if present else "none"
    if workflow_label and kind == "workflow" and not carries_workflow_label(labels):
        return True, ADD_WORKFLOW_LABEL, ""
    if label_only_workflow and carries_workflow_label(labels) and kind != "workflow":
        return True, REMOVE_WORKFLOW_LABEL, ""
    return False, "", kind


def _fail_case(name, detail):
    print(
        "self-test mismatch case={0} {1}".format(name, detail),
        file=sys.stderr,
    )
    print(
        "how to fix: fix the process-file classifier in scripts/check-scope.py",
        file=sys.stderr,
    )
    return 1


def self_test():
    def entry(name, previous=None):
        item = {"filename": name}
        if previous:
            item["previous_filename"] = previous
        return item

    def check_eval(name, entries, changed, base, default, labels, should_fail, needles, expect_kind=None):
        failed, message, kind = evaluate(entries, changed, base, default, labels)
        if isinstance(needles, str):
            needed = [needles] if needles else []
        else:
            needed = [item for item in needles if item]
        missing = [item for item in needed if item not in message]
        if failed != should_fail or missing:
            return _fail_case(
                name,
                "failed={0} message={1}".format(failed, message),
            )
        if failed and not message.startswith("how to fix:"):
            return _fail_case(name, "message missing how to fix")
        if not failed and expect_kind is not None and ("kind: " + kind) != ("kind: " + expect_kind):
            return _fail_case(name, "line={0}".format("kind: " + kind))
        return 0

    def check_kind(path, expected):
        got = kind_of(path)
        if got != expected:
            return _fail_case(path, "kind={0} expected={1}".format(got, expected))
        return 0

    added_kinds = [
        (".github/workflows/x.yml", "workflow"),
        (".GitHub/Workflows/x.yml", "workflow"),
        (".github/workflows/AGENTS.md", "workflow"),
        (".github/actions/a/action.yml", "workflow"),
        (".GitHub/Actions/a/action.yml", "workflow"),
        (".github/workflows", "workflow"),
        (".github/actions", "workflow"),
        (".GitHub/Workflows", "workflow"),
        (".GitHub/Actions", "workflow"),
        (".github/CODEOWNERS", "process"),
        (".github/dependabot.yml", "process"),
        (".keel/config", "process"),
        (".keel/deny.local", "process"),
        (".Keel/config", "process"),
        (".keel", "process"),
        (".KEEL", "process"),
        (".pi", "process"),
        ("sub/.pi", "process"),
        ("docs/.agents", "process"),
        ("setup", "process"),
        ("Setup", "process"),
        ("scripts", "process"),
        ("Scripts", "process"),
        (".github", "process"),
        (".GitHub", "process"),
        ("Sub/.Pi", "process"),
        ("Docs/.Agents", "process"),
        (".gitattributes", "process"),
        (".gitmodules", "process"),
        ("AGENTS.md", "process"),
        (".agents/skills/x/SKILL.md", "process"),
        ("sub/.keel/config", "code"),
        ("sub/.github/workflows/x.yml", "code"),
        ("docs/.gitattributes", "code"),
        ("sub/.gitmodules", "code"),
        ("docs/a.md", "code"),
        ("docs/.agentsx", "code"),
        (".pix", "code"),
    ]
    added_evals = [
        (
            "mix-workflow-code",
            [entry(".github/workflows/x.yml"), entry("docs/a.md")],
            2,
            [],
            True,
            (".github/workflows/x.yml", "docs/a.md"),
            None,
        ),
        (
            "mix-workflow-process",
            [entry(".github/workflows/checks.yml"), entry("scripts/check-gate.sh")],
            2,
            [],
            True,
            (".github/workflows/checks.yml", "scripts/check-gate.sh"),
            None,
        ),
        (
            "mix-actions-script",
            [entry(".github/actions/a/action.yml"), entry("scripts/x.sh")],
            2,
            [],
            True,
            (".github/actions/a/action.yml", "scripts/x.sh"),
            None,
        ),
        (
            "mix-keel-readme",
            [entry(".keel/config"), entry("README.md")],
            2,
            [],
            True,
            (".keel/config", "README.md"),
            None,
        ),
        (
            "mix-bare-keel",
            [entry(".keel"), entry("docs/k/config")],
            2,
            [],
            True,
            (".keel", "docs/k/config"),
            None,
        ),
        (
            "mix-all-three",
            [entry(".github/workflows/x.yml"), entry("scripts/x.sh"), entry("README.md")],
            3,
            [],
            True,
            (".github/workflows/x.yml", "scripts/x.sh", "README.md"),
            None,
        ),
        (
            "rename-workflow-to-docs",
            [entry("docs/a.yml", ".github/workflows/a.yml")],
            1,
            [],
            True,
            ("docs/a.yml", ".github/workflows/a.yml"),
            None,
        ),
        (
            "workflow-only-unlabelled",
            [entry(".github/workflows/checks.yml")],
            1,
            [],
            True,
            "add the workflow label",
            None,
        ),
        (
            "workflow-only-labelled",
            [entry(".github/workflows/checks.yml")],
            1,
            ["workflow"],
            False,
            "",
            "workflow",
        ),
        (
            "workflow-only-casefold",
            [entry(".github/workflows/x.yml")],
            1,
            ["Workflow"],
            False,
            "",
            "workflow",
        ),
        (
            "workflow-only-process-files",
            [entry(".github/workflows/x.yml")],
            1,
            ["process-files"],
            True,
            "add the workflow label",
            None,
        ),
        (
            "workflow-only-trailing-space",
            [entry(".github/workflows/x.yml")],
            1,
            ["workflow "],
            True,
            "add the workflow label",
            None,
        ),
        (
            "label-code-has-workflow",
            [entry("README.md")],
            1,
            ["workflow"],
            True,
            "remove the workflow label",
            None,
        ),
        (
            "label-process-has-workflow",
            [entry("scripts/check-gate.sh")],
            1,
            ["workflow"],
            True,
            "remove the workflow label",
            None,
        ),
        (
            "label-none-has-workflow",
            [],
            0,
            ["workflow"],
            True,
            "remove the workflow label",
            None,
        ),
        (
            "kind-none",
            [],
            0,
            [],
            False,
            "",
            "none",
        ),
    ]
    for name, entries, changed, labels, should_fail, needles, expect_kind in added_evals:
        failed = check_eval(
            name, entries, changed, "main", "main", labels, should_fail, needles, expect_kind
        )
        if failed:
            return failed
    for path, expected in added_kinds:
        failed = check_kind(path, expected)
        if failed:
            return failed

    classified = [
        ("setup/README.md", "code"),
        ("setup/readme.md", "code"),
        ("setup/TESTING.md", "code"),
        ("setup/testing.md", "code"),
        ("setup/tests/NOTES.md", "process"),
        ("setup/apply-github-rules.sh", "process"),
        ("setup/common.sh", "process"),
        ("setup/rulesets/protect-main.json", "process"),
        ("setup/rulesets/require-checks.json", "process"),
        ("setup/tests/test-fake-gh.sh", "process"),
        ("setup/tests/mock-gh.py", "process"),
        ("setup/tests/harness/run-tests.sh", "process"),
        ("setup/AGENTS.md", "process"),
        ("setup/agents.md", "process"),
        ("setup/a/README.md", "process"),
        ("setup/notes.md", "process"),
        ("setup/x.sh", "process"),
        ("setup/a/AGENTS.md", "process"),
        ("setup/CLAUDE.md", "process"),
        ("setup/CODEOWNERS", "process"),
        ("setup/AGENTS.override.md", "process"),
        (".github/workflows/scope.yml", "workflow"),
        (".github/README.md", "process"),
        (".GitHub/workflows/checks.yml", "workflow"),
        ("scripts/check-scope.py", "process"),
        ("scripts/NOTES.md", "process"),
        ("scripts/tests/test_md_links.py", "process"),
        (".pi/SYSTEM.md", "process"),
        (".pi/extensions/x.ts", "process"),
        (".pi/mcp.json", "process"),
        (".Pi/SYSTEM.md", "process"),
        (".agents/skills/a/SKILL.md", "process"),
        (".Agents/skills/a/SKILL.md", "process"),
        ("apps/.agents/skills/x/SKILL.md", "process"),
        ("apps/.Agents/skills/x/SKILL.md", "process"),
        ("pkg/.pi/SYSTEM.md", "process"),
        ("pkg/.Pi/SYSTEM.md", "process"),
        ("not.pi/SYSTEM.md", "code"),
        (" setup/README.md ", "code"),
        (" pkg/.pi/SYSTEM.md ", "process"),
        ("sub/AGENTS.override.md", "process"),
        ("sub/agents.override.md", "process"),
        ("sub/claude.md", "process"),
        ("sub/CLAUDE.md", "process"),
        ("README.md", "code"),
        ("docs/why.md", "code"),
        ("docs/AGENTS.md", "process"),
        ("docs/agents.md", "process"),
        ("tests/test_app.py", "code"),
        ("./setup/README.md", "code"),
        ("setup\\README.md", "code"),
        ("setup//README.md", "code"),
        (".//setup/README.md", "code"),
        ("./setup/keel.sh", "process"),
        ("setup\\keel.sh", "process"),
        ("Setup/keel.sh", "process"),
        ("Setup/README.md", "code"),
        ("Setup/TESTING.md", "code"),
        (".mcp.json", "code"),
        ("src/app.py", "code"),
        ("standards/rules.md", "code"),
        ("", "process"),
        ("setup/../README.md", "process"),
        ("/etc/passwd", "process"),
        (".github/workflows/caf\u0065\u0301.yml", "workflow"),
    ]
    for path, expected in classified:
        failed = check_kind(path, expected)
        if failed:
            return failed
    angstrom = "docs/\u212b.md"
    if canonical_path(angstrom) != unicodedata.normalize("NFC", angstrom):
        return _fail_case("nfc", "path was not Unicode NFC")
    if kind_of(angstrom) != "code":
        return _fail_case("nfc-angstrom", "NFC path was classified as a process file")

    many = [entry("f{}.txt".format(index)) for index in range(FILE_CAP)]
    cases = [
        ([entry("README.md")], 1, "main", "main", [], False, ""),
        ([entry(".github/workflows/checks.yml")], 1, "main", "main", [], True, "add the workflow label"),
        (
            [entry(".github/workflows/checks.yml")],
            1,
            "main",
            "main",
            ["workflow"],
            False,
            "",
            "workflow",
        ),
        (
            [entry(".github/workflows/checks.yml"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            True,
            "README.md",
        ),
        ([entry("tests/test_app.py"), entry("README.md")], 2, "main", "main", [], False, ""),
        (
            [entry("setup/apply-github-rules.sh"), entry("docs/why.md")],
            2,
            "main",
            "main",
            [],
            True,
            "docs/why.md",
        ),
        ([entry("AGENTS.md")], 1, "main", "main", [], False, ""),
        (
            [entry("docs/CLAUDE.md"), entry("docs/why.md")],
            2,
            "main",
            "main",
            [],
            True,
            "docs/CLAUDE.md",
        ),
        ([entry("scripts/check.sh")], 1, "main", "main", [], False, ""),
        ([entry("scripts/check.sh"), entry("README.md")], 2, "main", "main", [], True, "README.md"),
        ([entry("CODEOWNERS")], 1, "main", "main", [], False, ""),
        ([entry(".pi/SYSTEM.md"), entry("src/main.go")], 2, "main", "main", [], True, "src/main.go"),
        ([entry(".pi/extensions/x.ts")], 1, "main", "main", [], False, ""),
        (
            [entry(".agents/skills/a/SKILL.md"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            True,
            "README.md",
        ),
        ([entry("sub/AGENTS.override.md")], 1, "main", "main", [], False, ""),
        (
            [entry("sub/claude.md"), entry("docs/why.md")],
            2,
            "main",
            "main",
            [],
            True,
            "sub/claude.md",
        ),
        ([entry(".mcp.json"), entry("README.md")], 2, "main", "main", [], False, ""),
        (
            [entry(".pi/mcp.json"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            True,
            "README.md",
        ),
        ([entry(".shellcheckrc")], 1, "main", "main", [], False, ""),
        (
            [entry("./setup/README.md"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            False,
            "",
        ),
        (
            [entry("setup\\README.md"), entry("docs/why.md")],
            2,
            "main",
            "main",
            [],
            False,
            "",
        ),
        (
            [entry("setup//README.md"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            False,
            "",
        ),
        (
            [entry("./setup/keel.sh"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            True,
            "./setup/keel.sh",
        ),
        (
            [entry("setup/../README.md"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            True,
            "setup/../README.md",
        ),
        ([entry("scripts/tests/test_md_links.py")], 1, "main", "main", [], False, ""),
        (
            [entry("scripts/tests/test_md_links.py"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            True,
            "README.md",
        ),
        (
            [entry(".github/README-from-product.md", "README.md")],
            1,
            "main",
            "main",
            [],
            True,
            "README.md",
        ),
        (
            [entry("setup/README.md"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            False,
            "",
        ),
        (
            [entry("setup/TESTING.md"), entry("docs/why.md")],
            2,
            "main",
            "main",
            [],
            False,
            "",
        ),
        (
            [entry("setup/README.md"), entry("setup/apply-github-rules.sh")],
            2,
            "main",
            "main",
            [],
            True,
            "setup/README.md",
        ),
        (
            [entry("setup/AGENTS.md"), entry("setup/README.md")],
            2,
            "main",
            "main",
            [],
            True,
            "setup/AGENTS.md",
        ),
        (
            [entry("setup/CLAUDE.md"), entry("docs/why.md")],
            2,
            "main",
            "main",
            [],
            True,
            "setup/CLAUDE.md",
        ),
        (
            [entry("setup/rulesets/require-checks.json"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            True,
            "README.md",
        ),
        (
            [entry("setup/tests/test-fake-gh.sh"), entry("tests/test_app.py")],
            2,
            "main",
            "main",
            [],
            True,
            "tests/test_app.py",
        ),
        (
            [entry("scripts/NOTES.md"), entry("README.md")],
            2,
            "main",
            "main",
            [],
            True,
            "README.md",
        ),
        (
            [entry("docs/was-setup.md", "setup/README.md")],
            1,
            "main",
            "main",
            [],
            False,
            "",
        ),
        (
            [entry("docs/was-setup.sh", "setup/apply-github-rules.sh")],
            1,
            "main",
            "main",
            [],
            True,
            "setup/apply-github-rules.sh",
        ),
        ([entry(".github/b.yml", ".github/a.yml")], 1, "main", "main", [], False, ""),
        ([entry("docs/b.md", "README.md")], 1, "main", "main", [], False, ""),
        ([entry("README.md")], 2, "main", "main", [], True, "3000"),
        (many, FILE_CAP, "main", "main", [], True, "3000"),
        ([entry("README.md")], 1, "other", "main", [], True, "other"),
        ([entry("README.md")], 1, "main", "", [], True, "unknown"),
        ([entry("README.md")], None, "main", "main", [], True, "missing"),
    ]
    for index, case in enumerate(cases):
        entries, changed, base, default, labels, should_fail, needle = case[:7]
        expect_kind = case[7] if len(case) > 7 else None
        name = "evaluate[{0}] labels={1} needle={2} base={3} reported={4}".format(
            index, ",".join(labels), needle, base, changed
        )
        failed = check_eval(
            name, entries, changed, base, default, labels, should_fail, needle, expect_kind
        )
        if failed:
            return failed

    malformed = [
        ("labels-not-a-list", {"labels": "workflow"}),
        ("labels-item-not-object", {"labels": ["workflow"]}),
        ("labels-name-not-string", {"labels": [{"name": 1}]}),
        ("labels-name-absent", {"labels": [{"id": 1}]}),
        ("labels-missing", {}),
    ]
    if not LABEL_SHAPE_MESSAGE.startswith("how to fix:"):
        return _fail_case("label-payload-message", "message missing how to fix")
    for name, payload in malformed:
        if read_label_names(payload) is not None:
            return _fail_case(name, "malformed labels were accepted")
    if read_label_names({"labels": []}) != []:
        return _fail_case("labels-empty", "empty label list was rejected")
    if read_label_names({"labels": [{"name": "workflow"}, {"name": "process-files"}]}) != [
        "workflow",
        "process-files",
    ]:
        return _fail_case("labels-names", "label names were not read")
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
    labels = read_label_names(pull)
    if labels is None:
        print(LABEL_SHAPE_MESSAGE, file=sys.stderr)
        return 1
    failed, message, kind = evaluate(
        entries,
        pull.get("changed_files"),
        base_ref,
        info.get("default_branch") or "",
        labels,
    )
    if failed:
        print(message, file=sys.stderr)
        return 1
    print("kind: " + kind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
