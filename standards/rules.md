# Quality standard

This file is the only source of review rules. Views are generated from it. Do not edit a generated view by hand.

Suppression syntax is not accepted. A suppression is not authorization. The review step needs an owner-controlled approval path before a suppression can be authorized. This file has no approval field.

## Rules

### DES-01 — Architectural home
```keys
kind: judgment
severity: advice
block_when:
  bar: demonstrated
  condition: The change puts a concern in the wrong architectural layer, or it is a concrete architecture defect.
authors: developer, architect
reviewers: architect, auditor, design_reviewer
merges: DES-02, CMP-02
rule: Put the change in the existing architectural home, and keep one obvious place for a concern. Speculative generality, including an abstraction kept for a need that is not current, is advice. System complexity and simple over clever are advice when the only objection is taste. A concrete wrong layer is a defect.
flag: A persistence call is added inside a rendering helper, so a later reader cannot change storage without editing the view.
noflag: The change adds a function next to the existing one that already owns that concern, and a reviewer prefers a different folder name.
source: Google, eng-practices code review guide, https://google.github.io/eng-practices/review/reviewer/looking-for.html (to verify)
```

### DES-03 — Minimal public surface
```keys
kind: judgment
severity: advice
authors: developer, architect
reviewers: architect, design_reviewer
rule: Keep the public module surface limited to symbols a caller actually uses. Do not delete an export only because a tool cannot see a dynamic caller.
flag: A new public type is exported, nothing in the repository or the stated contract calls it, and the brief does not name an external consumer.
noflag: A symbol looks unused to a linter, and a documented plugin loads it by name.
source: Google TypeScript style guide, minimize exported API (to verify)
```

### DES-04 — Separate refactor and behavior
```keys
kind: judgment
severity: advice
authors: developer, architect
reviewers: architect, design_reviewer
rule: Separate a refactor from a behavior change, or say in the change that both are intentional. A justified combination is not forbidden.
flag: A bug fix is mixed with a rename of unrelated modules, and the description mentions only the bug.
noflag: The description states that a rename and a behavior fix ship together, and each part is identifiable.
source: Google, eng-practices code review guide, style and functionality (to verify)
```

### DES-05 — User-facing evidence
```keys
kind: judgment
severity: advice
block_when:
  bar: demonstrated
  condition: The task classification requires user-facing UI evidence and the change does not include it.
authors: developer, architect
reviewers: architect, design_reviewer
rule: When the task classification says the change is user-facing UI, include the evidence the task requires. An attachment alone does not prove the behavior. File names alone do not identify UI impact.
flag: The task classification says the screen changes, and the change contains no screenshot, preview, or demo note.
noflag: The change is a server-only response field, and the task classification does not require UI evidence.
source: Google, eng-practices code review guide, UI changes (to verify)
```

### CMP-01 — Local control flow
```keys
kind: judgment
severity: advice
authors: developer
only: developer
merges: CMP-04
rule: Keep local control flow readable. Deep nesting that hides the next step is authoring guidance, not a review finding. Extract a local branch when the nesting hides intent. This is local control flow, not a demand to redesign the system.
flag: A new function nests five branches so the success path cannot be named without drawing the conditions.
noflag: A short nested check handles a documented special case and the success path stays visible.
source: PEP 20, The Zen of Python, flat is better than nested (to verify); PEP 8, readability (to verify)
```

### REA-01 — Names describe behavior
```keys
kind: judgment
severity: advice
authors: developer
only: developer
rule: Choose names that describe the role or the behavior. Avoid a cryptic abbreviation when a plain name fits.
flag: A new public function is named px so a caller cannot tell that it posts a payment.
noflag: A local variable uses a short name that the surrounding function already makes obvious.
source: PEP 8, naming conventions (to verify)
```

### REA-02 — Comments say why
```keys
kind: judgment
severity: advice
authors: developer
only: developer
rule: A comment should say why, or name a constraint that the code does not show. Do not restate what the code already says.
flag: A new comment repeats the assignment on the next line and hides a unit conversion that is the real constraint.
noflag: The code's purpose is clear and there is no comment. Do not ask for a comment that restates it.
source: Google, eng-practices code review guide, comments (to verify)
```

### REA-03 — Consistent naming
```keys
kind: mechanical
severity: block
gate: naming
rule: Configured lint checks consistent names and the language's casing. The gate reports the tool result. This standard does not set a character limit.
source: PEP 8, naming conventions (to verify)
```

