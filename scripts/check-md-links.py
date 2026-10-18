#!/usr/bin/env python3
"""Check internal relative links and heading anchors in Markdown. Skip external URLs."""

import pathlib
import re
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
REF = re.compile(r"^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
ANCHOR = re.compile(r"""<a\s+[^>]*(?:id|name)\s*=\s*["']([^"']+)["']""", re.I)
FENCE = re.compile(r"^\s*```")
INLINE_CODE = re.compile(r"`[^`]*`")


def slug(text):
    """GitHub heading slug: keep inline-code text, do not collapse hyphens."""
    text = text.replace("`", "")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    return text


def anchors_in(path):
    found = set()
    if path.suffix.lower() != ".md":
        return found
    counts = {}
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
        if not heading:
            continue
        base = slug(heading.group(2))
        seen = counts.get(base, 0)
        counts[base] = seen + 1
        found.add(base if seen == 0 else "{0}-{1}".format(base, seen))
    return found


def dest_of(raw):
    raw = raw.strip()
    if raw.startswith("<"):
        end = raw.find(">")
        if end != -1:
            return raw[1:end]
    return raw.split()[0] if raw else raw


def split_dest(raw):
    raw = dest_of(raw)
    path, _sep, anchor = raw.partition("#")
    return urllib.parse.unquote(path), urllib.parse.unquote(anchor)


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
            found.append(match.group(1))
        ref = REF.match(line)
        if ref:
            found.append(ref.group(1))
    return found


def target_for(path, url, root):
    if url.startswith("/"):
        return (root / url.lstrip("/")).resolve()
    return (path.parent / url).resolve()


def check_tree(root):
    root = pathlib.Path(root)
    errors = []
    for path in sorted(root.rglob("*.md")):
        if ".git" in path.parts:
            continue
        for raw in links_in(path):
            url, anchor = split_dest(raw)
            if url and skip_url(url):
                continue
            if not url and not anchor:
                continue
            if not url:
                target = path
            else:
                target = target_for(path, url, root)
            try:
                target.relative_to(root)
            except ValueError:
                errors.append((path, raw))
                continue
            if not target.exists():
                errors.append((path, raw))
                continue
            if anchor and target.suffix.lower() == ".md":
                if anchor not in anchors_in(target):
                    errors.append((path, raw))
    return errors


def main():
    errors = check_tree(ROOT)
    if errors:
        for path, raw in errors:
            rel = path.relative_to(ROOT)
            print("{0}: broken link {1}".format(rel, raw), file=sys.stderr)
        first_path, first_link = errors[0]
        print(
            "how to fix: fix the broken link {0} in {1}".format(
                first_link, first_path.relative_to(ROOT)
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
