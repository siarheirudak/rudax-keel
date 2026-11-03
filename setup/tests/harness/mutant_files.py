#!/usr/bin/env python3
"""Which harness file each mutant edits, and which of those mutants CI runs.

The map is data. test-mutant-select.py checks it against mutate.M.
"""
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
]

# A change to one of these files selects only the CI mutants mapped to it.
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
))

# Fixture files and the oracles for R-H1, R-A1, and R-A8.
# A change here runs the full CI set.
ORACLE_FILES = (
    "setup/tests/harness/fixtures/runtime-rootless.info",
    "setup/tests/harness/fixtures/runtime-rootful.info",
    "setup/tests/harness/fixtures/runtime-userns.info",
    "setup/tests/harness/test-runtime.sh",
    "setup/tests/harness/runtime-stub.sh",
)

# Selector files. Covered by the setup/ and .github/ rule; kept so a test can name them.
TRIGGERS = [
    "setup/tests/harness/mutate.py",
    "setup/tests/harness/run-tests.sh",
    "setup/tests/harness/mutant_files.py",
    ".github/workflows/checks.yml",
]

SKIP_LINE = "RESULT mutate: skipped (no harness files changed)"
FULL_LINE = "RESULT mutate: run"


class SelectionError(Exception):
    pass


def needs_full_set(changed):
    """True when a changed path is under setup/ or .github/ and is not a mapped target."""
    for path in changed:
        if path in TARGET_ONLY:
            continue
        if path.startswith("setup/") or path.startswith(".github/"):
            return True
    return False


def select_mutants(changed):
    """Return (status, ids). status is full, some, or skip."""
    if needs_full_set(changed):
        return ("full", list(CI_IDS))
    chosen = [mid for mid in CI_IDS if set(changed) & set(FILES[mid])]
    if not chosen:
        return ("skip", [])
    return ("some", chosen)


def check_selection(changed, select=None):
    """Fail when a selector drops mutants or skips a file that requires the full set."""
    choose = select or select_mutants
    status, ids = choose(list(changed))
    ids = list(ids)
    changed_set = set(changed)
    if needs_full_set(changed):
        if status != "full" or ids != list(CI_IDS):
            raise SelectionError("full set required")
        return status, ids
    expected = [mid for mid in CI_IDS if changed_set & set(FILES[mid])]
    if expected and (status == "skip" or not ids):
        raise SelectionError("selection dropped every mutant")
    if expected and (status != "some" or ids != expected):
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
    if argv[1:2] == ["--decide"]:
        names = [line.strip() for line in sys.stdin if line.strip()]
        print(decision_line(names))
        return 0
    if argv[1:2] == ["--check-ids"]:
        return 0 if ids_accepted(argv[2:]) else 1
    print("usage: mutant_files.py --ci | --decide | --check-ids ID...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
