#!/usr/bin/env python3
"""Which harness file each mutant edits, and which of those mutants CI runs.

The map is data. test-mutant-select.py checks it against mutate.M.
"""
import fnmatch
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
]

# Docker mount probes, plus M01. Pull-request CI skips these. The daily full run includes them.
OFFLINE_IDS = [
    "M01",
    "M99",
    "M100",
    "M102",
    "M106",
]

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
))

# Whole path, or one basename glob under that directory. Not a directory prefix.
POLICY_SELECT = (
    ("setup/allow/*.paths", VISIBILITY_CI),
    ("setup/deny/base", VISIBILITY_CI),
    ("setup/egress/*.allow", EGRESS_CI),
)

# Exact oracle scripts. A change selects this CI list, not the full set.
ORACLE_SCRIPTS = {
    "setup/tests/harness/test-attacks.sh": ATTACK_CI,
    "setup/tests/harness/test-attack-results.sh": ("M78",),
    "setup/tests/harness/test-mutant-result.sh": ("M92", "M93"),
    "setup/tests/harness/test-runtime.sh": RUNTIME_CI,
    "setup/tests/harness/test-step4.sh": STEP4_CI,
    "setup/tests/harness/test-egress.sh": EGRESS_CI,
    "setup/tests/harness/visibility-suite.sh": VISIBILITY_CI,
}

# Fixtures and helpers that stay on the full CI set through the setup/ rule.
# test-runtime.sh and test-mutant-result.sh are selective oracle scripts.
ORACLE_FILES = (
    "setup/tests/harness/fixtures/runtime-rootless.info",
    "setup/tests/harness/fixtures/runtime-rootful.info",
    "setup/tests/harness/fixtures/runtime-userns.info",
    "setup/tests/harness/runtime-stub.sh",
    "setup/tests/harness/harness-keel.sh",
)

# Gate and binder paths outside setup/ and .github/. A change here is not a skip.
FULL_PATHS = frozenset((
    "scripts/check-gate.sh",
    "scripts/gate-jobs.txt",
    "scripts/tests/test_gate_jobs.py",
))

# Selector and binder files. A change here runs the full CI set.
TRIGGERS = [
    "setup/tests/harness/mutate.py",
    "setup/tests/harness/run-tests.sh",
    "setup/tests/harness/mutant_files.py",
    "setup/tests/harness/mutate-plan.sh",
    "setup/tests/harness/test-mutant-select.py",
    "setup/tests/harness/test-mutate-parse.py",
    "setup/tests/harness/mutant-result.py",
    ".github/workflows/checks.yml",
]

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


def is_selective(path):
    """True when this path selects a CI list instead of the full set.

    A trigger or a gate path is never selective, even if it is also a mutant
    edit target.
    """
    if path in TRIGGERS or path in FULL_PATHS:
        return False
    if path in TARGET_ONLY or path in ORACLE_SCRIPTS:
        return True
    return bool(policy_ids(path))


def ids_for_path(path):
    """CI ids contributed by one selective path. Empty when the path is not selective."""
    if not is_selective(path):
        return []
    found = []
    if path in TARGET_ONLY:
        found.extend(mid for mid in CI_IDS if path in FILES[mid])
    script_ids = ORACLE_SCRIPTS.get(path)
    if script_ids:
        found.extend(script_ids)
    found.extend(policy_ids(path))
    return found


def needs_full_set(changed):
    """True when the diff must run the full CI set.

    A selective edit target, an exact policy path, or a listed oracle script
    does not. A trigger, a gate path, or any other path under setup/ or
    .github/ does. A pull request that only edits a gate path is not a skip.
    """
    for path in changed:
        if is_selective(path):
            continue
        if path in FULL_PATHS or path in TRIGGERS:
            return True
        if path.startswith("setup/") or path.startswith(".github/"):
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
    if argv[1:2] == ["--decide"]:
        names = [line.strip() for line in sys.stdin if line.strip()]
        print(decision_line(names))
        return 0
    if argv[1:2] == ["--check-ids"]:
        return 0 if ids_accepted(argv[2:]) else 1
    print(
        "usage: mutant_files.py --ci | --full | --decide | --check-ids ID...",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
