#!/usr/bin/env python3
"""Mapped files, exact policy paths, and listed oracle scripts select CI mutants.

A selector that returns nothing, or that skips an unknown harness file, is caught.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mutate  # noqa: E402
import mutant_files as mf  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
BINDER = "setup/tests/harness/mutant-result.py"


def fail(msg):
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def mids(start, end):
    return ["M%02d" % n for n in range(start, end + 1)]


VIS = mids(45, 46) + mids(48, 52) + mids(70, 72) + mids(104, 105)
VIS_FILE = VIS + ["M128"]
EGRESS = mids(53, 66) + ["M68", "M76", "M77"]
ATTACK = ["M03", "M17", "M27"] + mids(45, 77) + ["M79"] + mids(82, 85)
RUNTIME = ["M80", "M81"] + mids(86, 91)
STEP4 = mids(94, 98) + ["M101", "M103"] + mids(104, 105) + mids(107, 118)
KEEL = [
    "M03", "M17", "M27", "M47", "M67", "M69",
    "M73", "M74", "M75", "M82", "M83", "M84", "M85", "M91",
]
PI = mids(94, 98) + ["M101", "M103", "M107", "M109"] + mids(111, 118) + ["M123"]
STEP5 = ["M{0}".format(n) for n in range(119, 139)]
RESIDUAL = (
    "setup/tests/harness/fixtures/runtime-rootless.info",
    "setup/tests/harness/fixtures/runtime-rootful.info",
    "setup/tests/harness/fixtures/runtime-userns.info",
    "setup/tests/harness/runtime-stub.sh",
    "setup/tests/harness/harness-keel.sh",
)
ORACLES = {
    "setup/tests/harness/test-attacks.sh": ATTACK,
    "setup/tests/harness/test-attack-results.sh": ["M78"],
    "setup/tests/harness/test-mutant-result.sh": ["M92", "M93"],
    "setup/tests/harness/test-runtime.sh": RUNTIME,
    "setup/tests/harness/test-step4.sh": STEP4,
    "setup/tests/harness/test-step5.sh": STEP5,
    "setup/tests/harness/test-egress.sh": EGRESS,
    "setup/tests/harness/visibility-suite.sh": VIS,
}


def in_ci_order(ids):
    want = set(ids)
    return [mid for mid in mf.CI_IDS if mid in want]


def with_dependents(path, own):
    extra = []
    for owner, deps in mf.DEPENDS.items():
        if path not in deps:
            continue
        for mid, paths in mf.FILES.items():
            if owner in paths and mid in mf.CI_IDS:
                extra.append(mid)
    return in_ci_order(list(own) + extra)


def validate():
    if set(mf.FILES) != set(mutate.M):
        fail("FILES and mutate.M differ")
    for mid, paths in mf.FILES.items():
        if not paths:
            fail("empty map " + mid)
        rel = mutate.M[mid][0]
        if rel.startswith("scripts/") or rel.startswith(".github/"):
            expect = [rel]
        else:
            expect = ["setup/" + rel]
        if mid == "M171":
            expect = [
                ".github/workflows/mutate-pr.yml",
                ".github/workflows/mutate-full.yml",
            ]
        if paths != expect:
            fail("%s map %s != %s" % (mid, paths, expect))
        for path in paths:
            if not os.path.isfile(os.path.join(ROOT, path)):
                fail("missing " + path)
    new_ids = ["M%d" % n for n in range(139, 175)]
    if len(mf.CI_IDS) != len(set(mf.CI_IDS)) or len(mf.CI_IDS) != 93 + len(new_ids):
        fail("CI id set changed")
    if mf.CI_IDS[-len(new_ids):] != new_ids:
        fail("new CI ids are not M139-M174")
    if len(mf.OFFLINE_IDS) != len(set(mf.OFFLINE_IDS)) or len(mf.OFFLINE_IDS) != 5:
        fail("offline id set changed")
    if len(mf.CI_IDS) + len(mf.OFFLINE_IDS) != 98 + len(new_ids):
        fail("full id count drifted")
    if len(mf.FULL_ONLY) != 40 or set(mf.FULL_ONLY) & set(mf.CI_IDS + mf.OFFLINE_IDS):
        fail("FULL_ONLY is not the remaining ids")
    if set(mf.FILES) != set(mf.CI_IDS) | set(mf.OFFLINE_IDS) | set(mf.FULL_ONLY):
        fail("an id is missing from the three lists")
    for mid in mf.CI_IDS + mf.OFFLINE_IDS + mf.FULL_ONLY:
        if mid not in mf.FILES:
            fail("listed id not mapped " + mid)
    for path in mf.TRIGGERS:
        if not os.path.isfile(os.path.join(ROOT, path)):
            fail("missing trigger " + path)
    mapped = {path for paths in mf.FILES.values() for path in paths}
    if not set(mf.TARGET_ONLY) <= mapped:
        fail("target-only file is not a mutant target")
    for path in (
        "setup/check.sh",
        "setup/docker/ancestor-guard.sh",
        "setup/keel-doctor.sh",
    ):
        if path not in mapped or path not in mf.TARGET_ONLY:
            fail("selective edit target missing " + path)
    if BINDER not in mf.GATE_PATHS or BINDER in mf.TARGET_ONLY:
        fail("SEL-M4 binder must stay a gate path and off the selective targets")
    if set(mf.ORACLE_FILES) != set(RESIDUAL):
        fail("SEL-M6 ORACLE_FILES is not the residual fixture set")
    for path in mf.ORACLE_FILES:
        if path in mf.TARGET_ONLY or path in mf.ORACLE_SCRIPTS:
            fail("residual oracle listed as selective " + path)
        if not os.path.isfile(os.path.join(ROOT, path)):
            fail("missing oracle " + path)
    if not set(ORACLES) <= set(mf.ORACLE_SCRIPTS):
        fail("oracle script map dropped a suite")
    for path, ids in (
        ("VISIBILITY_CI", VIS),
        ("EGRESS_CI", EGRESS),
        ("ATTACK_CI", ATTACK),
        ("RUNTIME_CI", RUNTIME),
        ("STEP4_CI", STEP4),
        ("STEP5_CI", STEP5),
    ):
        got = list(getattr(mf, path))
        if got != ids or got != in_ci_order(ids):
            fail("%s drifted: %s" % (path, got))
        if any(mid not in mf.CI_IDS for mid in got):
            fail("%s includes a non-CI id" % path)
    if len(ATTACK) != 41 or len(STEP4) != 21 or len(RUNTIME) != 8:
        fail("oracle list length changed")
    if len(VIS) != 12 or len(EGRESS) != 17:
        fail("policy list length changed")
    for path in mf.TARGET_ONLY:
        if path.startswith("setup/") or path.startswith(".github/"):
            continue
        fail("target-only path is outside setup/ and .github/: " + path)
    for name in ("M79", "M80", "M90", "M92", "M93"):
        if name not in mf.CI_IDS:
            fail(name + " is not in the CI set")
    if "M01" in mf.CI_IDS or "M01" not in mf.OFFLINE_IDS:
        fail("M01-H2 membership")
    if "test-runtime.sh" in "".join(mf.ORACLE_FILES) or "test-mutant-result.sh" in "".join(mf.ORACLE_FILES):
        fail("SEL-M6 selective oracle restored to ORACLE_FILES")


def expect_exact(changed, ids, label):
    got = mf.check_selection(changed)
    if got != ("some", list(ids)):
        fail("%s selection %s -> %s" % (label, changed, got))
    line = mf.decision_line(changed)
    if line != "RESULT mutate: run " + " ".join(ids):
        fail("%s decision %s" % (label, line))


def expect_full(path, label):
    if path in mf.TARGET_ONLY or path in mf.ORACLE_SCRIPTS:
        fail("%s listed as selective %s" % (label, path))
    got = mf.select_mutants([path])
    if got != ("full", list(mf.CI_IDS)):
        fail("%s full set required for %s, got %s" % (label, path, got))
    if mf.decision_line([path]) != mf.FULL_LINE:
        fail("%s decision for %s" % (label, path))


def expect_skip(path, label):
    got = mf.check_selection([path])
    if got != ("skip", []):
        fail("%s skip required for %s, got %s" % (label, path, got))
    if mf.decision_line([path]) != mf.SKIP_LINE:
        fail("%s skip line for %s" % (label, path))


def exists(path):
    if not os.path.isfile(os.path.join(ROOT, path)):
        fail("missing " + path)


def catch(changed, select, needle, label):
    try:
        mf.check_selection(changed, select)
    except mf.SelectionError as err:
        if needle not in str(err):
            fail("%s wrong error %s" % (label, err))
    else:
        fail("%s was not caught" % label)


def cli_lists():
    ci = subprocess.check_output(
        [sys.executable, os.path.join(HERE, "mutant_files.py"), "--ci"],
        text=True,
    ).split()
    full = subprocess.check_output(
        [sys.executable, os.path.join(HERE, "mutant_files.py"), "--full"],
        text=True,
    ).split()
    if "M01" in ci or ci != list(mf.CI_IDS):
        fail("M01-H2 --ci includes M01 or drifted")
    if "M01" not in full or full != list(mf.CI_IDS) + list(mf.OFFLINE_IDS):
        fail("M01-H2 --full dropped M01")
    if mf.ids_accepted(["M01"]) or not mf.ids_accepted(full):
        fail("M01-H2 id check")


def main():
    validate()
    for ids in (VIS, EGRESS, ATTACK, RUNTIME, STEP4, KEEL, PI):
        if ids != in_ci_order(ids):
            fail("id list is not in CI order")

    expect_exact(["setup/keel.sh"], KEEL, "SEL-H1")
    if "M03" not in KEEL or "M51" in KEEL:
        fail("SEL-H1 keel set")
    expect_exact(["setup/lib/visibility.py"], with_dependents("setup/lib/visibility.py", VIS_FILE), "SEL-H1 visibility")
    if set(KEEL) & set(VIS_FILE):
        fail("keel.sh and visibility.py share a CI mutant")
    both = mf.check_selection(["setup/keel.sh", "setup/lib/visibility.py"])
    union = [mid for mid in mf.CI_IDS if mid in set(KEEL) | set(with_dependents("setup/lib/visibility.py", VIS_FILE))]
    if both != ("some", union):
        fail("combined selection %s" % (both,))

    egress_py = [mid for mid in EGRESS if mid in ("M57", "M58", "M59", "M60", "M68", "M76")]
    egress_sh = [mid for mid in EGRESS if mid not in ("M57", "M58", "M59", "M60", "M61", "M62", "M63", "M68", "M76")]
    expect_exact(["setup/lib/egress.py"], with_dependents("setup/lib/egress.py", egress_py), "egress.py")
    expect_exact(["setup/lib/egress.sh"], with_dependents("setup/lib/egress.sh", egress_sh), "egress.sh")
    expect_exact(["setup/tests/harness/attack-results.sh"], ["M78"], "attack-results")
    expect_exact(["setup/check.sh"], ["M79"], "SEL-H6")
    expect_exact(["setup/docker/ancestor-guard.sh"], ["M108"], "ancestor-guard")
    expect_exact(["setup/keel-doctor.sh"], ["M89", "M110", "M129"], "keel-doctor")
    expect_exact(["setup/lib/pi_launch.py"], with_dependents("setup/lib/pi_launch.py", PI), "pi_launch")
    if "M99" in PI or "M01" in PI or len(PI) != 18:
        fail("pi_launch CI list includes an offline id")

    for path in (
        "setup/allow/developer.paths",
        "setup/allow/critic.paths",
        "setup/allow/architect.paths",
    ):
        exists(path)
        expect_exact([path], VIS, "SEL-H2")
    exists("setup/deny/base")
    expect_exact(["setup/deny/base"], VIS, "SEL-H3")
    exists("setup/egress/developer.allow")
    expect_exact(["setup/egress/developer.allow"], EGRESS, "SEL-H4")

    for path, ids in ORACLES.items():
        exists(path)
        label = "SEL-H5" if path.endswith("test-step4.sh") else "oracle"
        if path.endswith("test-runtime.sh"):
            label = "SEL-H8"
        elif path.endswith("test-mutant-result.sh"):
            label = "SEL-H9"
        elif path.endswith("test-egress.sh"):
            label = "SEL-H10"
        elif path.endswith("visibility-suite.sh"):
            label = "SEL-H11"
        expect_exact([path], ids, label)
        if list(mf.ORACLE_SCRIPTS[path]) != ids:
            fail("oracle constant drifted " + path)

    expect_skip("docs/status.md", "SEL-H7")
    expect_skip("docs/security.md", "docs")
    expect_skip("scripts/check.sh", "scripts")
    if mf.check_selection([]) != ("skip", []):
        fail("empty change should skip")
    docs_and_keel = mf.check_selection(["docs/status.md", "setup/keel.sh"])
    if docs_and_keel != ("some", KEEL):
        fail("docs next to a target %s" % (docs_and_keel,))

    full_paths = [
        "setup/tests/harness/test-happy.sh",
        "setup/tests/harness/h3-verdict.sh",
        "setup/common.sh",
        "setup/lib/mock_model.py",
        "setup/docker/keel-git.Dockerfile",
        "setup/docker/keel-proxy.Dockerfile",
        "setup/gitleaks.toml",
        "setup/gitleaks-install.sh",
        "setup/gitleaks.ignore",
        "setup/not-a-mapped-target",
        ".github/unknown.yml",
        "setup/allow/README.md",
        "setup/egress/README.md",
        "setup/deny/README.md",
        "setup/allow/foo.paths.bak",
        "setup/allow/nested/x.paths",
        "setup/deny/base.local",
        "setup/egress/developer.allow.bak",
    ]
    for path in full_paths:
        label = "SEL-A1" if path == "setup/not-a-mapped-target" else "full"
        if path == "setup/allow/README.md":
            label = "SEL-A6"
        elif path == "setup/egress/README.md":
            label = "SEL-A7"
        elif path in ("setup/allow/foo.paths.bak", "setup/allow/nested/x.paths"):
            label = "SEL-A9"
        if "not-a-mapped-target" not in path and not path.endswith("unknown.yml") and "foo.paths.bak" not in path and "nested/" not in path and not path.endswith(".bak") and path != "setup/deny/base.local" and path != "setup/deny/README.md":
            exists(path)
        expect_full(path, label)
    for path in RESIDUAL:
        exists(path)
        expect_full(path, "SEL-A8")
    for path in mf.MECHANISM:
        got = mf.select_mutants([path])
        if got[0] == "full":
            fail("mechanism file widened to the full set: " + path)
        if path == "setup/tests/harness/mutate.py" and got != ("skip", []):
            fail("SEL-A2 mutate.py selected %s" % (got,))
    for path in mf.GATE_PATHS:
        exists(path)
        expect_exact([path], ["M92", "M93"], "SEL-A4" if path.endswith("check-gate.sh") else "gate")
    mixed = mf.select_mutants(["setup/keel.sh", "setup/tests/harness/test-happy.sh"])
    if mixed != ("full", list(mf.CI_IDS)):
        fail("SEL-A3 oracle next to a target must select the full set")
    unknown = mf.select_mutants(["setup/keel.sh", "setup/not-mapped-X"])
    if unknown != ("full", list(mf.CI_IDS)):
        fail("SEL-A3 selective plus unknown must select the full set")
    attacks_and_keel = mf.select_mutants(["setup/keel.sh", "setup/tests/harness/test-attacks.sh"])
    if attacks_and_keel[0] != "some" or "M91" not in attacks_and_keel[1] or "M80" in attacks_and_keel[1]:
        fail("two selective paths became the full set %s" % (attacks_and_keel,))

    if mf.path_matches("setup/allow/README.md", "setup/allow/*.paths"):
        fail("SEL-A6 glob matched a README")
    if mf.path_matches("setup/allow/nested/x.paths", "setup/allow/*.paths"):
        fail("SEL-A9 glob matched a nested path")
    if mf.path_matches("setup/allow/foo.paths.bak", "setup/allow/*.paths"):
        fail("SEL-A9 glob matched a backup name")
    if not mf.path_matches("setup/allow/developer.paths", "setup/allow/*.paths"):
        fail("SEL-H2 glob missed developer.paths")
    if mf.path_matches("setup/deny/base.local", "setup/deny/base"):
        fail("deny suffix matched the exact base path")
    if mf.path_matches("setup/egress/README.md", "setup/egress/*.allow"):
        fail("SEL-A7 glob matched a README")

    def always_none(_changed):
        return ("skip", [])

    catch(["setup/keel.sh"], always_none, "selection dropped every mutant", "always-none")
    catch(["setup/allow/developer.paths"], always_none, "selection dropped every mutant", "SEL-M1")
    catch(["setup/lib/portable.sh"], always_none, "selection dropped every mutant", "SEL-M2")

    def skip_allow(changed):
        if any(mf.path_matches(path, "setup/allow/*.paths") for path in changed):
            return ("skip", [])
        return mf.select_mutants(changed)

    catch(["setup/allow/developer.paths"], skip_allow, "selection dropped every mutant", "SEL-M3")

    def binder_only(changed):
        if list(changed) == [BINDER]:
            return ("some", ["M92"])
        return mf.select_mutants(changed)

    catch([BINDER], binder_only, "selection does not match the map", "SEL-M4")

    def directory_prefix(changed):
        if changed and all(
            path.startswith("setup/allow/") or path.startswith("setup/egress/") or path.startswith("setup/deny/")
            for path in changed
        ):
            if not any(mf.policy_ids(path) for path in changed):
                return ("skip", [])
        return mf.select_mutants(changed)

    catch(["setup/allow/README.md"], directory_prefix, "full set required", "SEL-M5")

    def always_some(_changed):
        return ("some", ["M03"])

    catch(["setup/tests/harness/mutate.py"], always_some, "selection does not match the map", "partial-on-trigger")
    catch(["setup/tests/harness/test-happy.sh"], always_some, "full set required", "partial-on-unknown")
    catch(["setup/tests/harness/test-runtime.sh"], always_some, "selection does not match the map", "SEL-M6")

    line = mf.decision_line(["setup/keel.sh"])
    parts = line.split()
    if parts[:3] != ["RESULT", "mutate:", "run"] or "M03" not in parts or "M51" in parts:
        fail("decision " + line)
    if not mf.ids_accepted(KEEL) or mf.ids_accepted([]) or mf.ids_accepted(["M51", "M03"]):
        fail("id check")
    cli_lists()
    print("mutant select: SEL-H1 through SEL-M6 and M01-H2 hold")
    import speed_cases
    if speed_cases.main(["speed_cases.py"]) != 0:
        fail("speed cases")


if __name__ == "__main__":
    main()
