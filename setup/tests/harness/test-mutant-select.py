#!/usr/bin/env python3
"""Mapped files select CI mutants. A selector that returns nothing is caught."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mutate  # noqa: E402
import mutant_files as mf  # noqa: E402


def fail(msg):
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def validate():
    if set(mf.FILES) != set(mutate.M):
        fail("FILES and mutate.M differ")
    root = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
    for mid, paths in mf.FILES.items():
        if not paths:
            fail("empty map " + mid)
        expect = ["setup/" + mutate.M[mid][0]]
        if paths != expect:
            fail("%s map %s != %s" % (mid, paths, expect))
        for path in paths:
            if not os.path.isfile(os.path.join(root, path)):
                fail("missing " + path)
    if len(mf.CI_IDS) != len(set(mf.CI_IDS)):
        fail("duplicate CI id")
    for mid in mf.CI_IDS:
        if mid not in mf.FILES:
            fail("CI id not mapped " + mid)
    for path in mf.TRIGGERS:
        if not os.path.isfile(os.path.join(root, path)):
            fail("missing trigger " + path)
    mapped = {path for paths in mf.FILES.values() for path in paths}
    if not set(mf.TARGET_ONLY) <= mapped:
        fail("target-only file is not a mutant target")
    if "setup/check.sh" not in mapped or "setup/check.sh" in mf.TARGET_ONLY:
        fail("check.sh must be a mapped oracle")
    if "M79" not in mf.CI_IDS or "M80" not in mf.CI_IDS or "M90" not in mf.CI_IDS:
        fail("M79, M80, or M90 is not in the CI set")
    for path in mf.ORACLE_FILES:
        if path in mf.TARGET_ONLY:
            fail("oracle listed as a selective target " + path)
        if not os.path.isfile(os.path.join(root, path)):
            fail("missing oracle " + path)
        got = mf.select_mutants([path])
        if got[0] != "full" or "M80" not in got[1] or "M90" not in got[1]:
            fail("oracle %s did not select the full set" % path)
    for path in mf.TARGET_ONLY:
        if path.startswith("setup/") or path.startswith(".github/"):
            continue
        fail("target-only path is outside setup/ and .github/: " + path)


def expect_some(changed, present, absent):
    status, ids = mf.check_selection(changed)
    if status != "some" or present not in ids or absent in ids:
        fail("selection %s -> %s %s" % (changed, status, ids))
    return ids


def main():
    validate()
    keel = expect_some(["setup/keel.sh"], "M03", "M51")
    visibility = expect_some(["setup/lib/visibility.py"], "M51", "M03")
    expect_some(["setup/lib/egress.py"], "M76", "M03")
    expect_some(["setup/lib/egress.sh"], "M77", "M51")
    expect_some(["setup/tests/harness/attack-results.sh"], "M78", "M03")
    if set(keel) & set(visibility):
        fail("keel.sh and visibility.py share a CI mutant")
    both = mf.check_selection(["setup/keel.sh", "setup/lib/visibility.py"])
    if both[0] != "some" or both[1] != [mid for mid in mf.CI_IDS if mid in set(keel) | set(visibility)]:
        fail("combined selection %s" % (both,))
    full = mf.check_selection(["setup/keel.sh", "setup/tests/harness/mutate.py"])
    if full != ("full", list(mf.CI_IDS)):
        fail("trigger did not select the full set")
    for trigger in mf.TRIGGERS:
        got = mf.check_selection([trigger])
        if got != ("full", list(mf.CI_IDS)):
            fail("trigger %s -> %s" % (trigger, got))
    full_paths = [
        "setup/tests/harness/test-attacks.sh",
        "setup/tests/harness/test-happy.sh",
        "setup/tests/harness/h3-verdict.sh",
        "setup/tests/harness/test-egress.sh",
        "setup/tests/harness/visibility-suite.sh",
        "setup/lib/portable.sh",
        "setup/common.sh",
        "setup/lib/mock_model.py",
        "setup/allow/developer.paths",
        "setup/deny/base",
        "setup/egress/developer.allow",
        "setup/docker/keel-git.Dockerfile",
        "setup/docker/keel-proxy.Dockerfile",
        "setup/gitleaks.toml",
        "setup/gitleaks-install.sh",
        "setup/gitleaks.ignore",
        "setup/keel-doctor.sh",
        "setup/check.sh",
        "setup/tests/harness/mutate-plan.sh",
        "setup/not-a-mapped-target",
        ".github/workflows/mutate-full.yml",
        ".github/unknown.yml",
    ]
    root = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
    for path in full_paths:
        if path in mf.TARGET_ONLY:
            fail("full-set path listed as a mapped target " + path)
        if "not-a-mapped-target" not in path and not path.endswith("unknown.yml"):
            if not os.path.isfile(os.path.join(root, path)):
                fail("missing full-set path " + path)
        got = mf.select_mutants([path])
        if got != ("full", list(mf.CI_IDS)):
            fail("full set required for %s, got %s" % (path, got))
        if mf.decision_line([path]) != mf.FULL_LINE:
            fail("decision for %s" % path)
    mixed = mf.select_mutants(["setup/keel.sh", "setup/tests/harness/test-attacks.sh"])
    if mixed != ("full", list(mf.CI_IDS)):
        fail("oracle next to a target must select the full set")
    outside = mf.check_selection(["scripts/check.sh"])
    if outside != ("skip", []):
        fail("a file outside setup/ and .github/ should skip")
    skipped = mf.check_selection(["docs/security.md"])
    if skipped != ("skip", []):
        fail("docs should skip")
    if mf.check_selection([]) != ("skip", []):
        fail("empty change should skip")

    def always_none(_changed):
        return ("skip", [])

    try:
        mf.check_selection(["setup/keel.sh"], always_none)
    except mf.SelectionError as err:
        if "selection dropped every mutant" not in str(err):
            fail("wrong error " + str(err))
    else:
        fail("always-none was not caught")

    try:
        mf.check_selection(["setup/keel-doctor.sh"], always_none)
    except mf.SelectionError as err:
        if "full set required" not in str(err):
            fail("wrong error " + str(err))
    else:
        fail("always-none on an oracle was not caught")

    def always_some(_changed):
        return ("some", ["M03"])

    try:
        mf.check_selection(["setup/tests/harness/mutate.py"], always_some)
    except mf.SelectionError as err:
        if "full set required" not in str(err):
            fail("wrong error " + str(err))
    else:
        fail("partial-on-trigger was not caught")

    try:
        mf.check_selection(["setup/tests/harness/test-attacks.sh"], always_some)
    except mf.SelectionError as err:
        if "full set required" not in str(err):
            fail("wrong error " + str(err))
    else:
        fail("partial-on-oracle was not caught")

    line = mf.decision_line(["setup/keel.sh"])
    parts = line.split()
    if parts[:3] != ["RESULT", "mutate:", "run"] or "M03" not in parts or "M51" in parts:
        fail("decision " + line)
    if mf.decision_line(["docs/security.md"]) != mf.SKIP_LINE:
        fail("skip line")
    if mf.decision_line([".github/workflows/checks.yml"]) != mf.FULL_LINE:
        fail("full line")
    if not mf.ids_accepted(keel) or mf.ids_accepted([]) or mf.ids_accepted(["M51", "M03"]):
        fail("id check")
    print("mutant select: map matches; selection holds; always-none is caught")


if __name__ == "__main__":
    main()
