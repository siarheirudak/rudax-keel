#!/usr/bin/env python3
"""The gate job list, checks.yml needs, and the R_* env vars stay the same list."""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TYPES = "types: [opened, synchronize, reopened, edited]"


def fail(message):
    print(message, file=sys.stderr)
    print(
        "how to fix: keep scripts/gate-jobs.txt, the keel-gate needs list, and the R_* env vars in .github/workflows/checks.yml the same",
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


def require_types(text, label):
    header = text.split("\njobs:", 1)[0]
    if TYPES not in header:
        fail("{0} must include {1}".format(label, TYPES))


def main():
    listed = [
        line.strip()
        for line in (ROOT / "scripts" / "gate-jobs.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not listed:
        fail("scripts/gate-jobs.txt is empty")
    checks = (ROOT / ".github" / "workflows" / "checks.yml").read_text(encoding="utf-8")
    require_types(checks, "checks.yml")
    blocks = job_blocks(checks)
    missing = [job for job in listed if job not in blocks]
    if missing:
        fail("gate list names missing jobs: {0}".format(", ".join(missing)))
    gate = blocks.get("keel-gate", "")
    if "name: keel-gate" not in gate:
        fail("keel-gate job name must be keel-gate")
    needs = re.search(r"^    needs:\s*\[([^\]]+)\]\s*$", gate, re.M)
    if not needs:
        fail("keel-gate job has no needs list")
    needed = [part.strip() for part in needs.group(1).split(",")]
    if needed != listed:
        fail("needs {0} != gate-jobs.txt {1}".format(needed, listed))
    for job in listed:
        needle = "{0}: ${{{{ needs.{1}.result }}}}".format(env_name(job), job)
        if needle not in gate:
            fail("missing env {0}".format(needle))
    scope = (ROOT / ".github" / "workflows" / "scope.yml").read_text(encoding="utf-8")
    require_types(scope, "scope.yml")
    if "name: keel-process-files-separate" not in scope:
        fail("scope job name must be keel-process-files-separate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
