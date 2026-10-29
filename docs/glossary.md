# Glossary

Short definitions for this repository. The first time a longer page needs a word, it defines it again in place. If a page and this list disagree, the page that describes the current code wins for what is implemented, and [Implementation status](status.md) wins for whether a pipeline term exists yet.

## People and accounts

**Owner.** The repository owner: the human who approves decisions, merges pull requests, and creates releases.

**Bot.** The GitHub **bot account** used by this project to open pull requests. It has write access, not admin. Docs do not print the login.

**Agent.** A program that uses a language model to propose part of a task. Its own report is not evidence.

**Pi Agent.** The runtime the v1 design uses to host agent roles inside a container. It is not part of this repository.

**Role.** One agent job: orchestrator, researcher, critic, architect, tester, developer, auditor, design reviewer, verifier, or QA.

**Host script.** An ordinary program on the machine that runs the pipeline. It checks files and commands. It does not accept an agent’s summary as proof.

**Dispatcher.** A host script (control plane) that owns task state, a fixed transition table for links L0 through L11, gate runs, allowlisted request files (`keel_request`), logging, and launches of role containers via `setup/keel.sh role`. Agents do not message each other; they drop request files for the dispatcher. Design: [Harness design](harness/README.md).


**Intermediary.** An external chat agent that bridges the owner and the orchestrator in both directions. Its primary job is high-quality two-way transfer of meaning. It is not part of the harness trust boundary. Recommended instructions: [Intermediary agent instructions](intermediary-agent-instructions.md).

**Request file.** An allowlisted file the orchestrator (or another role) drops for the dispatcher. The dispatcher rejects kinds that are not on the allowlist.

**D1 confidence-notes log.** The detailed notes behind the brief’s D1 confidence rating. Written and readable by the orchestrator. Denied to the auditor until the auditor’s verdict. Not an owner-decision store. Exact path still open.

## Planes and steps

**Reasoning plane.** The agents. They propose.

**Control plane.** The host scripts. They accept or reject.

**Zero-trust.** In this project: do not trust an agent’s report. Trust a script, tests and gates the host runs, and the owner’s decision.

**Task.** One piece of work, from the owner’s message to a merge or a dossier.

**Link.** One step of a task in the v1 chain, L0 through L11. Not the same word as layer.

**Layer.** A slice already shipped in this repository. Layer 1 is GitHub protection. Layer 2 is the CI checks.

**Gate.** A host script that returns pass or fail. The red gate, the static gate, and the green gate are pipeline gates. `keel-gate` is the GitHub check-run name for this repository’s CI. The host gate in `setup/keel.sh` is the prototype that checks an exported bundle.

**Depth.** How much of the chain runs: full, light, or trivial. The script decides. [Architecture](architecture.md#depth).

**Brief.** The orchestrator’s written understanding of the task, which the owner approves.

**D0.** A required paragraph in the brief. The design does not set a longer template than that.

**D1.** The orchestrator’s confidence in the brief: high, medium, or low. Not an owner decision. Low confidence raises a D2 question. Detailed notes live in the D1 confidence-notes log (orchestrator writes; auditor hidden until verdict).

**D2.** A question for the owner, with options and a default. It waits until the owner answers.

**Out of scope.** The brief’s line naming what this task will not do.

**Envelope.** The script-built summary on the pull request. It is what the owner reads in order to merge.

**Tree hash.** Git’s id for the exact contents of the files. The green gate records it. CI blocks when the pull request’s files are a different tree.

**Dossier.** A failure record that stops the cycle when retries are used up, or when the brief is wrong and the cycle aborts. A script writes it.

## Tests and review

**Stub.** A signature and a body that is not the real implementation yet. The red gate runs tests against stubs.

**Red gate.** The script that checks new tests fail for an honest reason (an assertion, or not implemented) before implementation.

**Static gate.** The script that checks lint, types, signatures, paths, secrets, and complexity.

**Green gate.** The script that runs new tests, old tests, and mutation testing, then records the tree hash.

**L7T.** The mutation step of the green gate (see Mutation testing).

**Mutation testing.** Changing a small piece of logic to see whether a test fails. A survivor that nobody can explain blocks the green gate.

**Equivalent mutant.** A mutation that does not change behaviour, recorded with a reason, so it does not block.

**Yellow finding.** A review note listed on the pull request. It does not block the merge.

**Blocking finding.** A review note that returns the task to the developer. It needs a file and line, a rule id, and a behavioural effect.

**Fence.** A wrapping that marks repository text as data, so the model does not treat it as instructions. Content fencing (M5) is specified and deferred to the backlog; containers today receive ordinary files.

**Deny-list.** The paths a role must not see. The path is not mounted. Extra denies may be added. Harness denies may not be removed.

## Quality

**Rule id.** A short code for one entry in the quality standard, such as `DES-01`.

**Quality standard.** The single file `standards/rules.md`, which a generator splits into per-role views. The file is not in the repository yet.

**CRAP.** A score that rises when a function has many branches and tests do not cover them. The design blocks at 30 and above. The warn band from 10 up to 30 is a configurable project default.

**SEC-08.** A standing “do not flag” policy. The generator does not emit it as a rule id.

## Memory and release

**Task journal.** `.keel/runs/<task-id>/journal.md`, appended by the host after each link and deleted when the owner merges.

**Discovery.** A filtered note about a pitfall, kept after the task. Agents propose. A script accepts or discards.

**ADR.** An architecture decision record. One file per decision, packaged like a discovery.

**Skill.** A file of instructions for a role, under `.agents/skills/`. Changes need the owner’s approval.

**Process file.** A file that defines how the repository is checked or how agents are instructed, such as anything under `.github/` or `setup/`. A pull request that changes one must not change other files in the same pull request.

**Process-files pull request.** A separate pull request, labelled `process-files`, for those files. Skill approvals land this way.

**Rollback mode.** How the change would be undone: plain code, feature flag, migration, API change, or irreversible. Recorded on the envelope.

**Staging.** The default branch after the owner merges. Production is a later tag or a manually dispatched workflow.

**Red team.** A later, explicitly triggered check against a staging environment. Not part of the v1 build. The envelope may recommend it when a change touches authentication, payments, or user data.

## The harness that exists today

**Shadow git.** A per-task git directory the container commits into. It borrows objects from a base repo and is reset before each role, so one role cannot leave hooks for the next.

**Bundle.** A `git bundle` file exported from the shadow. It is the only thing the host gate reads. The gate does not trust the working tree directly.

**Push stub.** `setup/keel.sh push-stub`. It prints the push it would perform and does not push. It has no token.

**Rootless.** A container runtime that runs as a normal user. Mandatory in the v1 design. A warning, not a refusal, in today’s doctor (ENV-05).

## Related

[Architecture](architecture.md) · [Working through a chat agent](working-through-chat.md) · [Implementation status](status.md)
