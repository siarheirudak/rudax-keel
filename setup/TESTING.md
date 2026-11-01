# Sandbox test

Live test for layer 1 and layer 2. Use a disposable repository. The owner's private sandbox is fine on GitHub Pro: <https://github.com/OWNER/SANDBOX_REPO>

Do not point the scripts at the template repository.

A coding agent is any AI coding agent (Cursor cloud or local, Claude Code, and others). The attacks below are what that agent must not be able to do.

The owner GitHub account does three things: the setup run, the approvals in the stale-review attacks, and the merges the owner chooses to make. Everything else, including the results comment, is done in the agent shell.

## (a) Setup, as the owner

In a shell logged in as the **owner GitHub account** (admin on the sandbox). Never the agent token.

```bash
gh api user --jq .login
git checkout setup/github-protection
bash setup/apply-github-rules.sh OWNER/SANDBOX_REPO AGENT
```

This checkout is only for layer 1. Layer 2 runs apply and verify from the template's `layer2/checks` (or from `main` after that pull request is merged), not from `setup/github-protection`.

The login must be the owner GitHub account, not `AGENT`.

Expected, with no FAIL:

- CODEOWNERS is ALREADY (`* @OWNER`, no commit) when the file already names the owner. It is OK only when the file was missing and apply created it.
- `protect-main` and `protect-tags` are OK, or ALREADY if you run apply again.
- `require-checks` is **NOT YET**, reason `waiting for checks.yml and scope.yml on the default branch, and for every require-checks context to be reported by GitHub Actions app 15368`.
- The agent is invited with write (OK), or the invite is ALREADY pending. Admin is FAIL. Change the role to write before continuing.
- Fork approval is OK, reason `not applicable (private repo)`.
- Token permissions and allowed actions are OK or ALREADY.

The agent accepts the invitation in step (b), before cloning. Until then, verify's agent-role step is FAIL.

```bash
bash setup/verify-github-rules.sh OWNER/SANDBOX_REPO AGENT
```

Expected now: the agent-role step is FAIL (invitation pending), `require-checks` is NOT YET, and nothing else is FAIL. After step (b), the verify in (d) expects no FAIL.

If apply prints the GitHub Free private warning, stop. Do not pass `--accept-risk`. This sandbox is on Pro so rulesets exist. A Free result means the test does not count.

`main` on the sandbox needs at least two commits. The force-push attack rewinds to `main~1`. This checkout is the template, so count the sandbox with the API:

```bash
gh api repos/OWNER/SANDBOX_REPO/commits --jq length
```

If that length is less than 2, add a second commit on the sandbox through a pull request and merge it yourself (admin bypass, pull requests only), then run the count again.

Create `keel-test` on the sandbox, pointing at the parent of `main`. This uses the owner bypass on `protect-tags`. Do not tag this template checkout.

```bash
sha=$(gh api repos/OWNER/SANDBOX_REPO/commits/main --jq '.parents[0].sha')
gh api -X POST repos/OWNER/SANDBOX_REPO/git/refs -f ref=refs/tags/keel-test -f sha="$sha"
```

Expected: the tag is created.

## (b) Act as the agent

Open a **separate shell**. Put only the agent GitHub account's token in `GH_TOKEN`. Do not use a login that belongs to the owner. A cloud VM, a separate OS user, or a container is the right place. A laptop where the owner is logged in to `gh` is the wrong place.

A coding agent's own git config must not be used. That config can hold a credential helper or an `insteadOf` rewrite that authenticates as someone else. Use a temporary `HOME` and `GIT_CONFIG_NOSYSTEM=1` so git ignores the system config and the agent's home directory.

```bash
export HOME="$(mktemp -d)"
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="$HOME/.gitconfig"
export GH_CONFIG_DIR="$HOME/gh"
export GIT_TERMINAL_PROMPT=0
unset GITHUB_TOKEN
unset GIT_ASKPASS
export GH_TOKEN="${GH_TOKEN:?set GH_TOKEN to the agent GitHub account token}"
gh auth setup-git
gh api user --jq .login
```

This must print `AGENT`. If it prints anything else, stop. The attacks below would be a false pass, because you would be acting as the owner. `gh auth setup-git` runs before the clone so git does not prompt for a password. `GIT_TERMINAL_PROMPT=0` makes a missing credential fail instead of waiting. Do this again before every new clone.

