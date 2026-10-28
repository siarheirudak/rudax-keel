# rudax-keel

Rudax Keel is a guarded production line for building software with AI agents.

_The keel is laid first; everything else is built on it._

An **agent** is a program that uses a language model to propose a design, tests, or code. A **host script** is an ordinary program on the machine that runs the pipeline. A host script does not ask a model what to believe. It checks files, tests, and git history, and it accepts or rejects the result.

The **owner** is the human who decides. In this repository that person is Sergei, GitHub login `siarheirudak`. The **bot** is the GitHub account `isiarheiridak-agent`. The bot has write access. It opens pull requests. It is not an admin, so it cannot change the rules that constrain it.

## The idea

The pipeline does not trust an agent’s own report. Every claim an agent makes is checked by a host script before the next step starts. Agents propose. Scripts verify. The owner decides what is merged and what is released.

That split is what **zero-trust** means here. “Zero” is about the agent’s word, not about ignoring evidence. A passing script, a test the implementer never saw, and the owner’s approval are evidence. A sentence from the agent that says “done” is not.

Two planes do the work:

- The **reasoning plane** is the agents. In the v1 design they run as **Pi Agent** (the program that hosts the model roles) inside a container. Pi Agent is not in this repository, and those roles are not wired up yet.
- The **control plane** is the host scripts. They own the guarantees: what a role is allowed to see, whether tests really failed for the right reason, whether the files that were reviewed are the files being merged, and who is allowed to push.

GitHub is the last gate on the control plane that already exists. The bot (or any program holding only the bot’s token) can open a pull request. The owner merges it. [GitHub setup](docs/github-setup.md) is that gate. [Why these rules exist](docs/why.md) explains each one.

## What a task is

A **task** is one piece of work that starts from a message the owner types and ends when a pull request is merged, or when the cycle stops with a written failure record.

The v1 design runs a task through a chain of **links**, named L0 through L11. A link is one step with a purpose, an actor, inputs, outputs, and a limit on how many times it may be retried. Some links are agents. Some are scripts. A few pause until the owner answers.

The older docs in this repository also say **layer**. A layer is a slice that is already shipped: layer 1 is GitHub protection, layer 2 is the CI checks. A layer is not a link. The links are the planned production line. The layers are what you can run today.

The full chain, including who acts at each link and what stops it, is in [Architecture](docs/architecture.md) and [Pipeline](docs/pipeline.md).

## Roles

| Who | Kind | What they do |
|---|---|---|
| Owner | Human | Answers questions, approves skills and splits, merges, releases |
| Bot `isiarheiridak-agent` | GitHub account | Opens pull requests. Does not merge and does not release |
| Orchestrator, architect, critic, tester, developer, auditor, design reviewer, verifier, QA, researcher | Agents (planned) | Reason about one part of the task, inside a container |
| Host scripts | Programs | Package context, run gates, install dependencies, open the pull request, write the log |

What each role is allowed to see is a **deny-list**: a role can read the repository except for paths the list withholds, and the withheld paths are simply not mounted into that role’s container. The list can only grow. Details: [Roles and visibility](docs/roles.md).

## Where to read

| Question | Page |
|---|---|
| How does a task move from a chat message to a release? | [Architecture](docs/architecture.md) |
| What does each link take in, produce, and refuse? | [Pipeline](docs/pipeline.md) |
| Who can see which files? | [Roles and visibility](docs/roles.md) |
| Which checks are mandatory, and which only warn? | [Security](docs/security.md) |
| What standard do reviewers apply? | [Quality standard](docs/quality.md) |
| When does the owner have to decide? | [Human decisions](docs/decisions.md) |
| How are decisions and pitfalls remembered? | [Discoveries and ADRs](docs/discoveries.md) |
| What is written down while a task runs? | [Logging and the task journal](docs/logging.md) |
| What does a term mean? | [Glossary](docs/glossary.md) |
| What is built, and what is only specified? | [Implementation status](docs/status.md) |

## Quick start

Two things in this repository run today: the GitHub rules, and a local isolation harness. Neither one is the L0–L11 pipeline. The pipeline is specified and not built. [Status](docs/status.md) is the checklist.

### GitHub rules

Use two accounts. The owner account is an admin. The bot account gets write, not admin. Log in to `gh` as the owner and, from the repository root:

```bash
bash setup/apply-github-rules.sh OWNER/REPO AGENT_LOGIN
bash setup/verify-github-rules.sh OWNER/REPO AGENT_LOGIN
```

There is no config file. The script reads the logged-in account, and the repository visibility and plan, from GitHub. Commands and log lines: [setup/README.md](setup/README.md).

On a private repository on GitHub Free, rulesets are not available. Apply prints a warning and continues only if you type `yes` or pass `--accept-risk`. The ruleset steps stay failed, because GitHub will not create them. [Why](docs/why.md#free-private-risk).

The bot must run where the only GitHub token is the bot’s token: a cloud VM, a separate OS user, or a container. It must not run in a login where the owner is already authenticated. [Why](docs/why.md#agent-environment).

### Isolation harness

The harness runs a command inside a hardened container, keeps the work in a shadow git directory, exports a git bundle, and checks that bundle on the host. The host check holds no GitHub token. The push step is a stub: it prints the command it would run and does not push.

```bash
bash setup/keel-doctor.sh
bash setup/tests/harness/run-tests.sh
```

How to read the output: [Getting started](docs/harness-getting-started.md). Why each doctor line exists: [Harness checks](docs/harness-checks-why.md).

The v1 design requires a rootless container runtime and will refuse to start without one. The doctor in this repository still treats a rootful Linux daemon as a warning. [Security](docs/security.md#rootless).