### REA-04 — Boolean parameters
```keys
kind: judgment
severity: advice
authors: developer
only: developer
rule: At a call site, prefer a name that makes a boolean argument obvious. Replacing a boolean with an enumeration is not a review finding by itself. An ambiguous contract is a correctness or compatibility defect, not a naming nit.
flag: A new call passes true, true with no names, and a reader cannot tell which flag enables settlement.
noflag: A boolean parameter is already named at the call and the behavior matches the name.
source: Google TypeScript style guide, parameter names (to verify)
```

### TST-01 — Tests fail when the bug returns
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: A required behavior change has no test that fails when that behavior is wrong.
authors: developer, tester
reviewers: auditor
rule: A required behavior change ships with a test that fails if the bug returns. Do not invent a test obligation for a change that does not alter required behavior.
flag: The payment transition changes and no test fails when the new transition is removed.
noflag: A comment-only change does not alter behavior, and existing tests already cover the function.
source: Google, eng-practices code review guide, tests (to verify)
```

### TST-02 — Meaningful oracles
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: Required changed behavior is checked only by a vacuous or misleading oracle.
authors: developer, tester
reviewers: auditor
rule: Required changed behavior is exercised through an oracle that can detect a violation. A mock of the function under test that returns the configured answer is not evidence of that behavior. There is no per-assertion mutation quota.
flag: The test mocks the function under test and asserts that it returns the value configured on that mock, and this is presented as coverage of the business rule.
noflag: The test stubs a remote provider, runs the real handler, and asserts the persisted state.
source: Google, eng-practices code review guide, tests that fail when broken (to verify)
```

### TST-03 — Simple tests
```keys
kind: judgment
severity: advice
authors: developer, tester
rule: Keep tests and test helpers as simple as the check allows. Production-level cleverness in a helper needs a reason that the test itself cannot avoid.
flag: A new helper reimplements the production parser so the test cannot fail when the parser is wrong.
noflag: A short helper builds one input value the test repeats.
source: Google, eng-practices code review guide, tests (to verify)
```

### ERR-01 — No false success
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: Unexpected failure becomes an indistinguishable valid result or a successful state.
authors: developer, tester
reviewers: auditor
rule: Do not turn unexpected failure into a result that callers treat as success. Intentional recovery must match the declared contract and must not drop required state. Report one finding here for a swallowed failure, not a second finding under propagation guidance.
flag: A database outage returns an empty list that the caller treats as no customers, and existing rows are then deleted.
noflag: A documented cache miss loads the source of truth, and a failure of that load is reported as an error.
source: PEP 20, errors should never pass silently (to verify); OWASP Top 10:2025, exceptional conditions (to verify)
```

### ERR-02 — Handle or propagate
```keys
kind: judgment
severity: advice
authors: developer, tester
reviewers: auditor
rule: Catch what the function handles, and propagate the rest with the context the caller needs. A broad catch is not a defect by itself. A swallowed failure that looks like success is ERR-01, not a second finding here.
flag: A handler catches every failure, drops the cause, and continues as if the operation finished.
noflag: A handler catches a documented not-found case, returns the declared empty result, and lets other failures propagate.
source: PEP 20, explicit is better than implicit (to verify)
```

### ERR-03 — Real error types
```keys
kind: mechanical
severity: block
gate: error-type
rule: Configured tools check that raised values are real error types where the language provides that check. A missing tool is not a passing check. Coverage is not complete for every language.
source: Google TypeScript style guide, only throw errors (to verify)
```

### ERR-04 — Errors do not leak secrets
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: A user-facing or API error reveals a secret or an internal detail the caller must not receive.
authors: developer
reviewers: auditor
rule: User-facing and API errors do not reveal secrets or internal details. Disclosure through artifacts, logs, or client payloads is SEC-03. Missing audit events are REL-02. Cite one primary channel.
flag: An API error body includes a database connection string after a failed query.
noflag: An API error returns a stable public code and a message that does not include internal identifiers.
source: OWASP Top 10:2025, logging and alerting failures, category A09 (to verify)
```

