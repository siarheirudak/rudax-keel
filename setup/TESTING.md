# Sandbox test

Live test for this layer, on a disposable repository: <https://github.com/siarheirudak/rudax-keel-sandbix>

Run this only on that sandbox. Do not point the scripts at the template repository.

## Prerequisites

- The sandbox is **public**, or it is **private on GitHub Pro** (or another plan that includes rulesets). If apply prints the GitHub Free private warning, stop. Do not pass `--accept-risk`. The attacks below would not be blocked, so the test does not count.
- `gh auth login` as the **owner GitHub account** (the account that admins the sandbox). Never the agent GitHub account's token.
- `gh` and `jq` are installed.
- You have the `setup/github-protection` branch checked out (the open pull request for this layer).

```bash
gh api user -q .login
git checkout setup/github-protection
```

The login must be the owner GitHub account, not `isiarheiridak-agent`.

## Apply, then verify

From the repository root:

```bash
bash setup/apply-github-rules.sh siarheirudak/rudax-keel-sandbix isiarheiridak-agent
bash setup/verify-github-rules.sh siarheirudak/rudax-keel-sandbix isiarheiridak-agent
```

Expected on this layer:

- `require-checks` is **SKIPPED**, with the reason `CI not added yet; re-run after layer 2 merge`.
- `protect-main` and `protect-tags` are OK (or SKIPPED if you run apply again).
- The agent GitHub account is invited with write. It must **accept** the invitation. Until it does, verify's agent-role step is FAIL. Accept, then re-run verify.
- No step is FAIL.

## Attacks

Do these as a cloud agent, using the **agent GitHub account** (`isiarheiridak-agent`), after verify passes. Each one must be rejected.

1. **Direct push to the default branch.** Push a commit to `main`. Expected: push declined, `GH013`, `Changes must be made through a pull request`.
2. **Force push.** Force-push to `main`. Expected: `GH013` and `Cannot force-push to this branch`.
3. **Merge its own pull request.** Open a pull request as the agent GitHub account, then `gh pr merge` with no review from the owner GitHub account. Expected: merge blocked, review required, the base branch policy prohibits the merge.
4. **Tags.** Create a tag, move an existing tag, and delete a tag. Expected: `GH013`, and a message that the ref cannot be created, cannot be updated (`protected ref`), or cannot be deleted.

## If something passes

Stop. Do not merge pull request **#3**. Re-run verify, fix the rules, and repeat the attacks.

Merge pull request **#3** only if every attack above is blocked.
