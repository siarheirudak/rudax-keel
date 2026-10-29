# Roles and visibility

A **role** is one job in the pipeline: orchestrator, architect, critic, tester, developer, auditor, design reviewer, verifier, QA, or researcher. The owner and the bot are not agent roles. The owner decides. The bot account opens pull requests.

**Status.** The deny-list on this page is the v1 design. The harness that exists today starts every role with the same mounts. It does not yet enforce per-role deny mounts, it does not hide a new implementation from the tester, and it does not fence file contents as data. `setup/keel.sh role` accepts any role name and runs a shell command. The happy-path test uses the names `coder` and `tester`. Those names are not the v1 role set, and in that test the tester can read the file the coder just wrote.

## The deny-list

Visibility is a deny-list. A role may read the repository except the paths the list names. Enforcement is physical: the path is not mounted into that role’s container. The role is not asked to look away.

Two sources fill the list:

- Paths the harness always denies. A project cannot remove these.
- A per-project file, `.keel/deny.local`, which may add more denies. It cannot grant a path the harness denied. In Step 1 of the implementation plan this file is a **flat** list of paths (no per-role prefixes yet).

Secrets are denied to every role. A **secret** is a credential, a token, or any value that would let a role act as the owner or reach a system the task did not approve.

Everything else on the list is denied to specific roles, below.

Packaged text (repo files, ADRs, discoveries, skills, review diffs) is intended to be wrapped so the model treats it as data. That wrapping is called a **fence**. A sentence inside a fenced file is not an instruction to the agent. An instruction planted in a diff is a blocking review finding. **Content fencing (M5) is specified but deferred to the backlog**; it is not part of the first visibility step. The current containers receive ordinary files.

## Who is denied what

| Withheld | Denied to | Why |
|---|---|---|
| Secrets | Every role, including the orchestrator | A role must not be able to act as the owner or call an unapproved system |
| Paths in `.keel/deny.local` | Every role, including the orchestrator | Project extras such as user or customer data. Flat list; may only add denies |
| D1 confidence-notes log | The auditor until the auditor’s verdict | The brief carries the D1 confidence level. The detailed notes live in a log the **orchestrator writes and may read**. Hidden from the auditor until verdict. Not an owner-decision store. Exact path still open |
| The new implementation | The tester | The tester writes tests against stubs, on the commit from before the implementation. That tree is what gets mounted. Product tree mounts are **read-only**; writes only into allowed test directories (host `git diff --name-only` as defense in depth) |
| Developer skills | The auditor, until the auditor’s verdict | The auditor judges the diff against the brief and the rules, without the implementer’s private notes |
| Code and tokens | The researcher | The researcher looks up public sources for a skill and does not need the repository |

Ordinary tests are visible to every role with a work tree. Tester-written tests mount **read-only** for the developer. On gate FAIL the developer gets the **full** output and stacks. Honesty substitute for fitting code to tests: L7T mutation plus the L8 checklist item `Code hardcoded to specific test values instead of implementing the behavior` (see [Harness design](harness/README.md)).

Other roles see the repository minus secrets, minus any extra paths in `.keel/deny.local`. The auditor sees the diff under review.

### Orchestrator read and write (planned, Step 7)

The orchestrator and the host dispatcher are planned for Step 7. They are not built yet. In that design, the orchestrator is the main Pi Agent role in its own container.

- **Read:** everything except secrets and paths in `.keel/deny.local`. The D1 confidence-notes log is readable.
- **Write zone only:** the brief; the split plan; dispatcher **request files**; the D1 confidence-notes log; owner decisions into ADR / `docs/decisions.md` and discoveries (via allowed paths); messages to the owner.
- **Must not write:** product code, tests, process files, or gates.
- **Must not** launch containers or talk to other agents directly. It drops request files; the host **dispatcher** owns transitions and launches roles via `setup/keel.sh role`.

Product tests live in `tests/` today. Nothing in the current CI hides that directory by role. [tests/README.md](../tests/README.md).

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
