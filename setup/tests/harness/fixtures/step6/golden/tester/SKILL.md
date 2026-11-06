---
name: keel-standards-tester
description: Test-authoring guidance from the quality standard for the tester.
---

# keel-standards-tester

Generated from setup/standards/rules.md — do not edit

source-sha256: b99ed50575565436ccb7863e30b687b6eb080ee4bdde942f2c2a7a4804a4f34d

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
