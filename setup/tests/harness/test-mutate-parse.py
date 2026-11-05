#!/usr/bin/env python3
"""An invalid mutant is ERROR. A file that does not parse, or an empty RESULT, is not a survivor."""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mutate  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
KEEL = os.path.join(ROOT, "setup", "keel.sh")
STALE_M01 = '-v "$R/.git/objects:/base/objects:ro" "${MNT[@]}" -w /work "$IMG" sh -c "$*";;'


def fail(msg):
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def write_temp(name, text):
    directory = tempfile.mkdtemp(prefix="parse-")
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return directory, path


def apply_real(rel, mid):
    src = os.path.join(ROOT, "setup", rel)
    text = open(src, encoding="utf-8").read()
    old, new = mutate.M[mid][1], mutate.M[mid][2]
    if text.count(old) != 1:
        fail("%s old string count %s" % (mid, text.count(old)))
    updated, err = mutate.apply_edits(text, [(old, new)])
    if err or updated is None:
        fail("%s apply %s" % (mid, err))
    return updated


def parse_guard_holds(judge_fn):
    red, detail = judge_fn(["A1"], "RESULT A1: BLOCKED\n", None, True)
    return red is None and detail == mutate.PARSE_ERROR


def empty_is_error(judge_fn):
    red, detail = judge_fn(["A1"], "noise only\n", None, False)
    masked_red, masked_detail = judge_fn([], "noise only\n", None, False)
    return (
        red is None
        and detail == mutate.EMPTY_RESULT
        and masked_red is None
        and masked_detail == mutate.EMPTY_RESULT
        and mutate.verdict_tag(["A1"], red) == "ERROR"
        and mutate.verdict_tag([], masked_red) == "ERROR"
    )


def main():
    keel_text = open(KEEL, encoding="utf-8").read()
    old, new = mutate.M["M01"][1], mutate.M["M01"][2]
    if keel_text.count(old) != 1:
        fail("M01-H1 count %s" % keel_text.count(old))
    if old.count(":ro") != 1 or ":ro" in new:
        fail("M01-H1 replacement did not drop :ro")
    updated, err = mutate.apply_edits(keel_text, [(old, new)])
    if err or updated is None or updated.count(old) != 0 or updated.count(new) != 1:
        fail("M01-H1 apply %s" % err)
    directory, path = write_temp("keel.sh", updated)
    try:
        if not mutate.mutated_file_parses(path):
            fail("M01-H1 bash -n failed")
    finally:
        shutil.rmtree(directory)
    if keel_text.count(STALE_M01) != 0:
        fail("M01-A1 stale ;; string still matches")

    doubled = keel_text.replace(old, old + "\n" + old, 1)
    rejected, err = mutate.apply_edits(doubled, [(old, new)])
    if rejected is not None or not err or "2 matches" not in err:
        fail("M01-M1 uniqueness was not an error")
    red, detail = mutate.judge(["A1"], "RESULT A1: NOT BLOCKED\n", err, False)
    if red is not None or mutate.verdict_tag(["A1"], red) != "ERROR":
        fail("M01-M1 scored as a survivor")

    shell = apply_real("keel.sh", "M03")
    directory, path = write_temp("keel.sh", shell)
    try:
        if not mutate.mutated_file_parses(path):
            fail("PARSE-H1 shell apply does not parse")
    finally:
        shutil.rmtree(directory)
    python = apply_real("lib/visibility.py", "M45")
    directory, path = write_temp("visibility.py", python)
    try:
        if not mutate.mutated_file_parses(path):
            fail("PARSE-H1 python apply does not parse")
    finally:
        shutil.rmtree(directory)
    sample = "noise\nRESULT N1: NOT BLOCKED\nRESULT H3: BLOCKED\n"
    red, detail = mutate.judge(["N1"], sample, None, False)
    if red is None or "N1" not in detail or detail["N1"] != "NOT BLOCKED":
        fail("PARSE-H1 RESULT lines missing")
    if mutate.verdict_tag(["N1"], red) == "ERROR":
        fail("PARSE-H1 a present RESULT was an error")

    text, err = mutate.apply_edits("nothing here", [("missing", "x")])
    if text is not None or not err or "0 matches" not in err:
        fail("PARSE-A1 0-match was not an apply error")
    red, detail = mutate.judge(["A1"], "RESULT A1: BLOCKED\n", err, False)
    if red is not None or "0 matches" not in detail or mutate.verdict_tag(["A1"], red) != "ERROR":
        fail("PARSE-A1 0-match scored as NO")

    directory, path = write_temp("bad.py", "def broken(:\n    pass\n")
    try:
        if mutate.mutated_file_parses(path):
            fail("PARSE-A2 bad python parsed")
        red, detail = mutate.judge(["A1"], "RESULT A1: BLOCKED\n", None, True)
        if red is not None or detail != mutate.PARSE_ERROR:
            fail("PARSE-A2 parse failure was not ERROR")
    finally:
        shutil.rmtree(directory)

    directory, path = write_temp("bad.sh", "if then\nfi\n")
    try:
        if mutate.mutated_file_parses(path):
            fail("PARSE-A3 bad shell parsed")
        red, detail = mutate.judge(["A1"], "", None, not mutate.mutated_file_parses(path))
        if red is not None or detail != mutate.PARSE_ERROR or mutate.verdict_tag(["A1"], red) != "ERROR":
            fail("PARSE-A3 shell parse failure was not ERROR")
    finally:
        shutil.rmtree(directory)

    for exp in (["A1"], []):
        red, detail = mutate.judge(exp, "suite finished without a result\n", None, False)
        if red is not None or detail != mutate.EMPTY_RESULT or mutate.verdict_tag(exp, red) != "ERROR":
            fail("PARSE-A4 empty RESULT was not ERROR for %s" % exp)

    def disabled(_exp, out, applied_error=None, parse_failed=False):
        return mutate.judge(_exp, out, applied_error, False)

    if not parse_guard_holds(mutate.judge):
        fail("PARSE-M1 real parse guard missing")
    if parse_guard_holds(disabled):
        fail("PARSE-M1 disabled parse guard was not caught")

    def empty_as_success(_exp, out, applied_error=None, parse_failed=False):
        res = mutate.collect_results(out)
        return mutate.red_from_results(res), res

    if not empty_is_error(mutate.judge):
        fail("PARSE-M2 real empty RESULT path")
    if empty_is_error(empty_as_success):
        fail("PARSE-M2 empty RESULT treated as success was not caught")

    print("mutate parse: PARSE-H1 through PARSE-M2 and M01-H1, M01-A1, M01-M1 hold")


if __name__ == "__main__":
    main()
