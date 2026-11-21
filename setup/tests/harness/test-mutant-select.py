#!/usr/bin/env python3
"""Mapped files, exact policy paths, and listed oracle scripts select CI mutants.

A selector that returns nothing, or that skips an unknown harness file, is caught.
The two setup docs in DOC_PATHS select nothing. Other Markdown under setup/ or
.github/ selects the full set.
"""
import importlib.util
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
PI = mids(94, 98) + ["M101", "M103", "M107", "M109"] + mids(111, 118) + ["M123", "M224", "M225", "M226"]
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
    "setup/tests/harness/test-mutant-result.sh": ["M92", "M93"] + ["M%d" % n for n in range(240, 275) if n != 247] + ["M%d" % n for n in range(275, 287)] + ["M294", "M295", "M296", "M297", "M305", "M306", "M307"] + ["M%d" % n for n in range(313, 333)],
    "setup/tests/harness/test-runtime.sh": RUNTIME,
    "setup/tests/harness/test-step4.sh": STEP4,
    "setup/tests/harness/test-step5.sh": STEP5,
    "setup/tests/harness/test-egress.sh": EGRESS,
    "setup/tests/harness/visibility-suite.sh": VIS,
}


def scope_module():
    path = os.path.join(ROOT, "scripts", "check-scope.py")
    spec = importlib.util.spec_from_file_location("check_scope", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    legacy_ids = ["M%d" % n for n in range(139, 177)]
    step6_ids = ["M%d" % n for n in range(207, 234)]
    gate_step_ids = ["M%d" % n for n in range(240, 247)] + ["M%d" % n for n in range(248, 271)]
    p1b_ids = ["M%d" % n for n in range(240, 287)]
    doc_ids = ["M287", "M288", "M289"]
    plan_ids = ["M290", "M291", "M292", "M293"]
    cover_ids = ["M%d" % n for n in range(294, 306)]
    pin_ids = ["M306", "M307"]
    path_ids = ["M308", "M309", "M310", "M311", "M312"]
    labeler_ids = ["M%d" % n for n in range(313, 333)]
    added = len(legacy_ids) + len(step6_ids) + len(p1b_ids) + len(doc_ids) + len(plan_ids) + len(cover_ids) + len(pin_ids) + len(path_ids) + len(labeler_ids)
    if len(mf.CI_IDS) != len(set(mf.CI_IDS)) or len(mf.CI_IDS) != 93 + added:
        fail("CI id set changed")
    if mf.CI_IDS[-len(labeler_ids):] != labeler_ids:
        fail("new CI ids are not M313-M332")
    tail = len(labeler_ids)
    if mf.CI_IDS[-tail - len(path_ids):-tail] != path_ids:
        fail("new CI ids are not M308-M312")
    tail += len(path_ids)
    if mf.CI_IDS[-tail - len(pin_ids):-tail] != pin_ids:
        fail("new CI ids are not M306-M307")
    tail += len(pin_ids)
    if mf.CI_IDS[-tail - len(cover_ids):-tail] != cover_ids:
        fail("new CI ids are not M294-M305")
    tail += len(cover_ids)
    if mf.CI_IDS[-tail - len(plan_ids):-tail] != plan_ids:
        fail("new CI ids are not M290-M293")
    tail += len(plan_ids)
    if mf.CI_IDS[-tail - len(doc_ids):-tail] != doc_ids:
        fail("new CI ids are not M287-M289")
    tail += len(doc_ids)
    if mf.CI_IDS[-tail - len(p1b_ids):-tail] != p1b_ids:
        fail("new CI ids are not M240-M286")
    tail += len(p1b_ids)
    if mf.CI_IDS[-tail - len(step6_ids):-tail] != step6_ids:
        fail("new CI ids are not M207-M233")
    tail += len(step6_ids)
    if mf.CI_IDS[-tail - len(legacy_ids):-tail] != legacy_ids:
        fail("new CI ids are not M139-M176")
    for mid in gate_step_ids:
        if mf.FILES.get(mid) != [".github/workflows/checks.yml"] or mutate.SUITE_OF.get(mid) != "test-mutant-result.sh":
            fail("gate step mutant %s must target checks.yml with test-mutant-result.sh" % mid)
    for mid in ("M272", "M273", "M307"):
        if mf.FILES.get(mid) != ["setup/tests/harness/gate_step_check.py"] or mutate.SUITE_OF.get(mid) != "test-mutant-result.sh":
            fail("checkout mutant %s must target gate_step_check.py with test-mutant-result.sh" % mid)
    for mid in ("M271", "M274"):
        if mf.FILES.get(mid) != ["scripts/tests/test_gate_jobs.py"] or mutate.SUITE_OF.get(mid) != "test-mutant-result.sh":
            fail("%s must target test_gate_jobs.py with test-mutant-result.sh" % mid)
    for mid in ["M%d" % n for n in range(275, 287)] + ["M306"]:
        if mf.FILES.get(mid) != ["scripts/check-scope.py"] or mutate.SUITE_OF.get(mid) != "test-mutant-result.sh":
            fail("%s must target check-scope.py with test-mutant-result.sh" % mid)
    for mid in doc_ids:
        if mf.FILES.get(mid) != ["setup/tests/harness/mutant_files.py"] or mutate.SUITE_OF.get(mid) != "test-mutant-select.py":
            fail("%s must target mutant_files.py with test-mutant-select.py" % mid)
    for mid in plan_ids:
        if mf.FILES.get(mid) != ["setup/tests/harness/mutate_shards.py"] or mutate.SUITE_OF.get(mid) != "test-mutant-select.py":
            fail("%s must target mutate_shards.py with test-mutant-select.py" % mid)
    binder_new = ["M294", "M295", "M296", "M297", "M305"]
    for mid in binder_new:
        if mf.FILES.get(mid) != ["setup/tests/harness/mutant-result.py"] or mutate.SUITE_OF.get(mid) != "test-mutant-result.sh":
            fail("%s must target mutant-result.py with test-mutant-result.sh" % mid)
    if mf.FILES.get("M298") != ["setup/tests/harness/mutate_shards.py"] or mutate.SUITE_OF.get("M298") != "test-mutant-select.py":
        fail("M298 must target mutate_shards.py with test-mutant-select.py")
    for mid in ("M299", "M300", "M301"):
        if mf.FILES.get(mid) != ["setup/tests/harness/mutate.py"] or mutate.SUITE_OF.get(mid) != "test-mutant-select.py":
            fail("%s must target mutate.py with test-mutant-select.py" % mid)
    for mid in ("M302", "M303"):
        if mf.FILES.get(mid) != ["setup/tests/harness/mutate-plan.sh"] or mutate.SUITE_OF.get(mid) != "test-mutant-select.py":
            fail("%s must target mutate-plan.sh with test-mutant-select.py" % mid)
    if mf.FILES.get("M304") != ["setup/tests/harness/run-tests.sh"] or mutate.SUITE_OF.get("M304") != "test-mutant-select.py":
        fail("M304 must target run-tests.sh with test-mutant-select.py")
    for mid in ("M308", "M309", "M310", "M311"):
        if mf.FILES.get(mid) != ["setup/tests/harness/mutate_shards.py"] or mutate.SUITE_OF.get(mid) != "test-mutant-select.py":
            fail("%s must target mutate_shards.py with test-mutant-select.py" % mid)
    if mf.FILES.get("M312") != ["setup/tests/harness/mutate_shards.py"] or mutate.SUITE_OF.get("M312") != "test-mutate-shards.sh":
        fail("M312 must target mutate_shards.py with test-mutate-shards.sh")
    for mid in ["M%d" % n for n in range(313, 326)] + ["M332"]:
        if mf.FILES.get(mid) != [".github/workflows/labeler.yml"] or mutate.SUITE_OF.get(mid) != "test-mutant-result.sh":
            fail("%s must target labeler.yml with test-mutant-result.sh" % mid)
    for mid in ["M%d" % n for n in range(326, 332)]:
        if mf.FILES.get(mid) != ["scripts/tests/test_gate_jobs.py"] or mutate.SUITE_OF.get(mid) != "test-mutant-result.sh":
            fail("%s must target test_gate_jobs.py with test-mutant-result.sh" % mid)
    import speed_cases
    if "S-A62" not in speed_cases.SELECT_CASES:
        fail("S-A62 is not in the select group")
    if "S-A62" not in speed_cases.CASES:
        fail("S-A62 is not in the case table")
    if speed_cases.S_A62_MIN_IDS < 276:
        fail("S-A62 id minimum is below 276")
    if speed_cases.S_A62_MIN_TARGET_PATHS < 31:
        fail("S-A62 target path minimum is below 31")
    if len(mf.OFFLINE_IDS) != len(set(mf.OFFLINE_IDS)) or len(mf.OFFLINE_IDS) != 5:
        fail("offline id set changed")
    if len(mf.CI_IDS) + len(mf.OFFLINE_IDS) != 98 + added:
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
    import speed_cases
    speed_rc = speed_cases.main(["speed_cases.py"])
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
    if "M99" in PI or "M01" in PI or len(PI) != 21:
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

    if mf.DOC_PATHS != frozenset(("setup/README.md", "setup/TESTING.md")):
        fail("SEL-D1 doc list changed %s" % (sorted(mf.DOC_PATHS),))
    scope = scope_module()
    for path in sorted(mf.DOC_PATHS):
        exists(path)
        if scope.kind_of(path) != "code":
            fail("SEL-D1 doc is not an ordinary doc for the scope check " + path)
        expect_skip(path, "SEL-D1")
    doc_and_keel = mf.check_selection(["setup/TESTING.md", "setup/keel.sh"])
    if doc_and_keel != ("some", KEEL):
        fail("SEL-D3 doc next to a target %s" % (doc_and_keel,))
    doc_and_unknown = mf.select_mutants(["setup/TESTING.md", "setup/common.sh"])
    if doc_and_unknown != ("full", list(mf.CI_IDS)):
        fail("SEL-D3 doc next to an unknown path %s" % (doc_and_unknown,))
    for path in (
        "setup/pi/harness-rules.md",
        "setup/pi/roles/developer.md",
        "setup/standards/rules.md",
        "setup/standards/views/developer/SKILL.md",
        "setup/tests/harness/fixtures/step6/rules.md",
        "setup/chrome/README.md",
    ):
        exists(path)
        expect_full(path, "SEL-D2")
    for path in (
        "setup/tools/README.md",
        "setup/a/README.md",
        "setup/testing.md",
        ".github/pull_request_template.md",
        ".github/copilot-instructions.md",
    ):
        expect_full(path, "SEL-D2")

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
        if path == "setup/tests/harness/mutate.py" and got != ("some", ["M299", "M300", "M301"]):
            fail("SEL-A2 mutate.py selected %s" % (got,))
    expect_exact(["setup/tests/harness/mutate.py"], ["M299", "M300", "M301"], "mutate.py")
    expect_exact(["setup/tests/harness/test-mutate-parse.py"], ["M299", "M300", "M301"], "parse")
    expect_exact(["setup/tests/harness/mutate-plan.sh"], ["M302", "M303"], "plan")
    expect_exact(["setup/tests/harness/run-tests.sh"], ["M304"], "runner")
    speed_ids = [
        mid for mid in mf.CI_IDS
        if mutate.SUITE_OF[mid] in ("test-mutant-select.py", "test-mutate-shards.sh")
    ]
    expect_exact(["setup/tests/harness/speed_cases.py"], speed_ids, "speed")
    select_ids = [mid for mid in mf.CI_IDS if mutate.SUITE_OF[mid] == "test-mutant-select.py"]
    expect_exact(["setup/tests/harness/test-mutant-select.py"], select_ids, "select suite")
    expect_skip("setup/tests/harness/mutate-issue.py", "issue")
    for path in mf.GATE_PATHS:
        exists(path)
        # test_gate_jobs.py also carries M271 and M274 (required check names, P1c).
        if path == "scripts/tests/test_gate_jobs.py":
            want = ["M92", "M93", "M271", "M274"] + ["M%d" % n for n in range(326, 332)]
        elif path == BINDER:
            want = ["M92", "M93", "M294", "M295", "M296", "M297", "M305"]
        else:
            want = ["M92", "M93"]
        expect_exact([path], want, "SEL-A4" if path.endswith("check-gate.sh") else "gate")
    expect_exact(["scripts/check-scope.py"], ["M%d" % n for n in range(275, 287)] + ["M306"], "scope")
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
    print("mutant select: SEL-H1 through SEL-M6, SEL-D1 through SEL-D3 and M01-H2 hold")
    if speed_rc != 0:
        fail("speed cases")


if __name__ == "__main__":
    main()
