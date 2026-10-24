#!/usr/bin/env python3
"""Fail if a workflow uses: value is not a full commit SHA."""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BAD = []
for path in (ROOT / ".github" / "workflows").glob("*.y*ml"):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        match = re.search(r"uses:\s*([^\s#]+)", line)
        if not match:
            continue
        uses = match.group(1).strip("\"'")
        if uses.startswith("./") or uses.startswith("docker://"):
            continue
        ref = uses.rsplit("@", 1)[-1] if "@" in uses else ""
        if not re.fullmatch(r"[0-9a-f]{40}", ref):
            BAD.append(f"{path.relative_to(ROOT)}:{number}:{uses}")

if BAD:
    print("unpinned actions:\n" + "\n".join(BAD), file=sys.stderr)
    first = BAD[0]
    path, number, uses = first.split(":", 2)
    print(
        f"how to fix: pin {uses} in {path}:{number} to a full 40-character commit SHA",
        file=sys.stderr,
    )
    sys.exit(1)
