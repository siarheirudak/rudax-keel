---
name: keel-standards-developer
description: Authoring guidance from the quality standard for the developer.
---

# keel-standards-developer

Generated from setup/standards/rules.md — do not edit

source-sha256: 17717924e35ed68a58cb2f1054a9f6e36640bf6e6d188bcf7cff84c6220c0128

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

### CMP-01 — Local control flow

severity: advice

Keep local control flow readable. Deep nesting that hides the next step is authoring guidance, not a review finding. Extract a local branch when the nesting hides intent. This is local control flow, not a demand to redesign the system.

Flag: A new function nests five branches so the success path cannot be named without drawing the conditions.

Do not flag: A short nested check handles a documented special case and the success path stays visible.

### SCO-01 — Stay in scope

severity: block
bar: demonstrated
condition: The change includes a material edit outside the task.

Keep the change inside the task. A material opportunistic rewrite is a defect. A trivial touch that the task requires is not.

Flag: The task is a single validation message, and the change also rewrites an unrelated billing module.

Do not flag: The only edited lines are the validation the task names.

### SCO-02 — Protected paths

severity: block
bar: demonstrated
condition: A protected path changes without the required tier.

Do not edit a protected path, including workflow, authentication, billing, or secret paths, without the tier that path requires. The path check and the tier come from the project. An agent-writable note is not the tier.

Flag: A workflow file changes in a task that was not approved to touch workflows.

Do not flag: The task's approved tier includes the workflow file that changed.

### TYP-02 — Authorized type escape

severity: advice

An authorized escape may narrow a type only where the project allows that escape. A linked comment is not authorization. Unauthorized suppression of a required check is COR-04, not a second finding here.

Flag: A new escape disables the typechecker for a security check, and the project has no allowance for that escape.

Do not flag: The escape matches the project's written allowance and the surrounding check still holds.

### TYP-03 — Boundaries

severity: advice

Validate untrusted data at the trust boundary. Do not add a second deep validation of data the boundary already validated. A missing check on untrusted input is a defect when the boundary is the one that must reject it.

Flag: A request body is trusted past the boundary with no schema check, and a later function assumes the fields exist.

Do not flag: The boundary already validates the payload, and an internal helper uses that validated value.

### REL-01 — Test and revert evidence

severity: advice
bar: demonstrated
condition: The project's high tier requires test and revert evidence, and that evidence is missing.

When the project tier requires it, the change records how to test and how to revert or disable. Otherwise this is advice. Do not invent a tier.

Flag: The project's high tier applies and the change includes neither a test note nor a revert note.

Do not flag: The project tier for this change does not require that evidence, and the behavior is covered by existing tests.

### REL-02 — Security audit evidence

severity: advice
bar: demonstrated
condition: An explicitly required security audit event is missing.

When the project requires a security, privilege, or sensitive-mutation audit event, that event stays present, attributable, and useful. Otherwise this is advice. A payload leak is SEC-03, not a second finding here.

Flag: The project requires an audit event for a privilege change, and the change removes that event.

Do not flag: The change does not touch a path the project lists as requiring an audit event.

### TST-01 — Tests fail when the bug returns

severity: block
bar: demonstrated
condition: A required behavior change has no test that fails when that behavior is wrong.

A required behavior change ships with a test that fails if the bug returns. Do not invent a test obligation for a change that does not alter required behavior.

Flag: The payment transition changes and no test fails when the new transition is removed.

Do not flag: A comment-only change does not alter behavior, and existing tests already cover the function.

### TST-02 — Meaningful oracles

severity: block
bar: demonstrated
condition: Required changed behavior is checked only by a vacuous or misleading oracle.

Required changed behavior is exercised through an oracle that can detect a violation. A mock of the function under test that returns the configured answer is not evidence of that behavior. There is no per-assertion mutation quota.

Flag: The test mocks the function under test and asserts that it returns the value configured on that mock, and this is presented as coverage of the business rule.

Do not flag: The test stubs a remote provider, runs the real handler, and asserts the persisted state.

### TST-03 — Simple tests

severity: advice

Keep tests and test helpers as simple as the check allows. Production-level cleverness in a helper needs a reason that the test itself cannot avoid.

