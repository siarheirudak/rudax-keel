#!/usr/bin/env python3
"""Unit tests for scripts/check-md-links.py. No network."""

import importlib.util
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_md_links", ROOT / "scripts" / "check-md-links.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def fail(message):
    print(message, file=sys.stderr)
    print("how to fix: fix scripts/check-md-links.py so tests/test_md_links.py passes", file=sys.stderr)
    sys.exit(1)


def expect(actual, wanted, label):
    if actual != wanted:
        fail("{0}: got {1!r}, wanted {2!r}".format(label, actual, wanted))


def main():
    expect(MOD.slug("Foo - bar"), "foo---bar", "repeated hyphens")
    expect(MOD.slug("The `code` thing"), "the-code-thing", "inline code text")
    expect(MOD.slug("Hello, world!"), "hello-world", "punctuation")
    expect(MOD.dest_of("<docs/my file.md>"), "docs/my file.md", "angle destination")
    expect(MOD.dest_of('file.md "title"'), "file.md", "title")
    url, anchor = MOD.split_dest("my%20file.md#Foo%20Bar")
    expect(url, "my file.md", "percent path")
    expect(anchor, "Foo Bar", "percent anchor")

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "docs").mkdir()
        (root / "README.md").write_text("# Hello\n\n# Hello\n", encoding="utf-8")
        (root / "docs" / "my file.md").write_text("# Use `code`\n", encoding="utf-8")
        (root / "docs" / "page.md").write_text(
            "\n".join(
                [
                    "[root](/README.md)",
                    "[space](<my file.md>)",
                    "[encoded](my%20file.md)",
                    "[dup](/README.md#hello-1)",
                    "[code](<my file.md>#use-code)",
                    "[gone](/missing.md)",
                    "[out](https://example.com/nope)",
                    "",
                    "[ref]: <my file.md>",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        readme_anchors = MOD.anchors_in(root / "README.md")
        if "hello" not in readme_anchors or "hello-1" not in readme_anchors:
            fail("duplicate anchors: {0}".format(sorted(readme_anchors)))
        code_anchors = MOD.anchors_in(root / "docs" / "my file.md")
        if "use-code" not in code_anchors:
            fail("inline-code anchor: {0}".format(sorted(code_anchors)))
        errors = MOD.check_tree(root)
        broken = {path.name + ":" + raw for path, raw in errors}
        if broken != {"page.md:[gone](/missing.md)"} and not any(
            raw.startswith("[gone]") or "/missing.md" in raw for _path, raw in errors
        ):
            fail("unexpected link errors: {0}".format(sorted(broken)))
        if len(errors) != 1:
            fail("expected one broken link, got {0}".format(errors))

    if MOD.main() != 0:
        fail("repository markdown links failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