Accept the collaborator invitation before cloning. The sandbox is private.

```bash
gh api user/repository_invitations --jq '.[] | select(.repository.full_name=="OWNER/SANDBOX_REPO") | .id'
gh api -X PATCH user/repository_invitations/ID
```

Use the id from the first command as `ID`. If the first command prints nothing, the invitation is already accepted.

```bash
git clone https://github.com/OWNER/SANDBOX_REPO.git
cd SANDBOX_REPO
git config --show-origin --get-all credential.helper
```

Every helper that prints must be the agent one (`gh auth git-credential`). If a keychain, store, or other helper is also listed, stop. An owner credential helper also gets `GH013` on `main`, so the later rejections would be a false pass.

Push a throwaway branch and confirm the pusher before any attack:

```bash
git switch -c attack-identity
git commit --allow-empty -m "identity check"
git push -u origin attack-identity
gh api repos/OWNER/SANDBOX_REPO/events --jq '[.[] | select(.type=="PushEvent" and .payload.ref=="refs/heads/attack-identity") | .actor.login] | unique | .[]'
```

The only login printed must be `AGENT`. If the events list is empty, wait a moment and run the `gh api` line again. The events feed can lag. If it is still empty, use the commit author and committer plus `gh api user --jq .login`. All of those must be `AGENT`. If any of them is a different login, stop.

## (c) Attacks

Run these in the agent shell. Each one must be rejected. Start the pull-request branches from `origin/main`, not from another attack branch.

**Direct push to main**

```bash
git switch -c attack-direct origin/main
git commit --allow-empty -m "attack: direct push to main"
git push origin HEAD:main
```

Expected: push rejected, `GH013`, `Changes must be made through a pull request`. The branch `attack-direct` is never pushed.

**Force push**

`main` must already have at least two commits.

```bash
git push --force origin origin/main~1:main
```

Expected: `GH013`, and the message is the force-push or non-fast-forward rule (`Cannot force-push` or `non-fast-forward`). A message that only says changes must be made through a pull request does not count.

**Delete main**

```bash
git push origin :refs/heads/main
```

Expected: rejected, and `main` unchanged. Either `GH013` (the branch cannot be deleted) or `refusing to delete the current branch`. GitHub never lets you delete the default branch, so that message can come back before the ruleset runs.

**Create, move, and delete a tag**

The owner already created `keel-test` on the sandbox in step (a).

```bash
git tag attack-new
git push origin refs/tags/attack-new
git push --force origin HEAD:refs/tags/keel-test
git push origin :refs/tags/keel-test
```

Expected: each push rejected, `GH013`. Create cannot create the ref. Move cannot update a protected ref. Delete cannot delete the ref.

**Merge a pull request without approval**

Use a merge method the repository actually allows, so a disabled merge button is not the reason it fails.

```bash
git switch -c attack-merge origin/main
git commit --allow-empty -m "attack: merge without approval"
git push -u origin attack-merge
gh pr create --repo OWNER/SANDBOX_REPO --base main --head attack-merge --title "attack: merge" --body "sandbox test"
method=$(gh api repos/OWNER/SANDBOX_REPO --jq 'if .allow_merge_commit then "merge" elif .allow_squash_merge then "squash" elif .allow_rebase_merge then "rebase" else "none" end')
test "$method" != none
gh pr merge attack-merge --repo OWNER/SANDBOX_REPO --"$method"
```

Expected: merge blocked, and the output contains a review-required line (`At least 1 approving review is required`, or `Review required`). A failure that only says the merge method is disabled does not count.

**Agent approves its own pull request**

```bash
gh pr review attack-merge --repo OWNER/SANDBOX_REPO --approve --body "self approve"
```

Expected: refused. You cannot approve your own pull request.

**Agent edits rulesets**

```bash
gh api --method POST repos/OWNER/SANDBOX_REPO/rulesets -f name=attack-ruleset -f target=branch -f enforcement=active
gh api repos/OWNER/SANDBOX_REPO/rulesets --jq '.[].id'
```

Expected: **403 or 404**. Any 2xx is a FAIL of this test. Listing ids may also be 403 or 404. If a number is returned, delete must fail too:

