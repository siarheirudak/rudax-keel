---
name: keel-standards-developer
description: Authoring guidance from the quality standard for the developer.
---

# keel-standards-developer

Generated from setup/standards/rules.md — do not edit

source-sha256: b99ed50575565436ccb7863e30b687b6eb080ee4bdde942f2c2a7a4804a4f34d

Reviewers do not flag formatting, style, or naming.

## Not to flag

Flag a concrete defect in the changed code. A theoretical suggestion is not a finding.

## Rules

### DES-01 — Home

severity: advice
bar: demonstrated
condition: The change is in the wrong layer.

Keep one obvious place for a concern.

Flag: The storage call sits in the view.

Do not flag: The call sits next to the existing storage function.

### TST-01 — Tests

severity: block
bar: demonstrated
condition: Required behavior has no failing test.

A required behavior change has a test that fails when the bug returns.

Flag: The transition changed and no test fails if the change is removed.

Do not flag: Existing tests already fail when the behavior is removed.

### REA-01 — Names

severity: advice

Names describe behavior.

Flag: A public function is named px.

Do not flag: A local name is obvious in a three-line function.
