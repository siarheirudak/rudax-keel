#!/usr/bin/env python3
"""Which harness file each mutant edits, and which of those mutants CI runs.

The map is data. test-mutant-select.py checks it against mutate.M.
"""
import ast
import fnmatch
import os
import re
import sys

FILES = {
    "M01": ["setup/keel.sh"],
    "M02": ["setup/keel.sh"],
    "M03": ["setup/keel.sh"],
    "M04": ["setup/keel.sh"],
    "M05": ["setup/keel.sh"],
    "M06": ["setup/keel.sh"],
    "M07": ["setup/keel.sh"],
    "M08": ["setup/keel.sh"],
    "M09": ["setup/keel.sh"],
    "M10": ["setup/keel.sh"],
    "M11": ["setup/keel.sh"],
    "M12": ["setup/keel.sh"],
    "M13": ["setup/keel.sh"],
    "M14": ["setup/keel.sh"],
    "M15": ["setup/keel.sh"],
    "M16": ["setup/keel.sh"],
    "M17": ["setup/keel.sh"],
    "M18": ["setup/keel.sh"],
    "M19": ["setup/keel.sh"],
    "M20": ["setup/keel.sh"],
    "M21": ["setup/keel.sh"],
    "M22": ["setup/keel.sh"],
    "M23": ["setup/keel.sh"],
    "M24": ["setup/keel.sh"],
    "M25": ["setup/keel.sh"],
    "M26": ["setup/keel.sh"],
    "M27": ["setup/keel.sh"],
    "M28": ["setup/keel.sh"],
    "M29": ["setup/keel.sh"],
    "M30": ["setup/keel.sh"],
    "M31": ["setup/keel.sh"],
    "M32": ["setup/keel.sh"],
    "M33": ["setup/keel.sh"],
    "M34": ["setup/keel.sh"],
    "M35": ["setup/keel.sh"],
    "M36": ["setup/keel.sh"],
    "M37": ["setup/keel.sh"],
    "M38": ["setup/keel.sh"],
    "M39": ["setup/keel.sh"],
    "M40": ["setup/keel.sh"],
    "M41": ["setup/keel.sh"],
    "M42": ["setup/keel.sh"],
    "M43": ["setup/keel.sh"],
    "M44": ["setup/keel.sh"],
    "M45": ["setup/lib/visibility.py"],
    "M46": ["setup/lib/visibility.py"],
    "M47": ["setup/keel.sh"],
    "M48": ["setup/lib/visibility.py"],
    "M49": ["setup/lib/visibility.py"],
    "M50": ["setup/lib/visibility.py"],
    "M51": ["setup/lib/visibility.py"],
    "M52": ["setup/lib/visibility.py"],
    "M53": ["setup/lib/egress.sh"],
    "M54": ["setup/lib/egress.sh"],
    "M55": ["setup/lib/egress.sh"],
    "M56": ["setup/lib/egress.sh"],
    "M57": ["setup/lib/egress.py"],
    "M58": ["setup/lib/egress.py"],
    "M59": ["setup/lib/egress.py"],
    "M60": ["setup/lib/egress.py"],
    "M61": ["setup/lib/egress_proxy.py"],
    "M62": ["setup/lib/egress_proxy.py"],
    "M63": ["setup/lib/egress_proxy.py"],
    "M64": ["setup/lib/egress.sh"],
    "M65": ["setup/lib/egress.sh"],
    "M66": ["setup/lib/egress.sh"],
    "M67": ["setup/keel.sh"],
    "M68": ["setup/lib/egress.py"],
    "M69": ["setup/keel.sh"],
    "M70": ["setup/lib/visibility.py"],
    "M71": ["setup/lib/visibility.py"],
    "M72": ["setup/lib/visibility.py"],
    "M73": ["setup/keel.sh"],
    "M74": ["setup/keel.sh"],
    "M75": ["setup/keel.sh"],
    "M76": ["setup/lib/egress.py"],
    "M77": ["setup/lib/egress.sh"],
    "M78": ["setup/tests/harness/attack-results.sh"],
    "M79": ["setup/check.sh"],
    "M80": ["setup/lib/runtime.sh"],
    "M81": ["setup/lib/runtime.sh"],
    "M82": ["setup/keel.sh"],
    "M83": ["setup/keel.sh"],
    "M84": ["setup/keel.sh"],
    "M85": ["setup/keel.sh"],
    "M86": ["setup/lib/runtime.sh"],
    "M87": ["setup/lib/runtime.sh"],
    "M88": ["setup/lib/runtime.sh"],
    "M89": ["setup/keel-doctor.sh"],
    "M90": ["setup/tests/harness/doctor-score.sh"],
    "M91": ["setup/keel.sh"],
    "M92": ["setup/tests/harness/mutant-result.py"],
    "M93": ["scripts/check-gate.sh"],
    "M94": ["setup/lib/pi_launch.py"],
    "M95": ["setup/lib/pi_launch.py"],
    "M96": ["setup/lib/pi_launch.py"],
    "M97": ["setup/lib/pi_launch.py"],
    "M98": ["setup/lib/pi_launch.py"],
    "M99": ["setup/lib/pi_launch.py"],
    "M100": ["setup/lib/pi_launch.py"],
    "M101": ["setup/lib/pi_launch.py"],
    "M102": ["setup/lib/pi_launch.py"],
    "M103": ["setup/lib/pi_launch.py"],
    "M104": ["setup/lib/visibility.py"],
    "M105": ["setup/lib/visibility.py"],
    "M106": ["setup/lib/pi_launch.py"],
    "M107": ["setup/lib/pi_launch.py"],
    "M108": ["setup/docker/ancestor-guard.sh"],
    "M109": ["setup/lib/pi_launch.py"],
    "M110": ["setup/keel-doctor.sh"],
    "M111": ["setup/lib/pi_launch.py"],
    "M112": ["setup/lib/pi_launch.py"],
    "M113": ["setup/lib/pi_launch.py"],
    "M114": ["setup/lib/pi_launch.py"],
    "M115": ["setup/lib/pi_launch.py"],
    "M116": ["setup/lib/pi_launch.py"],
    "M117": ["setup/lib/pi_launch.py"],
    "M118": ["setup/lib/pi_launch.py"],
    "M119": ["setup/lib/discovery_filter.py"],
    "M120": ["setup/lib/discovery_filter.py"],
    "M121": ["setup/lib/discovery_filter.py"],
    "M122": ["setup/lib/discovery_filter.py"],
    "M123": ["setup/lib/pi_launch.py"],
    "M124": ["setup/lib/discovery_filter.py"],
    "M125": ["setup/lib/discovery_filter.py"],
    "M126": ["setup/lib/discovery_filter.py"],
    "M127": ["setup/lib/discovery_filter.py"],
    "M128": ["setup/lib/visibility.py"],
    "M129": ["setup/keel-doctor.sh"],
    "M130": ["setup/lib/discovery_judge.py"],
    "M131": ["setup/lib/discovery_judge.py"],
    "M132": ["setup/lib/discovery_filter.py"],
    "M133": ["setup/lib/discovery_judge.py"],
    "M134": ["setup/lib/discovery_filter.py"],
    "M135": ["setup/lib/discovery_filter.py"],
    "M136": ["setup/lib/discovery_judge.py"],
    "M137": ["setup/lib/discovery_judge.py"],
    "M138": ["setup/lib/discovery_judge.py"],
    "M139": ["setup/tests/harness/mutant_defs.py"],
    "M140": ["setup/tests/harness/mutant_defs.py"],
    "M141": ["setup/tests/harness/mutant_defs.py"],
    "M142": ["setup/tests/harness/mutant_defs.py"],
    "M143": ["setup/tests/harness/mutant_defs.py"],
    "M144": ["setup/tests/harness/mutant_defs.py"],
    "M145": ["setup/tests/harness/mutant_defs.py"],
    "M146": ["setup/tests/harness/mutant_defs.py"],
    "M147": ["setup/tests/harness/mutant_defs.py"],
    "M148": ["setup/tests/harness/mutant_defs.py"],
    "M149": ["setup/tests/harness/mutant_files.py"],
    "M150": ["setup/tests/harness/mutant_files.py"],
    "M151": ["setup/tests/harness/mutant_files.py"],
    "M152": ["setup/tests/harness/mutate_shards.py"],
    "M153": ["setup/tests/harness/mutate_shards.py"],
    "M154": ["setup/tests/harness/mutate_shards.py"],
    "M155": ["setup/tests/harness/mutate_shards.py"],
    "M156": ["setup/tests/harness/mutate-full-state.py"],
    "M157": ["setup/tests/harness/mutate-full-state.py"],
    "M158": ["setup/tests/harness/mutant_defs.py"],
    "M159": ["setup/tests/harness/mutate-full-state.py"],
    "M160": ["setup/tests/harness/mutant_defs.py"],
    "M161": ["setup/tests/harness/mutant_defs.py"],
    "M162": ["setup/tests/harness/mutant_defs.py"],
    "M163": ["setup/tests/harness/mutant_defs.py"],
    "M164": ["setup/tests/harness/mutate_shards.py"],
    "M165": ["setup/tests/harness/mutate_shards.py"],
    "M166": ["setup/tests/harness/mutate-full-state.py"],
    "M167": ["setup/tests/harness/mutate_shards.py"],
    "M168": ["setup/tests/harness/mutate_shards.py"],
    "M169": ["setup/tests/harness/mutate_shards.py"],
    "M170": ["setup/tests/harness/mutate_shards.py"],
    "M171": [".github/workflows/mutate-pr.yml", ".github/workflows/mutate-full.yml"],
    "M172": ["setup/tests/harness/mutate_shards.py"],
    "M173": ["setup/tests/harness/mutate_shards.py"],
    "M174": ["setup/tests/harness/mutate_shards.py"],
    "M175": [".github/workflows/mutate-pr.yml"],
    "M176": [".github/workflows/mutate-full.yml"],
    "M207": ["setup/standards/gen.py"],
    "M208": ["setup/standards/gen.py"],
    "M209": ["setup/standards/gen.py"],
    "M210": ["setup/standards/gen.py"],
    "M211": ["setup/standards/gen.py"],
    "M212": ["setup/standards/gen.py"],
    "M213": ["setup/standards/gen.py"],
    "M214": ["setup/standards/gen.py"],
    "M215": ["setup/standards/gen.py"],
    "M216": ["setup/standards/gen.py"],
    "M217": ["setup/standards/gen.py"],
    "M218": ["setup/standards/gen.py"],
    "M219": ["setup/standards/gen.py"],
    "M220": ["setup/standards/gen.py"],
    "M221": ["setup/standards/gen.py"],
    "M222": ["setup/standards/gen.py"],
    "M223": ["setup/standards/gen.py"],
    "M224": ["setup/lib/pi_launch.py"],
    "M225": ["setup/lib/pi_launch.py"],
    "M226": ["setup/lib/pi_launch.py"],
    "M227": ["setup/standards/gen.py"],
    "M228": ["setup/standards/gen.py"],
    "M229": ["setup/standards/gen.py"],
    "M230": ["setup/standards/gen.py"],
    "M231": ["setup/standards/gen.py"],
    "M232": ["setup/standards/gen.py"],
    "M233": ["setup/tests/harness/step6_check.py"],
}