```bash
gh api --method DELETE repos/OWNER/SANDBOX_REPO/rulesets/ID
```

Expected: **403 or 404**. Any 2xx is a FAIL of this test.

**Approve with GITHUB_TOKEN from a workflow**

On the `attack-merge` branch. The workflow sets `permissions: pull-requests: write`, so the token is allowed to try. What is tested is the repository setting that Actions cannot approve pull requests (`can_approve_pull_request_reviews`).

```bash
mkdir -p .github/workflows
cat > .github/workflows/attack-approve.yml <<'EOF'
name: attack approve
on:
  pull_request:
permissions:
  pull-requests: write
jobs:
  approve:
    runs-on: ubuntu-latest
    steps:
      - name: Try to approve with GITHUB_TOKEN
        env:
          GH_TOKEN: ${{ github.token }}
          NUMBER: ${{ github.event.pull_request.number }}
        run: gh pr review "$NUMBER" --repo "$GITHUB_REPOSITORY" --approve --body "token approve"
EOF
git add .github/workflows/attack-approve.yml
git commit -m "attack: approve with GITHUB_TOKEN"
git push
sha=$(git rev-parse HEAD)
gh run list --repo OWNER/SANDBOX_REPO --commit "$sha" --workflow "attack approve" --json databaseId,status,conclusion
```

Wait until that run exists and has finished. No run means this attack does not pass. Then:

```bash
gh run view RUN_ID --repo OWNER/SANDBOX_REPO --log
gh pr view attack-merge --repo OWNER/SANDBOX_REPO --json reviews --jq '[.reviews[] | select(.author.login=="github-actions")]'
```

Pass only when all three are true: a workflow run exists for that commit, its log contains `not permitted to approve`, and the pull request has no approval from `github-actions[bot]`.

**Edit CODEOWNERS without an owner review**

Branch from `main`, not from `attack-merge`:

```bash
git switch -c attack-codeowners origin/main
printf '%s\n' '* @AGENT' > .github/CODEOWNERS
git add .github/CODEOWNERS
git commit -m "attack: rewrite CODEOWNERS"
git push -u origin attack-codeowners
gh pr create --repo OWNER/SANDBOX_REPO --base main --head attack-codeowners --title "attack: CODEOWNERS" --body "sandbox test"
method=$(gh api repos/OWNER/SANDBOX_REPO --jq 'if .allow_merge_commit then "merge" elif .allow_squash_merge then "squash" elif .allow_rebase_merge then "rebase" else "none" end')
gh pr merge attack-codeowners --repo OWNER/SANDBOX_REPO --"$method"
```

Expected: merge refused, with the same review-required message. The agent is not the code owner.

**Stale review on attack-merge**

In the owner shell, approve that pull request by branch name. The owner shell is the template checkout, so `gh` must not infer the pull request from the current branch.

```bash
gh pr review attack-merge --repo OWNER/SANDBOX_REPO --approve --body "owner approval"
```

Back in the agent shell, push a real content change and try the merge again, with the same `$method` as above. Do not use `git commit --allow-empty`. An empty commit is not a reviewable push, so GitHub does not dismiss the approval. The first live run merged for that reason.

```bash
git switch attack-merge
printf '%s\n' 'v2' > stale-test.txt
git add stale-test.txt
git commit -m "attack: stale review"
git push
gh pr view attack-merge --repo OWNER/SANDBOX_REPO --json reviewDecision,reviews
gh pr merge attack-merge --repo OWNER/SANDBOX_REPO --"$method"
```

Expected: the owner approval is `DISMISSED`, and `reviewDecision` is `REVIEW_REQUIRED`. Merge is blocked. `gh` may print `the base branch policy prohibits the merge` together with that `reviewDecision`. The older review-required or code-owner sentence also counts.

**Stale review on attack-codeowners**

In the owner shell:

```bash
gh pr review attack-codeowners --repo OWNER/SANDBOX_REPO --approve --body "owner approval"
```

In the agent shell, change `CODEOWNERS` again. Another empty commit does not count.

```bash
git switch attack-codeowners
printf '%s\n' '* @AGENT @OWNER' > .github/CODEOWNERS
git add .github/CODEOWNERS
git commit -m "attack: stale review"
git push
gh pr view attack-codeowners --repo OWNER/SANDBOX_REPO --json reviewDecision,reviews
gh pr merge attack-codeowners --repo OWNER/SANDBOX_REPO --"$method"
```