### COR-01 — Stated behavior and domain invariants
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: Supported behavior or an established domain invariant is violated.
authors: developer, tester
reviewers: auditor
rule: Implement the stated behavior and the established domain invariants for supported inputs. Do not substitute a branch that only matches a fixture, or an approximation the specification does not allow. Preserve required precision, rounding, units, valid state transitions, and temporal meaning. The domain defines those rules. Do not invent an invariant the specification does not state.
flag: A payment transition accepts a paid state from a state the approved state machine forbids.
noflag: A tax computation uses the precision and rounding the domain specifies, and a reviewer prefers a different numeric API.
source: Google, eng-practices code review guide, functionality (to verify)
```

### COR-02 — Boundaries and failure
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: A boundary or failure path violates the contract, including a backend path that is not visible in a UI.
authors: developer, tester
reviewers: auditor
rule: Handle the relevant boundary and failure cases without violating the contract, losing non-persistent work, or skipping a required availability rule. This includes asynchronous and backend paths. Persisted-state integrity through partial failure, retry, or redelivery is DAT-01. Resource exhaustion is RES-01. Do not cite this rule for those defects.
flag: A background job fails after part of an in-memory batch was applied, and the caller is told the batch succeeded.
noflag: An optional enrichment failure is explicitly allowed and is reported as unavailable.
source: Google, eng-practices code review guide, functionality (to verify)
```

### COR-03 — Concurrency
```keys
kind: judgment
severity: block
block_when:
  bar: credible
  condition: A concrete race or consistency hazard is introduced across threads, processes, tasks, or distributed state.
authors: developer, architect, tester
reviewers: architect, auditor
rule: Mitigate a concrete concurrency hazard across threads, processes, tasks, and distributed state. A sanitizer or a race tool supplements the review and does not prove there is no race. Persisted partial writes and duplicate delivery are DAT-01, not a second race finding.
flag: Two requests update the same balance with a read-modify-write and no atomicity or version check, so one update is lost.
noflag: Shared state is updated through the existing atomic operation the module already uses for that field.
source: Google, eng-practices code review guide, concurrency (to verify)
```

### COR-04 — Unauthorized weakening
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: A required check is made green by unauthorized deletion, skipping, assertion weakening, configuration change, or suppression.
authors: developer, tester
reviewers: auditor
merges: TST-04
rule: Do not make a required check green by unauthorized deletion, skipping, assertion weakening, a configuration change, or a suppression. Marking a test expected-fail or skipped to greenwash a required check is this defect. An authorized test replacement must still verify the required behavior. A comment is not authorization. Suppression syntax is not accepted in this standard. The review step needs an owner-controlled approval path before a suppression can be authorized. An authorized type escape is TYP-02, not a second finding here.
flag: A scanner-disable comment is added so a real violation is ignored, and no owner-controlled approval records the exception.
noflag: A test that checked a removed behavior is replaced by a test that checks the required behavior that replaced it.
source: Google, eng-practices code review guide, tests (to verify)
```

### COR-05 — Fail closed
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: A risky default fails open on a security-sensitive path.
authors: developer, architect, tester
reviewers: architect, auditor
rule: A feature flag or configuration default fails closed for risky behavior. A default that denies a sensitive action until it is explicitly enabled is the expected shape.
flag: A new authorization flag defaults to allowed when the configuration omits it.
noflag: A new debug trace defaults to off, and the sensitive action still requires the existing authorization check.
source: OWASP Top 10:2025, security misconfiguration (category to verify)
```

### SEC-01 — Authorization of objects, actions, and properties
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: The change reads or writes an object, action, or property the caller is not allowed to access.
authors: developer, architect, tester
reviewers: architect, auditor
rule: Enforce authorization on the server for objects, actions, and readable or writable properties. Do not expose or bind fields beyond the caller's authority. Wire compatibility is API-01. Property-level authorization stays here.
flag: A handler returns every field of a stored record, including a field the caller's role is not allowed to read.
noflag: The handler copies an explicit allow-list of fields the caller's role may read.
source: OWASP API Security 2023, API3 Broken Object Property Level Authorization, https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/ (to verify); OWASP Top 10:2025, broken access control (category to verify)
```

### SEC-02 — Injection
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: Untrusted input is injected into an interpreter, query, shell, or template.
authors: developer, tester
reviewers: auditor
rule: Do not build an interpreter, query, shell, or template command from unsanitized input. Use the safe API the platform provides. Destination, path, and deserialization capability is SEC-09. Do not cite both for the same sink.
flag: A request parameter is concatenated into a shell command that the server executes.
noflag: The query uses a bound parameter and the input is passed as data.
source: OWASP Top 10:2025, injection (category to verify); OWASP ASVS (clause to verify)
```

