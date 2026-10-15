# Setup

`gh` logged in as the owner GitHub account with admin on the repo, via `gh auth login`. Never the agent's token.

From the repository root:

```bash
bash setup/setup.sh OWNER/REPO AGENT_LOGIN
bash setup/verify.sh OWNER/REPO AGENT_LOGIN
```

Example:

```bash
bash setup/setup.sh siarheirudak/rudax-keel isiarheiridak-agent
bash setup/verify.sh siarheirudak/rudax-keel isiarheiridak-agent
```

Logs: `setup/logs/setup-<timestamp>.log` and `setup/logs/verify-<timestamp>.log` (gitignored).

`OK` succeeded. `SKIPPED` already done. `FAIL` needs a fix; the script exits non-zero if any step failed.

- Not admin: `gh auth login` as the owner account that administers the repo.
- Empty repo: push an initial commit to the default branch, then re-run.
- Invite pending: the agent must accept the collaborator invitation.
