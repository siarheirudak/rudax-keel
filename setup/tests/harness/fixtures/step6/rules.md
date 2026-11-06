# Fixture

## Rules

### DES-01 — Home
```keys
kind: judgment
severity: advice
block_when:
  bar: demonstrated
  condition: The change is in the wrong layer.
authors: developer, architect
reviewers: architect, auditor, design_reviewer
merges: DES-02
rule: Keep one obvious place for a concern.
flag: The storage call sits in the view.
noflag: The call sits next to the existing storage function.
source: Fixture source
```

### TST-01 — Tests
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: Required behavior has no failing test.
authors: developer, tester
reviewers: auditor
rule: A required behavior change has a test that fails when the bug returns.
flag: The transition changed and no test fails if the change is removed.
noflag: Existing tests already fail when the behavior is removed.
source: Fixture source
```

### REA-01 — Names
```keys
kind: judgment
severity: advice
authors: developer
only: developer
rule: Names describe behavior.
flag: A public function is named px.
noflag: A local name is obvious in a three-line function.
source: Fixture source
```

### STY-01 — Format
```keys
kind: mechanical
severity: block
gate: formatter
rule: The configured formatter is clean.
source: Fixture source
```

## NOT-to-flag

### SEC-08 — Policy
```keys
id: SEC-08
policy: Flag a concrete defect in the changed code. A theoretical suggestion is not a finding.
source: Fixture source
```
