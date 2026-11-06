---
name: keel-standards-design_reviewer
description: Implementation-fit guidance from the quality standard for the design reviewer.
---

# keel-standards-design_reviewer

Generated from setup/standards/rules.md — do not edit

source-sha256: 04feb405582bc76cae27af8ecf6d0b219c242aa2082635a54ce7c8ae1ccc7225

Reviewers do not flag formatting, style, or naming.

## Not to flag

Flag a concrete defect in the changed code. A theoretical defense-in-depth suggestion is not a finding. A required control or an explicit policy violation can still block. A live exploit is not required. Do not flag a pre-existing issue the change does not touch. Do not flag an equally valid alternative. Do not restate a static-gate result as a review finding.

## Rules

### DES-01 — Architectural home

severity: advice
bar: demonstrated
condition: The change puts a concern in the wrong architectural layer, or it is a concrete architecture defect.

clause: speculative generality: advice
clause: simple over clever: advice
clause: system complexity: advice

Put the change in the existing architectural home, and keep one obvious place for a concern. Speculative generality, including an abstraction kept for a need that is not current, is advice. System complexity and simple over clever are advice when the only objection is taste. A concrete wrong layer is a defect.

Flag: A persistence call is added inside a rendering helper, so a later reader cannot change storage without editing the view.

Do not flag: The change adds a function next to the existing one that already owns that concern, and a reviewer prefers a different folder name.

### DES-03 — Minimal public surface

severity: advice

Keep the public module surface limited to symbols a caller actually uses. Do not delete an export only because a tool cannot see a dynamic caller.

Flag: A new public type is exported, nothing in the repository or the stated contract calls it, and the brief does not name an external consumer.

Do not flag: A symbol looks unused to a linter, and a documented plugin loads it by name.

### DES-04 — Separate refactor and behavior

severity: advice

Separate a refactor from a behavior change, or say in the change that both are intentional. A justified combination is not forbidden.

Flag: A bug fix is mixed with a rename of unrelated modules, and the description mentions only the bug.

Do not flag: The description states that a rename and a behavior fix ship together, and each part is identifiable.

### DES-05 — User-facing evidence

severity: advice
bar: demonstrated
condition: The task classification requires user-facing UI evidence and the change does not include it.

When the task classification says the change is user-facing UI, include the evidence the task requires. An attachment alone does not prove the behavior. File names alone do not identify UI impact.

Flag: The task classification says the screen changes, and the change contains no screenshot, preview, or demo note.

Do not flag: The change is a server-only response field, and the task classification does not require UI evidence.

### API-01 — Supported contracts

severity: advice

Preserve a supported request, response, event, or serialized contract for existing consumers, or ship the approved compatibility and migration plan. The auditor is the primary blocker. Interface fit for the design reviewer is advice. An approved coordinated change is not a defect. Property-level authorization is SEC-01.

Flag: A response field is renamed while a supported consumer still reads the old field, and no approved migration exists.

Do not flag: An approved migration updates the field and every supported consumer in the same change.