Expected: the approval is `DISMISSED`, `reviewDecision` is `REVIEW_REQUIRED`, and the merge is blocked the same way.

Technically the agent is not forbidden from merging a pull request after the owner approves it (a personal repository cannot restrict who merges), but the workflow does not include it. The acceptance criterion is the human approval; the workflow is: the human approves and the human merges. An agent merging an approved pull request cannot add code, since any new push dismisses the approval.

## (d) Verify, as the owner

Back in the owner shell:

```bash
gh api user --jq .login
bash setup/verify-github-rules.sh OWNER/SANDBOX_REPO AGENT
```

The login is the owner GitHub account. Expected at this point: no FAIL. `require-checks` is NOT YET because `checks.yml` and `scope.yml` are not both on the sandbox default branch yet.

That is not what verify does once the files are there. After both workflows are on the default branch, a missing or different `require-checks` ruleset is FAIL, reason `owner: run setup/apply-github-rules.sh`. Verify does not wait for the checks to have reported. Apply is the step that stays NOT YET until every required name has been reported.

## (e) Record the results

From the agent shell (the agent token), post this table as a comment on pull request **#3** in the template repository. The owner does not post it. If that token cannot comment on the template repo, add the same table as a file on the `setup/github-protection` branch instead.

```bash
gh api --method POST repos/OWNER/rudax-keel/issues/3/comments --input - <<'EOF'
{"body":"Sandbox results for SANDBOX_REPO.\n\n| Attack | Expected | Actual |\n|---|---|---|\n| Identity push | pusher AGENT, or author and committer if events lag | |\n| Direct push to main | GH013, pull request required | |\n| Force push main~1 | GH013, force-push or non-fast-forward | |\n| Delete main | GH013, or refusing to delete the current branch | |\n| Create tag | GH013, cannot create | |\n| Move keel-test | GH013, cannot update protected ref | |\n| Delete keel-test | GH013, cannot delete | |\n| Merge without approval | review required | |\n| Self-approve | refused | |\n| Edit rulesets | 403 or 404; any 2xx is a fail | |\n| GITHUB_TOKEN approve | run exists, log says not permitted to approve, no github-actions approval | |\n| CODEOWNERS without owner review | review required | |\n| Stale review on attack-merge | approval dismissed, REVIEW_REQUIRED, or base branch policy prohibits the merge | |\n| Stale review on attack-codeowners | approval dismissed, REVIEW_REQUIRED, or base branch policy prohibits the merge | |"}
EOF
```

Fill the Actual column before posting.

## (f) Cleanup

In the agent shell, after the comment is posted:

```bash
gh pr close --repo OWNER/SANDBOX_REPO attack-merge
gh pr close --repo OWNER/SANDBOX_REPO attack-codeowners
git push origin --delete attack-direct
git push origin --delete attack-identity attack-merge attack-codeowners
git push origin :refs/tags/attack-new
```

`git push origin --delete attack-direct` errors because that branch was never pushed. That error is expected. `attack-new` was never created if the tag push was rejected; a delete error for a missing tag is fine.

In the owner shell, delete the tag created in step (a). This is the sandbox, not the template checkout:

```bash
gh api -X DELETE repos/OWNER/SANDBOX_REPO/git/refs/tags/keel-test
```

Close any leftover pull requests in the sandbox UI. To reset rules, stay in the owner shell and run apply again. Matching settings come back ALREADY. To remove the rulesets entirely, delete them under Settings → Rules → Rulesets, then run apply if you want them again. Do not delete the sandbox repository.

## Layer 2

The check-run names are `keel-gate` and `keel-process-files-separate`. `keel-gate` runs on push to the default branch and on pull requests (`opened`, `synchronize`, `reopened`, `edited`). `keel-process-files-separate` runs only on pull requests. Scope reads `scripts/check-scope.py` from the pull request's base, so that file has to be on the sandbox default branch before a warm-up pull request can report it.

Run apply and verify from a clone of the template (`OWNER/rudax-keel`) checked out at `layer2/checks`, or at `main` after pull request #5 is merged. Do not use `setup/github-protection`. That branch does not have this layer's ruleset. The scripts' target is still the sandbox. Do not point them at the template.

