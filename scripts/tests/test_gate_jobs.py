#!/usr/bin/env python3
"""Every job in scripts/gate-jobs.txt is in the keel-gate needs list and has its R_* env var.

keel-gate reads gate-jobs.txt from the base commit (B16). The needs list may
hold more jobs than gate-jobs.txt, so a job can be added to needs first and to
the list in a later pull request, or dropped from the list first and from
needs later, with both pull requests green (D-353, B-01).
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TYPES = "types: [opened, synchronize, reopened, edited]"
SCOPE_TYPES = (TYPES, "types: [opened, synchronize, reopened, edited, labeled, unlabeled]")


def fail(message):
    print(message, file=sys.stderr)
    print(
        "how to fix: every job in scripts/gate-jobs.txt must be in the keel-gate needs list of .github/workflows/checks.yml with its R_* env var",
        file=sys.stderr,
    )
    sys.exit(1)


def env_name(job):
    return "R_" + job.upper().replace("-", "_")


def job_blocks(text):
    blocks = {}
    current = None
    buf = []
    for line in text.splitlines(keepends=True):
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            if current is not None:
                blocks[current] = "".join(buf)
            current = match.group(1)
            buf = [line]
        elif current is not None:
            buf.append(line)
    if current is not None:
        blocks[current] = "".join(buf)
    return blocks


class GateJobsError(Exception):
    pass


# Required check names. Each must name exactly one job across all workflows, so
# a decoy job cannot report a second, green check with the same name (Auditor FU-1).
REQUIRED_NAMES = ("keel-gate", "keel-process-files-separate")
names_once = True  # names-once
plain_names = True  # plain-names


NAME_KEY = re.compile(r"(^|[\s{,])name:(\s*)(.*)$")


def plain_name_errors(workflows):
    """Every name: value must be a plain or simply quoted scalar on its own line.

    A block scalar (| or >), an empty value continued on the next line, a tag
    (!!str), an anchor or alias (& or *) or a double-quoted escape (\\x2d) can
    all resolve to a required name that the text match above cannot see
    (Auditor FU-P2). Today's workflows use none of these forms, so rejecting
    them only fails closed.
    """
    problems = []
    for file in sorted(workflows):
        for number, line in enumerate(workflows[file].splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            match = NAME_KEY.search(line)
            if not match:
                continue
            value = match.group(3).strip()
            bad = (
                not value
                or value[0] in "|>!&*"
                or (value[0] == '"' and ("\\" in value or value.count('"') < 2))
                or (value[0] == "'" and value.count("'") < 2)
            )
            if bad:
                problems.append("{0}:{1}: name: value must be a plain one-line string, got {2!r}".format(file, number, value))
    return problems


def name_errors(workflows):
    """workflows: {file name: text}. Return problems with the required names.

    A check run is named by the job's name:, or by its job id when there is no
    name:. Every name: line with that value counts, quoted or in a flow
    mapping, and so does a job id equal to the name in a file that does not
    also hold the name: line.
    """
    if not names_once:
        return []
    problems = []
    if plain_names:
        problems.extend(plain_name_errors(workflows))
    for want in REQUIRED_NAMES:
        quoted = "[\"']?" + re.escape(want) + "[\"']?"
        # GitHub may match check names without regard to case [U], so a
        # Keel-Gate decoy counts too (Auditor FU-P3).
        name_re = re.compile(r"(^|[\s{,])name:\s*" + quoted + r"\s*($|[,}#])", re.I)
        id_re = re.compile(r"^\s+" + quoted + r":\s*($|#|\{)", re.I)
        hits = []
        ids = []
        for file in sorted(workflows):
            for line in workflows[file].splitlines():
                if line.lstrip().startswith("#"):
                    continue
                if name_re.search(line):
                    hits.append(file)
                if id_re.match(line):
                    ids.append(file)
        if len(hits) != 1:
            problems.append("{0}: name: {1} appears {2} times across workflows, expected 1".format(want, want, len(hits)))
        stray = [file for file in ids if file not in hits]
        if stray or len(ids) > 1:
            problems.append("{0}: a job id {0} also names a check in {1}".format(want, ", ".join(sorted(set(ids)))))
    return problems


def check(listed, checks, scope):
    """Raise GateJobsError when the job list, needs and env lines disagree.

    Return the needs jobs that gate-jobs.txt does not list. keel-gate does not
    enforce them, so main() prints a note (Auditor F4).
    """
    if not listed:
        raise GateJobsError("scripts/gate-jobs.txt is empty")
    if len(listed) != len(set(listed)):
        raise GateJobsError("scripts/gate-jobs.txt lists a job twice")
    if TYPES not in checks.split("\njobs:", 1)[0]:
        raise GateJobsError("checks.yml must include {0}".format(TYPES))
    blocks = job_blocks(checks)
    missing = [job for job in listed if job not in blocks]
    if missing:
        raise GateJobsError("gate list names missing jobs: {0}".format(", ".join(missing)))
    gate = blocks.get("keel-gate", "")
    if "name: keel-gate" not in gate:
        raise GateJobsError("keel-gate job name must be keel-gate")
    needs = re.search(r"^    needs:\s*\[([^\]]+)\]\s*$", gate, re.M)
    if not needs:
        raise GateJobsError("keel-gate job has no needs list")
    needed = [part.strip() for part in needs.group(1).split(",")]
    absent = [job for job in listed if job not in needed]
    if absent:
        raise GateJobsError("gate-jobs.txt jobs not in keel-gate needs: {0}".format(", ".join(absent)))
    for job in listed:
        needle = "{0}: ${{{{ needs.{1}.result }}}}".format(env_name(job), job)
        if needle not in gate:
            raise GateJobsError("missing env {0}".format(needle))
    scope_header = scope.split("\njobs:", 1)[0]
    if not any(item in scope_header for item in SCOPE_TYPES):
        raise GateJobsError(
            "scope.yml must include {0} or {1}".format(SCOPE_TYPES[0], SCOPE_TYPES[1])
        )
    if "name: keel-process-files-separate" not in scope:
        raise GateJobsError("scope job name must be keel-process-files-separate")
    return [job for job in needed if job not in listed]


def _sample(needs, env_jobs):
    env = "".join("          {0}: ${{{{ needs.{1}.result }}}}\n".format(env_name(job), job) for job in env_jobs)
    jobs = "".join("  {0}:\n    runs-on: x\n".format(job) for job in ("a", "b", "c"))
    return (
        "on:\n  pull_request:\n    " + TYPES + "\njobs:\n" + jobs
        + "  keel-gate:\n    name: keel-gate\n    needs: [" + ", ".join(needs) + "]\n"
        + "    steps:\n      - name: Gate\n        env:\n" + env
    )


def self_test():
    """Cases for the relaxed rule. Return a list of failed case names."""
    scope = "on:\n  pull_request_target:\n    " + TYPES + "\njobs:\n  x:\n    name: keel-process-files-separate\n"
    cases = [
        ("GJ-H1 same list", ["a", "b"], _sample(["a", "b"], ["a", "b"]), True),
        ("GJ-H2 needs has an extra job", ["a"], _sample(["a", "b"], ["a", "b"]), True),
        ("GJ-H3 needs in another order", ["a", "b"], _sample(["b", "a"], ["a", "b"]), True),
        ("GJ-A1 listed job not in needs", ["a", "c"], _sample(["a", "b"], ["a", "b", "c"]), False),
        ("GJ-A2 listed job has no env line", ["a", "b"], _sample(["a", "b"], ["a"]), False),
        ("GJ-A3 empty list", [], _sample(["a"], ["a"]), False),
        ("GJ-A4 listed job is not a job", ["a", "z"], _sample(["a", "z"], ["a", "z"]), False),
        ("GJ-A5 duplicate listed job", ["a", "a"], _sample(["a"], ["a"]), False),
    ]
    bad = []
    for name, listed, checks, want in cases:
        try:
            check(listed, checks, scope)
            ok = True
        except GateJobsError:
            ok = False
        if ok != want:
            bad.append(name)
    try:
        extra = check(["a"], _sample(["a", "b", "c"], ["a"]), scope)
    except GateJobsError:
        extra = None
    if extra != ["b", "c"]:
        bad.append("GJ-N1 unlisted needs jobs are reported")
    good = {"checks.yml": "jobs:\n  keel-gate:\n    name: keel-gate\n", "scope.yml": "jobs:\n  scope:\n    name: keel-process-files-separate\n"}
    name_cases = [
        ("GJ-H4 each required name once", good, True),
        ("GJ-A6 decoy job name in another workflow", dict(good, **{"x.yml": "jobs:\n  fake:\n    name: keel-gate\n"}), False),
        ("GJ-A7 decoy quoted name in the same workflow", {"checks.yml": good["checks.yml"] + "  fake:\n    name: 'keel-gate'\n", "scope.yml": good["scope.yml"]}, False),
        ("GJ-A8 decoy flow-style name", dict(good, **{"x.yml": "jobs:\n  fake: {name: keel-process-files-separate, runs-on: x}\n"}), False),
        ("GJ-A9 decoy job id with no name:", dict(good, **{"x.yml": "jobs:\n  keel-gate:\n    runs-on: x\n"}), False),
        ("GJ-A10 required name missing", {"checks.yml": good["checks.yml"]}, False),
        ("GJ-A11 decoy name as a block scalar", dict(good, **{"x.yml": "jobs:\n  fake:\n    name: >-\n      keel-gate\n"}), False),
        ("GJ-A12 decoy name on the next line", dict(good, **{"x.yml": "jobs:\n  fake:\n    name:\n      keel-gate\n"}), False),
        ("GJ-A13 decoy name with an escape", dict(good, **{"x.yml": "jobs:\n  fake:\n    name: \"keel\\x2dgate\"\n"}), False),
        ("GJ-A14 decoy name with a tag", dict(good, **{"x.yml": "jobs:\n  fake:\n    name: !!str keel-gate\n"}), False),
        ("GJ-A15 decoy name through an alias", dict(good, **{"x.yml": "env: {K: &kg keel-gate}\njobs:\n  fake:\n    name: *kg\n"}), False),
        ("GJ-A16 decoy name in another case", dict(good, **{"x.yml": "jobs:\n  fake:\n    name: Keel-Gate\n"}), False),
        ("GJ-A17 decoy in an upper-case .YML file", dict(good, **{"X.YML": "jobs:\n  fake:\n    name: keel-gate\n"}), False),
        ("GJ-H5 other plain and expression names are fine", dict(good, **{"x.yml": "jobs:\n  a:\n    name: build ${{ matrix.k }}\n    steps:\n      - name: 'quoted step'\n"}), True),
    ]
    for name, workflows, want in name_cases:
        if (not name_errors(workflows)) != want:
            bad.append(name)
    six = SCOPE_TYPES[1]
    scope_cases = [
        ("GJ-H6 scope with the label triggers", "on:\n  pull_request_target:\n    " + six + "\njobs:\n  x:\n    name: keel-process-files-separate\n", True),
        ("GJ-A18 scope label triggers without edited", "on:\n  pull_request_target:\n    types: [opened, synchronize, reopened, labeled, unlabeled]\njobs:\n  x:\n    name: keel-process-files-separate\n", False),
        ("GJ-A20 scope with an extra type", "on:\n  pull_request_target:\n    types: [opened, synchronize, reopened, edited, labeled, unlabeled, closed]\njobs:\n  x:\n    name: keel-process-files-separate\n", False),
    ]
    sample = _sample(["a", "b"], ["a", "b"])
    for name, scope_text, want in scope_cases:
        try:
            check(["a", "b"], sample, scope_text)
            ok = True
        except GateJobsError:
            ok = False
        if ok != want:
            bad.append(name)
    try:
        check(["a", "b"], sample.replace(TYPES, six, 1), scope)
        bad.append("GJ-A19 checks with the label triggers")
    except GateJobsError:
        pass
    return bad


def main():
    bad = self_test()
    if bad:
        fail("self-test failed: {0}".format(", ".join(bad)))
    listed = [
        line.strip()
        for line in (ROOT / "scripts" / "gate-jobs.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    checks = (ROOT / ".github" / "workflows" / "checks.yml").read_text(encoding="utf-8")
    scope = (ROOT / ".github" / "workflows" / "scope.yml").read_text(encoding="utf-8")
    try:
        extra = check(listed, checks, scope)
    except GateJobsError as err:
        fail(str(err))
    folder = ROOT / ".github" / "workflows"
    workflows = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(folder.iterdir())
        if path.suffix.lower() in (".yml", ".yaml") and path.is_file()
    }
    problems = name_errors(workflows)
    if problems:
        fail("; ".join(problems))
    if extra:
        print("NOTE: keel-gate needs has jobs not in scripts/gate-jobs.txt: {0} (not enforced by keel-gate)".format(", ".join(extra)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