# The CI set. Offline mutants stay out of pull-request runs.
CI_IDS = [
    "M03",
    "M17",
    "M27",
    "M45",
    "M46",
    "M47",
    "M48",
    "M49",
    "M50",
    "M51",
    "M52",
    "M53",
    "M54",
    "M55",
    "M56",
    "M57",
    "M58",
    "M59",
    "M60",
    "M61",
    "M62",
    "M63",
    "M64",
    "M65",
    "M66",
    "M67",
    "M68",
    "M69",
    "M70",
    "M71",
    "M72",
    "M73",
    "M74",
    "M75",
    "M76",
    "M77",
    "M78",
    "M79",
    "M80",
    "M81",
    "M82",
    "M83",
    "M84",
    "M85",
    "M86",
    "M87",
    "M88",
    "M89",
    "M90",
    "M91",
    "M92",
    "M93",
    "M94",
    "M95",
    "M96",
    "M97",
    "M98",
    "M101",
    "M103",
    "M104",
    "M105",
    "M107",
    "M108",
    "M109",
    "M110",
    "M111",
    "M112",
    "M113",
    "M114",
    "M115",
    "M116",
    "M117",
    "M118",
    "M119",
    "M120",
    "M121",
    "M122",
    "M123",
    "M124",
    "M125",
    "M126",
    "M127",
    "M128",
    "M129",
    "M130",
    "M131",
    "M132",
    "M133",
    "M134",
    "M135",
    "M136",
    "M137",
    "M138",
    "M139",
    "M140",
    "M141",
    "M142",
    "M143",
    "M144",
    "M145",
    "M146",
    "M147",
    "M148",
    "M149",
    "M150",
    "M151",
    "M152",
    "M153",
    "M154",
    "M155",
    "M156",
    "M157",
    "M158",
    "M159",
    "M160",
    "M161",
    "M162",
    "M163",
    "M164",
    "M165",
    "M166",
    "M167",
    "M168",
    "M169",
    "M170",
    "M171",
    "M172",
    "M173",
    "M174",
    "M175",
    "M176",
    "M207",
    "M208",
    "M209",
    "M210",
    "M211",
    "M212",
    "M213",
    "M214",
    "M215",
    "M216",
    "M217",
    "M218",
    "M219",
    "M220",
    "M221",
    "M222",
    "M223",
    "M224",
    "M225",
    "M226",
    "M227",
    "M228",
    "M229",
    "M230",
    "M231",
    "M232",
    "M233",
]

