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

## How to set it up

Do this as the **owner** account (admin on the repo). Never use the agent's token. Commands and log files: [setup/README.md](../setup/README.md).

### Automatic

From the repository root:

```bash
bash setup/setup.sh OWNER/REPO AGENT_LOGIN
bash setup/verify.sh OWNER/REPO AGENT_LOGIN
```

`setup.sh` creates or updates the [`protect-main` ruleset](../setup/rulesets/protect-main.json) and invites `AGENT_LOGIN` with write. Running it again skips what already matches. It does not create `CODEOWNERS`. `verify.sh` only reads the repo and exits non-zero on a mismatch.

The agent must accept the collaborator invitation before `verify.sh` can pass.

### Manually

Same outcome as `protect-main.json`.

1. Open **Settings → Rules → Rulesets → New branch ruleset**.
2. **Ruleset Name:** `protect-main`.
3. **Enforcement status:** Active.
4. **Bypass list:** add **Repository admin**, and set the bypass to **For pull requests only**.
5. **Target branches:** Include default branch (`~DEFAULT_BRANCH`).
6. Turn on only these rules:
   - **Restrict deletions**
   - **Block force pushes**
   - **Require a pull request before merging**, with **1** required approval, **Require review from Code Owners**, and **Dismiss stale pull request approvals when new commits are pushed**. Leave "Require approval of the most recent reviewable push" and "Require conversation resolution" off.
7. Create the ruleset.
8. **Settings → Collaborators:** invite the agent account with the **Write** role. Do not grant Admin. The agent must accept.
9. Add `.github/CODEOWNERS` containing `* @OWNER` in a pull request from the owner account, and merge that pull request with the admin bypass (pull requests only). The bypass is logged in Rule Insights.

`OWNER` is the owner GitHub login.
