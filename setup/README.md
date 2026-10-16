# Setup

`gh` logged in as the owner GitHub account, with admin on the repo (`gh auth login`). Never the agent GitHub account's token. No config file: the script uses the account that `gh` is logged in as.

From the repository root:

```bash
bash setup/apply-github-rules.sh OWNER/REPO AGENT_LOGIN
bash setup/verify-github-rules.sh OWNER/REPO AGENT_LOGIN
```

Apply is safe to re-run after each layer merge. Settings that already match are left as they are.

Private repository on GitHub Free: rulesets do not exist. Continue only with `--accept-risk`, or by typing `yes`.

Logs: `setup/logs/apply-<timestamp>.log` and `setup/logs/verify-<timestamp>.log` (gitignored). Each step is `OK`, `SKIPPED`, or `FAIL`, and links to [docs/why.md](../docs/why.md).

`OK` done. `SKIPPED` already in place, or not applicable yet. `FAIL` needs a fix. The script exits non-zero if any step failed.

- Not an admin: `gh auth login` as the owner GitHub account that administers the repo.
- Empty repo: push an initial commit to the default branch, then re-run.
- Invite pending: the agent GitHub account must accept the collaborator invitation.

Sandbox test: [TESTING.md](TESTING.md).
