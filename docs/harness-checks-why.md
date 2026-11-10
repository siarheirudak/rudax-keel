# Why each keel-doctor check exists

This page explains every check printed by `setup/keel-doctor.sh`. Each line of doctor output has an ID. The section for that ID is below. The fragment is the ID in lower case (`docs/harness-checks-why.md#env-08`). V-A9 is owner-only and is not a doctor line.

How to run it: [Getting started](harness-getting-started.md).

**Rule:** any new check needs a section here, in this shape, before it is added to the doctor. Same rule as [docs/why.md](why.md).

Levels: **CRITICAL**: a failure means NOT READY and exit code 1. **RECOMMENDED**: warn, harness still usable. **OPTIONAL**: informational. **Owner-only**: the doctor does not print the id. The owner checks it.

<a id="v-a9"></a>

### V-A9 path traversal and a second mount

**Level.** Owner-only.

**Check.** The owner checks that `../` and a second mount cannot widen what a role sees. The allow parser refuses a `../` path. The attack suite does not score V-A9.

**Why.** A traversal or a second mount can show a path the allowlist withheld.

**If it fails.** The owner treats the machine as not ready for agents.

**How to fix.** Keep `../` refused in the allow parser. Do not add a mount that escapes an allow root.

<a id="supported-os"></a>

## Supported operating systems

**Tested on Linux; meant to be portable.** Linux is not a hard requirement. The scripts target bash 3.2+ (the macOS default) and BSD or GNU userland, and they handle Docker Desktop. `setup/keel.sh` says Linux is the tested host and that macOS with Docker Desktop has not been run. Windows is untested. On any OS other than Linux the doctor prints a warning, `untested OS`, and that is a warning, not a refusal.

Docker Desktop differences the harness handles:

