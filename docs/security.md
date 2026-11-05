# Security

This page separates checks that refuse to run from checks that warn, and it records the v1 requirement that containers be rootless. The per-check write-up of the doctor that exists today is [Why each keel-doctor check exists](harness-checks-why.md). GitHub rules that already exist are in [Why these rules exist](why.md).

## The idea

An agent is untrusted about its own work. A host script checks the work. A container limits what the agent can touch while it works. GitHub limits what the bot account can do with the result.

Three layers carry that idea. The first two exist in the repository. The third is only partly built.

1. **GitHub.** The bot can open a pull request. The owner merges. Tag rules stop the bot from publishing a release. This is implemented. [GitHub setup](github-setup.md).
2. **The harness doctor and the host gate.** `setup/keel-doctor.sh` reports whether this machine can run the harness. `setup/keel.sh gate` rejects an exported bundle that breaks a path, history, or test rule. This is implemented.
3. **The v1 pipeline guards.** Per-role folder mounts and the developer egress proxy are implemented in the harness. A startup check that refuses a rootful daemon, fenced data, and the gates L4, L6, and L7 are specified and not built.

## What a role can see

`setup/keel.sh role` and `role-env` mount only the folder roots in `setup/allow/<role>.paths`. An unknown name, an empty list, a glob, or a path that escapes the tree refuses the launch. There is no whole-tree fallback.

`setup/deny/base` withholds secret basenames and the harness paths `.keel/logs/`, `.keel/runs/`, `.keel/deny.local`, and `.git`. `.keel/decisions/` is withheld from every role except the orchestrator and the architect. `.agents/` is withheld. `.agents/skills` is granted to every launchable role and is mounted read-only from a snapshot of the main branch. The rest of `.agents/` stays withheld. A project may add paths in `.keel/deny.local`. It cannot remove a base entry. The project file is read once per task. Roles cannot read or write it.

`.keel/decisions/<task-id>/` is in the product git tree when a task records it. The orchestrator can write it. The architect can read it. A public product repository publishes those files. The harness prints that warning once and does not store task decisions itself. This repository does not commit any.

Every launch appends one JSON object to `$KEEL_ROOT/.keel/logs/launch.jsonl`. The harness is the only writer. A record has `redactions` set to the number of replacements. A replacement is `[REDACTED:token]`, `[REDACTED:key]`, `[REDACTED:password]`, `[REDACTED:env]`, or `[REDACTED:unknown]`. If a value would still be present, the record is refused. Role output is not copied into the log. Cleanup does not delete the log. There is no size cap yet.

`$KEEL_ROOT/.keel/runs/` is temporary mount state. It is removed when the command exits. The task deny snapshot is removed by `cleanup` and when `setup` fails. `.keel/logs/` and `.keel/runs/` are gitignored.

Changing what a role can see is a `process-files` pull request, then review, then an owner merge.

These remain outside this step:

- A secret renamed so its basename is not in `setup/deny/base` is still visible. Content scanning is not in this step.
- A secret-named file created inside an already mounted read-write directory during that same command can be read until the command ends. The next launch withholds a matching basename.
- A read-only bind inside a read-write parent is how a withheld file stays unreadable. The suite checks that shape.

## Levels on the doctor

The doctor prints a level on every line.

- **CRITICAL.** A failed line (the mark is a cross, not a warning) makes the verdict NOT READY, and the doctor exits 1. Do not run agents on that machine.
- **RECOMMENDED.** A problem is a warning, or in one case a non-critical failure. The harness can still run. The verdict is READY WITH WARNINGS when nothing CRITICAL has failed.
- **OPTIONAL.** The doctor’s header names this level. No current check uses it.

A check can be labelled CRITICAL and still warn. ENV-01 does that for an operating system other than Linux: the line warns `untested OS`, and the verdict does not become NOT READY. ENV-02 warns when git is older than 2.30 and fails only when git is missing. The rule that changes the verdict is a CRITICAL line whose result is a failure.

The RECOMMENDED checks today are:

| Id | What it watches | What a problem means |
|---|---|---|
| ENV-06 | The local `keel-git` image exists and matches the machine’s architecture | Missing or emulated. The first role will fail or run slowly |
| REPO-04 | The base repo is on `main` | The gate compares the bundle with `main`. A warning, not a stop |
| DISK-01 | Free space under the harness root | Under 10 GiB warns. Under 2 GiB fails this line. The level is still RECOMMENDED, so the verdict can remain READY WITH WARNINGS. Writable mounts have no quota |
| ATK-A10 | Garbage collection while a task is active | A partial result is expected. The other attack checks are CRITICAL |

