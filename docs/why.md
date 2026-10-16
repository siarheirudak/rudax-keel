# Why these rules exist

Each log line from the setup scripts links to a section below.

**Rule:** any new rule needs a section here, in this shape, before it is added to the scripts.

<a id="who-runs-this"></a>

## Who runs this

**Rule.** Only the owner GitHub account runs apply and verify. That account must be an admin on the repository. The agent GitHub account must not be the account logged in to `gh`.

**Why.** The script changes repository settings. The agent GitHub account has write, not admin, so it must not be able to change the rules that constrain it.

**If disabled.** Anyone with the agent token could point the script at the repo, or the script could no-op while you think the rules are on.

**How to disable explicitly.** There is nothing to turn off. Log in as the owner GitHub account with `gh auth login` before you run the scripts.

<a id="protect-main"></a>

## Protect main

**Rule.** On the default branch: no deletion, no force push, and changes only through a pull request. The pull request needs 1 approval, a review from a code owner, and stale approvals are dismissed.

**Why.** The agent GitHub account can open a pull request. It cannot put commits on the default branch by itself. You see every change before it lands.

**If disabled.** The agent GitHub account can `git push` straight to the default branch. A bad or confused agent can ship code with no review.

**How to disable explicitly.** Delete the `protect-main` ruleset in the repository rules settings, and delete `setup/rulesets/protect-main.json`. Apply creates the ruleset again while that file is in the repository.

<a id="owner-bypass"></a>

## Owner bypass

**Rule.** The admin role may bypass `protect-main`, and only when merging a pull request. The bypass does not allow a direct push.

**Why.** GitHub does not let you approve your own pull request. Without this bypass, a code-owner review rule would block your own pull requests forever. The pull request still exists, so there is a record, and Rule Insights logs the bypass.

**If disabled.** You cannot merge your own pull request, including a pull request that only fixes `CODEOWNERS`. Work stops until some other code owner approves it.

