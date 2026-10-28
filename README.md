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

## Agent isolation harness

The harness runs each agent role in a hardened container. Work stays in a shadow git directory. Export is a git bundle. A host gate with no token checks that bundle before anything is published. How to run it on your machine: [Getting started](docs/harness-getting-started.md).

## Layer 2: CI checks

A status check is a pass or fail name GitHub stores on a commit. The names this layer requires are `keel-gate` and `keel-process-files-separate`. Those are the check-run names (the job `name:`). The Actions page shows `checks / keel-gate`. That display text is not the name the ruleset uses.

`keel-gate` fails if any other job in [`.github/workflows/checks.yml`](.github/workflows/checks.yml) failed, was cancelled, or was skipped. The workflow also runs on `edited`, so changing the pull request base runs the gate again and a green result from another base does not stay. This repository's own tests go in `project_checks()` in [`scripts/check.sh`](scripts/check.sh), and nowhere else. The workflow `project` job only runs `bash scripts/check.sh --project-only`. Until you add some, it prints `no project checks yet` and passes. `bash scripts/check.sh` runs the same checks on your machine. The template's own check tests live in `scripts/tests/`. Product tests live in `tests/`.

`require-checks` requires both names, and only from GitHub Actions (`integration_id` 15368). The branch must be up to date with the default branch. Apply creates the ruleset only after both workflow files are on the default branch and a check run with each exact name, from app 15368, exists. `keel-gate` can be a push to the default branch or a pull request. `keel-process-files-separate` runs only on pull requests, on any branch. Until both names have reported, the step is NOT YET. The reason lists the names that reported and the names still missing. [Why](docs/why.md#require-checks).

A success status posted with a user token does not count. That stops a mistake and a fake status. It does not stop a deliberately malicious agent. An agent with write can push a workflow, on some other branch, that requests `checks: write` and posts a successful check run of the required name onto the pull request head. That run still belongs to app 15368, and the workflow is not in the pull request diff. The checks catch mistakes and honest failures, and they block a merge while they are red. Against a deliberately malicious agent, the owner review is the control. A later layer may move the gate to an owner-owned GitHub App whose key only the default branch can use.

`scope` runs on `pull_request_target` for `opened`, `synchronize`, `reopened`, and `edited`, so changing the base runs it again. The workflow file is the one on the pull request's base branch. The job does not check out the pull request, and the token can only read. That is safe. Checking out pull request code, or giving the token write, would not be. The check fails if the base is not the default branch. A pull request that edits a process file must contain only process files. A rename counts the new path and the old path. Process files are `.github/`, `setup/`, `scripts/`, `.cursor/`, `.claude/`, and the names `CODEOWNERS`, `AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md`, `.cursorrules`, `.windsurfrules`, `.clinerules`, `.mcp.json`, and `.shellcheckrc`. `scripts/` counts because CI runs it from the pull request. `tests/` does not. A process-only pull request can weaken `checks.yml`. Owner review of process-only pull requests is the control, by design. [Why](docs/why.md#scope).

## Private repository on GitHub Free

Rulesets are not available. The agent GitHub account could push directly to the default branch, with no review, and checks are only advisory. Make the repository public, or use GitHub Pro. Apply prints that warning and continues only if you type `yes` or pass `--accept-risk`. The ruleset steps stay FAIL, because GitHub will not create them.