# Docker mount probes, plus M01. Pull-request CI skips these. The daily full run includes them.
OFFLINE_IDS = [
    "M01",
    "M99",
    "M100",
    "M102",
    "M106",
]

# Ids that are not in the CI or offline lists. The scheduled run grades every id.
FULL_ONLY = [
    "M02",
    "M04",
    "M05",
    "M06",
    "M07",
    "M08",
    "M09",
    "M10",
    "M11",
    "M12",
    "M13",
    "M14",
    "M15",
    "M16",
    "M18",
    "M19",
    "M20",
    "M21",
    "M22",
    "M23",
    "M24",
    "M25",
    "M26",
    "M28",
    "M29",
    "M30",
    "M31",
    "M32",
    "M33",
    "M34",
    "M35",
    "M36",
    "M37",
    "M38",
    "M39",
    "M40",
    "M41",
    "M42",
    "M43",
    "M44",
]

# Known masked ids. Each entry carries a reason. A new empty exp is refused
# until the id is listed here on the default branch.
EXPECTED_MASKED = {
    "M14": "paired with the merge-base edit and masked until that edit is applied",
    "M21": "bundle verify stays masked behind a later gate check",
    "M33": "prune expiry stays masked behind a later gate check",
    "M40": "nested git path rule stays masked until fetch fsck is removed with it",
    "M44": "orphan commit check stays masked behind a later gate check",
}

