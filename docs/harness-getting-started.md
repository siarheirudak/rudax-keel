# Getting started

The agent isolation harness (variant 2: a shadow `.git` with alternates, hardened containers, export by `git bundle`, a host gate with no token) lives in this repository under `setup/`. It runs on your machine, creates a **throwaway** git repo, and never touches GitHub or any token. Every role except the developer has no network. The developer joins an internal network and an explicit forward proxy. [Roles and visibility](roles.md#network).

Commands below are from the repository root.

## 1. Prerequisites

| | Linux | macOS (untested) | Windows |
|---|---|---|---|
| Shell | bash 3.2+ | built-in `/bin/bash` 3.2 is what `setup/lib/portable.sh` targets | untested (WSL2 is the likely path) |
| git | `sudo apt install git` | `xcode-select --install` (Xcode Command Line Tools), or `brew install git` | |
| Containers | `sudo apt install docker.io`, then `sudo usermod -aG docker $USER` and log in again (or use `DOCKER="sudo docker"`) | [Docker Desktop](https://www.docker.com/products/docker-desktop/), started, showing "Engine running" | |
| Disk | 2 GiB free for the DISK-01 warning band. `DISK-02` is critical and uses `KEEL_WORK_MIN_FREE` (512 MiB unless you set it). Hard filesystem quotas are optional host setup | same | |

`setup/keel.sh` says Linux is the tested host and that macOS with Docker Desktop has not been run. The `keel-git` image is built from `setup/docker/keel-git.Dockerfile` (Alpine and git, no platform pin), so `docker build` produces a native image. The script accepts `DOCKER=podman` and adds `--userns=keep-id` in that case. The egress network and the proxy have not been verified on Docker Desktop or Podman, and that path is unsupported for now.

ENV-05 is critical. On Linux the daemon passes only when `docker info` reports `rootless` in `SecurityOptions`, or when Podman is rootless. Install rootless Docker with `dockerd-rootless-setuptool.sh install`, or use rootless Podman. A rootful Linux daemon makes the doctor not ready. Docker Desktop on a Mac can pass that isolation line because containers run in its Linux VM; that pass does not mean the egress network works there, and Docker Desktop and Podman stay unsupported for egress. A hosted CI machine is often rootful. ENV-05 fails there, and the commands that start a container refuse. [Security](security.md#rootless).

## 2. Run it

```bash
bash setup/tests/harness/run-tests.sh
# Linux without the docker group:
DOCKER="sudo docker" bash setup/tests/harness/run-tests.sh
```

`setup/tests/harness/run-tests.sh` does the following:

`setup/check.sh` runs first. It reads `git ls-files -s` for every shell script the harness executes directly (`"$HERE/….sh"` or `"$SETUP/….sh"` as a command). A file whose mode is not `100755` stops the run, and the message names that file. A script started with `bash` and a sourced file are not in that set.

1. Runs `setup/tests/harness/test-mutant-select.py`, `setup/tests/harness/test-mutate-plan.sh`, and `setup/tests/harness/test-attack-results.sh`. A missing base commit must fail. The old “no changed files, so pass” result must not come back. A selector that drops every mutant must fail. `NOT BLOCKED` must not pass the result checker.
2. Runs `setup/tests/harness/test-vis-ro.sh`. A container command that cannot reach a daemon is an error, not `NOT BLOCKED`.
3. Runs `setup/tests/harness/test-h3-verdict.sh`. An unrelated exit 137 must not count as the memory limit containing the allocator.
4. Builds `keel-git` from `setup/docker/keel-git.Dockerfile` and `keel-proxy` from `setup/docker/keel-proxy.Dockerfile`.
5. Runs the visibility self-test and the egress self-test.
6. Runs `setup/tests/harness/test-happy.sh`: init-repo, setup, the gate-suite containers, export, gate, push-stub, cleanup, then the egress checks and the visibility checks.
7. Runs `setup/tests/harness/test-attacks.sh`. Each attack prints a `RESULT` line. The egress checks and the visibility checks run at the end.
8. Runs `setup/keel-doctor.sh` without `--attacks`. If `KEEL_REPO` is unset, it runs `setup/keel.sh init-repo` first, because the suites delete their throwaway repo.
9. Runs `setup/tests/harness/test-doctor-ids.sh`. A result id the doctor requires, if it is absent from the scored log, makes the verdict NOT READY.
10. Runs the mutants whose mapped files changed against the base. A change to a mutant's own mapped file runs only the CI mutants for that file. Any other change under `setup/` or `.github/` runs the full set, including a file that is not a mapped target. The full set covers the attack suite and the happy-path suite and their helpers (`setup/tests/harness/test-attacks.sh`, `setup/tests/harness/test-happy.sh`, `setup/tests/harness/h3-verdict.sh`, `setup/tests/harness/test-egress.sh`, `setup/tests/harness/visibility-suite.sh`), shared libraries such as `setup/lib/portable.sh` and `setup/common.sh`, `setup/allow/`, `setup/deny/`, `setup/egress/`, the Dockerfiles, `setup/gitleaks.toml`, `setup/gitleaks-install.sh`, `setup/gitleaks.ignore`, `setup/keel-doctor.sh`, `setup/check.sh`, `setup/tests/harness/mutate-plan.sh`, `setup/tests/harness/mutate.py`, `setup/tests/harness/run-tests.sh`, `setup/tests/harness/mutant_files.py`, and workflow files such as `.github/workflows/checks.yml`. If no mapped file changed and nothing else under `setup/` or `.github/` changed, it logs `RESULT mutate: skipped (no harness files changed)` and does not run the mutants. That line is a skip, not a pass. `.github/workflows/mutate-full.yml` runs the full set once a day and from `workflow_dispatch`. A failed run stays red and updates one open issue.

The suites delete `KEEL_ROOT` (default `~/keel-proto`). That directory is throwaway data, not a checkout of this repository. On macOS, `KEEL_ROOT` must sit under a directory Docker Desktop shares. The defaults in `setup/lib/portable.sh` are `/Users`, `/Volumes`, `/private`, `/tmp`, and `/var/folders`. A home directory under `/Users` qualifies. Otherwise `setup/keel.sh` stops with exit code 4 and tells you so.

Useful extra commands:

```bash
bash setup/keel-doctor.sh             # readiness checks only
bash setup/keel-doctor.sh --attacks   # readiness + the attack suite, mapped to ATK-* lines
bash setup/keel.sh init-repo && bash setup/keel.sh setup && bash setup/keel.sh mode
```

`bash setup/keel.sh mode` prints the mount mode this machine uses.

## 3. Reading the output

Each doctor line looks like this:

```
✅ ENV-08  CRITICAL    pointer mode: single-file ro bind works (primary mode)
```

- ✅ means the check passed.
- ⚠️ means a warning. The harness is usable, but read the detail. Examples: `untested OS` on anything other than Linux, `env` fallback mode (ENV-08), ATK-A10 PARTIAL (by design), and `N/A` attacks that do not apply on this OS or in this mode. A rootful Linux daemon is not one of these warnings: ENV-05 fails and the verdict is not ready.
- ❌ means the check failed. If the level is **CRITICAL**, the verdict is NOT READY.

Every ID the doctor prints has a "why / if it fails / how to fix" section in [harness-checks-why.md](harness-checks-why.md). The fragment is the ID in lower case (`#env-08`, `#atk-a2`, ...).

The verdict is the last line:

| Verdict | Exit code | Meaning |
|---|---|---|
| READY | 0 | Everything passed. |
| READY WITH WARNINGS | 0 | No critical failure. Review the warning lines. |
| NOT READY | 1 | At least one CRITICAL check failed. Do not run agents here. |

In the suites, every attack should say `BLOCKED` or `CONTAINED`. `PARTIAL` is expected only for A10. `N/A` is expected for A2 in env mode and for A11-detect on macOS. Anything else (`NOT BLOCKED`, `WRONG REASON`, `FAIL`, a missing line) is a real problem. Send the logs.

Exit codes from `setup/tests/harness/run-tests.sh`: 0 means the suites and the doctor passed. 1 means a suite or the doctor failed. 5 means the Docker daemon is not reachable (on macOS: start Docker Desktop).

## 4. Where the logs are

Suite logs go in `setup/tests/harness/logs/` (gitignored):

- `happy-<timestamp>.log` and `attacks-<timestamp>.log`, from `setup/tests/harness/run-tests.sh`
- `doctor-attacks-<timestamp>.log`, the raw suite output behind `bash setup/keel-doctor.sh --attacks` (the path is printed under the Attacks section)

When reporting a problem, send the full terminal output of `bash setup/tests/harness/run-tests.sh` plus those files, along with `uname -a`, `bash --version | head -1`, `git --version`, and `docker version`.

## 5. Known limits

- `setup/keel.sh` says the harness was tested on Linux, and that macOS with Docker Desktop has not been run. Windows is untested. On any OS other than Linux the doctor prints a warning, `untested OS`, and that is a warning, not a refusal. The scripts target bash 3.2 or newer. Docker Desktop and Podman are not verified for the egress network and are unsupported for that path for now.
- The proxy does not read SNI inside a tunnel it has already allowed. Peers on `keel-egress`, including the CI mock, are reachable without the proxy and must not forward. The IPv6 attack checks `disable_ipv6` and the network’s `--ipv6=false`. It does not open a public IPv6 connection.
- Some hosts drop traffic between containers. EG-03 then fails, and the doctor is not ready, until an operator allows that traffic. [EG-03](harness-checks-why.md#eg-03).
- A rootful Linux daemon fails ENV-05. `role`, `proto`, and `export` refuse. Docker Desktop on a Mac can pass the isolation line and still has no supported egress path. [Security](security.md#rootless).
- On macOS, file ownership is mapped by Docker Desktop, so the gate's foreign-owner check is only a warning there. See [harness-checks-why.md](harness-checks-why.md#supported-os).
