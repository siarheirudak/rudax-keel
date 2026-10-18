#!/usr/bin/env python3
"""Check internal relative links and heading anchors in Markdown. Skip external URLs."""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
REF = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
ANCHOR = re.compile(r"""<a\s+[^>]*(?:id|name)\s*=\s*["']([^"']+)["']""", re.I)
FENCE = re.compile(r"^\s*```")
INLINE_CODE = re.compile(r"`[^`]*`")


def slug(text):
    text = INLINE_CODE.sub("", text)
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def anchors_in(path):
    found = set()
    if path.suffix.lower() != ".md":
        return found
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in ANCHOR.finditer(line):
            found.add(match.group(1))
        heading = HEADING.match(line)
        if heading:
            found.add(slug(heading.group(2)))
    return found


def dest_of(raw):
    raw = raw.strip().strip("<>")
    if raw.startswith("<") and ">" in raw:
        raw = raw[1 : raw.index(">")]
    raw = raw.split()[0] if raw else raw
    return raw


def skip_url(url):
    lowered = url.lower()
    return lowered.startswith(("http://", "https://", "mailto:", "//"))


def visible_lines(text):
    lines = []
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        lines.append(INLINE_CODE.sub("", line))
    return lines


def links_in(path):
    found = []
    for line in visible_lines(path.read_text(encoding="utf-8")):
        for match in LINK.finditer(line):
            found.append(dest_of(match.group(1)))
        ref = REF.match(line)
        if ref:
            found.append(dest_of(ref.group(1)))
    return found


def main():
    errors = []
    for path in sorted(ROOT.rglob("*.md")):
        if ".git" in path.parts:
            continue
        for raw in links_in(path):
            if not raw or skip_url(raw):
                continue
            url, _, anchor = raw.partition("#")
            if not url:
                target = path
            else:
                target = (path.parent / url).resolve()
            try:
                target.relative_to(ROOT)
            except ValueError:
                errors.append((path, raw))
                continue
            if not target.exists():
                errors.append((path, raw))
                continue
            if anchor and target.suffix.lower() == ".md":
                if anchor not in anchors_in(target):
                    errors.append((path, raw))
    if errors:
        for path, raw in errors:
            rel = path.relative_to(ROOT)
            print(f"{rel}: broken link {raw}", file=sys.stderr)
        first_path, first_link = errors[0]
        print(
            f"how to fix: fix the broken link {first_link} in {first_path.relative_to(ROOT)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