# Which ids block a full run. A reviewed change sets this to "all".
RED_COUNTS = "ci+offline"

# Setting: full runs before a missing green all-id run is called out.
BOOTSTRAP_FULL_RUNS = 7

SUITES = (
    "test-attacks.sh",
    "test-attack-results.sh",
    "test-mutant-result.sh",
    "test-runtime.sh",
    "test-step4.sh",
    "test-step5.sh",
    "test-step6.sh",
    "test-egress.sh",
    "visibility-suite.sh",
    "test-mutant-select.py",
    "test-mutate-shards.sh",
)

# Frozen pairs. Growing this list fails the duplicate check.
KNOWN_DUPLICATES = (
    ("M23", "M82"),
    ("M24", "M83"),
    ("M25", "M84"),
)

# Direct imports and sourced files the scanner must agree with.
DEPENDS = {
    "setup/chrome/chromium-argv.sh": ("setup/lib/runtime.sh",),
    "setup/keel-doctor.sh": (
        "setup/lib/egress.sh",
        "setup/lib/portable.sh",
        "setup/lib/runtime.sh",
    ),
    "setup/keel.sh": (
        "setup/lib/egress.sh",
        "setup/lib/portable.sh",
        "setup/lib/runtime.sh",
    ),
    "setup/lib/discovery_filter.py": (
        "setup/lib/discovery_judge.py",
        "setup/lib/pi_launch.py",
        "setup/lib/visibility.py",
    ),
    "setup/lib/egress_proxy.py": ("setup/lib/egress.py",),
    "setup/lib/pi_launch.py": ("setup/lib/visibility.py",),
    "setup/lib/visibility.py": ("setup/lib/pi_launch.py",),
}

SCAN_FILES = (
    "setup/lib/discovery_filter.py",
    "setup/lib/discovery_judge.py",
    "setup/lib/egress.py",
    "setup/lib/egress_proxy.py",
    "setup/lib/mock_model.py",
    "setup/lib/pi_launch.py",
    "setup/lib/visibility.py",
    "setup/lib/egress.sh",
    "setup/lib/portable.sh",
    "setup/lib/runtime.sh",
    "setup/keel.sh",
    "setup/keel-doctor.sh",
    "setup/chrome/chromium-argv.sh",
)

