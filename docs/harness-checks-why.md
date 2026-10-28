# Why each keel-doctor check exists

This page explains every check printed by `setup/keel-doctor.sh`. Each line of doctor output has an ID. The section for that ID is below. The fragment is the ID in lower case (`docs/harness-checks-why.md#env-08`).

How to run it: [Getting started](harness-getting-started.md).

**Rule:** any new check needs a section here, in this shape, before it is added to the doctor. Same rule as [docs/why.md](why.md).

Levels: **CRITICAL**: a failure means NOT READY and exit code 1. **RECOMMENDED**: warn, harness still usable. **OPTIONAL**: informational.

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

**Level.** RECOMMENDED

**Check.** Where does a container escape land? Rootless Docker or rootless podman: pass. Docker Desktop on macOS or Windows (`OperatingSystem` contains "Docker Desktop"): pass, reported as `Docker Desktop VM`. An escape lands in Docker's Linux VM, not on the host. A rootful daemon on a Linux host: warning.

**Why.** With a rootful daemon, a container escape gives root on the host. This is the most serious residual risk.

**If it fails.** Warning. The harness still works, but a kernel or runtime bug becomes a host-root bug.

**How to fix.** Install rootless Docker (`dockerd-rootless-setuptool.sh install`) or podman. On a systemd host, enable cgroup delegation so `--pids-limit`, `--memory`, and `--cpus` work.

<a id="env-06"></a>

### ENV-06 Image keel-git

**Level.** RECOMMENDED

**Check.** Image `keel-git` exists locally and its architecture matches the daemon's (amd64 or arm64). `setup/docker/keel-git.Dockerfile` pins no platform, so `docker build` produces a native image.

**Why.** Containers run with `--network none`, so they cannot pull an image or install git at runtime.

**If it fails.** Warning. If the image is missing, the first role fails to start. If the architecture does not match, everything runs under emulation and is slow.

**How to fix.** From the repository root: `docker build -t keel-git -f setup/docker/keel-git.Dockerfile setup/docker`. The doctor prints that `-f` path from `setup/`.

<a id="env-07"></a>

### ENV-07 Hardening flags accepted

**Level.** CRITICAL

**Check.** A test container starts with `--network none --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp --pids-limit --memory --cpus --user uid:gid`.

**Why.** Without these flags the container is not an isolation boundary. Rootless runtimes without cgroup delegation reject the limits.

**If it fails.** FAIL. The harness would refuse to start, or run weaker containers.

**How to fix.** Enable cgroup v2 delegation (systemd), or use rootful Docker and accept ENV-05.

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

### ATK-N1 no network

**Level.** CRITICAL

**Check.** `--network none`: only `lo`, no HTTP, no DNS.

**Why.** Exfiltration of code or secrets; pulling malicious payloads.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Never pass `--network` other than none to agent containers.

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

**How to fix.** Keep `FORBID_PREFIX` and `FORBID_NAME` in `setup/keel.sh` in sync with `scripts/check-scope.py`. `setup/keel.sh` also forbids `.pi/` and `.gitmodules`.

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

**Check.** A mode-160000 entry is rejected. `.gitmodules` is also a forbidden path.

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

**Check.** Commits adding `.github/workflows/evil x.yml` (space), `.github/workflows/é.yml` (UTF-8, which git C-quotes), and `.github/a<TAB>b"c.yml` must fail with `forbidden path`. The suite calls these B1.

**Why.** Splitting `git diff --raw` on whitespace lets a space or a C-quoted path slip past every path rule.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Parse `git diff --raw -z` with `read -d ''`. Never parse non-`-z` diff output for paths.

<a id="atk-a18"></a>
<a id="atk-a18b"></a>

### ATK-A18/A18b PR #5 process paths

**Level.** CRITICAL

**Check.** `docs/AGENTS.md` (A18) must fail with `forbidden path`. A18b does the same, one path per run, for `CLAUDE.md`, `CLAUDE.local.md`, `CODEOWNERS`, `.cursorrules`, `.windsurfrules`, `.clinerules`, `.mcp.json`, `.shellcheckrc`, `.gitmodules`, `setup/`, `scripts/`, `.cursor/`, and `.claude/`. The doctor names both lines "PR #5 process paths". The suite calls this B2.

**Why.** The gate must not be weaker than `scripts/check-scope.py`. `setup/keel.sh` comments that its forbidden set is that process set, plus `.pi/` and `.gitmodules`.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Rule names match as a basename at any depth (`(^|/)name$`). Prefixes match at the root.

<a id="atk-a19"></a>
<a id="atk-a19b"></a>

### ATK-A19/A19b reset_shadow does not follow symlinks

**Level.** CRITICAL

**Check.** The agent replaces `shadow/<task>.git/config` with a symlink to a host file (A19), or `objects/info` with a symlink to a host dir (A19b). The host file must stay unchanged, and A19b must be refused (exit 8, `shadow tampered`). The suite calls this B3.

**Why.** The shadow is writable for the agent and `reset_shadow` runs on the host as the owner. Writing through a symlink clobbers any host file the owner can write.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Refuse if the shadow dir, `objects`, or `objects/info` is a symlink. `rm -f` control files before writing. Write with `set -C`.

<a id="atk-a20"></a>

### ATK-A20 nested .git path

**Level.** CRITICAL

**Check.** A hand-built tree containing `sub/.git/config` must fail. The suite accepts either `nested .git` or `fetch/fsck`. Fetch fsck catches it first. The gate rule `(^|/)\.git(/|$)` is the second layer. Mutants M40 and M41 in `setup/tests/harness/mutate.py` cover those two layers. The suite calls this B4.

**Why.** A nested `.git` runs agent-chosen config (for example `core.fsmonitor`) if anyone ever runs git in that directory on the host.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep both fetch fsck and the `DOTGIT` rule. Never run host git in task dirs.

<a id="atk-a21"></a>

### ATK-A21 tests run from main's entrypoint

**Level.** CRITICAL

**Check.** The agent rewrites `test.sh` to always print OK and breaks `app.txt`. The gate must fail with `tests (main:test.sh)`. The suite calls this B5.

**Why.** If the agent controls the test script, a passing gate test means nothing.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** The gate runs `main:$KEEL_TEST_ENTRY` (default `test.sh`), mounted read-only separately from the incoming tree.

<a id="atk-a22"></a>
<a id="atk-a22b"></a>

### ATK-A22/A22b no merge or orphan commits

**Level.** CRITICAL

**Check.** A merge with an unrelated orphan history (`-s ours`, zero files changed) (A22) and a merge of two main-based branches (A22b) must fail. The suite calls this B6.

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

**Check.** `pids.max` inside the container is a number (not `max`). The bomb is contained and the host can still fork. Run attack suites one at a time: containers share the host uid, and so share its process limit.

**Why.** Host denial of service.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `--pids-limit`.

<a id="atk-h3"></a>

### ATK-H3 memory limit

**Level.** CRITICAL

**Check.** The suite reads 2000m from `/dev/zero` and expects the process to be OOM-killed (exit 137).

**Why.** Host denial of service.

**If it fails.** FAIL (CRITICAL): the isolation property is not holding on this machine. Do not run agents.

**How to fix.** Keep `--memory`. The default in `setup/keel.sh` is `512m`.

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
