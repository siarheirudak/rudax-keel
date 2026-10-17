# Sandbox test

Live test for layer 1. Use a disposable repository. The owner's private sandbox is fine on GitHub Pro: <https://github.com/siarheirudak/rudax-keel-sandbix>

Do not point the scripts at the template repository.

A coding agent is any AI coding agent (Cursor cloud or local, Claude Code, and others). The attacks below are what that agent must not be able to do.

## (a) Setup, as the owner

In a shell logged in as the **owner GitHub account** (admin on the sandbox). Never the agent token.

```bash
gh api user --jq .login
git checkout setup/github-protection
bash setup/apply-github-rules.sh siarheirudak/rudax-keel-sandbix isiarheiridak-agent
```

The login must be the owner GitHub account, not `isiarheiridak-agent`.

Expected, with no FAIL:

- CODEOWNERS is OK (`* @siarheirudak` created or rewritten) or ALREADY.
- `protect-main` and `protect-tags` are OK, or ALREADY if you run apply again.
- `require-checks` is **NOT YET**, reason `CI not added yet; re-run after layer 2 merge`.
- The agent is invited with write (OK), or the invite is ALREADY pending.
- Fork approval is ALREADY, because the sandbox is private.
- Token permissions and allowed actions are OK or ALREADY.

The agent GitHub account must accept the invitation. Then:

```bash
bash setup/verify-github-rules.sh siarheirudak/rudax-keel-sandbix isiarheiridak-agent
```

Expected: no FAIL. `require-checks` is still NOT YET. The agent role is ALREADY only after the invite is accepted.

If apply prints the GitHub Free private warning, stop. Do not pass `--accept-risk`. This sandbox is on Pro so rulesets exist. A Free result means the test does not count.

## (b) Act as the agent

Open a **separate shell**. Put only the agent GitHub account's token in `GH_TOKEN`. Do not use a login that belongs to the owner. A cloud VM, a separate OS user, or a container is the right place. A laptop where the owner is logged in to `gh` is the wrong place.

```bash
unset GITHUB_TOKEN
gh api user --jq .login
```

This must print `isiarheiridak-agent`. If it prints anything else, stop. The attacks below would be a false pass, because you would be acting as the owner.

```bash
git clone https://github.com/siarheirudak/rudax-keel-sandbix.git
cd rudax-keel-sandbix
```

## (c) Attacks

Run these in the agent shell. Each one must be rejected.

**Direct push to main**

```bash
git switch -c attack-direct
git commit --allow-empty -m "attack: direct push to main"
git push origin HEAD:main
```

Expected: push rejected, `GH013`, `Changes must be made through a pull request`.

**Force push**

```bash
git push --force origin HEAD:main
```

Expected: `GH013` and `Cannot force-push to this branch`.

**Delete main**

```bash
git push origin :refs/heads/main
```

Expected: rejected, `GH013`, the branch cannot be deleted.

**Create, move, and delete a tag**

```bash
git tag attack-test
git push origin refs/tags/attack-test
git tag -f attack-test HEAD
git push --force origin refs/tags/attack-test
git push origin :refs/tags/attack-test
```

Expected: each push rejected, `GH013`. Create cannot create the ref. Move cannot update a protected ref. Delete cannot delete the ref.

**Merge a pull request without approval**

```bash
git switch -c attack-merge
git commit --allow-empty -m "attack: merge without approval"
git push -u origin attack-merge
gh pr create --repo siarheirudak/rudax-keel-sandbix --base main --head attack-merge --title "attack: merge" --body "sandbox test"
gh pr merge --repo siarheirudak/rudax-keel-sandbix --merge
```

Expected: merge blocked. Review is required. The base branch policy prohibits the merge.

**Agent approves its own pull request**

```bash
gh pr review --repo siarheirudak/rudax-keel-sandbix --approve --body "self approve"
```

Expected: refused. You cannot approve your own pull request.

**Agent edits rulesets**

```bash
gh api --method POST repos/siarheirudak/rudax-keel-sandbix/rulesets -f name=attack-ruleset -f target=branch -f enforcement=active
gh api repos/siarheirudak/rudax-keel-sandbix/rulesets --jq '.[].id'
```

Expected: the POST is **403**. Listing ids may also be 403. If a number is returned, delete must fail too:

```bash
gh api --method DELETE repos/siarheirudak/rudax-keel-sandbix/rulesets/ID
```

Expected: **403**.

**Approve with GITHUB_TOKEN from a workflow**

On the `attack-merge` branch:

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
```

Expected: the job fails, or the review is refused and does not count. The token cannot approve pull requests.

**Edit CODEOWNERS without an owner review**

```bash
git switch -c attack-codeowners
printf '%s\n' '* @isiarheiridak-agent' > .github/CODEOWNERS
git add .github/CODEOWNERS
git commit -m "attack: rewrite CODEOWNERS"
git push -u origin attack-codeowners
gh pr create --repo siarheirudak/rudax-keel-sandbix --base main --head attack-codeowners --title "attack: CODEOWNERS" --body "sandbox test"
gh pr merge --repo siarheirudak/rudax-keel-sandbix --merge
```

Expected: merge refused. A code owner review is required. The agent is not the code owner.

## (d) Verify, as the owner

Back in the owner shell:

```bash
gh api user --jq .login
bash setup/verify-github-rules.sh siarheirudak/rudax-keel-sandbix isiarheiridak-agent
```

The login is the owner GitHub account. Expected: no FAIL. `require-checks` is NOT YET.

## (e) Record the results

The owner posts this comment on pull request **#3** in the template repository. The agent does not post it.

| Attack | Expected | Actual |
|---|---|---|
| Direct push to main | GH013, pull request required | |
| Force push | GH013, cannot force-push | |
| Delete main | GH013, cannot delete | |
| Create tag | GH013, cannot create | |
| Move tag | GH013, cannot update protected ref | |
| Delete tag | GH013, cannot delete | |
| Merge without approval | review required, merge prohibited | |
| Self-approve | refused | |
| Edit rulesets | 403 | |
| GITHUB_TOKEN approve | refused or does not count | |
| CODEOWNERS without owner review | review required, merge prohibited | |

## (f) Cleanup

In the agent shell, after the table is filled:

```bash
gh pr close --repo siarheirudak/rudax-keel-sandbix attack-merge
gh pr close --repo siarheirudak/rudax-keel-sandbix attack-codeowners
git push origin --delete attack-direct attack-merge attack-codeowners
git push origin :refs/tags/attack-test
```

Close any leftover pull requests in the sandbox UI. `attack-test` was never created if the tag push was rejected; a delete error for a missing tag is fine.

To reset rules, switch back to the owner shell and run apply again. Matching settings come back ALREADY. To remove the rulesets entirely, delete them under Settings → Rules → Rulesets, then run apply if you want them again. Do not delete the sandbox repository.
