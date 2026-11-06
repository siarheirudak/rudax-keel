---
name: keel-standards-static_gate
description: Mechanical gate facets from the quality standard.
---

# keel-standards-static_gate

Generated from standards/rules.md — do not edit

source-sha256: 82112a686750f825609315b4a8a3c1046b8568bfb0102e6341493775fa694bfb

A required adapter with no tool behind it blocks. An optional adapter that is not supported is advice and is not a passing check.

## Rules

### TYP-01 — Typecheck

kind: mechanical
gate: typecheck

The configured typecheck must pass. A language with no typechecker is not a silent pass. This standard does not rank typecheckers.

### TYP-02 — Authorized type escape

kind: hybrid
gate: type-escape

Configured type-escape syntax check.

### ERR-03 — Real error types

kind: mechanical
gate: error-type

Configured tools check that raised values are real error types where the language provides that check. A missing tool is not a passing check. Coverage is not complete for every language.

### SEC-03 — Disclosure in artifacts, logs, and client payloads

kind: hybrid
gate: scanner

Configured artifact scan for recognizable secret literals.

### STY-01 — Formatter

kind: mechanical
gate: formatter

The configured formatter and import sorter must be clean, including the project's line length and quote rules. The gate reports the tool result. This standard does not set a column count.

### STY-02 — Lint

kind: mechanical
gate: lint

The configured linter must be clean, including the project's quote and comma rules when that linter owns them. Do not file a second formatting defect for the same tool failure. This standard does not set a numeric threshold.

### STY-04 — Debug artifacts

kind: mechanical
gate: debug-artifacts

The configured check rejects a debugger breakpoint and a committed debug artifact on a production path. Ordinary operational logging that the project allows is not this defect.

### DUP-01 — Duplication

kind: mechanical
gate: duplication

Duplication above the project's configured threshold is a gate result. This standard does not set a percentage.

### CX-01 — Complexity budget

kind: mechanical
gate: complexity

File size, function size, and complexity stay within the project's configured complexity budget. The budget is project policy. This standard does not set a universal number.

### REA-03 — Consistent naming

kind: mechanical
gate: naming

Configured lint checks consistent names and the language's casing. The gate reports the tool result. This standard does not set a character limit.
