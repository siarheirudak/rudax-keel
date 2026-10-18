# rudax-keel

Rudax Keel — a guarded production line for building software with AI agents.

_The keel is laid first; everything else is built on it._

A template for building software with AI coding agents safely. The agent GitHub account proposes changes. The owner GitHub account decides what reaches the default branch.

A **layer** is one proven step of this template. Layer 1 is GitHub protection. Layer 2 is CI checks.

## Three steps

1. Use two accounts. The owner GitHub account is an admin. The agent GitHub account gets write, not admin. See [GitHub setup](docs/github-setup.md).
2. Log in to `gh` as the owner GitHub account and apply the rules: `bash setup/apply-github-rules.sh OWNER/REPO AGENT_LOGIN`
3. Check them: `bash setup/verify-github-rules.sh OWNER/REPO AGENT_LOGIN`

There is no config file. The script reads the logged-in account, and the repository visibility and plan, from GitHub. Commands and logs: [setup/README.md](setup/README.md). Why each rule exists: [docs/why.md](docs/why.md).

## Where the coding agent runs

A coding agent is any AI coding agent: Cursor cloud or local, Claude Code, and others. Protection holds only if that agent runs in an environment that has only the agent GitHub account's token (a cloud VM, a separate OS user, or a container). It must not run where the owner is logged in, for example a local `gh` login as the owner. Otherwise the agent can act as the owner. [Why](docs/why.md#agent-environment).

## Layer 2: CI checks

A status check is a pass or fail name GitHub stores on a commit. This layer uses `checks / gate` and `scope / process-files-separate`.

`gate` fails if any other job in [`.github/workflows/checks.yml`](.github/workflows/checks.yml) failed, was cancelled, or was skipped. Put this repository's own tests in that file's `project` job (the comments show `npm test`, `pytest`, and `go test`). Until you add some, the job prints `no project checks yet` and passes. `bash scripts/check.sh` runs the same checks on your machine.

`require-checks` requires both names. The branch must be up to date with the default branch before it can merge. Each name is limited to GitHub Actions (`integration_id` 15368), so a success status posted through the API does not count. Apply creates the ruleset only after both workflow files are on the default branch and each check has reported once. Until then the step is NOT YET. [Why](docs/why.md#require-checks).

`scope` runs on `pull_request_target`, so the workflow is the copy on the default branch. The job does not check out the pull request, and the token can only read. That is safe. Checking out pull request code, or giving the token write, would not be. A pull request that edits process files (`.github/`, `setup/`, `scripts/`, `CODEOWNERS`, agent rule files) must contain only those files. `scripts/` counts because CI runs it from the pull request. `tests/` does not. [Why](docs/why.md#scope).

## Private repository on GitHub Free

Rulesets are not available. The agent GitHub account could push directly to the default branch, with no review, and checks are only advisory. Make the repository public, or use GitHub Pro. Apply prints that warning and continues only if you type `yes` or pass `--accept-risk`. The ruleset steps stay FAIL, because GitHub will not create them.
