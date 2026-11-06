---
name: keel-standards-tester
description: Test-authoring guidance from the quality standard for the tester.
---

# keel-standards-tester

Generated from standards/rules.md — do not edit

source-sha256: 82112a686750f825609315b4a8a3c1046b8568bfb0102e6341493775fa694bfb

Reviewers do not flag formatting, style, or naming.

## Not to flag

Flag a concrete defect in the changed code. A theoretical defense-in-depth suggestion is not a finding. A required control or an explicit policy violation can still block. A live exploit is not required. Do not flag a pre-existing issue the change does not touch. Do not flag an equally valid alternative. Do not restate a static-gate result as a review finding.

## Rules

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

### SEC-05 — Authentication and sessions

severity: block
bar: demonstrated
condition: Authentication or session handling on a sensitive path is wrong under the applicable threat model.

Authentication and session handling on a sensitive path must match the threat model. That includes cookie and token attributes the project requires, and a fresh check before a sensitive action when the project requires one.

Flag: A sensitive transfer accepts a session token after the project's required re-authentication step was removed.

Do not flag: The change keeps the existing session check and does not alter token storage.

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