Flag: A new helper reimplements the production parser so the test cannot fail when the parser is wrong.

Do not flag: A short helper builds one input value the test repeats.

### COR-01 — Stated behavior and domain invariants

severity: block
bar: demonstrated
condition: Supported behavior or an established domain invariant is violated.

Implement the stated behavior and the established domain invariants for supported inputs. Do not substitute a branch that only matches a fixture, or an approximation the specification does not allow. Preserve required precision, rounding, units, valid state transitions, and temporal meaning. The domain defines those rules. Do not invent an invariant the specification does not state.

Flag: A payment transition accepts a paid state from a state the approved state machine forbids.

Do not flag: A tax computation uses the precision and rounding the domain specifies, and a reviewer prefers a different numeric API.

### COR-02 — Boundaries and failure

severity: block
bar: demonstrated
condition: A boundary or failure path violates the contract, including a backend path that is not visible in a UI.

Handle the relevant boundary and failure cases without violating the contract, losing non-persistent work, or skipping a required availability rule. This includes asynchronous and backend paths. Persisted-state integrity through partial failure, retry, or redelivery is DAT-01. Resource exhaustion is RES-01. Do not cite this rule for those defects.

Flag: A background job fails after part of an in-memory batch was applied, and the caller is told the batch succeeded.

Do not flag: An optional enrichment failure is explicitly allowed and is reported as unavailable.

### COR-03 — Concurrency

severity: block
bar: credible
condition: A concrete race or consistency hazard is introduced across threads, processes, tasks, or distributed state.

Mitigate a concrete concurrency hazard across threads, processes, tasks, and distributed state. A sanitizer or a race tool supplements the review and does not prove there is no race. Persisted partial writes and duplicate delivery are DAT-01, not a second race finding.

Flag: Two requests update the same balance with a read-modify-write and no atomicity or version check, so one update is lost.

Do not flag: Shared state is updated through the existing atomic operation the module already uses for that field.

### COR-04 — Unauthorized weakening

severity: block
bar: demonstrated
condition: A required check is made green by unauthorized deletion, skipping, assertion weakening, configuration change, or suppression.

Do not make a required check green by unauthorized deletion, skipping, assertion weakening, a configuration change, or a suppression. Marking a test expected-fail or skipped to greenwash a required check is this defect. An authorized test replacement must still verify the required behavior. A comment is not authorization. Suppression syntax is not accepted in this standard. The review step needs an owner-controlled approval path before a suppression can be authorized. An authorized type escape is TYP-02, not a second finding here.

Flag: A scanner-disable comment is added so a real violation is ignored, and no owner-controlled approval records the exception.

Do not flag: A test that checked a removed behavior is replaced by a test that checks the required behavior that replaced it.

### COR-05 — Fail closed

severity: block
bar: demonstrated
condition: A risky default fails open on a security-sensitive path.

A feature flag or configuration default fails closed for risky behavior. A default that denies a sensitive action until it is explicitly enabled is the expected shape.

Flag: A new authorization flag defaults to allowed when the configuration omits it.

Do not flag: A new debug trace defaults to off, and the sensitive action still requires the existing authorization check.

### ERR-01 — No false success

severity: block
bar: demonstrated
condition: Unexpected failure becomes an indistinguishable valid result or a successful state.

Do not turn unexpected failure into a result that callers treat as success. Intentional recovery must match the declared contract and must not drop required state. Report one finding here for a swallowed failure, not a second finding under propagation guidance.

Flag: A database outage returns an empty list that the caller treats as no customers, and existing rows are then deleted.

Do not flag: A documented cache miss loads the source of truth, and a failure of that load is reported as an error.

### ERR-02 — Handle or propagate

severity: advice

Catch what the function handles, and propagate the rest with the context the caller needs. A broad catch is not a defect by itself. A swallowed failure that looks like success is ERR-01, not a second finding here.

Flag: A handler catches every failure, drops the cause, and continues as if the operation finished.

Do not flag: A handler catches a documented not-found case, returns the declared empty result, and lets other failures propagate.

### ERR-04 — Errors do not leak secrets

