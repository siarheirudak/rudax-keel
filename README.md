# rudax-keel

_The keel is laid first; everything else is built on it._

A template for building software with AI agents safely. The agent GitHub account proposes changes. The owner GitHub account decides what reaches the default branch.

## Three steps

1. Use two accounts. The owner GitHub account is an admin. The agent GitHub account gets write, not admin. See [GitHub setup](docs/github-setup.md).
2. Log in to `gh` as the owner GitHub account and apply the rules: `bash setup/apply-github-rules.sh OWNER/REPO AGENT_LOGIN`
3. Check them: `bash setup/verify-github-rules.sh OWNER/REPO AGENT_LOGIN`

There is no config file. The script reads the logged-in account, and the repository visibility and plan, from GitHub. Commands and logs: [setup/README.md](setup/README.md). Why each rule exists: [docs/why.md](docs/why.md).

## Private repository on GitHub Free

Rulesets are not available. The agent GitHub account could push directly to the default branch, with no review, and checks are only advisory. Make the repository public, or use GitHub Pro. Apply prints that warning and continues only if you type `yes` or pass `--accept-risk`.

_More steps are added here one at a time, each only after the previous one is proven to work._
