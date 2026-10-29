# Roles and visibility

A **role** is one job in the pipeline: orchestrator, architect, critic, tester, developer, auditor, design reviewer, verifier, QA, or researcher. The owner and the bot are not agent roles. The owner decides. The bot opens pull requests.

**Status.** The deny-list on this page is the v1 design. The harness that exists today starts every role with the same mounts. It does not hide holdouts, it does not hide a new implementation from the tester, and it does not fence file contents as data. `setup/keel.sh role` accepts any role name and runs a shell command. The happy-path test uses the names `coder` and `tester`. Those names are not the v1 role set, and in that test the tester can read the file the coder just wrote.

## The deny-list

Visibility is a deny-list. A role may read the repository except the paths the list names. Enforcement is physical: the path is not mounted into that role’s container. The role is not asked to look away.

Two sources fill the list:

- Paths the harness always denies. A project cannot remove these.
- A per-project file, `.keel/deny.local`, which may add more denies. It cannot grant a path the harness denied.

Secrets are denied to every role. A **secret** is a credential, a token, or any value that would let a role act as the owner or reach a system the task did not approve.

Everything else on the list is denied to specific roles, below.

The same rule covers packaged text. Repo files, ADRs, discoveries, and skills are wrapped so the model has to treat them as data. That wrapping is called a **fence**. A sentence inside a fenced file is not an instruction to the agent. Review diffs are fenced the same way. An instruction planted in a diff is a blocking review finding. Fencing is specified and not implemented. The current containers receive ordinary files.

## Who is denied what

| Withheld | Denied to | Why |
|---|---|---|
| Secrets | Every role | A role must not be able to act as the owner or call an unapproved system |
| `.keel/holdout/` | The developer. The architect and the critic are also specified as not receiving holdouts | The developer must not tune the implementation to tests that exist to catch a dishonest one. Holdouts are stored on the host |
| The new implementation | The tester | The tester writes tests against stubs, on the commit from before the implementation. That tree is what gets mounted |
| Developer skills, and the D1 log | The auditor, until the auditor’s verdict | The auditor judges the diff against the brief and the rules, without the implementer’s private notes or the confidence log |
| Code and tokens | The researcher | The researcher looks up public sources for a skill and does not need the repository |

Other roles see the repository minus secrets, minus any extra paths in `.keel/deny.local`. The auditor sees the diff under review. The developer sees tests and sees a compressed failure when a holdout fails: the rule text, not the holdout source.

Product tests that are not holdouts live in `tests/` today. Nothing in the current CI hides that directory by role. [tests/README.md](../tests/README.md).

## Network

The design puts an allowlist proxy in front of outbound traffic. A destination not on the list is refused, and the refusal is logged.

| Role | Network in the v1 design |
|---|---|
| Developer | No network, except the model API through the proxy |
| Researcher | Internet, for published sources. No code and no tokens in that container |
| Critic | No network |
| QA | The local app only |
| Other roles | The planning notes do not give them a separate destination list. They go through the same allowlist proxy |

The harness today passes `--network none` to every container, including setup, export, and the test re-run. There is no proxy, so there is also no path to a model API. That is stricter than the developer row above, and it is why the current harness cannot host Pi Agent. The proxy is specified in [Status](status.md) and is not built.

## Skills each role receives

A **skill** is a project file of instructions for a role, under `.agents/skills/`. Creating, changing, or deleting one requires the owner’s approval. [Human decisions](decisions.md).

The developer, the tester, QA, and the architect receive project skills. The orchestrator can be asked, in chat, to order a skill. Usage is written to the log. A comparison trial of two versions is reserved for a major stack skill. How that trial would be measured is still open.

Harness checklists for the critic and the reviewers are not project skills. They are generated from `standards/rules.md` and mounted read-only. They do not go through the project skill-approval card. The standard itself is specified in [Quality standard](quality.md) and the file is not in the repository yet.

A suspicious skill is one that contains install commands, network use, secret access, or a way around a gate. The scan highlights those lines on a card, and the skill stays off until the owner says yes.

## The owner and the bot

The owner is not a container role. The owner reads the envelope, answers D2 questions, and merges.

The bot is not a container role either. It is the GitHub account that opens the pull request at L10. In the design, a GitHub token exists only in that push step. The prototype’s push command is `setup/keel.sh push-stub`. It prints the command and does not push. The doctor fails if `GH_*`, `GITHUB_*`, or `BOT_GH_TOKEN` is set in the environment it runs from. [Security](security.md#tokens).

## Related

[Security](security.md) · [Pipeline](pipeline.md) · [Quality standard](quality.md)
