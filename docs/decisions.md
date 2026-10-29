# Human decisions

The pipeline pauses for a person in a fixed set of places. Everywhere else, a script or an agent continues, or a dossier stops the cycle. The person is the **owner**: the repository owner.

The bot account opens pull requests. It does not approve them, it does not merge them, and it does not create release tags. Tag protection is enforced by GitHub today. [Protect tags](why.md#protect-tags). On a personal repository GitHub cannot restrict the merge button to one account. The project rule is still that the owner merges. An approval goes stale if new commits are pushed. [Who merges](why.md#who-merges).

**Status.** The decisions below are the v1 design. The GitHub half (who may merge, who may tag, who may change rules) is implemented. The brief, the D2 cards, the skill card, and the envelope are not built.

Owner decisions travel through chat (external intermediary or direct Pi Agent terminal) into the same orchestrator input. There is no extra confirmation layer on top of D2. Answers are logged verbatim with a timestamp and appear in the PR envelope. [Working through a chat agent](working-through-chat.md). Owner decisions that belong in product memory go into ADR / this decisions file and discoveries — not a third decision log.

## The brief

L0 produces a **brief** the owner accepts. It has five parts.

| Part | What it is |
|---|---|
| Task understanding | What the orchestrator thinks the owner asked for |
| D0 | A paragraph in the brief. The design requires the section and does not set a longer template, so this page does not add fields to it. The owner accepts the paragraph by approving the brief |
| D1 | The orchestrator’s confidence: high, medium, or low. **Not an owner decision.** Low confidence always raises a D2 question. The orchestrator writes the D1 confidence-notes log. That log stays hidden from the auditor until the auditor has given a verdict |
| D2 | Questions for the owner. Each one has options and a default |
| Out of scope | One line naming what this task will not do |

A wrong brief stops the cycle. The next version is shown as a diff. Work continues only after the owner approves that diff.

Later, the script that builds the envelope refuses to open a pull request if D0, D1, D2, or the out-of-scope line is missing. An empty section is a stop, not a blank the owner is expected to overlook.

## Questions that wait

A **D2 question** is a decision the owner has to make before the task can move. It does not time out. The task stays in a waiting result until the owner answers.

The grilling step raises one for a fixed list of topics, even when D1 is high:

- User-visible wording or layout
- Data or a migration
- Money
- Security or access
- A new dependency
- A public API change
- A departure from the product docs
- A change that cannot be undone

The same wait is used in three other places:

| When | What the card shows |
|---|---|
| A new dependency, after the architect names one | Package, version, license, and reason |
| Rollback cannot be rehearsed | An irreversible-change acknowledgement |
| A skill looks suspicious | The skill text with the offending lines highlighted: install commands, network, secrets, or a way around a gate |

A suspicious skill is not turned on because the rest of the skill was approved. It needs its own yes.

At grilling, and again after the architect’s estimate, the owner is shown the size and the estimated cost and may raise the depth, for example from light to full. The script may also force full depth when the diff is larger than the architect claimed. [Architecture](architecture.md#depth).

## Approvals

**Skill approval.** Every create, change, or delete of a project skill waits on a card. The owner accepts with “yes to all” or rejects the skill. The card shows the size. There is no maximum length in the design. Rejected skills do not merge. Approved skills arrive only as a process-files pull request opened by the bot.

**Split approval.** If the architect’s estimate is over the project’s split threshold, the owner decides immediately, before dependencies and tests. Yes means the parts run one after another, each from grilling. No stops the parts that have not started. The threshold is a configurable default. [Architecture](architecture.md#split).

**Process files.** Changes to the rules of the repository (workflows, setup scripts, agent instruction files, and the other paths listed in [Scope](why.md#scope)) travel in their own pull request. The label in the design is `process-files`. The check that a process-file pull request contains nothing else is implemented today (`keel-process-files-separate`). The pipeline that opens that pull request after a skill approval is not.

## Merge

The owner merges. The design’s merge is a squash: the link-by-link commits become one commit on the default branch.

The owner is meant to merge from the envelope, without reading the code. The envelope is ready only when it can show all of the following.

1. The change is what the brief asked for.
2. It works, including tests the developer never saw.
3. The red gate saw an honest failure on the stubs, not an import or build error.
4. Existing tests still pass.
5. The auditor’s rules, including security, passed.
6. Rollback was rehearsed, or the change is plain code and the rehearsal was skipped, or the owner accepted an irreversible change.
7. D0, D1, D2, and the out-of-scope line are present.
8. The static gate left no blocking complexity or duplication problem. Warnings are listed in the envelope.
9. The envelope is bound to the tree hash of the files that passed the gates. CI blocks a merge when the branch’s tree is different.

Yellow review findings are listed and do not block. They are for the owner to read.

After the merge, the script deletes the task journal for that task.

The bot does not merge. The owner does not merge a pull request whose required checks are red. The admin bypass on branch protection does not skip the required checks.

## Release

<a id="release"></a>

Merge puts the change on the default branch, which the design treats as staging. Production is a second act.

The owner releases by creating a tag or by running the release workflow with `workflow_dispatch`. The bot cannot create, move, or delete tags. That block is the `protect-tags` ruleset, and it is implemented.

Before a release, the design asks for the pre-release list and a full end-to-end run. Rolling a release back means deploying the previous tag again, by hand, using the envelope’s rollback mode as the guide. Feature flags are optional. The architect opts in. The design does not yet choose whether a new project starts with flags off until that opt-in, or with a project-level default.

## Related

[Pipeline](pipeline.md#l0-grilling) · [Security](security.md) · [Logging and the task journal](logging.md)