### SEC-03 — Disclosure in artifacts, logs, and client payloads
```keys
kind: hybrid
severity: block
block_when:
  bar: credible
  condition: A secret or sensitive data can reach an artifact, a log, or a client-visible payload.
authors: developer, tester
reviewers: auditor
gate: scanner
mechanical: Configured artifact scan for recognizable secret literals.
rule: Do not disclose secrets or sensitive data in code artifacts, logs, or client-visible payloads. Review the data flow, not only a literal. Do not read real secret values. A user-facing error leak is ERR-04. Missing audit events are REL-02.
flag: Changed code copies a server-only token into a payload returned to an unprivileged client.
noflag: The logger receives an object that the code redacts before the write, and the redaction is the one the project already uses.
source: OWASP Top 10:2025, logging and alerting failures, category A09 (to verify)
```

### SEC-04 — Cryptography and keys
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: The change uses homemade cryptography or commits key material.
authors: developer
reviewers: auditor
rule: Use a vetted cryptographic library and the project's key handling. Do not invent a cipher or commit a key. Do not read key material to review the change.
flag: A new function implements its own block cipher and commits a key next to the source.
noflag: The change calls the project's existing vetted library and the key stays in the existing secret store.
source: OWASP Top 10:2025, cryptographic failures (category to verify)
```

### SEC-05 — Authentication and sessions
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: Authentication or session handling on a sensitive path is wrong under the applicable threat model.
authors: developer, tester
reviewers: auditor
rule: Authentication and session handling on a sensitive path must match the threat model. That includes cookie and token attributes the project requires, and a fresh check before a sensitive action when the project requires one.
flag: A sensitive transfer accepts a session token after the project's required re-authentication step was removed.
noflag: The change keeps the existing session check and does not alter token storage.
source: OWASP Top 10:2025, authentication failures (category to verify)
```

### SEC-06 — Dependency identity
```keys
kind: judgment
severity: advice
block_when:
  bar: demonstrated
  condition: Required package identity or reproducible resolution is missing, or the project's explicit advisory policy fails.
authors: developer, architect
reviewers: architect, auditor
rule: Introduce only a dependency whose package identity and source are approved, and whose resolution the controlled workflow can reproduce. Apply the project's advisory policy when it has one. Absence of an advisory policy is not itself a block. Do not invent an age or download threshold. Registry presence is not trust.
flag: A new dependency is added with a name that does not match the approved identity, and the lock resolution is not the approved one.
noflag: A dependency is added through the controlled workflow, the lock matches the approved identity, and the project has no additional advisory rule.
source: OWASP Top 10:2025, software supply chain failures, category A03 (to verify)
```

### SEC-07 — Unsanitized HTML
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: Untrusted data reaches an HTML sink without verified sanitization.
authors: developer, tester
reviewers: auditor
rule: Do not send unsanitized untrusted data to an HTML sink. A sink that uses the project's verified sanitizer is not this defect. Not every HTML API is exploitable when sanitization is verified.
flag: A client template writes request text into an HTML sink with no sanitizer.
noflag: The same sink passes the text through the project's verified sanitizer before insertion.
source: OWASP Top 10:2025, injection (category to verify)
```

### SEC-09 — Unauthorized capability
```keys
kind: judgment
severity: block
block_when:
  bar: credible
  condition: Untrusted input selects a network destination, a filesystem path, or a deserialization path that grants an unauthorized capability.
authors: developer, architect, tester
reviewers: architect, auditor
rule: Do not let untrusted input obtain an unauthorized network, file, or code-execution capability through destination selection, filesystem resolution, or deserialization. Enforce the destination or containment rule at the actual use, including redirects. Canonicalizing a path or checking URL syntax is not enough by itself. Injection into an interpreter is SEC-02. Do not cite both for the same sink.
flag: A caller-supplied URL is fetched, and a redirect reaches a destination the server is not allowed to contact.
noflag: The fetcher applies the project's destination policy at connection and redirect time, and refuses destinations outside it.
source: OWASP API Security 2023, API7 Server Side Request Forgery, https://owasp.org/API-Security/editions/2023/en/0xa7-server-side-request-forgery/ (to verify)
```

### SCO-01 — Stay in scope
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: The change includes a material edit outside the task.
authors: developer, architect
reviewers: architect, auditor
rule: Keep the change inside the task. A material opportunistic rewrite is a defect. A trivial touch that the task requires is not.
flag: The task is a single validation message, and the change also rewrites an unrelated billing module.
noflag: The only edited lines are the validation the task names.
source: Google, eng-practices code review guide, change scope (to verify)
```