ENV-05 is CRITICAL. A rootful Linux daemon fails it, and the verdict is not ready. Every other ENV, SEC, REPO, and attack check is CRITICAL when it fails. The full list, including what to do when a line fails, is [harness-checks-why.md](harness-checks-why.md).

Attack checks run only with `bash setup/keel-doctor.sh --attacks`. If a CRITICAL environment check has already failed, the suite is skipped and ATK-00 fails instead.

## Rootless containers

<a id="rootless"></a>

**Rootless** means the container daemon runs as an ordinary user. A bug that escapes the container does not become root on the host. Docker Desktop on macOS is a different boundary: containers run in a Linux virtual machine, and an escape lands in that virtual machine. ENV-05 records that as an isolation pass. It does not mean egress works there.

ENV-05 is CRITICAL. On Linux the daemon passes only when `SecurityOptions` contains `rootless`, or when Podman is rootless. A rootful Linux daemon fails the check. `role`, `proto`, `export`, and the other commands that start a container then refuse. The socket path is not the signal. There is no environment switch that turns the failure into a pass.

Install rootless Docker or rootless Podman on a Linux host. The scripts were tested on Linux. macOS with Docker Desktop has not been run end to end. On any other OS the doctor warns about the OS and does not treat that OS line as a rootless pass.

## Hardening the v1 design requires

The table compares the v1 requirement with `setup/keel.sh`, which applies one hardening set to every container it starts (role, setup, export, and the test re-run).

| Requirement in v1 | In `setup/keel.sh` today |
|---|---|
| Rootless Docker or Podman, refused at startup otherwise | ENV-05 is critical. Linux passes only when `SecurityOptions` contains the `rootless` token, or when Podman reports `Host.Security.Rootless`. The socket path is not proof. Docker Desktop on Darwin is an isolation pass only: an escape lands in the Desktop VM, and that pass does not mean egress works. A rootful Linux daemon fails the check |
| Drop all capabilities (`--cap-drop=ALL`) | Applied |
| `no-new-privileges` | Applied |
| Read-only root filesystem and a tmpfs for temporary files | Applied. The tmpfs is `/tmp`, size 64m |
| Memory, CPU, and process-count limits | Applied. Defaults are 512m, 1 CPU, and 128 processes, overridable with `MEM`, `CPUS`, and `PIDS`. `--memory-swap` is set equal to `--memory`. A cgroup `memory.swap.max` of `max` is not proof that pin held |
| A quota on the work directory | Soft free-space check only (`DISK-02`, critical). Below the configured minimum, startup is not ready and `setup` / `role` refuse. Hard filesystem quotas (XFS project quotas, ZFS datasets) are optional host operations, not required here |
| Developer network off, model API only through a proxy | The developer joins the internal network `keel-egress` and uses the forward proxy. Every other role, `proto`, setup, export, and the test re-run stay on `--network none`. The shipped allowlist names the CI mock, not a vendor model API |
| Secrets live under a separate user | Not a separate account in this step. Roles still do not hold secret values. The discoveries judge is a oneshot broker: it alone reads the key file and calls the Decisions API. A broker for the push step is still later work |
| Chromium’s sandbox stays on. No `--no-sandbox`. A seccomp profile for Chrome. Playwright is checked on the host before a container runs it | The helper refuses `--no-sandbox` and `--disable-setuid-sandbox`. No browser is started. Playwright absent is not a failed startup. A Chromium run under rootless belongs to the QA step |

ENV-07 is the CRITICAL check that a throwaway container actually starts with the flags in the second through fifth rows. If those flags are rejected, the verdict is NOT READY.

The host gate adds checks the container flags do not. It rejects a bundle that touches a forbidden path, contains a symlink or a nested `.git`, has a merge commit, or fails the test entry taken from the default branch rather than from the bundle. Limits on bundle size, diff size, and file count have defaults in `setup/keel.sh` (`MAX_BUNDLE`, `MAX_LINES`, `MAX_FILES`). Those are harness limits, not the pipeline’s review-chunk or split thresholds.

## GitHub side

These are implemented, and they are CRITICAL to the account split in the same plain sense: without them the bot can change the default branch or a release tag.

