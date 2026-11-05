# Roles and visibility

A **role** is one job in the pipeline: orchestrator, architect, critic, tester, developer, auditor, design reviewer, verifier, QA, or researcher. The owner and the bot are not agent roles. The owner decides. The bot account opens pull requests.

**Status.** Folder mounts are enforced by `setup/keel.sh role` and `role-env`. An unknown role name is refused. The gate suite’s work-tree container is `proto`, not a role. Content fencing is not in this step.

## Folder allowlist and unified deny

A role sees the folder roots in `setup/allow/<role>.paths`, and nothing else. The unified deny then removes paths from those roots. A path on both lists is withheld. Enforcement is the mount: the path is not readable and not writable. The role is not asked to look away.

| Role | Folder roots | Write |
|---|---|---|
| orchestrator | `briefs/`, `docs/`, `tests/`, `.keel/decisions/<task-id>/` | `briefs/`, `.keel/decisions/<task-id>/` |
| architect | `briefs/`, `docs/`, `.keel/decisions/<task-id>/` | none in this step (decisions are read-only) |
| developer | `src/`, `docs/`, `tests/` | `src/`, `docs/`. `tests/` is read-only |
| tester | `src/`, `docs/`, `tests/` from the commit recorded at setup | `tests/` in that snapshot only |
| auditor | `src/`, `docs/` | none |
| skills_auditor | `skills-draft/`, `skill-review/` | none |
| critic | `plans/` | none |
| design_reviewer | `docs/` | none |
| verifier | `findings/` | none |
| qa | `qa-stub/` | none |
| researcher | `research-stub/` | none |

`setup/deny/base` always withholds secret basenames (`.env` and the other names in that file), `.keel/logs/`, `.keel/runs/`, `.keel/deny.local`, and `.git`. `.keel/decisions/` is withheld from every role except the orchestrator and the architect. `.agents/` is withheld. `.agents/skills` is the exception: every launchable role may read it, and the harness mounts that tree read-only from a snapshot of the main branch. The rest of `.agents/` stays withheld, including from the skills auditor. `.keel/deny.local` may add paths. A line that tries to remove a base entry refuses the launch. The file is read once per task. Roles cannot edit it.

D1 confidence notes and the handoff for a task live at `.keel/decisions/<task-id>/` in the product git tree (`d1.md`, `handoff.md`). The orchestrator can write them. The architect can read them. The developer, the tester, and the auditor cannot. A public product repository publishes those files. The harness prints that warning once. This repository does not commit task decisions.

Launch decisions are JSONL at `$KEEL_ROOT/.keel/logs/launch.jsonl`. Only the harness writes that file. Each record includes `redactions`. Replacements are `[REDACTED:token]`, `[REDACTED:key]`, `[REDACTED:password]`, `[REDACTED:env]`, or `[REDACTED:unknown]`. `.keel/runs/` is temporary and is removed when the command exits. Both directories are gitignored.

Changing a role’s folders, the deny base, or who can see decisions is a `process-files` pull request, then review, then an owner merge.

A secret whose basename is not in the deny base is still visible. A secret-named file created inside a read-write mount during that same command can be read until the command ends. There is no size cap on the launch log. Content fencing is still backlog.

### Orchestrator read and write

The orchestrator and the host dispatcher are planned for Step 7. They are not built yet. The mount row above is what `role orchestrator` does now.

- **Read, in this step:** the folders in the table, except paths the unified deny withholds.
- **Write zone only, in this step:** `briefs/` and `.keel/decisions/<task-id>/`.
- **Read, in the Step 7 design:** everything except secrets and paths in `.keel/deny.local`. The D1 confidence-notes log is readable.
- **Write zone only, in the Step 7 design:** the brief; the split plan; dispatcher **request files**; the D1 confidence-notes log; owner decisions into ADR / `docs/owner-decisions.md` and discoveries (via allowed paths); messages to the owner.
- **Must not write:** product code, tests, process files, or gates.
- **Must not** launch containers or talk to other agents directly. The host launches roles via `setup/keel.sh role`.

Product tests live in `tests/` today. The developer can read that directory and cannot write it. [tests/README.md](../tests/README.md).

## Network