META = {
    "M139": ("plan-forced", "mechanism"),
    "M140": ("new-against-main", "mechanism"),
    "M141": ("compare-values", "mechanism"),
    "M142": ("parser-computed", "mechanism"),
    "M143": ("parser-second", "mechanism"),
    "M144": ("parser-names", "mechanism"),
    "M145": ("reject-removed", "mechanism"),
    "M146": ("compare-suite", "mechanism"),
    "M147": ("copy-widens", "mechanism"),
    "M148": ("suite-known", "mechanism"),
    "M149": ("unmapped-full", "mechanism"),
    "M150": ("depends-on", "mechanism"),
    "M151": ("dynamic-unresolved", "mechanism"),
    "M152": ("shard-last", "mechanism"),
    "M153": ("shard-complete", "mechanism"),
    "M154": ("shard-foreign", "mechanism"),
    "M155": ("shard-success", "mechanism"),
    "M156": ("skip-noise", "mechanism"),
    "M157": ("filter-runs", "mechanism"),
    "M158": ("class-check", "mechanism"),
    "M159": ("fresh-api-run", "mechanism"),
    "M160": ("duplicate-def", "mechanism"),
    "M161": ("exp-from-main", "mechanism"),
    "M162": ("new-masked", "mechanism"),
    "M163": ("coverage-safety", "mechanism"),
    "M164": ("artifact-allow", "mechanism"),
    "M165": ("main-moved", "mechanism"),
    "M166": ("trust-state", "mechanism"),
    "M167": ("extract-size", "mechanism"),
    "M168": ("extract-path", "mechanism"),
    "M169": ("extract-symlink", "mechanism"),
    "M170": ("line-cap", "mechanism"),
    "M171": ("shard-timeout", "mechanism"),
    "M172": ("timeout-not-success", "mechanism"),
    "M173": ("baseline-check", "mechanism"),
    "M174": ("tree-entry-check", "mechanism"),
    "M175": ("shard-readonly", "mechanism"),
    "M176": ("shard-readonly", "mechanism"),
    "M207": ("exclude-policy-ids", "fail-closed"),
    "M208": ("apply-merges", "fail-closed"),
    "M209": ("require-examples", "fail-closed"),
    "M210": ("honor-author-only", "fail-closed"),
    "M211": ("check-extra-files", "fail-closed"),
    "M212": ("check-fails-on-drift", "fail-closed"),
    "M213": ("emit-severity", "fail-closed"),
    "M214": ("ids-exclude-nonreview", "fail-closed"),
    "M215": ("stable-order", "fail-closed"),
    "M216": ("auditor-keeps-typ03", "fail-closed"),
    "M217": ("architect-no-tst", "fail-closed"),
    "M218": ("auditor-tst02", "fail-closed"),
    "M219": ("project-new-rules", "fail-closed"),
    "M220": ("no-retired-ids", "fail-closed"),
    "M221": ("validate-assignments", "fail-closed"),
    "M222": ("reject-style-reviewer", "fail-closed"),
    "M223": ("no-subset-matrix", "fail-closed"),
    "M224": ("standards-mount-ro", "visibility"),
    "M225": ("standards-no-extra-skill", "visibility"),
    "M226": ("standards-no-private-files", "visibility"),
    "M227": ("strict-schema", "fail-closed"),
    "M228": ("require-source", "fail-closed"),
    "M229": ("require-evidence-bar", "fail-closed"),
    "M230": ("hide-mechanical", "fail-closed"),
    "M231": ("architect-cor05", "fail-closed"),
    "M232": ("api01-role-severity", "fail-closed"),
    "M233": ("probe-five-roles", "visibility"),
}

