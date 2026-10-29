# Implementation status

This page is the line between what the repository does and what the v1 design specifies. When another page describes a link, a role mount, or a log, the behaviour is planned unless this page lists it under [Shipped](#shipped).

Nothing in the L0–L11 chain runs. There is no Pi Agent integration, no `standards/rules.md`, no `.keel/` directory, no `.agents/skills/` directory, and no envelope. The bot is a real GitHub account used with the rules below. The pipeline’s “bot opens the pull request” step is still the push stub.

## Shipped

### GitHub protection

Implemented in `setup/apply-github-rules.sh`, `setup/verify-github-rules.sh`, and `setup/rulesets/`.

- Two accounts. The owner is an admin and the code owner. The bot is invited with write, not admin.
- The default branch cannot be deleted, force-pushed, or updated except through a pull request. One code-owner approval is required. Stale approvals are dismissed. The owner can merge a pull request without a second reviewer. That bypass does not allow a direct push.
- Tags are blocked for everyone except an admin. The bot cannot create, move, or delete a release tag.
- Required check-run names are `keel-gate` and `keel-process-files-separate`, from GitHub Actions, on a branch that is up to date with the default branch. Apply waits until both workflows are on the default branch and each name has been reported.
- The default Actions token is read-only and cannot approve pull requests.
- On a public repository, fork workflows wait for approval.
- Actions are limited to GitHub-owned actions plus the exact pinned `uses:` values already on the default branch.

How to apply them: [GitHub setup](github-setup.md). Why each rule exists: [why.md](why.md).

### CI checks

Implemented in `.github/workflows/checks.yml`, `.github/workflows/scope.yml`, and `scripts/`.

- `keel-gate` fails if any other job in the checks workflow failed, was cancelled, or was skipped. The workflow also runs when a pull request is edited, so a base change runs the gate again.
- This repository’s own project checks belong in `project_checks()` inside `scripts/check.sh`. Until some are added, that function prints `no project checks yet` and passes. `bash scripts/check.sh` runs the same checks locally.
- `scope` fails when a pull request mixes process files with other files, and when the base is not the default branch. The job does not check out the pull request. Its token can only read.

### Isolation harness

Implemented in `setup/keel.sh`, `setup/keel-doctor.sh`, and `setup/tests/harness/`.

The harness builds a throwaway repo, runs a shell command in a hardened container, exports a git bundle, and checks the bundle on the host. The host check has no GitHub token. `push-stub` prints a push command and does not push.

Containers start with no network, all capabilities dropped, `no-new-privileges`, a read-only root filesystem, a tmpfs on `/tmp`, and limits on processes, memory, and CPU. They run as the invoking user’s uid and gid.

The host gate rejects a bundle that:

- is missing, too big, or not based on the current default branch
- contains anything other than the single task branch, a merge commit, or a root commit
- touches a forbidden process path, a symlink, a submodule, or a nested `.git`
- carries a commit identity other than the configured agent identity
- fails the test entry taken from the default branch, not from the files in the bundle

The doctor’s levels, and the fact that rootless is still a warning, are in [Security](security.md). How to run it: [Getting started](harness-getting-started.md).

The path checks in this gate are the behaviour the design wants L4, L6, L7, and L10 to share. They live inside `setup/keel.sh` today. They are not a library those links call, because those links do not exist.

## Specified and not built

The v1 build is a sequence of steps. Each one is intended to land as its own pull request, opened by the bot, and merged by the owner. Process-file and skill changes land as separate pull requests labelled `process-files`, after the owner approves them. None of the steps below have been started in this repository. The Step 7 design (dispatcher and warm orchestrator) is in [Harness design](harness/README.md).

The order is the dependency order from the v1 plan. Steps later in the list need earlier ones. Parallel reading is fine. Parallel merging still has to respect the dependencies.

| Step | What it adds | Depends on |
|---|---|---|
| 1 | Deny-list mounts. Ordinary tests stay visible; the developer mounts them read-only. Flat `.keel/deny.local`. Content fencing stays on the backlog | The harness that exists |
| 2 | An egress allowlist proxy | Step 1 |
| 3 | Rootless as a hard startup failure, plus the rest of the v1 container limits, including a work-directory quota and a separate user for secrets. Playwright checked on the host. Chromium’s sandbox left on | Steps 1 and 2 |
| 4 | L1 context packaging | Step 1 |
| 5 | The discoveries store and the accept-or-discard filter | Step 4 |
| 6 | `standards/rules.md` and the generator for per-role views | The rule text, which is an input, not code in this repo |
| 7 | The host dispatcher and the warm Pi orchestrator (task state, transitions, `keel_request`). A process-files pull request. Grilling behaviour is Step 8 | Step 1, and Step 2 when the orchestrator container needs the model API |
| 8 | L0 grilling, including size and estimated cost | Steps 4 and 7 |
| 9 | Stack detection, the skill directory, and the suspicious-skill card | Steps 5, 6, and 8 |
| 10 | Research, critic, owner approval, and the process-files pull request for a skill | Steps 2 and 9, and a real push (step 19) or an explicitly narrower push path |
| 11 | L2 architect, critic, syntax-tree checks, and the split decision | Steps 4, 6, 7, and 8 |
| 12 | Dependency resolve and an ephemeral install container, before tests | Steps 2, 7, and 11 |
| 13 | L3 tester write-scope (product read-only; test directories writable) | Steps 1, 7, 11, and 12 |
| 14 | L4 red gate, including honest-versus-import failure classes | Step 13 |
| 15 | L5 developer loop and the attempt accounting | Steps 5, 7, 12, and 14 |
| 16 | L6 static gate, warnings on the envelope, the shared path library, and leftover debug and temp files | Step 15 |
| 17 | L7 green gate, mutation testing (L7T), and the recorded tree hash | Steps 14 and 16 |
| 18 | L8 review, the verifier, and diff slicing | Steps 6, 16, and 17 |
| 19 | A real push, the L10 envelope, and CI that blocks a tree-hash mismatch | Steps 17 and 18, and the existing push stub |
| 20 | L9 QA and L9b rollback rehearsal | Steps 3, 13, and 19 |
| 21 | The task journal, appended after each link and deleted on merge | Step 8, plus the hooks in steps 15 through 20 |
| 22 | The self-describing JSONL log, with a glossary header and a scrub check | Step 21 |
| 23 | The release path and L11: metrics, the retrospective offer, journal deletion wired to the merge | Steps 19 through 22 |

Tracks that can be read side by side: isolation (steps 1–3), context and the standard (steps 4–6), the dispatcher, orchestration, and skills (steps 7–10), the build loop (steps 11–17), review, the pull request, and QA (steps 18–20), journal and release (steps 21–23). The build loop needs isolation, context, and the dispatcher. Review needs the build loop and rootless hardening. Release needs the pull request, QA, the journal, and the log.

Moving the harness into this repository is already done. It is not a remaining step.

## Settings still open

<a id="settings-still-open"></a>

These are project settings. Where the design names a starting number, that number is a configurable default. It is not a result measured in this repository, and it is not cited here from an outside study.

| Setting | Starting default in the design | What is still open |
|---|---|---|
| Split threshold, and the similar size band for a pull request | About 200 to 400 lines of human-written code, generated files and lockfiles excluded | Check the band on real tasks before treating it as enforced. Per project |
| Review slice size | About 50 to 150 lines of one syntax-tree unit | Check the band. It is explicitly still to be verified |
| Trivial-depth line limit | Unset | Choose it after the first measured tasks. Until then the script has no numeric cutoff |
| Mutation time limit | About 10 minutes, then sampling | Confirm on the runner and the language. A project choice |
| Dependency quarantine | 7 days, with a bypass for a security fix | Confirm against how fresh the advisory feed needs to be |
| Complexity warn band | From 10 up to 30 | The project’s own choice, to calibrate on a real baseline. The block at 30 and above is the design’s block line |
| Budget cap | Warn only, until 5 to 10 tasks are measured. Then about twice the median, plus an iteration limit | When the warning becomes a hard stop |
| Second and third models | A different model for reviewers than for the developer, and a third for the verifier when one exists | Which pairs are available. One model falls back to a different prompt and checklist, recorded in the envelope |
| Feature flags | Optional, the architect opts in | Whether a new project starts with flags off, or with a project-level default |
| Skill pull requests before a real push | Unsettled | Whether step 10 waits for step 19 |
| Egress proxy shape | An allowlist | One shared proxy, or a profile per role, and how allowlist edits are reviewed |
| Skill A/B trials | Only for a major stack skill | How the split is measured |
| macOS | Untested | The doctor warns. It does not refuse. Wording beyond “untested” is still open |
| Red-team recommendation | The envelope may recommend a pass when authentication, payments, or user data change | Whether that is only a recommendation, or also an item the owner ticks |

## Left out of v1

<a id="left-out-of-v1"></a>

- **Red team.** A later stage on staging, started only by an explicit trigger, using the browser and API scripts against synthetic data. Not built. The envelope may recommend it. The kinds of problems the notes name are access control, injection, authentication, rate limits, and payment races.
- **A known-bad set of diffs** for evaluating review. Not built.
- **Follow-up research on code review.** Not part of the build.
- **An agent that writes the product requirements.** Not part of v1. L0 reads product docs. It does not author them.
- **A retrospective agent.** The L11 counter offers one every 3 to 5 tasks and does not run it.
- **A real-time UI** on top of the system log. After the log exists, and not in this build.
- **Product mutation tests** beyond wiring mutation into the green gate. The green gate itself is not built.
- **A hacker role on the pull-request path.** Not in v1. Security rules sit with the auditor.
- **A readability reviewer.** Not in v1. Reviewers do not flag formatting, style, or naming.
- **A hard limit on skill length.** The approval card shows the size. There is no maximum length.
- **A non-Pi pipeline runtime.** The v1 pipeline’s agent runtime is Pi Agent. The GitHub rules still apply to whatever program holds the bot token.
- **A pre-flight admission step.** A task starts at L0.

## Related

[Architecture](architecture.md) · [Security](security.md#rootless) · [Pipeline](pipeline.md) · [Harness design](harness/README.md)