severity: block
bar: demonstrated
condition: A user-facing or API error reveals a secret or an internal detail the caller must not receive.

User-facing and API errors do not reveal secrets or internal details. Disclosure through artifacts, logs, or client payloads is SEC-03. Missing audit events are REL-02. Cite one primary channel.

Flag: An API error body includes a database connection string after a failed query.

Do not flag: An API error returns a stable public code and a message that does not include internal identifiers.

### SEC-01 — Authorization of objects, actions, and properties

severity: block
bar: demonstrated
condition: The change reads or writes an object, action, or property the caller is not allowed to access.

Enforce authorization on the server for objects, actions, and readable or writable properties. Do not expose or bind fields beyond the caller's authority. Wire compatibility is API-01. Property-level authorization stays here.

Flag: A handler returns every field of a stored record, including a field the caller's role is not allowed to read.

Do not flag: The handler copies an explicit allow-list of fields the caller's role may read.

### SEC-02 — Injection

severity: block
bar: demonstrated
condition: Untrusted input is injected into an interpreter, query, shell, or template.

Do not build an interpreter, query, shell, or template command from unsanitized input. Use the safe API the platform provides. Destination, path, and deserialization capability is SEC-09. Do not cite both for the same sink.

Flag: A request parameter is concatenated into a shell command that the server executes.

Do not flag: The query uses a bound parameter and the input is passed as data.

### SEC-03 — Disclosure in artifacts, logs, and client payloads

severity: block
bar: credible
condition: A secret or sensitive data can reach an artifact, a log, or a client-visible payload.

Do not disclose secrets or sensitive data in code artifacts, logs, or client-visible payloads. Review the data flow, not only a literal. Do not read real secret values. A user-facing error leak is ERR-04. Missing audit events are REL-02.

Flag: Changed code copies a server-only token into a payload returned to an unprivileged client.

Do not flag: The logger receives an object that the code redacts before the write, and the redaction is the one the project already uses.

### SEC-04 — Cryptography and keys

severity: block
bar: demonstrated
condition: The change uses homemade cryptography or commits key material.

Use a vetted cryptographic library and the project's key handling. Do not invent a cipher or commit a key. Do not read key material to review the change.

Flag: A new function implements its own block cipher and commits a key next to the source.

Do not flag: The change calls the project's existing vetted library and the key stays in the existing secret store.

### SEC-05 — Authentication and sessions

severity: block
bar: demonstrated
condition: Authentication or session handling on a sensitive path is wrong under the applicable threat model.

Authentication and session handling on a sensitive path must match the threat model. That includes cookie and token attributes the project requires, and a fresh check before a sensitive action when the project requires one.

Flag: A sensitive transfer accepts a session token after the project's required re-authentication step was removed.

Do not flag: The change keeps the existing session check and does not alter token storage.

### SEC-06 — Dependency identity

severity: advice
bar: demonstrated
condition: Required package identity or reproducible resolution is missing, or the project's explicit advisory policy fails.

Introduce only a dependency whose package identity and source are approved, and whose resolution the controlled workflow can reproduce. Apply the project's advisory policy when it has one. Absence of an advisory policy is not itself a block. Do not invent an age or download threshold. Registry presence is not trust.

Flag: A new dependency is added with a name that does not match the approved identity, and the lock resolution is not the approved one.

Do not flag: A dependency is added through the controlled workflow, the lock matches the approved identity, and the project has no additional advisory rule.

### SEC-07 — Unsanitized HTML

severity: block
bar: demonstrated
condition: Untrusted data reaches an HTML sink without verified sanitization.

Do not send unsanitized untrusted data to an HTML sink. A sink that uses the project's verified sanitizer is not this defect. Not every HTML API is exploitable when sanitization is verified.

Flag: A client template writes request text into an HTML sink with no sanitizer.

Do not flag: The same sink passes the text through the project's verified sanitizer before insertion.

### SEC-09 — Unauthorized capability

severity: block
bar: credible
condition: Untrusted input selects a network destination, a filesystem path, or a deserialization path that grants an unauthorized capability.