# CI ids, in CI_IDS order. Pull-request selection never includes OFFLINE_IDS.
VISIBILITY_CI = (
    "M45",
    "M46",
    "M48",
    "M49",
    "M50",
    "M51",
    "M52",
    "M70",
    "M71",
    "M72",
    "M104",
    "M105",
)
EGRESS_CI = (
    "M53",
    "M54",
    "M55",
    "M56",
    "M57",
    "M58",
    "M59",
    "M60",
    "M61",
    "M62",
    "M63",
    "M64",
    "M65",
    "M66",
    "M68",
    "M76",
    "M77",
)
ATTACK_CI = (
    "M03",
    "M17",
    "M27",
    "M45",
    "M46",
    "M47",
    "M48",
    "M49",
    "M50",
    "M51",
    "M52",
    "M53",
    "M54",
    "M55",
    "M56",
    "M57",
    "M58",
    "M59",
    "M60",
    "M61",
    "M62",
    "M63",
    "M64",
    "M65",
    "M66",
    "M67",
    "M68",
    "M69",
    "M70",
    "M71",
    "M72",
    "M73",
    "M74",
    "M75",
    "M76",
    "M77",
    "M79",
    "M82",
    "M83",
    "M84",
    "M85",
)
RUNTIME_CI = (
    "M80",
    "M81",
    "M86",
    "M87",
    "M88",
    "M89",
    "M90",
    "M91",
)
STEP4_CI = (
    "M94",
    "M95",
    "M96",
    "M97",
    "M98",
    "M101",
    "M103",
    "M104",
    "M105",
    "M107",
    "M108",
    "M109",
    "M110",
    "M111",
    "M112",
    "M113",
    "M114",
    "M115",
    "M116",
    "M117",
    "M118",
)
STEP5_CI = (
    "M119",
    "M120",
    "M121",
    "M122",
    "M123",
    "M124",
    "M125",
    "M126",
    "M127",
    "M128",
    "M129",
    "M130",
    "M131",
    "M132",
    "M133",
    "M134",
    "M135",
    "M136",
    "M137",
    "M138",
)

# A change to one of these files selects only the CI mutants mapped to it.
# Exact policy paths and listed oracle scripts are selective too.
# Every other changed path under setup/ or .github/ selects the full CI set.
TARGET_ONLY = frozenset((
    "setup/keel.sh",
    "setup/lib/visibility.py",
    "setup/lib/egress.sh",
    "setup/lib/egress.py",
    "setup/lib/egress_proxy.py",
    "setup/tests/harness/attack-results.sh",
    "setup/lib/runtime.sh",
    "setup/tests/harness/doctor-score.sh",
    "setup/lib/pi_launch.py",
    "setup/check.sh",
    "setup/docker/ancestor-guard.sh",
    "setup/keel-doctor.sh",
    "setup/lib/discovery_filter.py",
    "setup/lib/discovery_judge.py",
))

# Whole path, or one basename glob under that directory. Not a directory prefix.
POLICY_SELECT = (
    ("setup/allow/*.paths", VISIBILITY_CI),
    ("setup/deny/base", VISIBILITY_CI),
    ("setup/egress/*.allow", EGRESS_CI),
)