- **The VM boundary.** Containers run in a Linux VM. A container escape lands in the VM, not directly on the host (see [ENV-05](#env-05)).
- **File ownership.** Files are shared through VirtioFS/gRPC FUSE, which maps ownership to your user. A file that is root-owned inside the container still shows as yours on the Mac. So the gate's foreign-owner check ([ATK-A11-detect](#atk-a11-detect)) cannot see anything there. On Darwin it is a warning in the gate and N/A in the doctor, not a gate failure. `--user uid:gid` ([ATK-A11](#atk-a11)) still applies inside the VM.
- **Single-file bind mounts.** Some Docker Desktop versions handle them poorly. See [ENV-08](#env-08) for the fallback.
- **Shared paths.** Only the directories in Settings > Resources > File sharing can be mounted. The defaults in `setup/lib/portable.sh` are `/Users`, `/Volumes`, `/private`, `/tmp`, and `/var/folders`. `KEEL_ROOT` defaults to `~/keel-proto` (throwaway data, not this repository). `setup/keel.sh` exits 4 with a clear message if it is outside a shared directory.

## Environment checks

<a id="env-01"></a>

### ENV-01 Operating system

**Level.** CRITICAL

**Check.** `uname -s`. Linux passes (the host `setup/keel.sh` names as tested). Anything else is a warning, `untested OS`.

**Why.** Isolation depends on how bind mounts, ownership, and cgroup limits behave on the container host. The scripts say that behaviour has been verified on Linux.

**If it fails.** Warning only. Run `bash setup/keel-doctor.sh --attacks`. If every ATK check passes, the isolation properties hold on this machine.

**How to fix.** Nothing is required. For the tested setup, use a Linux host or VM.

<a id="env-02"></a>

### ENV-02 git

**Level.** CRITICAL

**Check.** `git` is on PATH. `setup/keel-doctor.sh` passes version 2.30 or newer. An older version is a warning. The warning text names 2.45-2.47 as the range the check was written against.

**Why.** The host gate runs `git bundle verify`, `fetch` with fsck, `diff`, and `archive`. An old git may lack fixes or behave differently.

**If it fails.** Missing: FAIL, the gate cannot run. Old: warning.

**How to fix.** Linux: `apt install git`. macOS: `xcode-select --install` (Apple git is fine) or `brew install git`.

<a id="env-03"></a>

### ENV-03 Container CLI

**Level.** CRITICAL

**Check.** The command in `$DOCKER` (docker, `sudo docker`, or podman) is on PATH.

**Why.** Every agent role, the export, and the test re-run happen in containers. Without them there is no isolation.

**If it fails.** FAIL. Nothing can run.

**How to fix.** Linux: `apt install docker.io`, or rootless Docker, or podman. macOS: install Docker Desktop.

<a id="env-04"></a>

### ENV-04 Daemon running

**Level.** CRITICAL

**Check.** `$DOCKER info` succeeds. If it does not, the doctor and `setup/keel.sh` print a hint that depends on the OS (on macOS: "Docker Desktop is not running, start it with `open -a Docker`"), and `setup/keel.sh` exits 5.

**Why.** Same as ENV-03. Also catches a stopped daemon or missing permission on the socket.

**If it fails.** FAIL.

**How to fix.** macOS: start Docker Desktop and wait for "Engine running". Linux: `sudo systemctl start docker`, or add your user to the docker group, or set `DOCKER="sudo docker"`.

<a id="env-05"></a>

### ENV-05 Isolation boundary

**Level.** CRITICAL

**Check.** Where does a container escape land? Docker on Linux passes only when `SecurityOptions` contains the option `rootless`. Podman passes only when `Host.Security.Rootless` is true. Docker Desktop on Darwin passes as an isolation boundary: an escape lands in the Desktop VM, not on the Mac. That pass does not mean egress or the rest of the harness works there. Docker Desktop on Linux stays a warning. A rootful Linux daemon fails. The socket path is not used. User-namespace remapping without `rootless` fails. `DOCKER_HOST` and the docker context are chosen by the owner; a stand-in daemon that prints `rootless` is an owner mistake, not something a role can set.

**Why.** With a rootful daemon, a container escape gives root on the host. Rootless shrinks that blast radius. It does not fix a kernel bug. See [Security](security.md#rootless).

**If it fails.** FAIL. The verdict is not ready, and `role`, `proto`, `export`, and the other commands that start a container refuse. There is no environment switch that turns the failure into a pass.

**How to fix.** Install rootless Docker (`dockerd-rootless-setuptool.sh install`) or rootless Podman. On a systemd host, enable cgroup delegation so `--pids-limit`, `--memory`, and `--cpus` work.

<a id="env-06"></a>

### ENV-06 Image keel-git

**Level.** RECOMMENDED

**Check.** Image `keel-git` exists locally and its architecture matches the daemon's (amd64 or arm64). `setup/docker/keel-git.Dockerfile` pins no platform, so `docker build` produces a native image.

**Why.** The image has to be present locally. A container is not given a path to a registry, so it cannot pull an image or install git at runtime.

**If it fails.** Warning. If the image is missing, the first role fails to start. If the architecture does not match, everything runs under emulation and is slow.

**How to fix.** From the repository root: `docker build -t keel-git -f setup/docker/keel-git.Dockerfile setup/docker`. The doctor prints that `-f` path from `setup/`.

<a id="env-07"></a>

### ENV-07 Hardening flags accepted

**Level.** CRITICAL

**Check.** A test container starts with `--network none --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp --pids-limit --memory --cpus --user uid:gid`.

**Why.** Without these flags the container is not an isolation boundary. Rootless runtimes without cgroup delegation reject the limits.

**If it fails.** FAIL. The harness would refuse to start, or run weaker containers.

**How to fix.** Enable cgroup v2 delegation (systemd) on a rootless daemon. A rootful daemon fails ENV-05.

<a id="env-08"></a>

### ENV-08 KEEL_ROOT mountable, pointer mode

**Level.** CRITICAL

**Check.** The probe makes a temp dir under `KEEL_ROOT` containing a `.git` file. It then checks three things: (1) the dir can be bind-mounted, (2) a single-file `:ro` bind over `/work/.git` works, and (3) that file is not writable inside the container. Result: pass, `pointer` mode, or a warning and fallback to `env` mode.

**Why.** The primary design mounts the shadow pointer `/work/.git` as a read-only single file, so an agent cannot redirect git elsewhere ([ATK-A2](#atk-a2)). Docker Desktop has had bugs with single-file binds. In that case `setup/keel.sh setup` falls back to **env mode**: it deletes the pointer file and passes `GIT_DIR=/shadow/<task>.git GIT_WORK_TREE=/work` to every role. `setup/keel.sh mode` prints the mode that was chosen. `KEEL_POINTER_MODE=pointer|env|auto` forces a mode (default auto).

**If it fails.** If KEEL_ROOT cannot be mounted, or the ro bind is writable: FAIL. Env fallback: warning. Env mode has a weaker guarantee. An agent can set its own `GIT_DIR` inside its process, but it can only reach the paths mounted into its container (its own work, its own shadow, the ro base objects). So it cannot reach other tasks or the host, and the gate still validates only the exported bundle. ATK-A2 reports N/A in env mode.

**How to fix.** Fallback: update Docker Desktop, or accept env mode. Mount failure: put `KEEL_ROOT` under `$HOME`, or add its parent in Docker Desktop's File sharing settings and tell the harness with `KEEL_SHARED_DIRS=/that/dir` (colon-separated).

<a id="sec-01"></a>

### SEC-01 No GitHub token in environment

**Level.** CRITICAL

**Check.** No variable named `GH_*`, `GITHUB_*`, or `BOT_GH_TOKEN` in the doctor's environment. Only names are printed, never values.

**Why.** Agents and the gate must have no token. Only the broker pushes. A token in the shell the harness runs from can leak into a container through a careless `-e`, or into logs.

**If it fails.** FAIL.

**How to fix.** Run the harness in a shell or user without the token. Keep the token only in the broker's environment.

<a id="repo-01"></a>

### REPO-01 gc.auto=0

**Level.** CRITICAL

**Check.** `git config gc.auto` in the base repo is 0.

**Why.** Each shadow `.git` borrows objects from the base repo through alternates. An automatic gc could pack or prune objects a task still needs.

**If it fails.** FAIL. A routine `git` command can trigger gc and corrupt an active task. If there is no git repo at `KEEL_REPO`, this is the line the doctor prints (`KEEL_REPO` defaults to `$KEEL_ROOT/repo`).

**How to fix.** `git -C <repo> config gc.auto 0`. Or `bash setup/keel.sh init-repo` for a throwaway repo.

<a id="repo-02"></a>

### REPO-02 maintenance.auto=false

**Level.** CRITICAL

**Check.** `git config maintenance.auto` is false.

**Why.** Same threat as REPO-01, through background maintenance.

**If it fails.** FAIL.

**How to fix.** `git -C <repo> config maintenance.auto false`.

<a id="repo-03"></a>

### REPO-03 gc.pruneExpire=never

**Level.** CRITICAL

**Check.** `git config gc.pruneExpire` is never.

**Why.** A manual `git gc` without flags then never deletes unreachable objects, so a task based on a rewound commit survives. The attack suite asserts that a plain `git gc` leaves the shadow intact, and that `git gc --prune=now` still breaks it.

**If it fails.** FAIL.

**How to fix.** `git -C <repo> config gc.pruneExpire never`. Never run `--prune=now` or `git prune` while a task exists.

<a id="repo-04"></a>

### REPO-04 On main

**Level.** RECOMMENDED

**Check.** The base repo's HEAD is `main`.

**Why.** Tasks are cut from main, and the gate compares the bundle base with main.

**If it fails.** Warning.

**How to fix.** `git -C <repo> switch main`.

<a id="disk-01"></a>

### DISK-01 Free disk

**Level.** RECOMMENDED

**Check.** Free space under `KEEL_ROOT`, in whole GiB: 10 or more passes, 2 to 9 warns, under 2 fails.

**Why.** Writable mounts have no quota, so an agent can fill the disk. Bundles and checkouts need space too.

**If it fails.** Warn or fail (not critical, so the verdict can still be READY WITH WARNINGS).

**How to fix.** Free space, or put `KEEL_ROOT` on its own filesystem or quota.

<a id="disk-02"></a>

### DISK-02 Work free space

**Level.** CRITICAL

**Check.** Free bytes under `KEEL_ROOT` are at least `KEEL_WORK_MIN_FREE` (512 MiB unless that name is set). This is separate from DISK-01. A warning on DISK-01 does not fail this line, and this line does not repeat DISK-01's 2 GiB and 10 GiB bands.

**Why.** Writable mounts have no hard project quota. The soft check is the refuse path the CI host can actually run. An XFS project quota or a ZFS dataset is optional host setup, not something this repository requires.

**If it fails.** FAIL. `setup` and `role` also refuse.

**How to fix.** Free space under `KEEL_ROOT`, or lower `KEEL_WORK_MIN_FREE` only if you accept the smaller margin.

<a id="chr-01"></a>

### CHR-01 Chromium sandbox argv

**Level.** CRITICAL when Playwright or a Chromium binary is installed, otherwise recommended.

**Check.** `setup/chrome/chromium-argv.sh` refuses `--no-sandbox` and `--disable-setuid-sandbox`. No browser is started. If those tools are absent, the line passes and says they are required before the QA browser step.

**Why.** Those flags turn the sandbox off. A real Chromium run under rootless, including a seccomp profile, is the QA step, not this check.

**If it fails.** FAIL when the tool is installed. Otherwise a warning only if the helper itself accepts a disable flag.

**How to fix.** Keep the refuse in `setup/chrome/chromium-argv.sh`.

## Egress checks

These run on every doctor invocation, before `--attacks`. All three are CRITICAL. A failure means the verdict is not ready.

<a id="eg-01"></a>

### EG-01 Proxy image

**Level.** CRITICAL

**Check.** The local image `keel-proxy` is present.

**Why.** The developer role cannot start its allowlisted path without that image. A missing image is not a successful dark launch.

**If it fails.** FAIL. The verdict is NOT READY.

**How to fix.** From the repository root: `docker build -t keel-proxy -f setup/docker/keel-proxy.Dockerfile setup/docker`.

<a id="eg-02"></a>

### EG-02 Egress network is internal

**Level.** CRITICAL

**Check.** The Docker network `keel-egress` exists and its internal flag is true.

**Why.** A network that is not internal gives the developer a route past the proxy.

**If it fails.** FAIL. The verdict is NOT READY. A missing network fails the same way.

**How to fix.** Run `bash setup/keel.sh egress-up` on a Linux Docker host. If a network of that name already exists and is not internal, remove it and create it again with `egress-up`. Docker Desktop and Podman are not verified for this check and are unsupported for it for now.

<a id="eg-03"></a>

### EG-03 Forward port answers with a denial

**Level.** CRITICAL

**Check.** A container on `keel-egress` sends a cleartext request to the proxy’s forward port and the body contains `DENIED`.

**Why.** The launch path needs a proxy that is up and refusing destinations that are not allowlisted. Silence is not a pass.

**If it fails.** FAIL. The verdict is NOT READY.

**How to fix.** Start the proxy with `bash setup/keel.sh egress-up`. On some hosts the packet filter drops traffic between containers on the same bridge. The probe then cannot reach the forward port. Allow that container-to-container traffic and rerun the doctor. Do not treat a failed probe as a ready machine.

## Attack checks (`--attacks`)

`--attacks` runs `setup/tests/harness/test-attacks.sh` in a throwaway temp dir on this machine with real containers, and maps each `RESULT` line to `ATK-<id>`. All are CRITICAL except ATK-A10 (RECOMMENDED). `BLOCKED` or `CONTAINED` passes. `PARTIAL`, `RISK`, or `N/A` warns. Anything else fails, including `WRONG REASON`. A gate test passes only if the gate fails **for the rule under test**. If it fails for another reason, the result is `WRONG REASON`. `setup/tests/harness/mutate.py` removes one protection at a time and checks that the attack it guards stops reporting `BLOCKED` or `CONTAINED`. Some mutants stay green because another layer still catches the same attack. `N/A` means that test does not apply in this mode or on this OS (ATK-A2 in env mode, ATK-A11-detect on Darwin). The temp dir is created under `$HOME`, so Docker Desktop can mount it.

If a CRITICAL check has already failed, the doctor does not run the suite. It prints [ATK-00](#atk-00) instead.

<a id="atk-00"></a>

### ATK-00 attack suite skipped

**Level.** CRITICAL

**Check.** Printed only with `--attacks`, and only when a CRITICAL check has already failed. The suite is not started.

**Why.** The attack suite needs a working container host. A run after a critical failure would not say whether isolation holds.

**If it fails.** FAIL. Fix the critical lines first, then rerun `bash setup/keel-doctor.sh --attacks`.

**How to fix.** Clear the CRITICAL failures above (environment, token, repository).

<a id="atk-n1"></a>

### ATK-N1 proto and the gate re-run have no network

**Level.** CRITICAL

**Check.** The `proto` container is started with `--network none`. It has no HTTP and no DNS. The gate’s test re-run uses that same flag.

**Why.** Exfiltration of code or secrets, and pulling a payload, from the containers that are not the developer role.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `--network none` on `proto`, on the gate re-run, and on every role except the developer. The developer path is the internal proxy, checked by the ATK-E lines below.

<a id="atk-e-h1"></a>

### ATK-E-H1 developer reaches the mock

**Level.** CRITICAL

**Check.** The developer, through the proxy, receives the mock body from the allowlisted host.

**Why.** The allowlist has to let the one intended destination through. A total black hole would also look like “blocked” and would hide a broken proxy.

**If it fails.** FAIL.

**How to fix.** Keep `keel-mock` in `setup/egress/developer.allow`, and keep the proxy and the mock on `keel-egress`.

<a id="atk-e-h2"></a>

### ATK-E-H2 critic has no network

**Level.** CRITICAL

**Check.** The critic container starts, and it cannot fetch the mock or a public host, and it cannot resolve a public name.

**Why.** The critic has no destination list. A network on that role is a new exfiltration path.

**If it fails.** FAIL.

**How to fix.** Keep the critic on `--network none`.

<a id="atk-e-h3"></a>

### ATK-E-H3 denial log is host and port

**Level.** CRITICAL

**Check.** A blocked developer request appends one record to `$KEEL_ROOT/.keel/logs/egress.jsonl`. The host field is the sanitized host and port. The reason is set. The path and the query are absent.

**Why.** A log that stores the URL can keep secrets that were in the query, and a raw host can break the line.

**If it fails.** FAIL.

**How to fix.** Keep denial logging on, and keep the log formatter on host:port.

<a id="atk-e-h4"></a>

### ATK-E-H4 proto has no network

**Level.** CRITICAL

**Check.** `proto` starts and cannot fetch or resolve a public destination.

**Why.** Same as [ATK-N1](#atk-n1), scored again on the egress suite so a developer-only network change cannot silently open `proto`.

**If it fails.** FAIL.

**How to fix.** Keep `proto` on `--network none`.

<a id="atk-e-h5"></a>

### ATK-E-H5 QA has no network

**Level.** CRITICAL

**Check.** QA starts, and it cannot fetch the mock or a public host, and it cannot resolve a public name.

**Why.** The design’s “local app only” path is not built. QA must not gain a network early.

**If it fails.** FAIL.

**How to fix.** Keep QA on `--network none`.

<a id="atk-e-h6"></a>

### ATK-E-H6 researcher has no network

**Level.** CRITICAL

**Check.** The researcher starts, and it cannot fetch the mock or a public host, and it cannot resolve a public name.

**Why.** The design’s research internet is not built. The researcher must not gain a network early.

**If it fails.** FAIL.

**How to fix.** Keep the researcher on `--network none`.

<a id="atk-e-a1"></a>

### ATK-E-A1 unauthorized host

**Level.** CRITICAL

**Check.** The developer is denied for a public name and for a public IP that are not on the allowlist. Both show up in the denial log as host:port with reason `not_allowlisted`.

**Why.** The proxy is the allowlist, not a general web gateway.

**If it fails.** FAIL.

**How to fix.** Match hosts exactly after normalization. Do not treat a wider host check as success.

<a id="atk-e-a2"></a>

### ATK-E-A2 no route when the proxy is unset

**Level.** CRITICAL

**Check.** With the proxy variables unset, a raw request from the developer to a public IP fails because the network is unreachable.

**Why.** Isolation has to be the network, not an environment variable the process can drop.

**If it fails.** FAIL.

**How to fix.** Keep `keel-egress` internal. Do not put the developer on the default bridge.

<a id="atk-e-a3"></a>

### ATK-E-A3 critic egress

**Level.** CRITICAL

**Check.** Same dark oracle as [ATK-E-H2](#atk-e-h2).

**Why.** A second probe so a change that opens the critic is not hidden behind the happy-path id alone.

**If it fails.** FAIL.

**How to fix.** Keep the critic on `--network none`.

<a id="atk-e-a4"></a>

### ATK-E-A4 QA egress

**Level.** CRITICAL

**Check.** Same dark oracle as [ATK-E-H5](#atk-e-h5).

**Why.** QA is still `--network none`.

**If it fails.** FAIL.

**How to fix.** Keep QA on `--network none`.

<a id="atk-e-a5"></a>

### ATK-E-A5 allow file is not mounted

**Level.** CRITICAL

**Check.** The developer container does not see `setup/egress/` or the allow file.

**Why.** A role that can edit its own allowlist can approve its own destinations.

**If it fails.** FAIL.

**How to fix.** Do not mount `setup/egress/` into the role.

<a id="atk-e-a6"></a>

### ATK-E-A6 malformed allow file

**Level.** CRITICAL

**Check.** A glob in the developer allow file refuses the launch. The container does not start.

**Why.** A bad pattern must not be read as “allow everything nearby”.

**If it fails.** FAIL.

**How to fix.** Refuse the launch when the profile does not parse.

<a id="atk-e-a7"></a>

### ATK-E-A7 researcher egress

**Level.** CRITICAL

**Check.** Same dark oracle as [ATK-E-H6](#atk-e-h6).

**Why.** The researcher is still `--network none`.

**If it fails.** FAIL.

**How to fix.** Keep the researcher on `--network none`.

<a id="atk-e-a8"></a>

### ATK-E-A8 proxy admin port

**Level.** CRITICAL

**Check.** From the developer container, the proxy’s admin port does not return the admin banner.

**Why.** An admin listener on the role network can change policy from inside the role.

**If it fails.** FAIL.

**How to fix.** Bind the admin port to `127.0.0.1` in the proxy’s own namespace.

<a id="atk-e-a9"></a>

### ATK-E-A9 embedded DNS does not forward

**Level.** CRITICAL

**Check.** A query for a public name to `127.0.0.11` from the developer does not return an answer.

**Why.** DNS questions are a way out even when TCP to the internet is closed.

**If it fails.** FAIL.

**How to fix.** Keep the role network internal so the embedded resolver does not forward.

<a id="atk-e-a10"></a>

### ATK-E-A10 IPv6 is disabled in the role

**Level.** CRITICAL

**Check.** The suite reads `disable_ipv6` in the developer container and expects 1. The network is created with `--ipv6=false`. This is not a connection to a public IPv6 address.

**Why.** An IPv6 route would bypass an IPv4-only story. This oracle checks the setting the harness applies, not a live path to the public IPv6 internet.

**If it fails.** FAIL.

**How to fix.** Keep the sysctl on the developer container and `--ipv6=false` on the network.

<a id="atk-e-a11"></a>

### ATK-E-A11 metadata address

**Level.** CRITICAL

**Check.** With the proxy variables unset, a request to the link-local metadata address is network-unreachable.

**Why.** A cloud metadata address is a credential store. It must not be reachable from the role.

**If it fails.** FAIL.

**How to fix.** Keep the role network internal.

<a id="atk-e-a12"></a>

### ATK-E-A12 disallowed port

**Level.** CRITICAL

**Check.** CONNECT to the allowlisted host on a port that is not 443, and not listed, is denied and logged as `not_allowlisted`.

**Why.** An allowlisted name is not permission for every port on that name.

**If it fails.** FAIL.

**How to fix.** Default CONNECT to port 443 only, unless the allow line names the port.

<a id="atk-e-a13"></a>

### ATK-E-A13 CONNECT target, not the Host header

**Level.** CRITICAL

**Check.** CONNECT to a denied host is refused even when the Host header names the allowlisted host. The proxy does not answer with a successful tunnel.

**Why.** Authorizing the Host header instead of the CONNECT target would open a host the operator did not list.

**If it fails.** FAIL.

**How to fix.** Decide CONNECT from the CONNECT host and port. The proxy does not intercept TLS, so it still cannot read SNI inside a tunnel it has already allowed. That residual is accepted.

<a id="atk-e-a14"></a>

### ATK-E-A14 redirect is checked again

**Level.** CRITICAL

**Check.** A request to the allowlisted mock that redirects to a different host on the same network is denied on that second hop, and the denial names that host. The body of the second host is not returned.

**Why.** The first hop being allowed must not carry the client to a peer that is not listed.

**If it fails.** FAIL.

**How to fix.** Do not follow the redirect inside the proxy without applying the allowlist again. The client’s own follow-up request is checked the same way.

<a id="atk-e-a15"></a>

### ATK-E-A15 denial line stays one record

**Level.** CRITICAL

**Check.** A CONNECT target that carries a line-break encoding does not add a second log line and does not leave that payload text in the log.

**Why.** One request must not add an extra JSONL record or keep an unsanitized host.

**If it fails.** FAIL.

**How to fix.** Sanitize the host before writing the record. Reject a line break, a NUL, or a host longer than 253 characters.

<a id="atk-e-a16"></a>

### ATK-E-A16 proxy down refuses the launch

**Level.** CRITICAL

**Check.** After the proxy container is stopped, the developer launch is refused and does not print a successful start.

**Why.** A dead proxy must not mean the role starts with whatever network is left behind.

**If it fails.** FAIL.

**How to fix.** If the proxy container exists and is not running, refuse. Do not start the role.

<a id="atk-e-a17"></a>

### ATK-E-A17 exact host match

**Level.** CRITICAL

**Check.** A name that merely contains the allowlisted host, a different spelling, a trailing-dot form of an unlisted name, and an unrelated punycode name are not served the mock body. The suffix form is logged as `not_allowlisted`.

**Why.** Suffix and pattern matches turn one listed host into many.

**If it fails.** FAIL.

**How to fix.** Compare the normalized host for equality with the listed host. Do not use a suffix or a glob.

<a id="atk-n2"></a>

### ATK-N2 host token not passed

**Level.** CRITICAL

**Check.** Sets fake `GH_TOKEN`, `GITHUB_TOKEN`, and `BOT_GH_TOKEN` on the host and checks they are absent in the container.

**Why.** An agent with a token can push or merge as the bot.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Pass only the explicit `-e` list in `setup/keel.sh`; never `--env-file` or `-e GH_*`.

<a id="atk-a1"></a>

### ATK-A1 /base/objects read-only

**Level.** CRITICAL

**Check.** Writes to `/base/objects` fail.

**Why.** Planting or corrupting objects in the real repo.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep the `:ro` on the base objects mount.

<a id="atk-a2"></a>

### ATK-A2 pointer file immutable

**Level.** CRITICAL

**Check.** Write, rm, and mv of `/work/.git` fail.

**Why.** Pointing git at another repo, or escaping the shadow.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep the single-file `:ro` bind. N/A in env mode (see [ENV-08](#env-08)).

<a id="atk-a3"></a>

### ATK-A3 no host code execution via shadow

**Level.** CRITICAL

**Check.** Plants hooks, fsmonitor, alias, and pager in the shadow, runs export, gate, and push-stub, and checks no host marker appears.

**Why.** Host code execution when the host runs git against the shadow.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Never run host git against shadow or work dirs; keep `hgit` hardening in `setup/keel.sh`.

<a id="atk-a12"></a>

### ATK-A12 no cross-role hooks

**Level.** CRITICAL

**Check.** Role A plants hooks and config, and the check shows nothing runs in role B or export.

**Why.** One role backdooring the next.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `reset_shadow` and `GIT_CONFIG_PARAMETERS` in `setup/keel.sh`.

<a id="atk-a4"></a>

### ATK-A4 gate forbids .github/

**Level.** CRITICAL

**Check.** A commit that touches `.github/` is rejected.

**Why.** An agent must not edit CI, CODEOWNERS, or workflows through the bundle.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `FORBID_PREFIX` and `FORBID_NAME` in `setup/keel.sh` in sync with `scripts/check-scope.py`. The host gate also forbids `.gitmodules`.

<a id="atk-a12b"></a>

### ATK-A12b forced git safety config

**Level.** CRITICAL

**Check.** Inside a role, `git config core.hooksPath` is `/dev/null` and `core.fsmonitor` is `false`.

**Why.** The second layer behind `reset_shadow`. The suite asserts it on its own because A12 stays green when only this layer is removed (`setup/tests/harness/mutate.py`).

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `GIT_CONFIG_PARAMETERS` in `GITENV`.

<a id="atk-a4b"></a>

### ATK-A4b gate forbids AGENTS.md, .pi/

**Level.** CRITICAL

**Check.** A commit that touches `AGENTS.md` or `.pi/` is rejected.

**Why.** An agent must not rewrite its own instructions or harness config through the bundle.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Same as [ATK-A4](#atk-a4).

<a id="atk-a4c"></a>

### ATK-A4c forbidden-path variants

**Level.** CRITICAL

**Check.** `.GitHub/workflows/w.yml`, `git mv app.txt .github/`, a mode-only change (`chmod +x .github/ci.yml`), and `agents.md` / `Agents.MD` are each rejected **as forbidden path**.

**Why.** macOS and Windows checkouts fold case, so `.GitHub/` becomes `.github/`. Renames and mode changes are still edits. (`./.github` and `..` components cannot exist in a git tree; fsck rejects them.)

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Match `FORBID_PREFIX` and `FORBID_NAME` case-insensitively (`grep -iE`). Keep `--no-renames` in the raw diff.

<a id="atk-a5"></a>

### ATK-A5 gate rejects symlinks

**Level.** CRITICAL

**Check.** A symlink (`-> /etc/passwd`) is rejected.

**Why.** Symlinks that read host files in later tooling.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep the mode-120000 check.

<a id="atk-a6"></a>

### ATK-A6 gate bundle size limit

**Level.** CRITICAL

**Check.** The suite commits 3000000 random bytes, base64-encoded. The gate rejects a bundle larger than `MAX_BUNDLE` (default 1048576 bytes).

**Why.** Repo bloat, review fatigue, denial of service.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Tune `MAX_BUNDLE` in `setup/keel.sh`.

<a id="atk-a6b"></a>

### ATK-A6b gate line limit

**Level.** CRITICAL

**Check.** The suite adds a file of 20000 lines. The gate rejects a diff over `MAX_LINES` (default 5000).

**Why.** Same as [ATK-A6](#atk-a6).

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Tune `MAX_LINES` in `setup/keel.sh`.

<a id="atk-a6c"></a>

### ATK-A6c changed-file count limit

**Level.** CRITICAL

**Check.** The suite adds 2000 empty files. The gate rejects them by `MAX_FILES` (default 500). Size and line limits both miss that case.

**Why.** Many empty files cause review fatigue and inode exhaustion, and they can hide one bad file.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Tune `MAX_FILES` in `setup/keel.sh`.

<a id="atk-a7"></a>

### ATK-A7 gate: one ref only

**Level.** CRITICAL

**Check.** A bundle with an extra branch or tag is rejected.

**Why.** Smuggling branches or tags.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep the list-heads check.

<a id="atk-a7b"></a>

### ATK-A7b gate: right branch name

**Level.** CRITICAL

**Check.** A bundle with a different branch name is rejected.

**Why.** Same as [ATK-A7](#atk-a7).

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Same as [ATK-A7](#atk-a7).

<a id="atk-a8"></a>

### ATK-A8 gate: base = current main

**Level.** CRITICAL

**Check.** A bundle on old main is rejected.

**Why.** Reintroducing reverted code, hiding changes in a stale base.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Rebase the task on current main and re-export.

<a id="atk-a8b"></a>

### ATK-A8b gate: bundle has a base

**Level.** CRITICAL

**Check.** A full-history bundle is rejected.

**Why.** Replacing history wholesale.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Export with the current main as the bundle prerequisite, then re-run the gate.

<a id="atk-a9"></a>

### ATK-A9 reviewer can't commit

**Level.** CRITICAL

**Check.** The reviewer has read-only work and shadow; the shadow is unchanged afterwards.

**Why.** The reviewer approving its own changes.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Always run reviewer roles with `ro`.

<a id="atk-a10"></a>

### ATK-A10 gc guard (RECOMMENDED)

**Level.** RECOMMENDED

**Check.** `setup/keel.sh repo-gc` and `repo-prune` refuse with exit code 3 while tasks exist (asserted). A plain `git gc` leaves the shadow intact (asserted). **PARTIAL:** `git gc --prune=now` by hand still breaks the shadow.

**Why.** Corrupted task, lost work.

**If it fails.** PARTIAL is a warning by design. FAIL if the guard stops refusing.

**How to fix.** Do not run git maintenance by hand while `work/*` exists.

<a id="atk-a10b"></a>

### ATK-A10b main can't move backwards

**Level.** CRITICAL

**Check.** `setup/keel.sh set-main` refuses a non-fast-forward while tasks exist.

**Why.** Base objects become unreachable, then pruned.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Only move main through `setup/keel.sh set-main`.

<a id="atk-a11"></a>

### ATK-A11 no root-owned files

**Level.** CRITICAL

**Check.** The container uid equals the host uid, and no foreign-owned files exist.

**Why.** The host user cannot clean up; root files planted on the host.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `--user`.

<a id="atk-a11-detect"></a>

### ATK-A11-detect gate rejects foreign-owned files

**Level.** CRITICAL

**Check.** Root files from a container without `--user` make the gate refuse.

**Why.** Same as [ATK-A11](#atk-a11).

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** chown back via a container, then fix the launcher. N/A on macOS: Docker Desktop file sharing maps ownership to your user, so the check cannot see foreign owners. The gate warns instead of failing (see [Supported operating systems](#supported-os)).

<a id="atk-a13"></a>

### ATK-A13 fsck rejects corrupt objects

**Level.** CRITICAL

**Check.** A commit object with a malformed author date (`hash-object --literally`) is rejected at `fetch` with `fetch.fsckObjects` and `transfer.fsckObjects`.

**Why.** Malformed objects can crash or confuse later tooling and the broker push. `bundle verify` does not fsck.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep the fsck flags on the gate fetch.

<a id="atk-a14"></a>

### ATK-A14 submodule / gitlink rejected

**Level.** CRITICAL

**Check.** A mode-160000 entry is rejected. A path whose basename is `.gitmodules`, including `lib/.gitmodules`, is also forbidden.

**Why.** A gitlink pulls in code from another repository that nobody reviewed. CI or a later checkout might fetch it.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep the gitlink rule.

<a id="atk-a15"></a>

### ATK-A15 agent-only commit identity

**Level.** CRITICAL

**Check.** Every new commit must have author and committer `KEEL_AGENT_IDENT` (default `agent <a@x>`). A commit with `--author="Some Maintainer <...>"` is rejected.

**Why.** Otherwise an agent can make its work look human-authored, which misleads review and blame.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Set `KEEL_AGENT_IDENT` to the identity the harness injects.

<a id="atk-a16"></a>

### ATK-A16 push stub: one sha, one branch

**Level.** CRITICAL

**Check.** After a passing gate, the broker command contains exactly one `push` with the refspec `<gated sha>:refs/heads/agent/<task>`. No `--all`, `--mirror`, or tags.

**Why.** The broker holds the token. It must publish only what the gate checked, to the agent branch.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep the broker command a single explicit refspec. Rerun A16 against the real broker when it replaces the stub in `setup/keel.sh`.

<a id="atk-a17"></a>
<a id="atk-a17b"></a>
<a id="atk-a17c"></a>

### ATK-A17/A17b/A17c NUL-safe path parsing

**Level.** CRITICAL

**Check.** Commits adding `.github/workflows/evil x.yml` (space), `.github/workflows/é.yml` (UTF-8, which git C-quotes), and `.github/a<TAB>b"c.yml` must fail with `forbidden path`.

**Why.** Splitting `git diff --raw` on whitespace lets a space or a C-quoted path slip past every path rule.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Parse `git diff --raw -z` with `read -d ''`. Never parse non-`-z` diff output for paths.

<a id="atk-a18"></a>
<a id="atk-a18b"></a>

### ATK-A18/A18b Pi process paths

**Level.** CRITICAL

**Check.** `docs/AGENTS.md` (A18) must fail with `forbidden path`. A18b does the same, one path per run, for `.pi/SYSTEM.md`, `.pi/extensions/x.ts`, `.pi/mcp.json`, `.agents/skills/a/SKILL.md`, `pkg/.pi/SYSTEM.md`, `apps/.agents/skills/x/SKILL.md`, `sub/AGENTS.override.md`, `sub/claude.md`, `CLAUDE.md`, `CODEOWNERS`, `.shellcheckrc`, `lib/.gitmodules`, `setup/keel.sh`, and `scripts/check.sh`. `.pi/` and `.agents/` are process directories at any depth. `setup/README.md` and `setup/TESTING.md` are not forbidden. `CLAUDE.md` is the fallback context file Pi Agent loads. The doctor names both lines "Pi process paths".

**Why.** The gate must not be weaker than `scripts/check-scope.py` on Pi Agent paths. The host gate also forbids `.gitmodules`.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Rule names match as a basename at any depth (`(^|/)name$`). `.github/`, `setup/`, and `scripts/` match at the root. `.pi/` and `.agents/` match at any depth (`(^|/)`).

<a id="atk-a19"></a>
<a id="atk-a19b"></a>

### ATK-A19/A19b reset_shadow does not follow symlinks

**Level.** CRITICAL

**Check.** The agent replaces `shadow/<task>.git/config` with a symlink to a host file (A19), or `objects/info` with a symlink to a host dir (A19b). The host file must stay unchanged, and A19b must be refused (exit 8, `shadow tampered`).

**Why.** The shadow is writable for the agent and `reset_shadow` runs on the host as the owner. Writing through a symlink clobbers any host file the owner can write.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Refuse if the shadow dir, `objects`, or `objects/info` is a symlink. `rm -f` control files before writing. Write with `set -C`.

<a id="atk-a20"></a>

### ATK-A20 nested .git path

**Level.** CRITICAL

**Check.** A hand-built tree containing `sub/.git/config` must fail. The suite accepts either `nested .git` or `fetch/fsck`. Fetch fsck catches it first. The gate rule `(^|/)\.git(/|$)` is the second layer. Mutants M40 and M41 in `setup/tests/harness/mutate.py` cover those two layers.

**Why.** A nested `.git` runs agent-chosen config (for example `core.fsmonitor`) if anyone ever runs git in that directory on the host.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep both fetch fsck and the `DOTGIT` rule. Never run host git in task dirs.

<a id="atk-a21"></a>

### ATK-A21 tests run from main's entrypoint

**Level.** CRITICAL

**Check.** The agent rewrites `test.sh` to always print OK and breaks `app.txt`. The gate must fail with `tests (main:test.sh)`.

**Why.** If the agent controls the test script, a passing gate test means nothing.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** The gate runs `main:$KEEL_TEST_ENTRY` (default `test.sh`), mounted read-only separately from the incoming tree.

<a id="atk-a22"></a>
<a id="atk-a22b"></a>

### ATK-A22/A22b no merge or orphan commits

**Level.** CRITICAL

**Check.** A merge with an unrelated orphan history (`-s ours`, zero files changed) (A22) and a merge of two main-based branches (A22b) must fail.

**Why.** Merges let an agent park unrelated history on the branch the broker pushes, with an empty diff.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** `rev-list --min-parents=2 main..I` and `--max-parents=0 main..I` must both be empty.

<a id="atk-h1"></a>

### ATK-H1 no mount/chown/caps

**Level.** CRITICAL

**Check.** mount, chown, and unshare are denied; CapEff=0, **CapBnd=0**, NoNewPrivs=1. CapEff is 0 for any non-root user, so the suite also requires CapBnd. On Darwin, an emulated chown on a bind mount still passes when mount and unshare are denied and CapEff, CapBnd, and NoNewPrivs match.

**Why.** Privilege escalation inside the container, the first step of an escape.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `--cap-drop ALL --security-opt no-new-privileges`.

<a id="atk-h2"></a>

### ATK-H2 fork bomb contained

**Level.** CRITICAL

**Check.** The bomb container reads its own `pids.max` and compares it with `${PIDS:-128}` (the same expansion `keel.sh` passes to `--pids-limit`) before any bomb starts. A reading of `max`, or any other number, is not that pinned limit: the bomb does not start and the result is `NOT BLOCKED`. M26 deletes `--pids-limit` and is killed by `pids.max` not equal to the pinned limit. On a runner whose default `pids.max` is already 128, this mutant could survive, because the reading would match the pin. When the values match, the bomb must finish and the host must still fork. Run attack suites one at a time: containers share the host uid, and so share its process limit.

**Why.** Host denial of service.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `--pids-limit`.

<a id="atk-h3"></a>

### ATK-H3 memory limit

**Level.** CRITICAL

**Check.** The container's `memory.max` matches the configured limit, and the allocator is OOM-killed (exit 137) or the container is OOM-killed. `--memory-swap` is set equal to `--memory`, so the limit is not raised by swap.

**Why.** Host denial of service. Swap on top of the memory limit can let an over-limit allocation survive.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `--memory` and `--memory-swap` equal. The default in `setup/keel.sh` is `512m`. On some cgroup v2 hosts `memory.swap.max` still reads `max` because swap is not accounted. That reading is not the verdict; the OOM result is.

<a id="atk-h4"></a>

### ATK-H4 no writes outside mounts

**Level.** CRITICAL

**Check.** `/` is mounted `ro` (from `/proc/mounts`), no writes outside the mounts, and `/tmp` tmpfs is capped at 64 MiB. The suite checks that a write of `/tmp` stops at 67108864 bytes. A non-root user cannot write `/etc` anyway, so the suite also checks the mount.

**Why.** Persisting tools or state in the image layer; filling host disk through /tmp.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `--read-only --tmpfs /tmp:size=64m`.

<a id="atk-h5"></a>

### ATK-H5 cpu limit

**Level.** CRITICAL

**Check.** `cpu.max` inside the container has a quota (not `max`).

**Why.** One agent can starve the host and the other agents.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `--cpus`.

<a id="atk-s-h1"></a>

### ATK-S-H1 clean environment starts a role

**Level.** CRITICAL

**Check.** With no denylisted name set, a role starts and those names are absent inside the container.

**Why.** A clean launch has to keep working. The container must not inherit the host environment.

**If it fails.** FAIL.

**How to fix.** Pass only the explicit environment list in `setup/keel.sh`.

<a id="atk-s-a1"></a>

### ATK-S-A1 denylisted name refuses the role

**Level.** CRITICAL

**Check.** Setting one exact denylisted name refuses the role. The value is not printed and is not in the launch log. The container does not start.

**Why.** A secret in the launching environment must not ride into a role.

**If it fails.** FAIL.

**How to fix.** Keep the exact-name check in front of `role` and `role-env`.

<a id="atk-s-a2"></a>

### ATK-S-A2 format patterns are redacted

**Level.** CRITICAL

**Check.** Token prefixes, `sk-` and `sk-ant-` keys, a PEM private key block, and `password=`, `api_key=`, and `token=` assignments are replaced when they are not environment values.

**Why.** A renamed variable bypasses the name list. The log still has to hide those shapes.

**If it fails.** FAIL.

**How to fix.** Keep the pattern scan in redaction and in the second pass.

<a id="atk-s-a3"></a>

### ATK-S-A3 mount error is logged

**Level.** CRITICAL

**Check.** An unexpected error while building mounts is written as `mounts_internal` with the exception type, and the command returns failure.

**Why.** A traceback with no log line hides a refused launch.

**If it fails.** FAIL.

**How to fix.** Log that failure and return non-zero. Do not ignore it.

<a id="atk-sec-h1"></a>

### ATK-SEC-H1 clean bundle

**Level.** CRITICAL

**Check.** A change with no secret shape passes the gate.

**Why.** The scanner must not fail an ordinary bundle.

**If it fails.** FAIL.

**How to fix.** Keep the scan limited to files added or edited in the change. Git history is not scanned. An encoded secret is not this check. A secret split across files is not this check.

<a id="atk-sec-03"></a>

### ATK-SEC-03 secret shape in the change

**Level.** CRITICAL

**Check.** A bundle that adds a `ghp_` shaped token fails the gate with `secret in change`. The token text is not printed.

**Why.** A secret in the change must not pass the host gate.

**If it fails.** FAIL.

**How to fix.** Keep the gitleaks scan in `setup/keel.sh gate`. Pass `--ignore-gitleaks-allow`, `--config` for the harness config, and `--gitleaks-ignore-path` for the harness ignore file. Do not load a `.gitleaksignore` or `.gitleaks.toml` from the change. Install gitleaks 8.30.1 before the gate runs. A timeout or any other scanner error fails the gate. `GL-01` is the critical doctor check for that binary.

<a id="atk-sec-04"></a>

### ATK-SEC-04 inline allow comment

**Level.** CRITICAL

**Check.** A `ghp_` shape with a `gitleaks:allow` comment on the same line still fails the gate.

**Why.** An inline comment must not suppress a finding in the change.

**If it fails.** FAIL.

**How to fix.** Keep `--ignore-gitleaks-allow` on the scan.

<a id="atk-sec-05"></a>

### ATK-SEC-05 product ignore file

**Level.** CRITICAL

**Check.** A change that adds both a `ghp_` shape and a `.gitleaksignore` naming that finding still fails the gate.

**Why.** The product must not supply the ignore list or the scanner config.

**If it fails.** FAIL.

**How to fix.** Point `--gitleaks-ignore-path` at the harness ignore file, and do not copy `.gitleaksignore` or `.gitleaks.toml` into the scanned tree.

## Pi launch

<a id="pi-01"></a>

### PI-01 Pi version

**Level.** CRITICAL

**Check.** The installed `@mariozechner/pi-coding-agent` package and the `keel-pi` image both report 0.73.1.

**Why.** Flag meaning and prompt order are pinned to that release. A different release can load different files.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Install that exact package and rebuild `keel-pi` from `setup/docker/keel-pi.Dockerfile`.

<a id="pi-02"></a>

### PI-02 Append file

**Level.** CRITICAL

**Check.** Every launch passes `--append-system-prompt` with a file path under `$KEEL_ROOT/.keel/runs/`. The value is a file, not inline text.

**Why.** Pi treats a missing flag as a request to load `APPEND_SYSTEM.md` from the project or the agent directory. Inline text also hits the operating-system argument limit.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Keep the launch writer on a file path, and pass that flag on every role.

<a id="pi-03"></a>

### PI-03 Discovery flags

**Level.** CRITICAL

**Check.** The launch argv contains `-ne` and `-np`. It does not contain `-nc`, `-ns`, or `-e`.

**Why.** `-ne` turns off extension discovery. `-np` turns off prompt templates. `-nc` would turn off `AGENTS.md` and `CLAUDE.md`. `-ns` would turn off skills. An explicit `-e` still loads an extension even when `-ne` is set.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Keep `-ne` and `-np`. Do not pass `-nc`, `-ns`, or `-e`.

<a id="pi-04"></a>

### PI-04 Agent directory

**Level.** CRITICAL

**Check.** `PI_CODING_AGENT_DIR` is an empty directory mounted read-only. A missing directory is a failure. An empty directory is a pass.

**Why.** Pi reads extensions, settings, skills, and prompt templates from that directory. A writable directory lets the role plant them.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Create an empty directory for the launch and mount it read-only. Do not mount the host `~/.pi`.

<a id="pi-05"></a>

### PI-05 HOME

**Level.** CRITICAL

**Check.** `HOME` is an empty directory mounted read-only. A missing directory is a failure. `HOME=/tmp` is a failure.

**Why.** With skills left on, Pi also looks at `$HOME/.agents/skills`. A writable home lets the role create that tree.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Point `HOME` at an empty read-only directory. Do not use `/tmp`.

<a id="pi-06"></a>

### PI-06 Skills snapshot

**Level.** CRITICAL

**Check.** `/work/.agents/skills` is mounted read-only from a snapshot of `.agents/skills` on the main branch. The export refuses a symlink. The worktree copy is not the source.

**Why.** A role must not publish a skill for the next role by writing the worktree, and a symlink must not point the catalog outside the snapshot.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Export the tree from `main` with `git ls-tree`, refuse mode `120000`, and mount the result read-only.

<a id="pi-07"></a>

### PI-07 Ancestors of /work

**Level.** CRITICAL

**Check.** The role image has no `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md`, or `CLAUDE.MD` in any ancestor of `/work`, including `/`. The image build runs the same guard.

**Why.** Pi walks context files from the working directory to filesystem `/`, not only to the git root. A file baked into the image would load after the harness rules.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Keep `setup/docker/ancestor-guard.sh` in the image build. Do not add those names above `/work`.

<a id="pi-08"></a>

### PI-08 Precedence

**Level.** CRITICAL

**Check.** The harness rules in the append file say that harness rules win, and that this covers Project Context files (`AGENTS.md` and `CLAUDE.md`) and skill descriptions.

**Why.** Pi places Project Context and the skills catalog after the append. Those texts are untrusted. The harness states which side wins.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Keep that sentence in the harness part of the append file.

<a id="pi-09"></a>

### PI-09 Extensions

**Level.** CRITICAL

**Check.** The row is present and recorded as not applicable. This step does not load an extension.

**Why.** A missing row must not look like a pass. An extension can add tools and change the prompt, so discovery stays off until a later step vendors one and pins its hash.

**If it fails.** FAIL, including when the row is missing. The verdict is not ready.

**How to fix.** Keep the recorded not-applicable row. Do not pass `-e`.

## Discoveries

<a id="disc-01"></a>

### DISC-01 Accepted directories only

**Level.** CRITICAL

**Check.** The memory index walks `.keel/memory/discoveries/` and `.keel/memory/adr/` only. It does not add a sibling candidates directory.

**Why.** A candidate is untrusted until the host accepts it. Indexing it would put one role’s draft into the next role’s prompt.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Keep the index on those two directories.

<a id="disc-02"></a>

### DISC-02 Candidates are excluded

**Level.** CRITICAL

**Check.** A file under `.keel/candidates/` is not listed in the index, and the candidates directory exists as a place the host can scan at the end of the iteration.

**Why.** Discarded and pending notes are not memory.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Do not point the index at `.keel/candidates/`.

<a id="disc-03"></a>

### DISC-03 Accepted memory is read-only

**Level.** CRITICAL

**Check.** The `.keel/memory` mount for a role is read-only.

**Why.** An accepted note is changed only by the harness.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Keep the memory mount read-only.

<a id="disc-04"></a>

### DISC-04 Filter entrypoint

**Level.** CRITICAL

**Check.** `setup/lib/discovery_filter.py` is present and is not a symlink.

**Why.** Promotion has to go through the host filter.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Restore that file from the harness tree.

<a id="disc-05"></a>

### DISC-05 Tools mount

**Level.** CRITICAL

**Check.** `setup/tools/write-memory-candidate.py` is present, and the tools mount mode is read-only.

**Why.** Append roles share one script. They must not be able to replace it.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Keep the script in `setup/tools/` and mount that snapshot read-only.

<a id="disc-06"></a>

### DISC-06 Skill visibility

**Level.** CRITICAL

**Check.** The skills snapshot for the developer and the orchestrator includes `keel-write-memory`. The snapshot for another role does not.

**Why.** Other roles are not candidate writers. A skill they can read is an instruction they should not have.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Drop that skill directory when exporting a non-append role.

<a id="disc-07a"></a>

### DISC-07a Stub and Decisions pin (CI)

**Level.** CRITICAL

**Check.** The stub is refused when the CI marker is unset, and it is allowed when `CI=true`. The judge allow file names only `openrouter.ai`. The broker accepts `POST /api/alpha/decisions` and refuses a chat-completions path. The model id is `typesafe/jev-1.14`. A live key is not required for this row.

**Why.** CI must not call the paid API, and a production promote must not silently keep the stub. The broker must not become a generic proxy.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Keep the stub tied to the CI marker, and keep the host and path pin.

<a id="disc-07b"></a>

### DISC-07b Key file outside CI

**Level.** CRITICAL

**Check.** When the CI marker is set, the row passes because the stub needs no live key. Otherwise the configured key path must exist, must not be a symlink, and must not be group- or world-accessible. The check does not read the file.

**Why.** A promote outside CI needs a key the broker can open, and a loose file is visible to other users. Printing the value would copy it into the doctor output.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Point `KEEL_JUDGE_KEY_FILE` at a regular file with mode `0600` or `0400`, or place that file at `$KEEL_ROOT/.keel/keys/openrouter.key`. Do not commit a real key.

<a id="disc-08"></a>

### DISC-08 Judge is not reachable from a role

**Level.** CRITICAL

**Check.** A role cannot reach the judge. The judge network is `keel-judge`, not `keel-egress`, and the launch spec publishes no port and passes no key in the environment.

**Why.** A role that can open the broker can ask it to spend the key.

**If it fails.** FAIL. The verdict is not ready.

**How to fix.** Keep the judge off the role network. Do not publish a port and do not put the key in the environment.
