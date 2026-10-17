# rudax-keel

_The keel is laid first; everything else is built on it._

A template for building software with AI coding agents safely. The agent GitHub account proposes changes. The owner GitHub account decides what reaches the default branch.

A **layer** is one proven step of this template. This page is layer 1, GitHub protection. The next layer is added only after this one works.

## Three steps

1. Use two accounts. The owner GitHub account is an admin. The agent GitHub account gets write, not admin. See [GitHub setup](docs/github-setup.md).
2. Log in to `gh` as the owner GitHub account and apply the rules: `bash setup/apply-github-rules.sh OWNER/REPO AGENT_LOGIN`
3. Check them: `bash setup/verify-github-rules.sh OWNER/REPO AGENT_LOGIN`

There is no config file. The script reads the logged-in account, and the repository visibility and plan, from GitHub. Commands and logs: [setup/README.md](setup/README.md). Why each rule exists: [docs/why.md](docs/why.md).

## Where the coding agent runs

A coding agent is any AI coding agent: Cursor cloud or local, Claude Code, and others. Protection holds only if that agent runs in an environment that has only the agent GitHub account's token (a cloud VM, a separate OS user, or a container). It must not run where the owner is logged in, for example a local `gh` login as the owner. Otherwise the agent can act as the owner. [Why](docs/why.md#agent-environment).

## Private repository on GitHub Free

Rulesets are not available. The agent GitHub account could push directly to the default branch, with no review, and checks are only advisory. Make the repository public, or use GitHub Pro. Apply prints that warning and continues only if you type `yes` or pass `--accept-risk`. The ruleset steps stay FAIL, because GitHub will not create them.
