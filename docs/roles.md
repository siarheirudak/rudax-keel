# Roles and visibility

A **role** is one job in the pipeline: orchestrator, architect, critic, tester, developer, auditor, design reviewer, verifier, QA, or researcher. The owner and the bot are not agent roles. The owner decides. The bot account opens pull requests.

**Status.** Folder mounts are enforced by `setup/keel.sh role` and `role-env`. An unknown role name is refused. The gate suite’s work-tree container is `proto`, not a role. Content fencing is not in this step.

## Folder allowlist and unified deny

A role sees the folder roots in `setup/allow/<role>.paths`, and nothing else. The unified deny then removes paths from those roots. A path on both lists is withheld. Enforcement is the mount: the path is not readable and not writable. The role is not asked to look away.

| Role | Folder roots | Write |
|---|---|---|
| orchestrator | `briefs/`, `docs/`, `tests/`, `.keel/decisions/<task-id>/` | `briefs/`, `.keel/decisions/<task-id>/` |
| architect | `briefs/`, `docs/`, `.keel/decisions/<task-id>/` | none in this step (decisions are read-only) |
| developer | `src/`, `docs/`, `tests/` | `src/`, `docs/`. `tests/` is read-only |
| tester | `src/`, `docs/`, `tests/` from the commit recorded at setup | `tests/` in that snapshot only |
| auditor | `src/`, `docs/` | none |
| skills_auditor | `skills-draft/`, `skill-review/` | none |
| critic | `plans/` | none |
| design_reviewer | `docs/` | none |
| verifier | `findings/` | none |
| qa | `qa-stub/` | none |
| researcher | `research-stub/` | none |

`setup/deny/base` always withholds secret basenames (`.env` and the other names in that file), `.keel/logs/`, `.keel/runs/`, `.keel/deny.local`, and `.git`. `.keel/decisions/` is withheld from every role except the orchestrator and the architect. `.agents/` is withheld from every role except the skills auditor. `.keel/deny.local` may add paths. A line that tries to remove a base entry refuses the launch. The file is read once per task. Roles cannot edit it.

D1 confidence notes and the handoff for a task live at `.keel/decisions/<task-id>/` in the product git tree (`d1.md`, `handoff.md`). The orchestrator can write them. The architect can read them. The developer, the tester, and the auditor cannot. A public product repository publishes those files. The harness prints that warning once. This repository does not commit task decisions.

Launch decisions are JSONL at `$KEEL_ROOT/.keel/logs/launch.jsonl`. Only the harness writes that file. Each record includes `redactions`. Replacements are `[REDACTED:token]`, `[REDACTED:key]`, `[REDACTED:password]`, `[REDACTED:env]`, or `[REDACTED:unknown]`. `.keel/runs/` is temporary and is removed when the command exits. Both directories are gitignored.

Changing a role’s folders, the deny base, or who can see decisions is a `process-files` pull request, then review, then an owner merge.

A secret whose basename is not in the deny base is still visible. A secret-named file created inside a read-write mount during that same command can be read until the command ends. There is no size cap on the launch log. Content fencing is still backlog.

### Orchestrator read and write

The orchestrator and the host dispatcher are planned for Step 7. They are not built yet. The mount row above is what `role orchestrator` does now.

- **Read:** the folders in the table, except paths the unified deny withholds.
- **Write zone only, in this step:** `briefs/` and `.keel/decisions/<task-id>/`.
- **Must not write:** product code, tests, process files, or gates.
- **Must not** launch containers or talk to other agents directly. The host launches roles via `setup/keel.sh role`.

Product tests live in `tests/` today. The developer can read that directory and cannot write it. [tests/README.md](../tests/README.md).

## Network

The design puts an allowlist proxy in front of outbound traffic. A destination not on the list is refused, and the refusal is logged.

| Role | Network in the v1 design |
|---|---|
| Developer | No network, except the model API through the proxy |
| Researcher | Internet, for published sources. No code and no tokens in that container |
| Critic | No network |
| QA | The local app only |
| Other roles | The same allowlist proxy. The design does not give them a separate destination list |

The harness today passes `--network none` to every container, including setup, export, and the test re-run. There is no proxy, so there is also no path to a model API. That is stricter than the developer row above, and it is why the current harness cannot host Pi Agent. The proxy is specified in [Status](status.md) and is not built.

## Skills each role receives

A **skill** is a project file of instructions for a role, under `.agents/skills/`. Creating, changing, or deleting one requires the owner’s approval. [Human decisions](decisions.md).

The developer, the tester, QA, and the architect receive project skills. The orchestrator can be asked, in chat, to order a skill. Usage is written to the log. A comparison trial of two versions is reserved for a major stack skill. How that trial would be measured is still open.

Harness checklists for the critic and the reviewers are not project skills. They are generated from `standards/rules.md` and mounted read-only. They do not go through the project skill-approval card. The standard itself is specified in [Quality standard](quality.md) and the file is not in the repository yet.

A suspicious skill is one that contains install commands, network use, secret access, or a way around a gate. The scan highlights those lines on a card, and the skill stays off until the owner says yes.

## The owner and the bot

The owner is not a container role. The owner reads the envelope, answers D2 questions, and merges. The owner may work through an external chat **intermediary** or a direct Pi Agent terminal; both hit the same orchestrator input. [Working through a chat agent](working-through-chat.md).

The bot is not a container role either. It is the GitHub **bot account** that opens the pull request at L10. In the design, a GitHub token exists only in that push step. The prototype’s push command is `setup/keel.sh push-stub`. It prints the command and does not push. The doctor fails if `GH_*`, `GITHUB_*`, or `BOT_GH_TOKEN` is set in the environment it runs from. [Security](security.md#tokens).

## Related

[Security](security.md) · [Pipeline](pipeline.md) · [Quality standard](quality.md) · [Architecture](architecture.md) · [Working through a chat agent](working-through-chat.md)
