# Pipeline

Each link of the v1 chain: what it is for, who acts, what it reads, what it writes, what it refuses, and how many times it may be sent back. The diagram of the same chain is in [Architecture](architecture.md).

**Status.** Specified for v1. None of these links run in this repository. The container harness under `setup/` can run a named shell role and a host gate. That gate is the ancestor of the path checks named below. It is not L4, L6, L7, or L10.

A **result name** is the status string a link reports to the control plane, such as `BRIEF_READY`. The names below are the design’s names.

Retry limits for the whole chain are collected again at the [end of this page](#retry-limits).

## How a return works

A **return** sends the task back to an earlier link with the failure attached. A return counts. When the count for that loop is exhausted, the cycle stops in a dossier. A **pause** waits for the owner and does not count as a try. A **dossier** is written by a script, including the abort note stored with discoveries. The agent that was working does not write that note.

The **task journal** is a host file, `.keel/runs/<task-id>/journal.md`. After every link the script appends a line: which link, which role, the result, the commit, the artifacts, the money and the minutes, and the dossier reason when there is one. That file is how a stopped task resumes at the last green link. It is specified in [Logging](logging.md) and it is not created by the current code.

## Skills intake

Skills are a side path, triggered rather than numbered.

**Purpose.** Add or change a skill only with the owner’s approval, after a critic and a suspicious-content scan.

**Who acts.** A stack-detect script. A researcher agent. A critic agent with no network. The owner. A script that opens a process-files pull request.

**Triggers.** A project is starting. The stack changed. The same pitfall has been accepted into discoveries twice. The owner asks the orchestrator for a skill.

**Inputs.** Manifests and lockfiles, plus a deterministic table from filename to technology. A research brief.

**Outputs.** Skill files under `.agents/skills/`, or a harness checklist generated from the quality standard. The approval card shows the file size. The design sets no maximum length. Leaving length uncapped has not been measured, so the card shows the size and the owner judges.

**What must pass.** The researcher may use the internet and may not see code or tokens. Official sources come first. A secondary source is allowed only next to an official one. Forum posts are not a source. The note records the version it read and the date it was read. Then a block-list, a critic with no network, and a scan. The scan escalates to the owner, with the lines highlighted, when a skill contains install commands, network use, secret access, or a way around a gate. That skill stays disabled until the owner gives an explicit yes.

**Stops and retries.** The critic may return findings once before the approval card. Every create, change, and delete waits for the owner. A rejection does not merge.

**Result names.** `SKILLS_APPROVED`, `SKILLS_REJECTED`, `WAITING_SKILL_APPROVAL`, `WAITING_SUSPICIOUS_SKILL_D2`.

The developer, the tester, QA, and the architect receive project skills. The critic checklist and the reviewer checklists are the exception: they are generated from `standards/rules.md` and mounted read-only by the harness. See [Quality standard](quality.md).

## L0. Grilling

**Purpose.** Turn the owner’s message into a brief the rest of the chain can follow, and stop early when the brief is wrong.

**Who acts.** The orchestrator agent. The owner, for answers and for approving the brief.

**Inputs.** The owner’s message. Product docs at the level of a product requirements document. The previous brief, if this is a revision. The task journal, if the task is resuming.

**Outputs.** A brief with five parts: what the task is understood to be, a D0 paragraph, a D1 confidence (high, medium, or low), D2 questions that each carry options and a default, and one line naming what is out of scope. The owner is also shown the size and the estimated cost.

**What must pass.** Some topics always raise a D2 question, even when confidence is high: user-visible wording or layout, data or migrations, money, security or access, a new dependency, a public API change, a departure from the product docs, and any change that cannot be undone. Low confidence also raises a D2 question. A bugfix gets a lighter grilling. A behaviour change that departs from the product docs is still a D2 question. Later, the envelope refuses to open if D0, D1, D2, or the out-of-scope line is missing.

**Stops and retries.** An unanswered D2 question waits indefinitely. A wrong brief stops the cycle. The orchestrator shows version 2 as a diff, and the cycle continues only after the owner approves that diff. An abort writes a dossier.

**Result names.** `BRIEF_READY`, `WAITING_D2`, `BRIEF_REJECTED`.

**Visibility.** The orchestrator sees the chat and the product docs, fenced as data. It does not see secrets. The D1 log stays hidden from the auditor until the auditor has given a verdict. [Roles](roles.md).

## L1. Context packaging

**Purpose.** Give later agents the notes and files they need, without handing them a whole repository of instructions.

**Who acts.** A host script. The orchestrator only if the packet is over the token limit and must be split into iterations.

**Inputs.** The brief. The paths the task is allowed to touch. ADR entries and discoveries that the script has already accepted. Repository files. The per-role view of the quality standard.

**Outputs.** A context package. An entry is included in full when it matches the task’s paths or tags, or when it is marked critical. Other entries are one index line each, newest first. The index is built in memory for that packaging and is not stored. Every packaged body is fenced as data.

**What must pass.** The files in the package are the allowed paths plus one level of imports. Agents may read further files only as read-only data, still fenced. Each ADR and each discovery is one file, with front matter (id, title, tags, paths, severity) and a date-prefixed filename. A CI check reports paths that do not exist. A rename produces a suggested new path from `git log --follow`. A deleted path is marked stale. Over the token limit, the result is `NEEDS_SPLIT` and the orchestrator divides the work into iterations.

**Stops and retries.** There is no dossier on this link. Over-limit work splits. A later `NEEDS_CONTEXT` from the developer returns here for a new package.

**Result names.** `CONTEXT_READY`, `NEEDS_SPLIT`, `STALE_PATHS`.

**Visibility.** The deny-list applies to what can be packaged. Holdouts and secrets are never packaged for the developer.

## L2. Stubs and plan

**Purpose.** Agree the shape of the change, the depth, and the size before tests or code.

**Who acts.** The architect agent. A critic agent. A host script that checks the result. The owner, if the estimate should be split.

**Inputs.** The fenced context package, the brief, and the architect’s view of the quality standard (the DES, CMP, SCO, TYP-03, and REL-01 families). Those family codes are defined in [Quality standard](quality.md).

**Outputs.** Stubs and a plan. A depth of full, light, or trivial, which the script may override. A dependency list of names and purposes, with no versions. A size estimate in lines of code, excluding generated files and lockfiles. An estimated cost for the owner.

**What must pass.** The script compares the claimed depth with the diff. A mismatch forces full depth. A task with a D2 question is never trivial. Trivial is decided by script rules only, never by the architect’s say-so. Stubs are checked as syntax trees for TypeScript and Python. A **syntax tree** is the structure of the code (functions, parameters, classes), not the raw characters. The critic reviews signatures and the plan, with script metrics such as the count of new files and the duplication the script measured. The critic is adversarial. A different model from the developer’s is used when one is available. When only one model is available, the critic gets a different prompt and checklist, and the envelope records which models ran.

**Stops and retries.** The critic may return the plan to the architect twice. The third failure is a dossier. A signature change requested later from L5 may return here once. The second signature change is a dossier. The split decision, when the estimate is over the project threshold, happens here, before L3. The starting threshold is the configurable band described in [Architecture](architecture.md#split).

**Result names.** `STUBS_READY`, `WAITING_SPLIT_APPROVAL`, `SPLIT_REJECTED`, `SIGNATURE_CHANGE_NEEDED`.

**Visibility.** The architect and the critic do not receive holdouts or secrets. Packaged content is fenced.

## Dependencies

This step sits after L2 and before L3. It is not a numbered link.

**Purpose.** Install approved dependencies on the host before the tester writes tests, so the developer’s container never has a general network.

**Who acts.** A host script. The owner, when a dependency is new.

**Inputs.** The architect’s list of names and purposes. Package registries, reached through the allowlist proxy.

**Outputs.** Resolved versions, a lockfile, checksums, and an install performed on the host through the proxy. A package cache.

**What must pass.** The script takes the latest stable release and lets the package manager resolve compatibility. It checks known vulnerabilities (an advisory feed such as OSV). A new version waits out a quarantine before install, unless it is a security fix, which may skip the wait. The default wait is 7 days. That number is a project setting, still to be confirmed against how fresh the advisory feed needs to be. It is not a measured result from this repository. A new dependency raises a D2 card with the package, the version, the license, and the reason. Install uses `--ignore-scripts` where the package manager allows it. Exceptions are approved separately and listed in the envelope.

**Stops and retries.** An unanswered dependency question waits indefinitely. If the developer later reports `NEEDS_DEPENDENCY`, the task pauses here and that pause does not spend a coding attempt.

**Result names.** `DEPS_READY`, `WAITING_DEP_D2`, `NEEDS_DEPENDENCY`.

When the architect listed no new dependency, L3 may use the lockfile that already exists. When new dependencies were listed, L3 starts only after `DEPS_READY`.

## L3. Tests

**Purpose.** Write the tests that define the behaviour, including tests the implementer will not see.

**Who acts.** The tester agent. A host script that stores holdouts.

**Inputs.** The brief’s rules. The stubs and signatures. The tester’s view of the quality standard (TST, COR-02, COR-04). The tree from before the implementation. Dependencies, already installed when the task needed new ones.

**Outputs.** Unit tests and integration tests. One or two holdouts per brief rule, aimed at edge cases, guided by the tester’s checklist skill. A note for the envelope: how many old tests changed, and the brief rule that justifies each change.

**What must pass.** There is no test critic. The tester may change an existing test, and each change must name the brief rule that requires it. For a bugfix, the reproducing test must run alone on a clean default branch and must fail on an assertion. Holdouts are written by the tester and stored by the script under `.keel/holdout/` on the host. Content the tester sees is fenced as data.

**Stops and retries.** Returns from the red gate are capped at two, then a dossier. Those returns are counted on L4.

**Result names.** `TESTS_READY`, `REPRO_FAILED` when a bugfix test does not fail on the default branch.

**Visibility.** The new implementation is not mounted. The tester works on the pre-implementation commit. Holdouts, once stored, are not visible to the developer.

## L4. Red gate

**Purpose.** Prove the new tests fail for an honest reason before any implementation is accepted.

**Who acts.** A host script. Agents do not run this gate.

**Inputs.** The tests from L3. The stubs, or the current code when the depth is light. Test reports through adapters for pytest and for Vitest or Jest, read as JUnit-style XML or JSON.

**Outputs.** Pass or fail, with a failure class. A return to the tester, or permission to continue.

**What must pass.** Tests run on the stubs (on the current code in light depth). A test that passes against empty code is rejected. Tag coverage must be complete: every tag the brief’s tests are required to carry is present. The design names that check and does not define a separate tag syntax, so this page does not invent one. Old tests are green. A light bugfix skips the recheck against the default branch. Trivial depth skips this gate. Only an assertion failure, or a not-implemented result, counts as an honest red. An import error or a build error is `RED_FAIL` and goes back to the tester. It is not `RED_PASS`.

The path checks inside this gate are specified to share one library with L6, L7, and L10: parse paths without breaking on unusual characters, reject forbidden paths, reset a shadow checkout without following a symlink, reject a nested `.git`, take tests from the default branch, and reject a commit with more than one parent. The prototype gate in `setup/keel.sh` already enforces that family of checks on an exported bundle. The shared library those four links would call is not extracted yet.

**Stops and retries.** At most two returns to the tester, then a dossier.

**Result names.** `RED_PASS`, `RED_FAIL`.

## L5. Code

**Purpose.** Implement the stubs so the visible tests pass, and stop when the same approach fails twice.

**Who acts.** The developer agent.

**Inputs.** The brief, the stubs, the tests (not the holdouts), the fenced context package, the developer style guide (every quality rule, including REA-01, REA-02, and REA-04, which appear only there), the developer’s skills, and the same lint and type tools the static gate will run.

**Outputs.** Local implementation commits. Discovery candidates. A script, not the developer, accepts or discards those candidates. [Discoveries](discoveries.md).

**What must pass.** Nothing the developer reports is trusted until L6 and L7 have run. A failure report is compressed. When the failure came from a holdout, the report contains the rule text and does not contain the holdout’s source.

**Stops and retries.** Three submissions, plus the task budget. Until spend has been measured on the first several tasks, the budget only warns. [Logging](logging.md#budget). The same failure twice stops early, into a dossier. `NEEDS_DEPENDENCY` pauses and does not spend a submission. A rollback rehearsal that fails returns here and does spend a submission.

The link has exactly four special exits:

| Exit | Where it goes | Does it spend a submission? |
|---|---|---|
| `NEEDS_CONTEXT` | L1, to rebuild the package | No. It leaves the coding loop |
| `SIGNATURE_CHANGE_NEEDED` | L2, once | A second request is a dossier |
| `NEEDS_DEPENDENCY` | The dependency step | No |
| `BRIEF_CONFLICT` | Dossier | The cycle stops |

Any other exhaustion of the three submissions is a dossier. A normal submission goes to L6.

**Visibility.** No `.keel/holdout/`, no secrets, and no network except the model API through the proxy.

## L6. Static gate

**Purpose.** Reject a submission that is unformatted, untyped, off the stubs, outside the allowed paths, or carrying a secret, before any behavioural test is trusted.

**Who acts.** A host script.

**Inputs.** The developer’s submission, as a bundle or a diff.

**Outputs.** Pass or fail. The script applies formatting itself. Warnings are listed for the envelope rather than dropped.

**What blocks.** Lint. Types, on the changed files and as a project-wide type check. Signatures that no longer match the stubs, compared as syntax trees. Path boundaries: tests, holdouts, and process files untouched, using the shared path library named under L4. Secrets, scanned in the spirit of rule SEC-03. A lockfile that does not match the approved set. Complexity at or above the block line. Basic pattern scan (semgrep); a suppression needs a reason, and reviewers look at that reason later.

**What warns, and is listed in the envelope.** Complexity in the warn band. Duplicates.

Complexity here is a CRAP score: a function scores higher when it has many branches and the tests do not cover those branches. The design blocks at 30 and above, and treats that block line as settled for v1. The warn band from 10 up to 30 is a configurable default the project chose. It should be adjusted once a real codebase has a baseline. It is not a result measured in this repository. Legacy debt can sit on a baseline so that old code is not newly blocked for an old score.

The static gate owns the mechanical rule families STY, TYP-01, DUP, CX, REA-03, ERR-03, and SEC-03. Reviewers do not re-flag formatting. [Quality standard](quality.md).

**Stops and retries.** A failure returns to the developer and spends one submission, inside the L5 budget. Any code change that happens after review must run L6 and L7 again.

**Result names.** `STATIC_PASS`, `STATIC_FAIL`.

## L7. Green gate

**Purpose.** Run the tests the developer saw, the tests the developer did not see, and a mutation check, then freeze the tree hash of the passing files.

**Who acts.** A host script. The tester, for at most one return, when a mutation gap has to be closed.

**Inputs.** The submission that passed L6. New tests, old tests, and the host holdouts.

**Outputs.** Pass or fail. Coverage is shown and does not block. A mutation trend, as a percentage, is shown. A list of quarantined flaky tests. The tree hash, `gated_tree_sha`, written for the envelope.

**What must pass.** The script runs new tests, old tests, and host holdouts, then mutation testing on the changed files. JavaScript and TypeScript use Stryker. Python uses mutmut. Other languages are skipped, and the envelope says so. The gate blocks only on an unexplained mutant that survived on changed logic. A test that kills a mutant must cite a brief rule id. A survivor with no rule id still blocks. An equivalent mutant is allowed when the reason is recorded. An **equivalent mutant** is a change that leaves the program’s behaviour the same, so no test should fail.

Coverage is shown and is not a blocking number.

A test is treated as flaky by a host rule only. It is related to this task when the tester changed that test file during the task. Otherwise it is quarantined. The agent does not get to classify a flake.

The full mutation run stops after a configurable time limit and then samples. The default limit is about 10 minutes. That number is a project choice to confirm on the machine that will run the gate. It is not a measured recommendation.

**Stops and retries.** The tester may close a mutation gap once. After that, the developer fixes the gap inside the L5 submission budget. Exhaustion is a dossier.

**Result names.** `GREEN_PASS`, `GREEN_FAIL`, `MUTATION_GAP`.

**Visibility.** Holdouts run on the host. The developer sees the rule text in the failure report, not the holdout body.

## L8. Review

**Purpose.** Judge the diff against the brief and the quality rules, with a second model filtering weak findings.

**Who acts.** In parallel, an auditor and a design reviewer. Then a verifier. Light depth runs the auditor only. The verifier uses a different model from the reviewers when a third model exists. Reviewers use a different model from the developer when one exists. The fallback, when a second or third model is not available, is a different prompt and checklist. Model ids are recorded in the envelope.

A readability reviewer is not part of v1. A separate hacker role is not part of the pull-request chain. Security rules are part of the auditor’s view.

**Inputs.** Diff chunks, fenced as data. The brief. The per-role standard. The project’s `REVIEW.md` when it exists, which lists what not to flag. Gate results. There is no `REVIEW.md` in this repository today.

**Outputs.** Findings. A blocking finding names a file and a line, a rule id, and the behavioural effect. Blocking findings go back to the developer. Non-blocking findings, called yellow, are listed on the pull request for the owner.

**What must pass.** The auditor covers the families COR, TST, ERR, TYP-02, TYP-03, SEC, SCO, REL, and DOC: the diff against the brief, scope that grew past the brief, every brief rule cited from a test and a code line, a test made weaker without a rule, suppressions, equivalent mutants, and security judgment. The design reviewer covers DES and CMP. An instruction hidden inside the diff is a blocking finding. Reviewers never flag formatting, style, or naming.

Each reviewer call receives one slice of the syntax tree, enriched with neighbouring signatures and the brief. Slices run in parallel. The verifier merges them, drops duplicates, and drops a finding that repeats one already rejected in an earlier round. The auditor also makes one pass over a summary of the whole diff, so a problem that only shows up across files is not missed.

The target size of a slice is a configurable band of about 50 to 150 lines. That band is still to be checked. It is not a measured result, and this page does not treat it as one. Projects can set another band.

**Stops and retries.** At most three rounds, then a dossier. A blocking finding returns to the developer, then L6 and L7 run again, the tree hash is recorded again, and only the new diff is reviewed.

**Result names.** `REVIEW_PASS`, `REVIEW_BLOCK`.

**Visibility.** Until the verdict, the auditor does not see developer skills or the D1 log. The diff and the rest of the package are fenced as data.

## L9. QA

**Purpose.** Exercise the brief’s user-visible scenarios against a running local app, when the change has a user interface or an API and the depth is full.

**Who acts.** The QA agent. Light depth, trivial depth, and a diff that does not touch a UI or an API skip this link.

**Inputs.** Scenarios from the brief. The local app, running in its own rootless container. A Chrome DevTools connection. The QA skills.

**Outputs.** Playwright end-to-end tests for the brief’s scenarios. Screenshots and the console log. Visual diffs, shown in the envelope and not blocking.

**What must pass.** The container follows the hardening in [Security](security.md#rootless). The Chromium sandbox stays on. The only network is the local app. Each pull request runs the affected features and a smoke pass. A full run happens daily and before a release. Claims are checked against the end-to-end run, the screenshots, or the console log. Data is synthetic. External services are stubbed.

**Stops and retries.** A bug goes to the tester first, then the developer, then L6, L7, a diff-only re-review, and QA again. That path may happen twice. The third failure is a dossier.

**Result names.** `QA_PASS`, `QA_FAIL`, `QA_SKIP`.

**Visibility.** Network only to the local app. No secrets. No production data.

## L9b. Rollback rehearsal

**Purpose.** Show that the change can be undone, or make the owner accept that it cannot.

**Who acts.** A host script. The owner, when the change cannot be rehearsed.

**Inputs.** The diff after L9, or after `QA_SKIP`. The brief. The previous tag and the existing tests.

**Outputs.** An envelope field `rollback_mode`, and the rehearsal evidence. The mode is one of: plain code, feature flag, migration, API change, or irreversible.

**What the script does.** It classifies the diff.

| Mode | Rehearsal |
|---|---|
| Plain code | None. The result is a skip |
| Feature flag | Old tests and a smoke pass with the flag off |
| Migration | Apply, roll back, run the old tests, apply again |
| API change | The previous version runs against the new data, with a smoke pass |
| Irreversible | The owner must acknowledge it. The question waits |

**Stops and retries.** A failed rehearsal returns to the developer and spends one L5 submission. An unanswered irreversible question waits indefinitely.

**Result names.** `ROLLBACK_PASS`, `ROLLBACK_FAIL`, `WAITING_IRREVERSIBLE_D2`, `ROLLBACK_SKIP`.

## L10. Pull request

**Purpose.** Open a pull request whose evidence matches the tree that passed the gates, and leave the merge to the owner.

**Who acts.** A host script. The bot account opens the pull request. The owner merges and, later, releases. The developer is involved again only when a rebase conflicts.

**Inputs.** The gates that passed, including the rollback rehearsal. The holdouts. The envelope inputs: the brief, the gate results, the metrics, the tree hash, and the rollback mode.

**Outputs.** A branch push and a pull request opened by `isiarheiridak-agent`. An envelope bound to the tree hash. Holdouts converted into ordinary tests by a script, in a separate commit from the implementation. Process-file changes go out as their own pull request, labelled `process-files`.

**What must pass.** CI runs the script gates again. Mutation on CI reports the trend and does not repeat the full blocking run. CI blocks when the tree of `HEAD` is not the recorded tree hash. The envelope contains the brief and fails closed when D0, D1, D2, or the out-of-scope line is missing. It also contains gate results, the count of old tests changed, the mutation trend, every warning, suppressions, QA media when QA ran, the rollback mode and the rehearsal evidence, tokens, time, budget remaining, and model ids.

Commits are cut per link. The owner squash-merges. The script rebases. A conflict goes to the developer, then L6 and L7 run again and the envelope is bound to the new tree. The split, if there was one, was decided at L2. This link only opens the part that is next.

The envelope may recommend a red-team pass when the diff touches authentication, payments, or user data. That stage is not part of the v1 build. It is described in [Status](status.md#left-out-of-v1).

The human-size band used when judging whether a pull request is large is the same configurable default as the L2 split threshold: about 200 to 400 lines, generated files and lockfiles excluded, still to be checked per project.

**Stops and retries.** A rebase conflict returns through the developer and through L6 and L7. A tree-hash mismatch sends the task back through the gates.

**Result names.** `PR_OPEN`, `REBASE_CONFLICT`, `TREE_HASH_MISMATCH`.

**Visibility.** The envelope is the page the owner reads. The design expects the owner to be able to merge from that page.

Release is a separate owner action after the merge, documented in [Human decisions](decisions.md#release).

## L11. After the merge

**Purpose.** Keep the record, drop the working journal, and offer a retrospective without starting one.

**Who acts.** A host script.

**Inputs.** The merged task, the logs, the metrics, and any abort dossiers.

**Outputs.** A task log and metrics as self-describing JSONL. Discoveries that the script filter accepted. A retrospective offer when the counter hits, still never run automatically. The task journal, deleted immediately after the owner’s merge.

**What must pass.** Discoveries are accepted only by the script filter described in [Discoveries and ADRs](discoveries.md). A candidate that fails the filter is discarded. There is no queue of rejected proposals. Abort-cause entries are written by the dossier script.

**Stops and retries.** None. This is the last link.

**Result names.** `FINALIZED`, `RETRO_OFFERED` when the counter hit. A retrospective agent is not part of v1. The counter only offers.

## Retry limits

| Loop | Limit | What happens at the limit |
|---|---|---|
| D2 question, new dependency, irreversible change, suspicious skill | No timeout | The task waits |
| Wrong brief | Stop until version 2 is approved | Dossier if the cycle is aborted |
| Critic back to architect | 2 returns | Dossier |
| Signature change | 1 return to L2 | The second request is a dossier |
| Red gate back to tester | 2 returns | Dossier |
| Developer submissions | 3, plus the budget warning | Dossier. The same failure twice stops early |
| Missing dependency during coding | Pause | Does not spend a submission |
| Tester closing a mutation gap | 1 return | Then the developer, inside the submission budget, else a dossier |
| Review rounds | 3 | Dossier |
| QA bug path | 2 | Dossier |
| Rollback rehearsal failure | Spends one coding submission | Inside the L5 budget |
| Token limit on the context package | Split into iterations | No dossier |

## Related

[Architecture](architecture.md) · [Human decisions](decisions.md) · [Quality standard](quality.md) · [Implementation status](status.md)
