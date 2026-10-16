# GitHub setup

This is the foundation. Everything else in the template relies on it.

## Two accounts

| Name | Who | Role in the repo |
|---|---|---|
| **Owner GitHub account** | You, the human | Admin, code owner |
| **Agent GitHub account** | The account AI agents act through | Write (not admin) |

Each account has one name and one job, so it's always clear who did what.

## Process 1: the agent's pull request (the everyday flow)

![Agent pull request flow](diagrams/step1-agent.png)

The agent can only do one thing: **open a pull request**. Then:

1. GitHub requires **one approving review from a code owner** (you).
2. After you approve, **you** merge it into `main`.

Everything else is blocked:

| Blocked action | Why |
|---|---|
| Direct push to `main` | Every change must pass through a PR you can see and review. |
| Approve or merge its own PR | An agent checking its own work isn't a check. Only a human decides. |
| Force push or delete `main` | History must stay intact, so nothing can be hidden or lost. |
| Turn off the rules | The agent has **write**, not **admin**. Only admins can change rules, so the agent can't free itself. |

**Why it works:** the rules are enforced by GitHub itself, not by the agent's good behaviour. Even a buggy or misled agent can't put code into `main` without you.

## Process 2: the owner's own pull request

![Owner pull request flow](diagrams/step1-owner.png)

Sometimes you change things yourself, for example the `CODEOWNERS` file. GitHub doesn't let anyone approve their own PR, so the review rule would block you forever. That's why there's a **bypass**:

1. You open a PR, as usual.
2. You merge it through the bypass. The bypass is for the **admin role, pull requests only**.
3. Every bypass is **logged** (Rule Insights), so you can always see when it was used.

### Why you can't push directly to `main`, even as owner

The bypass is set to **"pull requests only"**, not "always". So you still have to go through a PR. That gives you:

- **A record of every change.** Each change to `main` has a PR showing what changed and why, even your own.
- **Checks still run.** Automated checks run on the PR before merge, catching mistakes before they land.
- **Protection if your account is misused.** A stolen session or a tool acting as you can't silently push to `main`. It would have to open a visible PR.
- **One way in.** Everything, from the agent or from you, enters `main` the same way. That's simple to understand and to audit.

## What the script configures

Do this as the **owner GitHub account** (admin on the repo). Never use the agent GitHub account's token. Commands: [setup/README.md](../setup/README.md). Reasons: [why.md](why.md).

There is no config file. Apply asks GitHub who is logged in (`gh api user`). That login is the owner GitHub account. It also reads whether the repository is public or private, and the plan.

From the repository root:

```bash
bash setup/apply-github-rules.sh OWNER/REPO AGENT_LOGIN
bash setup/verify-github-rules.sh OWNER/REPO AGENT_LOGIN
```

Apply is idempotent. Run it again after each layer is merged. A setting that already matches is left untouched.

| Step | What it sets |
|---|---|
| `protect-main` | Default branch: no deletion, no force push, pull request required, 1 approval, code-owner review, dismiss stale reviews. Admin bypass for pull requests only. |
| `protect-tags` | All tags: block creation, update, and deletion. Admin bypass only. |
| `require-checks` | Required check `checks / gate` on the default branch, strict, no bypass. Created only when `.github/workflows/checks.yml` is already on the default branch. |
| Agent access | Invite `AGENT_LOGIN` with write. Does not remove admin if you already granted it. |
| `CODEOWNERS` | If missing, write `* @<login>` for the logged-in owner GitHub account. If the file already lists that login, leave it. If it lists someone else, stop and do not overwrite it. |
| Actions token | Default `GITHUB_TOKEN` is read-only and cannot approve pull requests. |
| Fork approval | On a public repository, require approval for fork pull request workflows from all outside collaborators. |
| Allowed actions | GitHub-owned actions, plus the exact `uses:` values in workflows on the default branch. |

The agent GitHub account must accept the collaborator invitation before verify's agent-role step can pass.

<a id="how-rulesets-stack"></a>

## How rulesets stack

The script keeps more than one ruleset. GitHub applies every active ruleset that matches a ref. A bypass applies only inside its own ruleset.

- The admin bypass on `protect-main` lets you merge a pull request without a second review. It does not let you force-push, and it does not apply to tags.
- `protect-tags` has its own admin bypass. The pull-request bypass mode is not valid for tags, so this one is "always", and only the admin role is on the list. The agent GitHub account has write, not admin, so it cannot create, move, or delete a tag.
- `require-checks` has an empty bypass list. An admin cannot skip `checks / gate`. Merging through the `protect-main` bypass still waits for that check once the check exists.

JSON for the three rulesets lives in [setup/rulesets](../setup/rulesets).