### SCO-02 — Protected paths
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: A protected path changes without the required tier.
authors: developer, architect
reviewers: architect, auditor
rule: Do not edit a protected path, including workflow, authentication, billing, or secret paths, without the tier that path requires. The path check and the tier come from the project. An agent-writable note is not the tier.
flag: A workflow file changes in a task that was not approved to touch workflows.
noflag: The task's approved tier includes the workflow file that changed.
source: OWASP Top 10:2025, software supply chain failures, category A03 (to verify)
```

### REL-01 — Test and revert evidence
```keys
kind: judgment
severity: advice
block_when:
  bar: demonstrated
  condition: The project's high tier requires test and revert evidence, and that evidence is missing.
authors: developer, architect
reviewers: architect, auditor
rule: When the project tier requires it, the change records how to test and how to revert or disable. Otherwise this is advice. Do not invent a tier.
flag: The project's high tier applies and the change includes neither a test note nor a revert note.
noflag: The project tier for this change does not require that evidence, and the behavior is covered by existing tests.
source: Google, eng-practices code review guide, documenting the change (to verify)
```

### REL-02 — Security audit evidence
```keys
kind: judgment
severity: advice
block_when:
  bar: demonstrated
  condition: An explicitly required security audit event is missing.
authors: developer, architect
reviewers: architect, auditor
rule: When the project requires a security, privilege, or sensitive-mutation audit event, that event stays present, attributable, and useful. Otherwise this is advice. A payload leak is SEC-03, not a second finding here.
flag: The project requires an audit event for a privilege change, and the change removes that event.
noflag: The change does not touch a path the project lists as requiring an audit event.
source: OWASP Top 10:2025, logging and alerting failures, category A09 (to verify)
```

### DOC-01 — Operational documents
```keys
kind: judgment
severity: advice
block_when:
  bar: demonstrated
  condition: A required operational document is materially false.
authors: developer
reviewers: auditor
rule: When a required user, build, test, or release document would be materially false after the change, update it. A preference for more prose is advice.
flag: The release steps still name a command the change removed, and operators following the document hit a failure.
noflag: The change does not alter a command or a behavior the operational documents describe.
source: Google, eng-practices code review guide, documentation (to verify)
```

### DOC-02 — Protected instructions
```keys
kind: judgment
severity: advice
block_when:
  bar: demonstrated
  condition: A required protected instruction is materially false.
authors: developer, architect
reviewers: architect, auditor
rule: When a material change makes a required protected instruction false, the update goes through the owner-controlled path. Do not continue on an instruction known to be wrong. Product roles do not edit protected instructions. A wish for more architecture prose is advice.
flag: A required protected instruction still tells the role to call a tool the change removed, and the task depends on that instruction.
noflag: The instruction is unchanged and still matches the workflow.
source: Google, eng-practices code review guide, documentation (to verify)
```

### DAT-01 — Persisted state integrity
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: Persisted state breaks an integrity rule or an approved transition.
authors: developer, architect, tester
reviewers: architect, auditor
rule: Preserve declared persisted state through partial failure, concurrent change, and retry. Use an atomic or compensating protocol, and idempotency or duplicate handling, where redelivery is possible. A migration supports the approved rollout and rollback, or an explicitly authorized irreversible transition. Approval of that transition comes from an owner-controlled record. A transaction across every service is not required. Non-persistent boundary handling is COR-02. A concurrency hazard that is not a partial write or a duplicate delivery is COR-03.
flag: A redelivered webhook charges the customer twice, and the stated contract is a single charge.
noflag: A compensating workflow reaches the specified eventual state, and a cross-service transaction is not the specified contract.
source: OWASP Top 10:2025, software and data integrity failures, category A08 (to verify)
```

