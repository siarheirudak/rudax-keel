#!/usr/bin/env python3
"""Write one discovery or ADR candidate. Does not promote or read secrets.

The harness mounts this file read-only at .keel/tools/write-memory-candidate.py.
The host filter, not this script, accepts or discards the file.
"""

import argparse
import os
import re
import sys
import uuid

KINDS = ("discovery", "adr")
SEVERITIES = ("critical", "normal", "low")


def _slug(text):
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", text).strip("-")
    return cleaned[:40] or "task"


def _body(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def render(args, body):
    paths = args.paths or []
    tags = args.tags or []
    lines = [
        "---",
        "id: {0}".format(args.id),
        "title: {0}".format(args.title),
        "date: {0}".format(args.date),
        "tags: [{0}]".format(", ".join(tags)),
    ]
    if paths:
        lines.append("paths:")
        for rel in paths:
            lines.append("  - {0}".format(rel))
    else:
        lines.append("paths: []")
    lines.append("severity: {0}".format(args.severity))
    lines.append("kind: {0}".format(args.kind))
    if args.rule:
        lines.append("rule: {0}".format(args.rule))
    if args.task:
        lines.append("task_id: {0}".format(args.task))
    lines.append("---")
    text = "\n".join(lines) + "\n" + body
    if not text.endswith("\n"):
        text += "\n"
    return text


def main(argv):
    parser = argparse.ArgumentParser(description="append a memory candidate")
    parser.add_argument("--work", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--severity", default="normal", choices=SEVERITIES)
    parser.add_argument("--date", default="2026-11-05")
    parser.add_argument("--id", default="")
    parser.add_argument("--tags", action="append", default=[])
    parser.add_argument("--paths", action="append", default=[])
    parser.add_argument("--rule", default="")
    parser.add_argument("--body-file", required=True)
    args = parser.parse_args(argv)
    if not args.id:
        args.id = "cand-" + uuid.uuid4().hex[:12]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.date):
        sys.stderr.write("bad date\n")
        return 2
    body = _body(args.body_file)
    root = os.path.join(args.work, ".keel", "candidates")
    os.makedirs(root, exist_ok=True)
    name = "cand-{0}-{1}.md".format(_slug(args.task), uuid.uuid4().hex[:8])
    dest = os.path.join(root, name)
    with open(dest, "w", encoding="utf-8") as handle:
        handle.write(render(args, body))
    sys.stdout.write(dest + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