- The default branch accepts changes only through a pull request, with one approval from a code owner, and stale approvals are dismissed. The owner can merge without a second reviewer. That bypass is pull requests only. It does not allow a direct push.
- Tags cannot be created, moved, or deleted except by an admin. The bot is not an admin.
- The default branch also requires the check-run names `keel-gate` and `keel-process-files-separate`, from GitHub Actions, on a branch that is up to date. A status posted with a user token does not satisfy the rule.
- A pull request that edits a process file must contain only process files. Process files are `.github/`, `scripts/`, and `setup/` at the root (except the whole paths `setup/README.md` and `setup/TESTING.md`, any case), plus `.pi/` and `.agents/` at any depth, such as `pkg/.pi/` and `apps/.agents/`. These names are process files anywhere, ignoring case: `AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md` (the fallback context file Pi Agent loads), `CODEOWNERS`, and `.shellcheckrc`. The host gate also forbids a path whose basename is `.gitmodules`, including `lib/.gitmodules`.
- The default Actions token can read and cannot approve pull requests.
- The bot is invited with write, not admin. Apply will not demote an account that already has admin. That step fails and leaves the role unchanged.

Each rule’s failure mode is in [why.md](why.md). On a personal repository, GitHub cannot limit the merge button to a single person. The project rule is still that the owner merges. [Who merges](why.md#who-merges).

## Tokens

<a id="tokens"></a>

Roles do not hold secret values, and the harness does not pass the host environment into a role container. A key for the discoveries judge lives only in the oneshot broker in `setup/lib/discovery_judge.py`. That process reads the key file, adds `Authorization` on its own request, and calls `POST https://openrouter.ai/api/alpha/decisions` on `openrouter.ai`. It does not accept another path on that host. Role containers, the filter, and the promote command do not read the file. The doctor checks that the path is present and private outside CI, and it does not print or read the value. In CI the judge is a stub, and a live key is not required. The stub is refused when the CI marker is absent. The push step still has no broker and does not push.

`role` and `role-env` refuse to start, with a non-zero exit and a refuse line that names the variable and not its value, when the launching environment contains any exact name on `LAUNCH_DENY_ENV` in `setup/lib/visibility.py`. That list is the existing `SECRET_ENV` names plus `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, and `OPENROUTER_API_KEY`. It is not a prefix match. The judge does not receive the key through that environment. A role cannot open a connection to the judge. The judge is not attached to `keel-egress`.

A renamed variable is not on that list. Format-pattern redaction in the launch log is the backstop for token prefixes, `sk-` and `sk-ant-` keys, PEM private key blocks, and `password=`, `api_key=`, and `token=` assignments. The host gate scans the files added or edited in the change with gitleaks 8.30.1 and fails the bundle when one of those shapes is present. The binary is pinned by version and checksum and is installed before the gate runs; the gate itself does not download it. `GL-01` is critical: the binary must be present and report `8.30.1`.

The scan passes `--config` and `--gitleaks-ignore-path` pointing at harness files, and `--ignore-gitleaks-allow`, so an inline `gitleaks:allow` comment does not suppress a finding. A `.gitleaksignore` or `.gitleaks.toml` added in the change is not loaded. The harness config also ignores the obvious fixture tokens used by the harness tests. That is not the only suppression control. A timeout, or any scanner exit other than a clean pass, fails the gate.

The scan does not read git history. A secret that is encoded so it no longer matches these shapes is not caught. A secret split across files is not caught. Text sent to an allowlisted model provider is an accepted residual: the proxy allows the connection, and this log does not see the body.

The launch log does not read environment values. A denylisted name refuses the launch. Text that reaches the log is redacted only when it matches a format pattern.

Today, `push-stub` has no token and does not push. SEC-01 fails the doctor when `GH_*`, `GITHUB_*`, or `BOT_GH_TOKEN` is set in the doctor’s environment. The check prints variable names, not values. The attack suite checks that a denylisted name refuses the role and that a clean environment can start one.

## Fenced data

Fencing is a v1 requirement on the reasoning plane. Every role receives repository files, ADRs, discoveries, and skills as data, not as instructions. The same fence wraps diffs at review. This is specified so that text inside the project cannot redirect an agent. The current harness does not wrap file contents. It relies on mounts, the read-only git pointer, and the host gate.

## Related

[Roles and visibility](roles.md) · [Getting started](harness-getting-started.md) · [Implementation status](status.md)
