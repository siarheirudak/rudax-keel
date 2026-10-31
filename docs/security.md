# Security

This page separates checks that refuse to run from checks that warn, and it records the v1 requirement that containers be rootless. The per-check write-up of the doctor that exists today is [Why each keel-doctor check exists](harness-checks-why.md). GitHub rules that already exist are in [Why these rules exist](why.md).

## The idea

An agent is untrusted about its own work. A host script checks the work. A container limits what the agent can touch while it works. GitHub limits what the bot account can do with the result.

Three layers carry that idea. Only the first two exist in the repository.

1. **GitHub.** The bot can open a pull request. The owner merges. Tag rules stop the bot from publishing a release. This is implemented. [GitHub setup](github-setup.md).
2. **The harness doctor and the host gate.** `setup/keel-doctor.sh` reports whether this machine can run the harness. `setup/keel.sh gate` rejects an exported bundle that breaks a path, history, or test rule. This is implemented.
3. **The v1 pipeline guards.** Per-role mounts, an egress proxy, a startup check that refuses a rootful daemon, fenced data, and the gates L4, L6, and L7. These are specified and not built. Where the prototype already does a piece of one, this page says so.

## Levels on the doctor

The doctor prints a level on every line.

- **CRITICAL.** A failed line (the mark is a cross, not a warning) makes the verdict NOT READY, and the doctor exits 1. Do not run agents on that machine.
- **RECOMMENDED.** A problem is a warning, or in one case a non-critical failure. The harness can still run. The verdict is READY WITH WARNINGS when nothing CRITICAL has failed.
- **OPTIONAL.** The doctor’s header names this level. No current check uses it.

A check can be labelled CRITICAL and still warn. ENV-01 does that for an operating system other than Linux: the line warns `untested OS`, and the verdict does not become NOT READY. ENV-02 warns when git is older than 2.30 and fails only when git is missing. The rule that changes the verdict is a CRITICAL line whose result is a failure.

The RECOMMENDED checks today are:

| Id | What it watches | What a problem means |
|---|---|---|
| ENV-05 | Whether the container runtime is rootless, or is Docker Desktop’s virtual machine | A rootful daemon on Linux warns. An escape from a container would be root on the host. The harness still starts |
| ENV-06 | The local `keel-git` image exists and matches the machine’s architecture | Missing or emulated. The first role will fail or run slowly |
| REPO-04 | The base repo is on `main` | The gate compares the bundle with `main`. A warning, not a stop |
| DISK-01 | Free space under the harness root | Under 10 GiB warns. Under 2 GiB fails this line. The level is still RECOMMENDED, so the verdict can remain READY WITH WARNINGS. Writable mounts have no quota |
| ATK-A10 | Garbage collection while a task is active | A partial result is expected. The other attack checks are CRITICAL |

Every other ENV, SEC, REPO, and attack check is CRITICAL when it fails. The full list, including what to do when a line fails, is [harness-checks-why.md](harness-checks-why.md).

Attack checks run only with `bash setup/keel-doctor.sh --attacks`. If a CRITICAL environment check has already failed, the suite is skipped and ATK-00 fails instead.

## Rootless containers

<a id="rootless"></a>

**Rootless** means the container daemon runs as an ordinary user. A bug that escapes the container does not become root on the host. Docker Desktop on macOS is a different boundary: containers run in a Linux virtual machine, and an escape lands in that virtual machine. The doctor accepts that boundary and says so on ENV-05.

In the v1 design, rootless Docker or rootless Podman is mandatory. A startup script refuses to run when the runtime is not rootless. That refusal is not what the doctor does today. ENV-05 is RECOMMENDED. A rootful Linux daemon warns, and the harness still runs.

The v1 startup check is one of the unbuilt steps in [Status](status.md). Until it exists, follow ENV-05’s own advice on a Linux host: install rootless Docker or Podman. The scripts were tested on Linux. macOS with Docker Desktop has not been run. On any other OS the doctor warns and does not refuse.

## Hardening the v1 design requires

