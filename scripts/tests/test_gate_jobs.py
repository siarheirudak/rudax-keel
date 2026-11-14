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
    if TYPES not in scope.split("\njobs:", 1)[0]:
        raise GateJobsError("scope.yml must include {0}".format(TYPES))
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
    if extra:
        print("NOTE: keel-gate needs has jobs not in scripts/gate-jobs.txt: {0} (not enforced by keel-gate)".format(", ".join(extra)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
