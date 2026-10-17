# Setup

`gh` logged in as the owner GitHub account, with admin on the repo (`gh auth login`). Never the agent GitHub account's token. No config file: the script uses the account that `gh` is logged in as.

From the repository root:

```bash
bash setup/apply-github-rules.sh OWNER/REPO AGENT_LOGIN
bash setup/verify-github-rules.sh OWNER/REPO AGENT_LOGIN
```

Apply is safe to re-run after each layer merge. Settings that already match are left as they are. CODEOWNERS is fixed before `protect-main`.

Private repository on GitHub Free: rulesets do not exist. Continue only with `--accept-risk`, or by typing `yes`. The ruleset lines stay FAIL.

Logs: `setup/logs/apply-<timestamp>.log` and `setup/logs/verify-<timestamp>.log` (gitignored). Each line links to [docs/why.md](../docs/why.md).

- **OK** — just applied.
- **ALREADY** — was already correct.
- **NOT YET** — intentionally later. `require-checks` is NOT YET until `checks.yml` exists.
- **FAIL** — not done. The script exits non-zero if any step is FAIL. A line that names a Settings page is a manual step the API cannot do.

An unpinned `uses:` is OK with a reason starting `warning:`.

- Not an admin: `gh auth login` as the owner GitHub account that administers the repo.
- Empty repo: push an initial commit to the default branch, then re-run.
- Invite pending: the agent GitHub account must accept the collaborator invitation.

Sandbox test: [TESTING.md](TESTING.md).
