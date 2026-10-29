# Why these rules exist

This protection limits the agent GitHub account. It does not protect the owner GitHub account. Protect that yourself (2FA, never share your token).

Each log line from the setup scripts links to a section below.

**Rule:** any new rule needs a section here, in this shape, before it is added to the scripts.

<a id="who-runs-this"></a>

## Who runs this

**Rule.** Only the owner GitHub account runs apply and verify. That account must be an admin on the repository. The agent GitHub account must not be the account logged in to `gh`.

**Why.** The script changes repository settings. The agent GitHub account has write, not admin, so it must not be able to change the rules that constrain it.

**If disabled.** Anyone with the agent token could point the script at the repo, or the script could no-op while you think the rules are on.

**How to disable explicitly.** There is nothing to turn off. Log in as the owner GitHub account with `gh auth login` before you run the scripts.

<a id="gh-version"></a>

## gh version

**Rule.** Apply and verify need `gh` 1.7.0 or newer.

**Why.** Listing rulesets uses `gh api --paginate` and `gh api --jq`. Those flags exist from 1.7.0. `gh api --slurp` needs 2.48.0, so these scripts do not use it. An older `gh` answers an unknown flag with its whole usage page, and the rules are not applied.

**If disabled.** The version check fails and the script stops. Nothing is written.

**How to disable explicitly.** There is nothing to turn off. Upgrade `gh` from <https://cli.github.com/>.

<a id="agent-environment"></a>

## Where the coding agent runs

**Rule.** Protection holds only if the coding agent runs where the only GitHub token is the agent GitHub account's token. That means a cloud VM, a separate OS user, or a container. It must not run where the owner GitHub account is logged in, for example a laptop `gh` login as the owner.

**Why.** A coding agent is any AI coding agent (Cursor cloud or local, Claude Code, and others). It can run whatever `gh` and `git` are already logged in as. If that is the owner, the agent can merge, push, and change rules as the owner.

**If disabled.** The agent acts as the owner GitHub account. The write-only role never comes into play.

**How to disable explicitly.** Do not. Run the agent in an environment that has only the agent token. Before a sandbox attack, `gh api user --jq .login` must print the agent GitHub account. Any other login means the test is a false pass.

The harness in this repository is one such container. Why each check it prints exists: [Why each keel-doctor check exists](harness-checks-why.md).

<a id="protect-main"></a>

## Protect main

**Rule.** On the default branch: no deletion, no force push, and changes only through a pull request. The pull request needs 1 approval, a review from a code owner, and stale approvals are dismissed.

**Why.** The agent GitHub account can open a pull request. It cannot put commits on the default branch by itself. You see every change before it lands.

**If disabled.** The agent GitHub account can `git push` straight to the default branch. A bad or confused agent can ship code with no review.

**How to disable explicitly.** Delete the `protect-main` ruleset in the repository rules settings, and delete `setup/rulesets/protect-main.json`. Apply creates the ruleset again while that file is in the repository.

<a id="owner-bypass"></a>

## Owner bypass

**Rule.** The admin role may bypass `protect-main`, and only when merging a pull request. The bypass does not allow a direct push.

**Why.** GitHub does not let you approve your own pull request. Without this bypass, a code-owner review rule would block your own pull requests forever. The pull request still exists, so there is a record. Rule Insights (Settings → Rules → Insights) logs the bypass.

**If disabled.** You cannot merge your own pull request, including a pull request that only fixes `CODEOWNERS`. Work stops until some other code owner approves it.