### API-01 — Supported contracts
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: A supported request, response, event, or serialized contract breaks without an approved migration.
authors: developer, architect, tester
reviewers: architect, auditor, design_reviewer
block_reviewers: auditor
rule: Preserve a supported request, response, event, or serialized contract for existing consumers, or ship the approved compatibility and migration plan. The auditor is the primary blocker. Interface fit for the design reviewer is advice. An approved coordinated change is not a defect. Property-level authorization is SEC-01.
flag: A response field is renamed while a supported consumer still reads the old field, and no approved migration exists.
noflag: An approved migration updates the field and every supported consumer in the same change.
source: Google, eng-practices code review guide, compatibility (to verify)
```

### RES-01 — Bounded work
```keys
kind: judgment
severity: block
block_when:
  bar: demonstrated
  condition: Work, retries, waits, or resource lifetime violate the execution contract or exhaust a required resource.
authors: developer, architect, tester
reviewers: architect, auditor
rule: Bound work, retries, external waits, and resource lifetime to the execution contract and the project budget when one exists. Honor an inherited deadline or cancellation, and a valid batch or stream limit. Absence of a budget is not itself a block. A missing local timeout argument is not itself a block. Do not cite COR-02 for a resource-budget defect.
flag: A caller-controlled fan-out retries without a limit and can exhaust a required service.
noflag: A bounded batch makes sequential calls under a shared deadline and closes the resources it opens.
source: OWASP API Security 2023, API4 Unrestricted Resource Consumption, https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/ (to verify)
```

### STY-01 — Formatter
```keys
kind: mechanical
severity: block
gate: formatter
merges: STY-03
rule: The configured formatter and import sorter must be clean, including the project's line length and quote rules. The gate reports the tool result. This standard does not set a column count.
source: PEP 8, code lay-out (to verify)
```

### STY-02 — Lint
```keys
kind: mechanical
severity: block
gate: lint
merges: STY-03
rule: The configured linter must be clean, including the project's quote and comma rules when that linter owns them. Do not file a second formatting defect for the same tool failure. This standard does not set a numeric threshold.
source: PEP 8, code lay-out (to verify)
```

### STY-04 — Debug artifacts
```keys
kind: mechanical
severity: block
gate: debug-artifacts
rule: The configured check rejects a debugger breakpoint and a committed debug artifact on a production path. Ordinary operational logging that the project allows is not this defect.
source: Google TypeScript style guide, debugging (to verify)
```

### TYP-01 — Typecheck
```keys
kind: mechanical
severity: block
gate: typecheck
rule: The configured typecheck must pass. A language with no typechecker is not a silent pass. This standard does not rank typecheckers.
source: Google TypeScript style guide, type checking (to verify)
```

### TYP-02 — Authorized type escape
```keys
kind: hybrid
severity: advice
authors: developer
reviewers: auditor
gate: type-escape
mechanical: Configured type-escape syntax check.
rule: An authorized escape may narrow a type only where the project allows that escape. A linked comment is not authorization. Unauthorized suppression of a required check is COR-04, not a second finding here.
flag: A new escape disables the typechecker for a security check, and the project has no allowance for that escape.
noflag: The escape matches the project's written allowance and the surrounding check still holds.
source: Google TypeScript style guide, any and suppressions (to verify)
```

### TYP-03 — Boundaries
```keys
kind: judgment
severity: advice
authors: developer, architect
reviewers: architect, auditor
rule: Validate untrusted data at the trust boundary. Do not add a second deep validation of data the boundary already validated. A missing check on untrusted input is a defect when the boundary is the one that must reject it.
flag: A request body is trusted past the boundary with no schema check, and a later function assumes the fields exist.
noflag: The boundary already validates the payload, and an internal helper uses that validated value.
source: OWASP Top 10:2025, injection (category to verify)
```

### DUP-01 — Duplication
```keys
kind: mechanical
severity: block
gate: duplication
rule: Duplication above the project's configured threshold is a gate result. This standard does not set a percentage.
source: Google, eng-practices code review guide, small related changes (to verify)
```

### CX-01 — Complexity budget
```keys
kind: mechanical
severity: block
gate: complexity
merges: CMP-03
rule: File size, function size, and complexity stay within the project's configured complexity budget. The budget is project policy. This standard does not set a universal number.
source: Google, eng-practices code review guide, complexity (to verify)
```

## NOT-to-flag

### SEC-08 — Concrete defects
```keys
id: SEC-08
policy: Flag a concrete defect in the changed code. A theoretical defense-in-depth suggestion is not a finding. A required control or an explicit policy violation can still block. A live exploit is not required. Do not flag a pre-existing issue the change does not touch. Do not flag an equally valid alternative. Do not restate a static-gate result as a review finding.
source: Cloudflare security review, what to flag and what not to flag (to verify)
```