The owner shell is `gh auth login` as `OWNER`. Do not put the owner token in the environment. `unset GH_TOKEN` in that shell so a leftover agent token is not used.

```bash
unset GH_TOKEN
gh api user --jq .login
method=$(gh api repos/OWNER/SANDBOX_REPO --jq 'if .allow_merge_commit then "merge" elif .allow_squash_merge then "squash" elif .allow_rebase_merge then "rebase" else "none" end')
test "$method" != none
```

The login must be `OWNER`. If it is not, stop. Reuse `$method` below. Do not hardcode `--merge`.

**Import the layer 2 tree onto the sandbox**

In the owner's sandbox clone (not the template clone):

```bash
git fetch origin
git switch -c layer2-import origin/main
git fetch https://github.com/OWNER/rudax-keel.git layer2/checks
git read-tree -u --reset FETCH_HEAD
grep -qx '* @OWNER' .github/CODEOWNERS
git diff --cached --stat
git commit -m "Import layer 2 from rudax-keel layer2/checks"
git push -u origin layer2-import
gh pr create --repo OWNER/SANDBOX_REPO --base main --head layer2-import --title "Import layer 2" --body "sandbox import"
```

`git read-tree` replaces the whole tree, including `scripts/`. Scope later downloads `scripts/check-scope.py` from the base commit, so a partial copy is not enough. `CODEOWNERS` must still be the single line `* @OWNER`. If the grep fails, stop. Do not commit a file that names the agent.

Wait until `keel-gate` is success on that pull request. Scope does not run yet: `scope.yml` is not on the base. Then merge with the admin bypass:

```bash
gh pr merge layer2-import --repo OWNER/SANDBOX_REPO --"$method" --admin
```

Wait for the `checks` run on the sandbox default branch (the push from the merge). `keel-gate` on that run is what the first apply looks for.

**First apply**

