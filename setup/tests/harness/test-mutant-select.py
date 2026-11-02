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


def expect_some(changed, present, absent):
    status, ids = mf.check_selection(changed)
    if status != "some" or present not in ids or absent in ids:
        fail("selection %s -> %s %s" % (changed, status, ids))
    return ids


def main():
    validate()
    keel = expect_some(["setup/keel.sh"], "M03", "M51")
    visibility = expect_some(["setup/lib/visibility.py"], "M51", "M03")
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

    def always_some(_changed):
        return ("some", ["M03"])

    try:
        mf.check_selection(["setup/tests/harness/mutate.py"], always_some)
    except mf.SelectionError as err:
        if "full set required" not in str(err):
            fail("wrong error " + str(err))
    else:
        fail("partial-on-trigger was not caught")

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