A role is not started when the launching environment contains a denylisted secret name, or when free space under `KEEL_ROOT` is below `KEEL_WORK_MIN_FREE`. The container does not receive the host environment. The same runtime check applies to every role. See [Tokens](security.md#tokens).

The harness runs one forward proxy and one internal Docker network, `keel-egress`. `setup/keel.sh egress-up` creates that network with `--internal` and `--ipv6=false`, starts the CI mock on it, and starts the proxy. The proxy is the only container also attached to a second network that can route outward. Roles do not get a route of their own.

`setup/keel.sh role developer` joins `keel-egress`, points `HTTP_PROXY` and `HTTPS_PROXY` at the proxy’s forward port, and turns off IPv6 inside the container. The forward port is 3128. The proxy’s admin port listens on `127.0.0.1` inside the proxy’s own network namespace, not on the role network.

Every other role stays on `--network none`: orchestrator, architect, critic, tester, auditor, skills auditor, design reviewer, verifier, QA, and researcher. So do `proto`, setup, export, and the test re-run. QA does not reach a local app yet. The researcher does not reach the internet yet. Those two rows in the design table below wait for the research step and the QA step. Other roles do not share the proxy until one of them needs a model API.

| Role | Network in the v1 design | What the harness runs |
|---|---|---|
| Developer | No network, except the model API through the proxy | Internal network plus the proxy. The allowlist is the CI mock only |
| Researcher | Internet, for published sources. No code and no tokens in that container | `--network none` |
| Critic | No network | `--network none` |
| QA | The local app only | `--network none` |
| Other roles | The same allowlist proxy, once they need a model API | `--network none` |

Allowlists live in `setup/egress/<role>.allow`, one destination per line, `host` or `host:port`. Blank lines and `#` comments are ignored. A glob, a suffix wildcard, or any other malformed token refuses the launch. Before a match, an ASCII host is lowercased, one trailing dot is removed, and an IDN is converted to punycode. An IP is allowed only when that literal is listed. A line without a port allows port 80 for cleartext HTTP and port 443 for CONNECT. Any other port must be written on the line. The grammar is also in [setup/egress/README.md](../setup/egress/README.md).

HTTPS is decided from the CONNECT host and port. Cleartext HTTP is decided from the request target’s host and port. A redirect is checked again on the next request. The proxy does not intercept TLS, so it does not read SNI inside a tunnel it has already allowed.

A missing profile, a malformed profile, a proxy container that exists but is not running, or an egress network whose internal flag is not the one the harness is built for refuses the launch. The harness does not restart a stopped proxy. That failure is logged.

Denials are appended to `$KEEL_ROOT/.keel/logs/egress.jsonl`. A record has a timestamp, the role, the sanitized host and port, and a reason. The path, the query, and any userinfo are not written. A host that contains a line break, a NUL, or more than 253 characters is recorded as invalid so one request cannot add a second line.

Peers on `keel-egress`, including the CI mock, are reachable from the developer container without using the proxy. The mock answers its own HTTP responses and does not dial out. Anything else placed on that network is reachable the same way, so it must not forward traffic off the network. Only the proxy is attached to the outward network.

The IPv6 check in the suite reads the container’s `disable_ipv6` setting and relies on the network being created with `--ipv6=false`. It does not open a public IPv6 connection.

On some hosts the packet filter drops traffic between containers. The doctor’s EG-03 check then fails, because the forward port does not answer, and the verdict is not ready. An operator has to allow that container-to-container traffic before the proxy path can work. Docker Desktop and Podman have not been verified for this network and are unsupported for it for now. Linux Docker is the path the checks cover. [Why each keel-doctor check exists](harness-checks-why.md#eg-01).

## Skills each role receives

A **skill** is a project file of instructions for a role, under `.agents/skills/`. Creating, changing, or deleting one requires the owner’s approval. [Human decisions](owner-decisions.md).

The developer, the tester, QA, and the architect receive project skills. The orchestrator can be asked, in chat, to order a skill. Usage is written to the log. A comparison trial of two versions is reserved for a major stack skill. How that trial would be measured is still open.

Harness checklists for the critic and the reviewers are not project skills. They are generated from `standards/rules.md` and mounted read-only. They do not go through the project skill-approval card. The standard itself is specified in [Quality standard](quality.md) and the file is not in the repository yet.

A suspicious skill is one that contains install commands, network use, secret access, or a way around a gate. The scan highlights those lines on a card, and the skill stays off until the owner says yes.

## The owner and the bot

The owner is not a container role. The owner reads the envelope, answers D2 questions, and merges. The owner may work through an external chat **intermediary** or a direct Pi Agent terminal; both hit the same orchestrator input. [Working through a chat agent](working-through-chat.md).

The bot is not a container role either. It is the GitHub **bot account** that opens the pull request at L10. In the design, a GitHub token exists only in that push step. The prototype’s push command is `setup/keel.sh push-stub`. It prints the command and does not push. The doctor fails if `GH_*`, `GITHUB_*`, or `BOT_GH_TOKEN` is set in the environment it runs from. [Security](security.md#tokens).

## Related

[Security](security.md) · [Pipeline](pipeline.md) · [Quality standard](quality.md) · [Architecture](architecture.md) · [Working through a chat agent](working-through-chat.md)