**How to disable explicitly.** Remove the admin bypass from `protect-main`, and from `setup/rulesets/protect-main.json`. Apply puts the bypass back while the file still has it. This bypass does not apply to other rulesets. See [how rulesets stack](github-setup.md#how-rulesets-stack).

<a id="protect-tags"></a>

## Protect tags

**Rule.** Nobody except an admin may create, move, or delete any tag. The admin bypass on tags is "always", because a pull-request bypass is only valid on branch rulesets. The agent GitHub account is not an admin, so it still cannot change tags.

**Why.** Tags are the names you trust for a release. A move or a delete rewrites what a name points at.

**If disabled.** The agent GitHub account can push a tag, move `v1.0` to a different commit, or delete the tag.

**How to disable explicitly.** Delete the `protect-tags` ruleset, and delete `setup/rulesets/protect-tags.json`. Apply creates it again while the file is there. The admin bypass on `protect-main` does not let anyone change tags.

<a id="require-checks"></a>

## Require checks

**Rule.** The default branch cannot be updated unless the status check `checks / gate` has passed on the latest commit. The check is strict. This ruleset has no bypass list.

**Why.** Review is not a test run. The check has to pass even for an admin. A bypass on `protect-main` does not skip this ruleset.

**If disabled.** A pull request can be merged while tests are red or missing. The agent GitHub account, or a tired owner, can land a broken tree.

**How to disable explicitly.** Delete the `require-checks` ruleset, and delete `setup/rulesets/require-checks.json`. Apply creates it only when `.github/workflows/checks.yml` is already on the default branch. Until that file exists, apply logs SKIPPED: `CI not added yet; re-run after layer 2 merge`.

<a id="read-only-token"></a>

## Read-only token

**Rule.** The default `GITHUB_TOKEN` in Actions can read the repository and cannot approve pull requests.

**Why.** A workflow runs code from the branch. A write token, or a token that can approve, lets that code satisfy the review rule or push more changes.

**If disabled.** A workflow triggered by the agent GitHub account can approve the pull request it arrived on, or push commits back to the branch.

**How to disable explicitly.** In Settings → Actions → General → Workflow permissions, choose Read and write repository contents, or allow GitHub Actions to approve pull requests. Apply sets both back: read-only, and cannot approve.

<a id="fork-approval"></a>

## Fork approval

**Rule.** On a public repository, a pull request from a fork runs Actions only after approval, for every outside collaborator.

**Why.** A fork's workflow runs in the context of your repository's secrets and `GITHUB_TOKEN` once GitHub allows it. An unknown fork should not get that on open.

**If disabled.** The first pull request from a stranger can run a workflow in your repository before you have looked at it.

**How to disable explicitly.** In Settings → Actions → General → Fork pull request workflows, choose a weaker approval rule, or stop requiring approval. Apply sets "all outside collaborators" again when the API is available. On a private repository this setting is skipped. If the API returns not found, apply and verify print the manual step and do not fail.

<a id="pinned-actions"></a>

## Pinned actions

**Rule.** Actions may run GitHub-owned actions, plus the exact `uses:` values already used by workflows on the default branch. Other actions are not allowed. Verify warns when a `uses:` value is not a full 40-character commit SHA. Local `./` actions and `docker://` images are not part of that check.

**Why.** A tag such as `@v4` can move. A pin to a commit stays on the code you read. The allow-list stops a new workflow from pulling in an action you have not already accepted.

**If disabled.** A workflow can switch to a different action, or a tag you pinned last month can point at new code.

**How to disable explicitly.** In Settings → Actions → General → Actions permissions, allow all actions, or add patterns you did not review. Apply sets the allow-list again from the workflows on the default branch. `patterns_allowed` is enforced on public repositories. Verify still warns about unpinned `uses:` lines; the warning is OK, not FAIL.

<a id="codeowners"></a>

## CODEOWNERS

**Rule.** The `*` rule in `.github/CODEOWNERS` lists the owner GitHub account: the login returned by `gh api user` for the person running the script.

**Why.** `protect-main` requires a code-owner review. With no `CODEOWNERS` file, GitHub has nobody to ask. The script does not hardcode a person. It writes `* @<login>` only when the file is missing. If the file already lists that login, it is left untouched. If the file lists someone else, the script stops and does not overwrite it. This repository's committed `.github/CODEOWNERS` is that file for this repository, generated the same way when it was added.

**If disabled.** The code-owner review has no owner. Either every pull request is stuck, or the review rule is not doing what you think.

**How to disable explicitly.** Delete `.github/CODEOWNERS` and do not re-run apply. Apply will create `* @<login>` again while you are logged in as the owner GitHub account. If rulesets block the script from committing the file, add the line in your own pull request and merge it with the admin bypass (pull requests only).

<a id="agent-write-access"></a>

## Agent write access

**Rule.** The agent GitHub account is a collaborator with write, not admin. Apply invites that account if needed. It does not demote an account that already has admin; it warns and leaves the role. Verify fails until the role is write and the invitation has been accepted.

**Why.** Write is enough to open a pull request. Admin would let the agent GitHub account change or delete the rules.

**If disabled.** The agent cannot open pull requests, or it is an admin and can turn the rules off.

**How to disable explicitly.** Remove the agent GitHub account from collaborators. Apply invites it again on the next run. If you granted admin, change the role to write yourself; apply will not do that for you.

<a id="free-private-risk"></a>

## Free private repository

**Rule.** Rulesets are not available on a private repository on GitHub Free. Apply refuses to continue until you type `yes` or pass `--accept-risk`. That acceptance is written in the log. Verify repeats the warning on every run. The ruleset steps are SKIPPED. Other settings that the API still allows are still applied.

**Why.** Without rulesets, the agent GitHub account could push directly to the default branch. There is no review. Checks are only advisory. The safe options are: make the repository public, or use GitHub Pro (or a plan that includes rulesets).

**If disabled.** This is not a switch you turn off. It is a limit of the plan. Accepting the risk does not create the rules. It only lets the rest of the script continue, and it records that you saw the warning.

**How to disable explicitly.** Make the repository public, or move it to a plan that includes rulesets, then re-run apply. To proceed on GitHub Free anyway, type `yes` at the prompt, or re-run with `--accept-risk`. In a non-interactive shell the script stops unless `--accept-risk` is present.