Do not let untrusted input obtain an unauthorized network, file, or code-execution capability through destination selection, filesystem resolution, or deserialization. Enforce the destination or containment rule at the actual use, including redirects. Canonicalizing a path or checking URL syntax is not enough by itself. Injection into an interpreter is SEC-02. Do not cite both for the same sink.

Flag: A caller-supplied URL is fetched, and a redirect reaches a destination the server is not allowed to contact.

Do not flag: The fetcher applies the project's destination policy at connection and redirect time, and refuses destinations outside it.

### DOC-01 — Operational documents

severity: advice
bar: demonstrated
condition: A required operational document is materially false.

When a required user, build, test, or release document would be materially false after the change, update it. A preference for more prose is advice.

Flag: The release steps still name a command the change removed, and operators following the document hit a failure.

Do not flag: The change does not alter a command or a behavior the operational documents describe.

### DOC-02 — Protected instructions

severity: advice
bar: demonstrated
condition: A required protected instruction is materially false.

When a material change makes a required protected instruction false, the update goes through the owner-controlled path. Do not continue on an instruction known to be wrong. Product roles do not edit protected instructions. A wish for more architecture prose is advice.

Flag: A required protected instruction still tells the role to call a tool the change removed, and the task depends on that instruction.

Do not flag: The instruction is unchanged and still matches the workflow.

### REA-01 — Names describe behavior

severity: advice

Choose names that describe the role or the behavior. Avoid a cryptic abbreviation when a plain name fits.

Flag: A new public function is named px so a caller cannot tell that it posts a payment.

Do not flag: A local variable uses a short name that the surrounding function already makes obvious.

### REA-02 — Comments say why

severity: advice

A comment should say why, or name a constraint that the code does not show. Do not restate what the code already says.

Flag: A new comment repeats the assignment on the next line and hides a unit conversion that is the real constraint.

Do not flag: The code's purpose is clear and there is no comment. Do not ask for a comment that restates it.

### REA-04 — Boolean parameters

severity: advice

At a call site, prefer a name that makes a boolean argument obvious. Replacing a boolean with an enumeration is not a review finding by itself. An ambiguous contract is a correctness or compatibility defect, not a naming nit.

Flag: A new call passes true, true with no names, and a reader cannot tell which flag enables settlement.

Do not flag: A boolean parameter is already named at the call and the behavior matches the name.

### DAT-01 — Persisted state integrity

severity: block
bar: demonstrated
condition: Persisted state breaks an integrity rule or an approved transition.

Preserve declared persisted state through partial failure, concurrent change, and retry. Use an atomic or compensating protocol, and idempotency or duplicate handling, where redelivery is possible. A migration supports the approved rollout and rollback, or an explicitly authorized irreversible transition. Approval of that transition comes from an owner-controlled record. A transaction across every service is not required. Non-persistent boundary handling is COR-02. A concurrency hazard that is not a partial write or a duplicate delivery is COR-03.

Flag: A redelivered webhook charges the customer twice, and the stated contract is a single charge.

Do not flag: A compensating workflow reaches the specified eventual state, and a cross-service transaction is not the specified contract.

### API-01 — Supported contracts

severity: block
bar: demonstrated
condition: A supported request, response, event, or serialized contract breaks without an approved migration.

Preserve a supported request, response, event, or serialized contract for existing consumers, or ship the approved compatibility and migration plan. The auditor is the primary blocker. Interface fit for the design reviewer is advice. An approved coordinated change is not a defect. Property-level authorization is SEC-01.

Flag: A response field is renamed while a supported consumer still reads the old field, and no approved migration exists.

Do not flag: An approved migration updates the field and every supported consumer in the same change.

### RES-01 — Bounded work

severity: block
bar: demonstrated
condition: Work, retries, waits, or resource lifetime violate the execution contract or exhaust a required resource.

Bound work, retries, external waits, and resource lifetime to the execution contract and the project budget when one exists. Honor an inherited deadline or cancellation, and a valid batch or stream limit. Absence of a budget is not itself a block. A missing local timeout argument is not itself a block. Do not cite COR-02 for a resource-budget defect.

Flag: A caller-controlled fan-out retries without a limit and can exhaust a required service.

Do not flag: A bounded batch makes sequential calls under a shared deadline and closes the resources it opens.
