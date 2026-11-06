---
name: keel-standards-architect
description: Design guidance from the quality standard for the architect.
---

# keel-standards-architect

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

### COR-03 — Concurrency

severity: block
bar: credible
condition: A concrete race or consistency hazard is introduced across threads, processes, tasks, or distributed state.

Mitigate a concrete concurrency hazard across threads, processes, tasks, and distributed state. A sanitizer or a race tool supplements the review and does not prove there is no race. Persisted partial writes and duplicate delivery are DAT-01, not a second race finding.

Flag: Two requests update the same balance with a read-modify-write and no atomicity or version check, so one update is lost.

Do not flag: Shared state is updated through the existing atomic operation the module already uses for that field.

### COR-05 — Fail closed

severity: block
bar: demonstrated
condition: A risky default fails open on a security-sensitive path.

A feature flag or configuration default fails closed for risky behavior. A default that denies a sensitive action until it is explicitly enabled is the expected shape.

Flag: A new authorization flag defaults to allowed when the configuration omits it.

Do not flag: A new debug trace defaults to off, and the sensitive action still requires the existing authorization check.

### SEC-01 — Authorization of objects, actions, and properties

severity: block
bar: demonstrated
condition: The change reads or writes an object, action, or property the caller is not allowed to access.

Enforce authorization on the server for objects, actions, and readable or writable properties. Do not expose or bind fields beyond the caller's authority. Wire compatibility is API-01. Property-level authorization stays here.

Flag: A handler returns every field of a stored record, including a field the caller's role is not allowed to read.

Do not flag: The handler copies an explicit allow-list of fields the caller's role may read.

### SEC-06 — Dependency identity

severity: advice
bar: demonstrated
condition: Required package identity or reproducible resolution is missing, or the project's explicit advisory policy fails.

Introduce only a dependency whose package identity and source are approved, and whose resolution the controlled workflow can reproduce. Apply the project's advisory policy when it has one. Absence of an advisory policy is not itself a block. Do not invent an age or download threshold. Registry presence is not trust.

Flag: A new dependency is added with a name that does not match the approved identity, and the lock resolution is not the approved one.

Do not flag: A dependency is added through the controlled workflow, the lock matches the approved identity, and the project has no additional advisory rule.

### SEC-09 — Unauthorized capability

severity: block
bar: credible
condition: Untrusted input selects a network destination, a filesystem path, or a deserialization path that grants an unauthorized capability.

Do not let untrusted input obtain an unauthorized network, file, or code-execution capability through destination selection, filesystem resolution, or deserialization. Enforce the destination or containment rule at the actual use, including redirects. Canonicalizing a path or checking URL syntax is not enough by itself. Injection into an interpreter is SEC-02. Do not cite both for the same sink.

Flag: A caller-supplied URL is fetched, and a redirect reaches a destination the server is not allowed to contact.

Do not flag: The fetcher applies the project's destination policy at connection and redirect time, and refuses destinations outside it.

### DOC-02 — Protected instructions

severity: advice
bar: demonstrated
condition: A required protected instruction is materially false.

When a material change makes a required protected instruction false, the update goes through the owner-controlled path. Do not continue on an instruction known to be wrong. Product roles do not edit protected instructions. A wish for more architecture prose is advice.

Flag: A required protected instruction still tells the role to call a tool the change removed, and the task depends on that instruction.

Do not flag: The instruction is unchanged and still matches the workflow.

### DAT-01 — Persisted state integrity

severity: block
bar: demonstrated
condition: Persisted state breaks an integrity rule or an approved transition.

Preserve declared persisted state through partial failure, concurrent change, and retry. Use an atomic or compensating protocol, and idempotency or duplicate handling, where redelivery is possible. A migration supports the approved rollout and rollback, or an explicitly authorized irreversible transition. Approval of that transition comes from an owner-controlled record. A transaction across every service is not required. Non-persistent boundary handling is COR-02. A concurrency hazard that is not a partial write or a duplicate delivery is COR-03.

Flag: A redelivered webhook charges the customer twice, and the stated contract is a single charge.

Do not flag: A compensating workflow reaches the specified eventual state, and a cross-service transaction is not the specified contract.

### API-01 — Supported contracts

severity: advice

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