The table compares the v1 requirement with `setup/keel.sh`, which applies one hardening set to every container it starts (role, setup, export, and the test re-run).

| Requirement in v1 | In `setup/keel.sh` today |
|---|---|
| Rootless Docker or Podman, refused at startup otherwise | Not refused. ENV-05 warns on a rootful Linux daemon |
| Drop all capabilities (`--cap-drop=ALL`) | Applied |
| `no-new-privileges` | Applied |
| Read-only root filesystem and a tmpfs for temporary files | Applied. The tmpfs is `/tmp`, size 64m |
| Memory, CPU, and process-count limits | Applied. Defaults are 512m, 1 CPU, and 128 processes, overridable with `MEM`, `CPUS`, and `PIDS` |
| A quota on the work directory | Not applied. DISK-01 reports free disk only |
| Developer network off, model API only through a proxy | Network is off for every container. There is no proxy and no model-API exception |
| Secrets live under a separate user | Not applied. The doctor instead fails when token variables are present in its own environment |
| Chromium’s sandbox stays on. No `--no-sandbox`. A seccomp profile for Chrome. Playwright is checked on the host before a container runs it | Not in the repository. QA is not built |

ENV-07 is the CRITICAL check that a throwaway container actually starts with the flags in the second through fifth rows. If those flags are rejected, the verdict is NOT READY.

The host gate adds checks the container flags do not. It rejects a bundle that touches a forbidden path, contains a symlink or a nested `.git`, has a merge commit, or fails the test entry taken from the default branch rather than from the bundle. Limits on bundle size, diff size, and file count have defaults in `setup/keel.sh` (`MAX_BUNDLE`, `MAX_LINES`, `MAX_FILES`). Those are harness limits, not the pipeline’s review-chunk or split thresholds.

## GitHub side

These are implemented, and they are CRITICAL to the account split in the same plain sense: without them the bot can change the default branch or a release tag.

- The default branch accepts changes only through a pull request, with one approval from a code owner, and stale approvals are dismissed. The owner can merge without a second reviewer. That bypass is pull requests only. It does not allow a direct push.
- Tags cannot be created, moved, or deleted except by an admin. The bot is not an admin.
- The default branch also requires the check-run names `keel-gate` and `keel-process-files-separate`, from GitHub Actions, on a branch that is up to date. A status posted with a user token does not satisfy the rule.
- A pull request that edits a process file must contain only process files. Process files are `.github/`, `scripts/`, and `setup/` at the root (except the whole paths `setup/README.md` and `setup/TESTING.md`, any case), plus `.pi/` and `.agents/` at any depth, such as `pkg/.pi/` and `apps/.agents/`. These names are process files anywhere, ignoring case: `AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md` (the fallback context file Pi Agent loads), `CODEOWNERS`, and `.shellcheckrc`. The host gate also forbids `.gitmodules`.
- The default Actions token can read and cannot approve pull requests.
- The bot is invited with write, not admin. Apply will not demote an account that already has admin. That step fails and leaves the role unchanged.

Each rule’s failure mode is in [why.md](why.md). On a personal repository, GitHub cannot limit the merge button to a single person. The project rule is still that the owner merges. [Who merges](why.md#who-merges).

## Tokens

<a id="tokens"></a>

The design keeps a GitHub token in one place: the push step that opens the pull request. Agent containers and the host gate do not receive it.

Today, `push-stub` has no token and does not push. SEC-01 fails the doctor when `GH_*`, `GITHUB_*`, or `BOT_GH_TOKEN` is set in the doctor’s environment. The check prints variable names, not values. The attack suite checks that those variables are not visible inside a role container.

## Fenced data

Fencing is a v1 requirement on the reasoning plane. Every role receives repository files, ADRs, discoveries, and skills as data, not as instructions. The same fence wraps diffs at review. This is specified so that text inside the project cannot redirect an agent. The current harness does not wrap file contents. It relies on mounts, the read-only git pointer, and the host gate.

## Related

[Roles and visibility](roles.md) · [Getting started](harness-getting-started.md) · [Implementation status](status.md)