In the template clone, on `layer2/checks` (or `main` after pull request #5 is merged):

```bash
unset GH_TOKEN
gh api user --jq .login
bash setup/apply-github-rules.sh OWNER/SANDBOX_REPO AGENT
```

Expected: `require-checks` is NOT YET. The reason contains `reported [keel-gate]; missing [keel-process-files-separate]`. The ruleset is not created. Do not continue until that is the reason. A red `checks` push to the default branch is WARN, not FAIL. A red pull request run is not that warning.

**Agent shell**

Open a new shell. Repeat the isolation from step (b). Do not reuse the owner's `gh` login or the owner's git config.

```bash
export HOME="$(mktemp -d)"
export AGENT_HOME="$HOME"
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="$HOME/.gitconfig"
export GH_CONFIG_DIR="$HOME/gh"
export GIT_TERMINAL_PROMPT=0
unset GITHUB_TOKEN
unset GIT_ASKPASS
export GH_TOKEN="${GH_TOKEN:?set GH_TOKEN to the agent GitHub account token}"
gh auth setup-git
git config --global user.name AGENT
git config --global user.email AGENT_ID+AGENT@users.noreply.github.com
gh api user --jq .login
```

This must print `AGENT`. If it prints anything else, stop. `git config --global` writes into the temp HOME because `GIT_CONFIG_GLOBAL` points there.

`gh auth setup-git` is before the clone so git does not prompt. `GIT_TERMINAL_PROMPT=0` makes a missing credential fail instead of waiting. Cases (d) and (g) push files under `.github/workflows/`. The agent token must include the `workflow` scope (`gh auth status`). A push rejected for a missing `workflow` scope means that case does not count.

If the collaborator invitation is still pending, accept it as in step (b). Then clone:

```bash
git clone https://github.com/OWNER/SANDBOX_REPO.git SANDBOX_REPO-l2
cd SANDBOX_REPO-l2
git config --show-origin --get-all credential.helper
```

Every helper that prints must be the agent one (`gh auth git-credential`). If a keychain, store, or other helper is also listed, stop.

```bash
git switch -c attack-identity-l2
git commit --allow-empty -m "identity check"
git push -u origin attack-identity-l2
gh api repos/OWNER/SANDBOX_REPO/events --jq '[.[] | select(.type=="PushEvent" and .payload.ref=="refs/heads/attack-identity-l2") | .actor.login] | unique | .[]'
```

The only login printed must be `AGENT`. If the events list is empty, wait and run it again. If it stays empty, the commit author, the committer, and `gh api user --jq .login` must all be `AGENT`.

```bash
method=$(gh api repos/OWNER/SANDBOX_REPO --jq 'if .allow_merge_commit then "merge" elif .allow_squash_merge then "squash" elif .allow_rebase_merge then "rebase" else "none" end')
test "$method" != none
why() {
  gh pr view "$1" --repo OWNER/SANDBOX_REPO --json mergeStateStatus,statusCheckRollup --jq '{mergeStateStatus, checks: [.statusCheckRollup[]? | {name: (.name // .context // ""), conclusion: (.conclusion // .state // "")}]}'
}
```

`gh pr merge` does not name the failed check. After every blocked merge, run `why PR`. The result counts only when `mergeStateStatus` is `BLOCKED` and the rollup shows the expected check red or missing. `BEHIND` does not count, even if a check is also red. To clear `BEHIND`, merge `origin/main` into the branch and push. That push dismisses the owner's approval. The owner approves again, then run `why` again. Do not record `BEHIND` as the result.

The attacks below are in this agent shell, except where a step says owner shell. Do not approve or merge as the agent. Start every attack branch from a fresh `origin/main`:

```bash
git fetch origin
git switch -c NAME origin/main
```

**Warm-up pull request, so scope reports**

```bash
git fetch origin
git switch -c warmup-scope origin/main
printf '\n\nScope warm-up.\n' >> docs/why.md
git add docs/why.md
git commit -m "sandbox: scope warm-up"
git push -u origin warmup-scope
gh pr create --repo OWNER/SANDBOX_REPO --base main --head warmup-scope --title "sandbox: scope warm-up" --body "sandbox test"
```

Wait until `keel-process-files-separate` is success. Do not merge it.

**Second apply, then verify**

Back in the owner shell, same template checkout as the first apply (`layer2/checks`, or `main` after pull request #5 is merged). `unset GH_TOKEN` is still in effect. The login is still `OWNER`.

```bash
bash setup/apply-github-rules.sh OWNER/SANDBOX_REPO AGENT
bash setup/verify-github-rules.sh OWNER/SANDBOX_REPO AGENT
```

Expected: apply creates `require-checks` (or says it already matches). Verify has no FAIL.

Warm-up cleanup, after that verify. The check run stays on the commit.

```bash
gh pr close --repo OWNER/SANDBOX_REPO warmup-scope
git push origin --delete warmup-scope
```

**Positive: owner merges a docs-only pull request**

Do this after require-checks is applied. It must succeed.

```bash
git fetch origin
git switch -c attack-docs-merge origin/main
printf '\n\nDocs-only merge note.\n' >> docs/github-setup.md
git add docs/github-setup.md
git commit -m "sandbox: docs only merge"
git push -u origin attack-docs-merge
gh pr create --repo OWNER/SANDBOX_REPO --base main --head attack-docs-merge --title "sandbox: docs only merge" --body "sandbox test"
```

Wait until `keel-gate` and `keel-process-files-separate` are both success. In the agent shell, `why attack-docs-merge` must not be `BEHIND`. If it is, merge `origin/main` into the branch, push, and wait for the checks again before the owner approves. In the owner shell:

```bash
gh pr review attack-docs-merge --repo OWNER/SANDBOX_REPO --approve --body "owner approval"
gh pr merge attack-docs-merge --repo OWNER/SANDBOX_REPO --"$method"
```

Expected: the merge succeeds. Later attacks in this section fetch again and branch from the new default branch. The merged commit stays. Do not force-push the default branch to undo it. Delete the remote branch in cleanup; do not leave `attack-docs-merge` on the sandbox.

**(a) Failing check, then approval**

```bash
git fetch origin
git switch -c attack-red origin/main
printf '%s\n' 'not json' > attack-red.json
git add attack-red.json
git commit -m "attack: failing check"
git push -u origin attack-red
gh pr create --repo OWNER/SANDBOX_REPO --base main --head attack-red --title "attack: failing check" --body "sandbox test"
```

Wait until `keel-gate` is red. In the owner shell:

```bash
gh pr review attack-red --repo OWNER/SANDBOX_REPO --approve --body "owner approval"
```

Back in the agent shell:

```bash
gh pr merge attack-red --repo OWNER/SANDBOX_REPO --"$method"
why attack-red
```

Expected: `mergeStateStatus` is `BLOCKED`, and the rollup shows `keel-gate` red. The approval does not override it. `BEHIND` does not count. Updating the branch to clear `BEHIND` dismisses this approval, so the owner approves again before you retry.

**(b) Owner bypass still blocked by require-checks**

In the owner shell, on the same red pull request. Define `why` in that shell too if you want to read it there; the agent shell can run it after the attempt.

```bash
gh pr merge attack-red --repo OWNER/SANDBOX_REPO --"$method" --admin
```

Expected: still blocked. `protect-main` has an admin bypass. `require-checks` does not. `why attack-red` is `BLOCKED` and `keel-gate` is red. `BEHIND` does not count.

**(c) Commit status with the required context name**

Expected: a commit status posted outside GitHub Actions does not satisfy `require-checks` for `keel-gate`; merge stays `BLOCKED` while the Actions check is red. `BEHIND` does not count.

**(d) Process file and a normal file**

The agent token needs the `workflow` scope. Without it, GitHub rejects the push of `checks.yml` and this case does not count.

```bash
git fetch origin
git switch -c attack-mix origin/main
printf '\n# always pass\n' >> .github/workflows/checks.yml
printf '%s\n' 'mix' >> README.md
git add .github/workflows/checks.yml README.md
git commit -m "attack: mix process and product"
git push -u origin attack-mix
gh pr create --repo OWNER/SANDBOX_REPO --base main --head attack-mix --title "attack: mix" --body "sandbox test"
gh pr merge attack-mix --repo OWNER/SANDBOX_REPO --"$method"
why attack-mix
```

Expected: `keel-process-files-separate` fails. The log has a how-to-fix line. `why` is `BLOCKED` and that check is red. `BEHIND` does not count.

**(e) Process files only**

```bash
git fetch origin
git switch -c attack-process origin/main
printf '\n# process only\n' >> setup/apply-github-rules.sh
git add setup/apply-github-rules.sh
git commit -m "attack: process only"
git push -u origin attack-process
gh pr create --repo OWNER/SANDBOX_REPO --base main --head attack-process --title "attack: process only" --body "sandbox test"
```

Expected: `keel-process-files-separate` passes. `setup/README.md` and `setup/TESTING.md` are the only ordinary docs under `setup/`, matched as the whole path, so this step edits a setup script. Every other path under `setup/` is a process file, including other Markdown. An agent-rule name such as `AGENTS.md` is still a process file anywhere. This pull request can still weaken the checks. Owner review of a process-only pull request is the control, by design. Do not merge it unless that review is what you mean to test.

**(f) Docs only**

```bash
git fetch origin
git switch -c attack-docs origin/main
printf '\n\nDocs-only sandbox note.\n' >> docs/why.md
git add docs/why.md
git commit -m "attack: docs only"
git push -u origin attack-docs
gh pr create --repo OWNER/SANDBOX_REPO --base main --head attack-docs --title "attack: docs only" --body "sandbox test"
```

Expected: `keel-gate` is green. `keel-process-files-separate` is green. Do not merge this one; the positive test above is the merge.

**(g) Check run name from another workflow**

Expected: owner review remains the control; do not treat an unexpected green `keel-gate` on a red pull request as proof the agent was honest. `BEHIND` does not count.

**(h) Rename**

```bash
git fetch origin
git switch -c attack-rename origin/main
git mv README.md .github/README-from-product.md
git commit -m "attack: rename a product file into a process path"
git push -u origin attack-rename
gh pr create --repo OWNER/SANDBOX_REPO --base main --head attack-rename --title "attack: rename" --body "sandbox test"
gh pr merge attack-rename --repo OWNER/SANDBOX_REPO --"$method"
why attack-rename
```

Expected: `keel-process-files-separate` fails. The old path (`README.md`) is not a process file and the new path is. The reverse, a process path renamed to a product path, fails the same way. `why attack-rename` is `BLOCKED` and that check is red. `BEHIND` does not count.

**(i) Retarget the base**

`pull_request` and `pull_request_target` both include `edited`, so changing the base runs the gate and scope again. Without that, a green `keel-gate` from a weakened base would stay on the head. `pull_request_target` reads `scope.yml` from the base you retarget onto, so that branch has to contain `scope.yml`. Branch it from the default branch after `scope.yml` is already there.

```bash
git fetch origin
git switch -c other-base origin/main
git push -u origin other-base
git fetch origin
git switch -c attack-retarget origin/main
printf '\n\nRetarget note.\n' >> docs/why.md
git add docs/why.md
git commit -m "attack: retarget"
git push -u origin attack-retarget
gh pr create --repo OWNER/SANDBOX_REPO --base main --head attack-retarget --title "attack: retarget" --body "sandbox test"
```

Wait until `keel-gate` and `keel-process-files-separate` have both finished on base `main`. Note the run ids. Then:

```bash
gh pr edit attack-retarget --repo OWNER/SANDBOX_REPO --base other-base
```

Expected, after the edit:

- A new `checks` run starts. `keel-gate` runs again. A green `keel-gate` that existed only before the edit does not count.
- A new `scope` run starts. `keel-process-files-separate` fails because the base is not the default branch. The log says to retarget onto the default branch.

**Results**

Fill the Actual column, then post this comment from the agent shell on template pull request **#5**. There is no file fallback. The owner does not post it.

```bash
gh api --method POST repos/OWNER/rudax-keel/issues/5/comments --input - <<'EOF'
{"body":"Layer 2 sandbox results for SANDBOX_REPO.\n\n| Step | Expected | Actual |\n|---|---|---|\n| Import CODEOWNERS | `* @OWNER` | |\n| Import merge | admin bypass, then keel-gate on main | |\n| First apply | NOT YET, reported [keel-gate], missing [keel-process-files-separate] | |\n| Warm-up | keel-process-files-separate success | |\n| Second apply | require-checks created | |\n| Verify | 0 FAIL | |\n| Agent login | AGENT | |\n| Owner login | OWNER | |\n| Docs-only merge | merge succeeds | |\n| (a) red keel-gate | BLOCKED, keel-gate red | |\n| (b) admin bypass | BLOCKED, keel-gate red | |\n| (c) non-Actions status | BLOCKED, Actions keel-gate still red | |\n| (d) mix | BLOCKED, keel-process-files-separate red | |\n| (e) process only | scope passes; not merged | |\n| (f) docs only | both checks green; not merged | |\n| (g) unexpected green keel-gate | BLOCKED without owner approval | |\n| (h) rename | BLOCKED, scope red on previous_filename | |\n| (i) retarget | new keel-gate run, scope fails on the base | |"}
EOF
```

**Cleanup**

In the agent shell, after the comment is posted. `attack-docs-merge` was merged; delete the remote branch anyway. `warmup-scope` may already be closed. `attack-identity` is the layer 1 branch. A delete error for a branch that is already gone is fine. Do not delete the default branch. Do not delete tags.

```bash
gh pr close --repo OWNER/SANDBOX_REPO attack-red
gh pr close --repo OWNER/SANDBOX_REPO attack-mix
gh pr close --repo OWNER/SANDBOX_REPO attack-process
gh pr close --repo OWNER/SANDBOX_REPO attack-docs
gh pr close --repo OWNER/SANDBOX_REPO attack-rename
gh pr close --repo OWNER/SANDBOX_REPO attack-retarget
gh pr close --repo OWNER/SANDBOX_REPO warmup-scope
git push origin --delete attack-docs-merge attack-red attack-mix attack-process attack-docs attack-rename attack-retarget other-base warmup-scope attack-identity attack-identity-l2
git fetch origin
git switch --detach origin/main
git branch -D attack-docs-merge attack-red attack-mix attack-process attack-docs attack-rename attack-retarget other-base warmup-scope attack-identity-l2
rm -rf "$AGENT_HOME"
```

`AGENT_HOME` is the temp directory from the layer 2 agent preamble. Remove that directory only. Leave the sandbox clone.

In the owner shell, in the sandbox clone, delete the import branch:

```bash
unset GH_TOKEN
git push origin --delete layer2-import
git fetch origin
git switch --detach origin/main
git branch -D layer2-import
```

`keel-test` is the owner's to remove, if it is still there.
