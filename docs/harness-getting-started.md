# Getting started

The agent isolation harness (variant 2: a shadow `.git` with alternates, hardened containers, export by `git bundle`, a host gate with no token) lives in this repository under `setup/`. It runs on your machine, creates a **throwaway** git repo, uses no network inside containers, and never touches GitHub or any token.

Commands below are from the repository root.

## 1. Prerequisites

| | Linux | macOS (untested) | Windows |
|---|---|---|---|
| Shell | bash 3.2+ | built-in `/bin/bash` 3.2 is what `setup/lib/portable.sh` targets | untested (WSL2 is the likely path) |
| git | `sudo apt install git` | `xcode-select --install` (Xcode Command Line Tools), or `brew install git` | |
| Containers | `sudo apt install docker.io`, then `sudo usermod -aG docker $USER` and log in again (or use `DOCKER="sudo docker"`) | [Docker Desktop](https://www.docker.com/products/docker-desktop/), started, showing "Engine running" | |
| Disk | 2 GiB free. `DISK-01` fails under 2 GiB, warns from 2 GiB through 9 GiB, and passes at 10 GiB or more | same | |

`setup/keel.sh` says Linux is the tested host and that macOS with Docker Desktop has not been run. The `keel-git` image is built from `setup/docker/keel-git.Dockerfile` (Alpine and git, no platform pin), so `docker build` produces a native image. Set `DOCKER=podman` to use podman. `setup/keel.sh` adds `--userns=keep-id` in that case.

The v1 design requires a rootless runtime and will refuse to start without one. This doctor does not refuse yet: a rootful Linux daemon is a warning on ENV-05. [Security](security.md#rootless).

## 2. Run it

```bash
bash setup/tests/harness/run-tests.sh
# Linux without the docker group:
DOCKER="sudo docker" bash setup/tests/harness/run-tests.sh
```

`setup/tests/harness/run-tests.sh` does the following:

1. Builds the `keel-git` image from `setup/docker/keel-git.Dockerfile`.
2. Runs `setup/tests/harness/test-happy.sh`: init-repo, setup, a coder role, a tester role, export, gate, push-stub, then cleanup.
3. Runs `setup/tests/harness/test-attacks.sh`. Each attack prints a `RESULT` line.
4. Runs `setup/keel-doctor.sh` without `--attacks`, and prints that verdict last. If `KEEL_REPO` is unset, it runs `setup/keel.sh init-repo` first, because the suites delete their throwaway repo.

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
- ⚠️ means a warning. The harness is usable, but read the detail. Examples: `untested OS` on anything other than Linux, the rootful daemon on Linux (ENV-05), `env` fallback mode (ENV-08), ATK-A10 PARTIAL (by design), and `N/A` attacks that do not apply on this OS or in this mode.
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

- `setup/keel.sh` says the harness was tested on Linux, and that macOS with Docker Desktop has not been run. Windows is untested. On any OS other than Linux the doctor prints a warning, `untested OS`, and that is a warning, not a refusal. The scripts target bash 3.2 or newer.
- Rootless Docker or Podman is a mandatory requirement of the v1 pipeline. The doctor still classifies that boundary as RECOMMENDED (ENV-05). A rootful daemon warns. It does not make the verdict NOT READY. [Security](security.md#rootless).
- On macOS, file ownership is mapped by Docker Desktop, so the gate's foreign-owner check is only a warning there. See [harness-checks-why.md](harness-checks-why.md#supported-os).
