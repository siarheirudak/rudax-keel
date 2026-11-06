---
name: keel-standards-tester
description: Test-authoring guidance from the quality standard for the tester.
---

# keel-standards-tester

Generated from standards/rules.md — do not edit

source-sha256: 9cb42bf2e1f2811d9e8d1e2953d74497a16e6f2f5eee4c073a0771a6e275979b

Reviewers do not flag formatting, style, or naming.

## Not to flag

Flag a concrete defect in the changed code. A theoretical suggestion is not a finding.

## Rules

### TST-01 — Tests

severity: block
bar: demonstrated
condition: Required behavior has no failing test.

A required behavior change has a test that fails when the bug returns.

Flag: The transition changed and no test fails if the change is removed.

Do not flag: Existing tests already fail when the behavior is removed.