def _oracle_scripts():
    """CI ids whose suite is that script, plus the two shared oracle scripts."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import mutate

    found = {}
    for mid in CI_IDS:
        suite = mutate.SUITE_OF[mid]
        found.setdefault(suite, []).append(mid)
    scripts = {}
    for suite, ids in found.items():
        scripts["setup/tests/harness/" + suite] = tuple(mid for mid in CI_IDS if mid in set(ids))
    scripts["setup/tests/harness/test-egress.sh"] = EGRESS_CI
    scripts["setup/tests/harness/visibility-suite.sh"] = VISIBILITY_CI
    return scripts


# Exact oracle scripts. A change selects this CI list, not the full set.
ORACLE_SCRIPTS = _oracle_scripts()

# Fixtures and helpers that stay on the full CI set through the setup/ rule.
# test-runtime.sh and test-mutant-result.sh are selective oracle scripts.
ORACLE_FILES = (
    "setup/tests/harness/fixtures/runtime-rootless.info",
    "setup/tests/harness/fixtures/runtime-rootful.info",
    "setup/tests/harness/fixtures/runtime-userns.info",
    "setup/tests/harness/runtime-stub.sh",
    "setup/tests/harness/harness-keel.sh",
)

# Gate paths select the mapped gate ids. They do not widen to the full CI set.
GATE_PATHS = frozenset((
    "scripts/check-gate.sh",
    "scripts/gate-jobs.txt",
    "scripts/tests/test_gate_jobs.py",
    "setup/tests/harness/mutant-result.py",
))
FULL_PATHS = GATE_PATHS

# Mechanism files do not widen to the full CI set. Mapped ids still run.
MECHANISM = frozenset((
    "setup/tests/harness/mutate.py",
    "setup/tests/harness/run-tests.sh",
    "setup/tests/harness/mutant_files.py",
    "setup/tests/harness/mutate-plan.sh",
    "setup/tests/harness/test-mutant-select.py",
    "setup/tests/harness/test-mutate-parse.py",
    "setup/tests/harness/mutant_defs.py",
    "setup/tests/harness/mutate_shards.py",
    "setup/tests/harness/mutate-full-state.py",
    "setup/tests/harness/mutate-issue.py",
    "setup/tests/harness/speed_cases.py",
    "setup/tests/harness/test-mutate-shards.sh",
    ".github/workflows/checks.yml",
    ".github/workflows/mutate-pr.yml",
    ".github/workflows/mutate-full.yml",
))
TRIGGERS = MECHANISM

SKIP_LINE = "RESULT mutate: skipped (no harness files changed)"
FULL_LINE = "RESULT mutate: run"


class SelectionError(Exception):
    pass


def path_matches(path, pattern):
    """Whole-path equality, or one basename glob in a fixed directory.

    A star matches inside that final path segment only. A directory prefix
    is not a match.
    """
    if not any(ch in pattern for ch in "*?["):
        return path == pattern
    if "/" not in pattern:
        return False
    directory, basepat = pattern.rsplit("/", 1)
    parent, sep, name = path.rpartition("/")
    if sep != "/" or parent != directory or not name:
        return False
    return fnmatch.fnmatchcase(name, basepat)


def policy_ids(path):
    found = []
    for pattern, ids in POLICY_SELECT:
        if path_matches(path, pattern):
            found.extend(ids)
    return found


unmapped_full = True  # unmapped-full
use_depends = True  # depends-on
dynamic_unresolved = True  # dynamic-unresolved

_SOURCE_RE = re.compile(r"^(?:source|\.)[ \t]+(\S+)")
_DYNAMIC_RE = re.compile(r"(importlib|__import__|\bexec\s*\()")


def _shell_token(script, token):
    token = token.strip().strip("\"'")
    if token.startswith("$HERE/"):
        rest = token[len("$HERE/"):]
        if "$" in rest:
            return None
        parent = script.rsplit("/", 1)[0]
        return parent + "/" + rest
    if token.startswith("$SETUP/"):
        rest = token[len("$SETUP/"):]
        if "$" in rest:
            return None
        return "setup/" + rest
    if "$" in token or token.startswith("/"):
        return None
    parent = script.rsplit("/", 1)[0]
    return parent + "/" + token


def scan_text(path, text):
    """Return a sorted tuple of repo paths, or None when the file is unresolvable."""
    if path.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None
        parent = path.rsplit("/", 1)[0]
        deps = set()
        dynamic = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in ("import_module", "__import__") or (isinstance(func, ast.Name) and func.id == "exec"):
                    dynamic = True
            if isinstance(node, ast.Import):
                for alias in node.names:
                    sibling = parent + "/" + alias.name.split(".")[0] + ".py"
                    if os.path.isfile(os.path.join(_repo_root(), sibling)) or alias.name in (
                        "visibility",
                        "egress",
                        "discovery_judge",
                        "discovery_filter",
                        "pi_launch",
                    ):
                        deps.add(parent + "/" + alias.name.split(".")[0] + ".py")
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                sibling = parent + "/" + node.module.split(".")[0] + ".py"
                base = node.module.split(".")[0]
                if base in ("visibility", "egress", "discovery_judge", "discovery_filter", "pi_launch"):
                    deps.add(sibling)
        if dynamic and dynamic_unresolved:
            return None
        if _DYNAMIC_RE.search(text) and dynamic_unresolved and dynamic:
            return None
        return tuple(sorted(deps))
    deps = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _SOURCE_RE.match(line)
        if not match:
            continue
        resolved = _shell_token(path, match.group(1))
        if resolved is None:
            if dynamic_unresolved:
                return None
            continue
        if resolved.startswith("setup/"):
            deps.add(resolved)
    return tuple(sorted(deps))


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, os.pardir, os.pardir, os.pardir))


def scan_repo(root=None):
    root = root or _repo_root()
    found = {}
    for rel in SCAN_FILES:
        path = os.path.join(root, rel)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        deps = scan_text(rel, text)
        if deps is None:
            return None
        if deps:
            found[rel] = deps
    return found


def depends_covers(path):
    if path in DEPENDS:
        return True
    return any(path in deps for deps in DEPENDS.values())


def dependent_ids(path):
    if not use_depends:
        return []
    found = []
    for owner, deps in DEPENDS.items():
        if path in deps:
            found.extend(mid for mid in CI_IDS if owner in FILES[mid])
    return found


def path_is_unresolvable(path, root=None):
    if path not in SCAN_FILES and not path.startswith("setup/lib/"):
        return False
    root = root or _repo_root()
    full = os.path.join(root, path)
    if not os.path.isfile(full):
        return False
    with open(full, encoding="utf-8") as handle:
        text = handle.read()
    return scan_text(path, text) is None


def is_selective(path):
    """True when this path selects a CI list instead of the full set."""
    if path in MECHANISM or path in GATE_PATHS:
        return True
    if path in TARGET_ONLY or path in ORACLE_SCRIPTS:
        return True
    if policy_ids(path):
        return True
    if path.startswith("setup/lib/") and depends_covers(path):
        return True
    return False


def ids_for_path(path):
    """CI ids contributed by one selective path. Empty when the path is not selective."""
    if not is_selective(path):
        return []
    found = []
    if path in GATE_PATHS:
        found.extend(mid for mid in ("M92", "M93") if mid in CI_IDS)
    if path in TARGET_ONLY or path in MECHANISM or path in FILES.values() or True:
        found.extend(mid for mid in CI_IDS if path in FILES.get(mid, ()))
    script_ids = ORACLE_SCRIPTS.get(path)
    if script_ids:
        found.extend(script_ids)
    found.extend(policy_ids(path))
    found.extend(dependent_ids(path))
    return [mid for mid in CI_IDS if mid in set(found)]


def needs_full_set(changed):
    """True when the diff must run the full CI set.

    A mapped target, a mechanism file, a gate path, or a listed oracle script
    does not. An unmapped path under setup/ or .github/ does. A module whose
    imports cannot be resolved does too.
    """
    for path in changed:
        if path_is_unresolvable(path):
            return True
        if is_selective(path):
            continue
        if unmapped_full and (path.startswith("setup/") or path.startswith(".github/")):
            return True
    return False


def select_mutants(changed):
    """Return (status, ids). status is full, some, or skip."""
    if needs_full_set(changed):
        return ("full", list(CI_IDS))
    found = set()
    for path in changed:
        found.update(ids_for_path(path))
    chosen = [mid for mid in CI_IDS if mid in found]
    if not chosen:
        return ("skip", [])
    return ("some", chosen)


def check_selection(changed, select=None):
    """Fail when a selector drops mutants or skips a file that requires the full set."""
    choose = select or select_mutants
    status, ids = choose(list(changed))
    ids = list(ids)
    if needs_full_set(changed):
        if status != "full" or ids != list(CI_IDS):
            raise SelectionError("full set required")
        return status, ids
    _status, expected = select_mutants(list(changed))
    if expected and (status == "skip" or not ids):
        raise SelectionError("selection dropped every mutant")
    if expected and (status != "some" or ids != list(expected)):
        raise SelectionError("selection does not match the map")
    if not expected and (status != "skip" or ids):
        raise SelectionError("selection does not match the map")
    return status, ids


def decision_line(changed):
    status, ids = select_mutants(changed)
    if status == "skip":
        return SKIP_LINE
    if status == "full":
        return FULL_LINE
    return "RESULT mutate: run " + " ".join(ids)


def ids_accepted(ids):
    if not ids:
        return False
    if list(ids) == list(CI_IDS) + list(OFFLINE_IDS):
        return True
    if len(ids) != len(set(ids)):
        return False
    pos = {mid: index for index, mid in enumerate(CI_IDS)}
    if any(mid not in pos for mid in ids):
        return False
    order = [pos[mid] for mid in ids]
    return order == sorted(order)


def main(argv):
    if argv[1:2] == ["--ci"]:
        print(" ".join(CI_IDS))
        return 0
    if argv[1:2] == ["--full"]:
        print(" ".join(list(CI_IDS) + list(OFFLINE_IDS)))
        return 0
    if argv[1:2] == ["--all"]:
        ordered = sorted(FILES, key=lambda mid: int(mid[1:]))
        print(" ".join(ordered))
        return 0
    if argv[1:2] == ["--decide"]:
        names = [line.strip() for line in sys.stdin if line.strip()]
        print(decision_line(names))
        return 0
    if argv[1:2] == ["--check-ids"]:
        return 0 if ids_accepted(argv[2:]) else 1
    print(
        "usage: mutant_files.py --ci | --full | --all | --decide | --check-ids ID...",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