**How to disable explicitly.** Remove the admin bypass from `protect-main`, and from `setup/rulesets/protect-main.json`. Apply puts the bypass back while the file still has it. This bypass does not apply to other rulesets. See [how rulesets stack](github-setup.md#how-rulesets-stack).

<a id="protect-tags"></a>

## Protect tags

**Rule.** Nobody except an admin may create, move, or delete any tag. The admin bypass on tags is "always", because a pull-request bypass is only valid on branch rulesets. The agent GitHub account is not an admin, so it still cannot change tags.

**Why.** Tags are how you name a release. Only the owner should create, move, or delete them. The agent GitHub account must not be able to fake a release. A move or a delete rewrites what a name points at. The bypass is the admin role only, which the agent does not have.

**If disabled.** The agent GitHub account can push a tag, move `v1.0` to a different commit, or delete the tag.

**How to disable explicitly.** Delete the `protect-tags` ruleset, and delete `setup/rulesets/protect-tags.json`. Apply creates it again while the file is there. The admin bypass on `protect-main` does not let anyone change tags.

<a id="require-checks"></a>

## Require checks

**Rule.** The default branch cannot be updated unless `keel-gate` and `keel-process-files-separate` have passed on the latest commit. Those strings are the check-run names. The Actions page shows `checks / keel-gate`; that is only a display label. The rule is strict: the branch must be up to date before merge. There is no bypass list. Each check is restricted to GitHub Actions (`integration_id` 15368, the id from `GET /apps/github-actions`).

**Why.** A status check is a pass or fail name GitHub stores on a commit. `keel-gate` fails if any job in `.github/workflows/checks.yml` failed, was cancelled, or was skipped. `checks` includes `edited`, so a base change runs the gate again and a green result from another base does not stay. Limiting the name to GitHub Actions means a success status posted with a user token does not count. It does not stop a deliberately malicious agent. An agent with write can push a workflow on another branch that requests `checks: write` and posts a successful check run of the required name. That run belongs to app 15368 and the workflow is not in the pull request diff. The checks catch mistakes and honest failures, and they block a merge while they are red. Against a deliberately malicious agent, the owner review is the control. A later layer may move the gate to an owner-owned GitHub App whose key only the default branch can use. Strict means a new commit has to run the checks again. Apply creates the ruleset only when both workflow files are on the default branch and a check run with each exact name, from app 15368, has been seen. It stops looking once both names have been seen, and it reads at most two pages of runs per workflow. `keel-process-files-separate` runs only on pull requests, so that run can be on any branch. Until then the step is NOT YET, and the reason lists reported names and missing names. Verify fails with `owner: run setup/apply-github-rules.sh` when those files are on the default branch and the ruleset is missing or different, including `integration_id`. A red `checks` push to the default branch is WARN, not FAIL. A red pull request run is not that warning.

Merge queue is not supported: these workflows have no `merge_group` trigger, so a queued merge does not run them.

A pull request opened by `GITHUB_TOKEN` does not run GitHub Actions checks.

**If disabled.** A pull request can be merged while tests are red or missing. The admin bypass on `protect-main` does not skip this ruleset.

**How to disable explicitly.** Delete the `require-checks` ruleset, and delete `setup/rulesets/require-checks.json`. Apply creates it again once both workflows are on the default branch and every required check-run name has been reported by GitHub Actions app 15368.

<a id="scope"></a>

## Scope

**Rule.** A pull request that changes a process file must contain only process files. Process files are `.github/**`, `scripts/**` (including `scripts/tests/`), `.cursor/**`, `.claude/**`, every file under `setup/**` whose name does not end in `.md` (scripts, ruleset JSON, and `setup/tests/**`), and these names anywhere, including under `setup/`: `CODEOWNERS`, `AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md`, `.cursorrules`, `.windsurfrules`, `.clinerules`, `.mcp.json`, `.shellcheckrc`. Markdown under `setup/`, such as `setup/README.md` and `setup/TESTING.md`, is an ordinary doc. `scripts/` is included because the checks run those files from the pull request. A file under `docs/` counts only when its name is one of those. `tests/` is not a process path; product tests live there. The template's own check tests live in `scripts/tests/`. Labels are not permission. A rename counts `filename` and `previous_filename`. The pull request base must be the repository default branch. If the API file list does not match `changed_files`, or the pull request changes 3000 or more files, the check fails closed.

**Why.** The check runs from `pull_request_target`, so the workflow file is the one on the pull request's base branch, not the copy in the head. The types include `edited`, so changing the base runs it again. The job does not check out pull request code. Its token can only read contents and pull requests. That is safe. The same trigger is dangerous if the job checks out the pull request head or the token can write: untrusted code would then run with that token. The check fails when the base is not the default branch, so a retarget does not skip it. A retarget test has to branch the other base from the default branch after `scope.yml` exists, because the workflow file comes from that base. Keeping process edits in their own pull request means the checks that judge other changes are the ones already on the default branch. A process-only pull request can still weaken `checks.yml`. Owner review of process-only pull requests is the control, by design.

**If disabled.** One pull request can change a check and the code that check should reject.

**How to disable explicitly.** First set the `require-checks` ruleset enforcement to disabled, or remove the `keel-process-files-separate` context from it. Then delete `.github/workflows/scope.yml`. Do not delete `scope.yml` while that context is still required: merges wait for a check that nothing runs.

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

**How to disable explicitly.** In Settings → Actions → General → Fork pull request workflows, choose a weaker approval rule, or stop requiring approval. Apply sets "all outside collaborators" again when the API works. On a private repository the step is OK, reason `not applicable (private repo)`, because this setting is only for public repositories. If the API returns not found, the step is FAIL and tells you the Settings path. The script cannot see whether you did that click.

<a id="pinned-actions"></a>

## Pinned actions

**Rule.** Call a well-known tool with `run:` when it is already installed or is a one-command install (`shellcheck` and `jq` on an Ubuntu runner). Use a ready-made action only for a complex job (CodeQL, Docker, cache), from a known author, pinned to a full commit SHA. Write your own code only when nothing exists, and keep it small. The allow-list is GitHub-owned actions, plus the exact `uses:` values already on the default branch. Other actions are not allowed. Verify reports an unpinned `uses:` as OK with a reason starting `warning:`. Local `./` actions and `docker://` images are not part of that check.

**Why.** A tag such as `@v4` can move. A pin stays on the code you read. GitHub-owned actions are always allowed, and other tools run via `run:`, so you rarely need a third-party action. Adding one is a pull request that pins it by SHA. The owner merges (the admin bypass on `protect-main` if you are the only code owner). Then the owner re-runs apply, and that exact `uses:` value is added to the allow-list. Until that re-run, the new action is not allowed.

**If disabled.** A workflow can switch to a different action, or a tag you used last month can point at new code.

**How to disable explicitly.** In Settings → Actions → General → Actions permissions, allow all actions, or add patterns you did not review. Apply sets the allow-list again from the workflows on the default branch. `patterns_allowed` is enforced on public repositories.

<a id="codeowners"></a>

## CODEOWNERS

**Rule.** `.github/CODEOWNERS` is `* @<login>`, where the login is the owner GitHub account from `gh api user`. Apply writes that line only when the file is missing, or when the file is exactly the template line `* @siarheirudak`. That commit is made as the logged-in owner, on the default branch, and only if `protect-main` does not exist yet. If the file already matches the logged-in owner, the step is ALREADY and no commit is made. In this owner's own repositories the file is already `* @siarheirudak`, so apply makes no CODEOWNERS commit. Any other content (a team, a path rule, several owners) is left as it is and the step is FAIL. `--rewrite-codeowners` replaces that other content, and only before `protect-main` exists. If `protect-main` already exists, apply does not commit the file and does not use the admin bypass.

**Why.** `protect-main` asks a code owner to review. A copied template still names `siarheirudak`, and that one line is safe to replace with the person running apply. A file someone already wrote must not be destroyed. In the owner's own repo the line already names them, so there is nothing to commit.

**If disabled.** The code-owner review has no owner, or it names the wrong account. A copied template would keep asking the original owner. If this step is FAIL, apply still creates `protect-main`. The fix is a pull request the owner merges (admin bypass, pull requests only). Rule Insights (Settings → Rules → Insights) records that merge.

**How to disable explicitly.** Delete `.github/CODEOWNERS` and do not re-run apply. Apply writes `* @<login>` again while `protect-main` is not there yet. After `protect-main` exists, change the file in your own pull request and merge it with the admin bypass (pull requests only).

<a id="agent-write-access"></a>

## Agent write access

**Rule.** The agent GitHub account is a collaborator with write, not admin. Apply invites that account if needed. It does not demote an account that already has admin. That step is FAIL, and the role is left unchanged. Verify fails until the role is write and the invitation has been accepted.

**Why.** Write is enough to open a pull request. Admin would let the agent GitHub account change or delete the rules.

**If disabled.** The agent cannot open pull requests, or it is an admin and can turn the rules off.

**How to disable explicitly.** Remove the agent GitHub account from collaborators. Apply invites it again on the next run. If you granted admin, change the role to write yourself; apply will not do that for you.

<a id="who-merges"></a>

## Who merges

Technically the agent is not forbidden from merging a pull request after the owner approves it. A personal repository cannot restrict who merges. The workflow does not include that. The acceptance criterion is the human approval. The workflow is: the human approves and the human merges. An agent merging an approved pull request cannot add code, since any new push dismisses the approval.

You may instruct the agent to enable GitHub auto-merge on its pull requests. That has pitfalls: several pull requests merging one after another, conflicts between them surfacing in `main`, and until required checks exist it merges even with failing checks. The template does not do it by default.

<a id="free-private-risk"></a>

## Free private repository

**Rule.** Rulesets are not available on a private repository on GitHub Free. Apply refuses to continue until you type `yes` or pass `--accept-risk`. That acceptance is logged as OK. The ruleset steps are then FAIL, because GitHub will not create them. Other settings that the API still allows are still applied. Verify repeats the FAIL on every run.

**Why.** Without rulesets, the agent GitHub account could push directly to the default branch. There is no review. Checks are only advisory. The safe options are: make the repository public, or use GitHub Pro (or a plan that includes rulesets).

**If disabled.** This is not a switch you turn off. It is a limit of the plan. Accepting the risk does not create the rules. It only lets the rest of the script continue, and it records that you saw the warning.

**How to disable explicitly.** Make the repository public, or move it to a plan that includes rulesets, then re-run apply. To proceed on GitHub Free anyway, type `yes` at the prompt, or re-run with `--accept-risk`. In a non-interactive shell the script stops unless `--accept-risk` is present.
