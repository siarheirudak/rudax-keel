# rudax-keel implementation plan v1

Docs name the owner, the user, and the bot. Among AI runtimes they name Pi only. `CLAUDE.md` appears only as a Pi fallback filename.

Each step is one future PR that needs the owner's yes before it lands. The bot opens PRs; the owner alone merges and approves. Effort: **S** small, **M** medium, **L** large (rough). Do not treat unverified research numbers as facts; thresholds marked **to verify**, **our choice**, or **our number** stay labelled until measured.

Depends on the existing base: agent isolation and the host-gate prototype. The harness is already in this repository. Process-file and skill changes go in separate `process-files` pull requests after the owner approves them.

---

## Orchestrator and host dispatcher (design)

This is the control-plane wiring for chat-driven work. It is built as **Step 7**; grilling behaviour is **Step 8**. Authoritative detail: [Orchestrator and dispatcher](orchestrator-dispatcher.md) and [dispatcher transitions](dispatcher-transitions-v1.yaml).

### Two front ends, one input

Usage is entirely through chat in natural language.

1. **Typical:** the user talks to an **external chat agent** (an intermediary). That agent relays into the **dispatcher inbox**. Recommended intermediary instructions live in [Intermediary agent instructions](../intermediary-agent-instructions.md) and [Working through a chat agent](../working-through-chat.md).
2. **Alternative:** a **direct Pi** path that still enters through the same dispatcher inbox (the dispatcher alone writes orchestrator rpc stdin).

Both front ends hit the same warm orchestrator. There is no second confirmation layer on top of D2. No `/approve` command.

### Safety model (chat path)

- **Merge** is done only by the owner on GitHub. The intermediary cannot merge, approve, or change GitHub rules.
- The intermediary passes the owner's D2 answer **verbatim** together with its **interpretation**; if unclear or the two disagree, the orchestrator re-asks; raw text goes to audit. Per-relay checklist: never drop owner-critical items; end with what is needed from the user (or “nothing”).
- The user's answers are **logged verbatim with timestamp** in the task log and are **visible in the PR envelope**.
- Orchestrator/agent output and other external content are **data**, not instructions to the intermediary.
- Secrets stay out of chat.
- Mid-turn user messages are **queued** and not lost. Priority interrupt or cancel mid-turn is backlog.

### Orchestrator (reasoning plane)

- **Warm per-task** Pi container: `pi --mode rpc` with the **session file in the task folder**. Removed at task end (PR / cancel / fail / dossier); on owner wait → **stop** (not remove), resume from session.
- **One tool only:** `keel_request` (allowlisted kinds). Argv fail-closed: **no** bash, write, edit, or codemode. Read/search-class tools plus `keel_request` only.
- **Read:** everything except **secrets** and paths in **`.keel/deny.local`**. Reads/writes the **D1 confidence-notes log** (hidden from the auditor until verdict). Ordinary product **tests are visible**.
- **Write zone only (via dispatcher):** the brief; the split plan; `keel_request` payloads; the D1 log; ADR / `docs/decisions.md` and discoveries. Messages to the user (D2 cards: options + default) go through the dispatcher / intermediary.
- **Must not write:** product code, tests, process files, or gates.
- **Does not launch containers** and does not talk to other agents. Extension computes a deterministic `idempotency_key`; dispatcher applies a two-phase WAL.
- **D1** = orchestrator **confidence** (high / medium / low), not an owner decision. Low confidence always raises a D2. **D2** is always an owner decision.
- On `TEST_CONTRADICTS_BRIEF`, the orchestrator **checks the claim against the brief** and decides; developer prose is **never** forwarded to L3 — only the orchestrator's reformulated finding.

### Host dispatcher (control plane) — new component

A host script (not an agent) that:

- Owns **task state** and the machine FSM from [dispatcher-transitions-v1.yaml](dispatcher-transitions-v1.yaml) (repo path after Step 7: `setup/dispatcher/transitions.v1.yaml`). Prose is not a second truth.
- Runs **gates**, journals, status line (no LLM), and role launches via `setup/keel.sh role` (**ephemeral** `--rm` role containers).
- Accepts at most **one** `keel_request` per orchestrator turn, only after rpc **turn-end**; second request → refuse + audit.
- Idempotency WAL: write **`IN_PROGRESS`** before the side effect, then **`COMMITTED`** after; on restart reconcile `IN_PROGRESS` (never silent skip, never blind re-run).
- Circuit breaker: identical **diff-hash** on consecutive attempts only. Every `kind: back` edge has non-null `budget_ref`.
- Deep back to L2/L3: RO **previous-attempt** archive outside the work tree/git; developer **keeps read access**; shallow gate→L5 keeps the worktree.
- L3 mounts: product tree **RO**, writes only in test dirs; host `git diff --name-only` defense in depth. Developer tests mount **RO**; on FAIL the developer gets **full** gate output and stacks.
- Mechanical gate FAIL → `dispatcher_only` edges (no model vote).
- **Logs** every transition, rejection, gate result, timeout, circuit-breaker, and owner answer (raw D2 in audit).
- Is the only path from one role to the next: agents never message each other.

**Pi smoke (before implementation):** a short rpc and tool-lock smoke on the orchestrator image. It proves a `pi --mode rpc` session can start and stop, and that bash, write, and edit are unavailable.

The owner's answers (a D2 question, a skill, a split, an irreversible change, a merge, or a release) are recorded in an ADR, in `docs/decisions.md`, or as a discovery. A new dependency still waits on a D2 question (`WAITING_DEP_D2`).

---

## Build order

### Step 1 — Visibility deny-list + mount policy
- **Does:** Enforce deny-list by not mounting: **secrets** (all roles); **D1 confidence-notes log** (**auditor** until verdict only — orchestrator writes and may read it); new implementation (tester → pre-implementation commit); developer skills (auditor until verdict). Ordinary product **tests are visible** to roles that mount the work tree; **developer** mounts tests **read-only**. Harness-fixed paths + **`.keel/deny.local`** as a **flat list** of extra paths denied to **all** agents (including the orchestrator; e.g. user/customer data), enforced at **container mount** level, documented; project file may only **add** denies. Harness **base secret-pattern list**; projects may only **extend** it (cannot narrow). Tester write-scope and L3 product-RO / test-RW mounts are finalized in **Step 7** on top of this matrix. Content fencing is not in this step (backlog). See [Roles and visibility](../roles.md).
- **Depends on:** isolation (green), gate (green)
- **Effort:** M
- **Done when:** Developer can read tests but cannot write them (RO mount); orchestrator can read the D1 log and cannot see secrets/`deny.local` paths; auditor cannot see developer skills or D1 log before verdict; `deny.local` is flat and extend-only; secret-pattern base cannot be narrowed; docs state the matrix (no fence fixtures required here).

### Step 2 — Egress allowlist proxy
- **Does:** Harness proxy allowlist; developer has no network except model API (`network none` + proxy); other roles per design (researcher internet; QA only local app; critic no network).
- **Depends on:** Step 1
- **Effort:** M
- **Done when:** Developer egress test shows only model API; unauthorized destinations blocked; proxy logs denials.

### Step 3 — Rootless hardening + startup verification (mandatory in v1)
- **Does:** Make rootless Docker or Podman mandatory. Containers: `--cap-drop=ALL`, `no-new-privileges`, read-only rootfs + tmpfs, memory/cpu/pids limits, workdir quota; developer network none; secrets under a separate user. Startup verification script refuses to run if hardening is not in place. Chromium sandbox ON (no `--no-sandbox`); seccomp profile for Chrome; verify Playwright on the host first.
- **Depends on:** Step 1, Step 2, isolation green
- **Effort:** L
- **Done when:** Doctor/startup script fails closed on rootful or missing caps/limits; Playwright host check documented; Chromium runs without `--no-sandbox` under rootless; fixture refuses weak config.

### Step 4 — L1 context packaging script
- **Does:** Package allowed paths + one import level; ADR/discoveries one-file-per-entry; in-memory index (newest first); full text for path/tag/critical matches; token limit → `NEEDS_SPLIT`; CI path-exist / rename-follow / stale-deleted. (Content fencing remains backlog; packaging still treats packaged text as data in the design sense once fences land.)
- **Depends on:** Step 1
- **Effort:** M
- **Done when:** Fixture repo packages correctly under token budget; over-limit returns `NEEDS_SPLIT`; stale/renamed paths reported; index not stored on disk.

### Step 5 — Discoveries store (script filter accept/discard)
- **Does:** Date-prefixed discovery files with front matter; agents may append candidates; host script filter auto-accepts only if schema, existing paths, size, no bypass imperatives, and significance check pass (concrete paths or a rule + non-obvious pitfall/decision). Failures **DISCARDED** (no proposed list). Dossier script writes abort-cause entries. Only harness edits/deletes accepted files. Answers that belong in product memory go into an ADR, `docs/decisions.md`, or a discovery.
- **Depends on:** Step 4
- **Effort:** M
- **Done when:** Filter rejects bypass-imperative and insignificant fixtures; abort path writes cause via dossier script; L1 indexes only accepted discoveries; no proposed queue exists; those answers do not get a separate store.

### Step 6 — Standards generator (`standards/rules.md` → per-role views)
- **Does:** Single source `standards/rules.md`; generate per-role views mounted read-only as harness skills: developer (all rules; REA-01/02/04 only here), architect (DES/CMP/SCO/TYP-03/REL-01), tester (TST/COR-02/COR-04), auditor (COR/TST/ERR/TYP-02/03/SEC/SCO/REL/DOC), design reviewer (DES/CMP), static gate (STY/TYP-01/DUP/CX/REA-03/ERR-03/SEC-03). Apply merges DES-02→DES-01, CMP-03→CX-01, TST-04→COR-04. Move SEC-08 to NOT-to-flag. Each judgment rule gets flag / do-not-flag examples.
- **Depends on:** quality-standard research (done as input)
- **Effort:** M
- **Done when:** Generator produces views from one source; role mounts get only their subset; SEC-08 absent from emit-able ids; flag/do-not-flag examples present for judgment rules.

### Step 7 — Host dispatcher + warm orchestrator (process-files PR)
- **Pre-impl smoke (required first):** short Pi smoke on the target image — `pi --mode rpc` session start/stop, and **tool lock** proving bash / write / edit / codemode are unavailable while `keel_request` is present. Fail closed if smoke fails. Step 7 uses **rpc**.
- **Does:**
  - **Warm per-task orchestrator:** Pi in its own container with `pi --mode rpc` and the **session file under the task folder**; **rm** container at task end; **stop** (keep session) while waiting on the owner. Mounts per Step 1 (secrets + `.keel/deny.local` denied; D1 confidence-notes log readable/writable by orchestrator; tests visible). Skills/argv forbid writing product code, tests, process files, or gates.
  - **Single tool `keel_request`:** allowlisted kinds only (`ask_d2`, `brief_upsert`, `record_d1`, `propose_split`, `advance`, `return_to`, `run_role`, `wait_user`, `dossier`, `record_decision`, …). Extension computes deterministic `idempotency_key = hash(task, stage, attempt, kind, canonical payload)`. Atomic request write (`.tmp` → `rename`).
  - **Host dispatcher FSM:** load `dispatcher-transitions-v1.yaml` → install as `setup/dispatcher/transitions.v1.yaml`; task state store; gate runners; `setup/keel.sh role` for **ephemeral** roles; journals and status line (no LLM); allowlist reject + audit; agents never peer-message. Mechanical FAIL uses `dispatcher_only` edges.
  - **Rules in this step:** the circuit breaker fires only on an identical diff-hash; dependency install uses an ephemeral networked container without host secrets or control-plane mounts (the install policy is Step 12); every back edge has a non-null `budget_ref`; at most one `keel_request` per turn, after rpc turn-end, and mid-turn user messages are queued; a two-phase write-ahead log (`IN_PROGRESS`, then `COMMITTED`) with restart reconcile; a deep return archives the previous attempt outside git and the developer keeps read access; the intermediary passes the raw D2 answer and an interpretation, re-asks when they disagree, and has no `/approve` command; L3 mounts the product tree read-only and writes only in test directories, with `git diff --name-only` as a second check; on `TEST_CONTRADICTS_BRIEF` the orchestrator checks the brief and does not forward developer prose to L3; L6 checks leftover debug, temp, scratch, and backup files, with configurable patterns and no invented thresholds.
  - **Timeouts:** per-stage DEFAULT wall timeout + short **container-start** timeout; values are **starting values, measure later**. Owner D2 wait is not killed by these timeouts.
  - **Recovery & monitoring:** rehydrate store → last clean SHA → orphan cleanup by `task_id`; resume orchestrator from session; do not resurrect mid-flight roles; WAL reconcile on `IN_PROGRESS`; journals for transitions / reject / timeout / circuit-breaker / `second_request_same_turn`; status-line fields without secrets.
  - **Tests:** implement behavioral stub-model suite **D-T1…D-T28** and **D-T30…D-T33** (D-T29 unused — no instruction-file line-checks). Happy / attacks / mutate style as in [Orchestrator and dispatcher](orchestrator-dispatcher.md) §16. **Wire D-T tests and mutants into `run-tests.sh` / keel-gate in this same process-files PR** (done-when for Step 7).
  - Front ends: chat intermediary and direct Pi both enter the **dispatcher inbox**; only the dispatcher writes rpc stdin.
- **Depends on:** Step 1, isolation green; Step 2 when model API egress is required for the orchestrator container
- **Effort:** L
- **Acceptance / done when:**
  - Pi rpc + tool-lock smoke green before merge of the implementation.
  - Fixture task advances only through YAML dispatcher transitions; illegal / second-same-turn / bad-schema requests refused and audited.
  - Orchestrator has no bash/write/edit; cannot write product code; can read D1 log; cannot read secrets/`deny.local`.
  - Developer tests are RO; L3 product write fails at mount (D-T30) and host write-scope still refuses out-of-scope paths (D-T7).
  - `TEST_CONTRADICTS_BRIEF` path: developer text absent from L3 input (D-T31); routing/budget per D-T25.
  - WAL kill-between-phases → effect exactly once (D-T32); `COMMITTED` replay is idempotent (D-T18).
  - L6 fails leftover breakpoint/temp artifact fixtures (D-T33).
  - CB only on identical diff-hash (D-T12); hash-stability fixture (D-T21); every back edge has `budget_ref` (D-T19).
  - `run-tests.sh` / keel-gate invoke the new D-T suite and mutate wiring.
  - No agent-to-agent channel; both front-end shapes documented against one inbox.

### Step 8 — L0 Orchestrator grilling (minimal)
- **Does:** First message = task understanding, D0, **D1 confidence** (not an owner decision), **D2** options+default for the owner, out-of-scope; hard D2 triggers (incl. irreversible); unanswered D2 waits (via chat or direct Pi — no extra confirmation layer); wrong brief → stop for brief v2 diff; bugfix lighter path; show size and estimated cost (the owner may raise the depth). Dispatcher persists wait state; intermediary path requires verbatim D2 surface then paraphrase (documented, not enforced inside this PR alone).
- **Depends on:** Step 4, Step 7
- **Effort:** L
- **Done when:** Golden chat fixtures produce briefs with required sections; D1 labelled as confidence; hard triggers force D2; wait state persists; brief v2 requires an owner-shaped approval artifact; cost/size surfaced; D2 answers appear verbatim in the task log fixture.

### Step 9 — Stack-detect script + skills skeleton + suspicious-skill D2
- **Does:** Deterministic stack-detect (manifests/lockfiles + file→tech map); skill layout under `.agents/skills/` (no hard length limit — show size); harness-level critic/reviewer checklist exception (from Step 6); usage log hooks; trigger hooks (project start, stack change, pitfall×2, chat order). Suspicious-skill scan: install commands, network, secrets, gate bypasses → D2 card with lines highlighted; not enabled without the owner's yes. Pi instruction filenames: project agents follow Pi conventions; `CLAUDE.md` only as Pi fallback filename if the runtime expects it — no other AI-tool product names in harness docs.
- **Depends on:** Step 5, Step 6, Step 8
- **Effort:** M
- **Done when:** Detect fixtures for major stacks; skill create path stops at owner approval card; suspicious fixtures escalate with highlighted lines; size shown; no skill lands without approval; usage logged.

### Step 10 — Skills research → critic → approval → process-files PR
- **Does:** Researcher (internet, no code/tokens; official first; secondary alongside; forums forbidden; version+access date); block-list; critic without network; suspicious scan; owner "yes to all"; process-files PR.
- **Depends on:** Step 2, Step 9, push stub→real push (or land with Step 19 if push still stub)
- **Effort:** L
- **Done when:** End-to-end skill proposal on a fixture stops for owner card; rejected skills do not merge; approved skills open labeled process-files PR only via the bot; suspicious path requires D2 yes.

### Step 11 — L2 architect stubs + critic + AST verify + split-after-estimate
- **Does:** Architect proposes depth full/light/trivial; script picks/overrides (light = no new deps/API/UI/data → tests+gates+auditor only; trivial by script rules only); dependency list (name+purpose, no version); size estimate; script verifies depth vs diff (mismatch→full; D2 never trivial); AST stubs (TS, Python); critic with metrics, adversarial, different model if possible (else a different prompt and checklist), max 2 returns; `SIGNATURE_CHANGE_NEEDED` is logged as a miss, **once, then a dossier**. Split gate immediately after estimate if over per-project threshold (~200–400 LOC human norm, **to verify**). Split proposals are written by the orchestrator (via dispatcher), not by peer agent chat.
- **Depends on:** Step 4, Step 6, Step 7, Step 8
- **Effort:** L
- **Done when:** Depth mismatch forced to full; trivial blocked when D2/API/UI present; AST rejects bad stubs; critic return counter stops at 2 with dossier; split wait fires after estimate before deps/L3; signature-change second hit → dossier.

### Step 12 — Dependency resolve + install (ephemeral) before L3
- **Does:** Latest stable via registry; package-manager resolve; OSV/audit; **7-day quarantine with security-fix bypass**; new dep **D2** card (`WAITING_DEP_D2`). Install in an **ephemeral** networked container **without** host secrets or control-plane mounts; cache/vendor mounted **RO** into later roles; lockfile+checksums; `--ignore-scripts` by default (exceptions in envelope). L3 depends on `DEPS_READY` when new deps listed. `NEEDS_DEPENDENCY` from L5 does not spend a submission.
- **Depends on:** Step 2, Step 7 (dispatcher DEPS edges), Step 11
- **Effort:** L
- **Done when:** New dep blocks on D2 card; install is not on the host OS and not in the developer container; L3 fixture with new deps waits for DEPS_READY; quarantine+bypass documented; ignore-scripts default with exception list in envelope; D-T22-class checks covered or reused from Step 7.

### Step 13 — L3 tester + write-scope
- **Does:** Unit+integration on pre-implementation commit after deps when needed. Tester sees the **pre-implementation** tree; mounts product **RO** and may write only under allowed **test directories** (Step 7 mounts). Host `git diff --name-only` refuses out-of-scope paths (`test_write_scope_violate`). Old-test changes listed with brief-rule reasons; envelope "old tests changed: N". Bugfix repro must fail on clean main assertion. No test critic. Content treated as data (fences when backlog item lands).
- **Depends on:** Step 1, Step 7 (L3 mounts), Step 11, Step 12
- **Effort:** L
- **Done when:** Tester cannot see new implementation; product-path write fails at mount and/or host write-scope; developer mounts tests RO; bugfix repro gate fails if test passes on main; envelope counts old-test edits; deps-before-tests ordering held.

### Step 14 — L4 red gate (assertion/NotImplemented class)
- **Does:** Run tests on stubs (current code in light mode); JUnit XML/JSON adapters (pytest, Vitest/Jest); reject pass-on-empty; tag coverage 100%; old tests green; **count only assertion/NotImplemented as honest red**; import/build errors → return to tester; max 2 returns then dossier; light bugfix skips main recheck; trivial skips gate. Reuse shared path-check library.
- **Depends on:** Step 13
- **Effort:** M
- **Done when:** Adapters classify failure class; import-error fixtures return to tester not RED_PASS; empty-pass rejected; return counter and dossier path work; trivial/light skip rules match depth from L2; shared lib linked.

### Step 15 — L5 developer loop + task journal hooks
- **Does:** Named submission / edge budgets (starting values, measure; a hard per-task total budget is backlog). Stop early on identical **diff-hash** circuit breaker within edge budgets; same gate fail with a **different** diff spends normal budget. On FAIL the developer gets **full gate output and stacks** (not a sanitized rule-text-only report). Exits include: `NEEDS_CONTEXT`, `SIGNATURE_CHANGE_NEEDED` (once→dossier), `NEEDS_DEPENDENCY` (pause, no submission spend), `BRIEF_CONFLICT`, **`TEST_CONTRADICTS_BRIEF`** (do not fit code to a contradicting test; the orchestrator verifies the claim against the brief). Tests mounted **RO**. Lint/type tools same as static gate; developer style guide; discovery candidates to filter. Journal append after each link (see Step 21).
- **Depends on:** Step 5, Step 7, Step 12, Step 14
- **Effort:** L
- **Done when:** Attempt accounting matches exits; `NEEDS_DEPENDENCY` does not consume submission; CB only on identical diff-hash; developer FAIL fixture includes stack markers; `TEST_CONTRADICTS_BRIEF` fixture routes per YAML when orchestrator chooses L3; budget warn-only for the global task cap until that calibration.

### Step 16 — L6 static gate + shared path library + envelope warnings + leftover debug and temp files
- **Does:** Block: lint, types, signature immutability (AST vs stubs), path boundaries via shared prototype path-check library, gitleaks (SEC-03), lockfile matches approved, and **leftover debug / breakpoint / temp / scratch / backup artifacts** in the diff (patterns are a configurable harness base, and a project may only extend them; **no invented numeric thresholds**). Warn: CRAP 10–30 (**our choice**), duplicates — all warnings listed for envelope. Block: CRAP 30+ (**verified**, Savoia 2007). Changed files + project-wide types; legacy baseline; auto-format; basic semgrep with reasoned suppressions. Owns STY/TYP-01/DUP/CX/REA-03/ERR-03/SEC-03. Failure consumes attempt (`static_debug_leftover` among L6 fail categories).
- **Depends on:** Step 15
- **Effort:** L
- **Done when:** Each block rule has a failing fixture (including leftover breakpoint/temp → L6 FAIL / D-T33); warn vs block thresholds behave; warnings appear in envelope fixture; auto-format applied; attempt decrements; path-lib mutations (A17–A22b) still fail closed.

### Step 17 — L7 green gate + mutation (L7T) + tree-hash bind
- **Does:** New tests + old tests. **Mutation (L7T)** on changed files (Stryker, mutmut; other languages skipped, shown in envelope); block only unexplained surviving mutant on changed logic; **mutation-killing tests must cite brief rule id **; trend %. Mutation does **not** catch hardcoding to specific test values — that is an **L8** checklist item (English: `Code hardcoded to specific test values instead of implementing the behavior`) verified later via known-bad eval backlog, not instruction-file line-checks. Tester closes mutation gap max 1 return; coverage shown not blocking; flaky: host heuristic — task-related iff tester changed that test file this task; ~10 min fuse (**our number**) then sampling; equivalent mutants with reason; record `gated_tree_sha` after GREEN_PASS.
- **Depends on:** Step 14, Step 16
- **Effort:** L
- **Done when:** Dishonest-impl fixtures are caught by visible tests and/or mutation as designed; kill without rule id blocked; flaky task-related decision is script-only; time-box switches to sampling; tree sha recorded; one tester gap return then dossier/developer path; L8 hardcode checklist item is present in the reviewer instruction (behavioral quality via backlog eval set).

### Step 18 — L8 review agents + verifier + diff chunking
- **Does:** Parallel auditor and design reviewer only (security rules sit with the auditor; there is no readability reviewer and no hacker role); verifier on different model (model inversion: reviewers ≠ developer model; verifier third if available; else different prompt+checklist; model ids in envelope). Diff chunking: 50–150-line AST chunks (**to verify**) enriched with neighbouring types/signatures + brief; parallel calls; verifier merges/dedupes and remembers rejected findings across rounds; auditor one cross-file pass over diff summary. Findings need file:line + rule id + behavioral impact; drop style/naming/formatting; checklists include flag/do-not-flag examples and the explicit item `Code hardcoded to specific test values instead of implementing the behavior` (with L7T mutation; not proven by instruction-file line-checks). Blocking → developer → L6–L7 → rebind tree sha → diff-only re-review; max 3 rounds then dossier; yellow in PR; the diff is fenced when content fencing lands; injected instructions = red; light mode = auditor only.
- **Depends on:** Step 6, Step 16, Step 17
- **Effort:** L
- **Done when:** Missing file:line/rule id/behavioral impact dropped; repeats auto-dropped; injected-instruction fixture is red; 3-round dossier fires; light mode runs auditor only; chunker produces AST units in 50–150 band (labelled to verify); no readability/hacker agents in chain.

### Step 19 — Real push + L10 PR envelope
- **Does:** Token only in push step; PR under the bot account. CI reruns script gates (mutation: trend only) and **blocks `HEAD^{tree} != gated_tree_sha`**; script envelope (brief with D0, D1 confidence, D2 answers, and out of scope — fail closed if any of those is missing; gates; old tests changed; mutation trend; all warnings; suppressions; QA media; rollback mode; tokens, time, and budget; model ids; **verbatim D2 questions and answers with timestamps**). Commits per link; script rebase; conflict → developer + L6–L7 + rebind; process-files separate PR. Split already decided at L2. Envelope may recommend Red Team (backlog) when auth/payments/user data touched. Tests written by L3 are ordinary suite tests.
- **Depends on:** Step 17, Step 18, existing push stub
- **Effort:** L
- **Done when:** Agent/gate paths have no token; envelope fields present and fail closed on missing D0/D1/D2/oos; D2 verbatim answers visible; CI rejects tree mismatch; rebase-conflict re-enters L6–L7; process-files PRs labeled and separate.

### Step 20 — L9 QA/e2e + L9b rollback rehearsal
- **Does:** L9: isolated rootless container; Chrome DevTools MCP; Chromium sandbox ON; network only to local app; Playwright for brief scenarios; affected + smoke per PR; full run daily/pre-release; bugs → tester → developer → L6 → L7 → diff re-review → QA (max 2); visual diffs shown not blocking; synthetic data; externals stubbed. L9b: after L9/QA_SKIP, script picks rollback type from diff — plain (skip); feature flag (old tests+smoke flag off); migration (up→down→old tests→up); API change (previous version over new data + smoke); irreversible → D2. Failure → developer, costs attempt. Envelope records `rollback_mode` + evidence.
- **Depends on:** Step 3, Step 19, Step 13
- **Effort:** L
- **Done when:** Non-UI/API or light/trivial → `QA_SKIP`; QA cannot reach external net; a QA bug returns through L6 and L7; each rollback mode has a fixture; irreversible waits on D2; failure consumes attempt; media + rollback rows in envelope.

### Step 21 — Task journal
- **Does:** Host-side `.keel/runs/<task-id>/journal.md` appended by script after each link: link, role, result, commit, artifacts, money and minutes, dossier reason. Resume from last green step; redo uses journal as fenced context when fences exist. Delete journal right after the owner's merge. Budget: measure 5–10 tasks then set ≈2× median + iteration limit; until then warn only.
- **Depends on:** Step 8 (L0 start), hooks in Steps 15–20
- **Effort:** M
- **Done when:** Journal appears after each link on fixture run; resume restarts at last green; merge deletes journal; budget warn path works without hard kill until calibration.

### Step 22 — Self-describing system logging
- **Does:** JSONL events: time with zone, task id, link with expansion, role, model, action, result, reason, artifact refs. Glossary header in each export. No secrets or code. Scrub check on export. Test: no-context LLM explains a run from the export.
- **Depends on:** Step 21
- **Effort:** M
- **Done when:** Export includes glossary; scrub rejects secret/code fixtures; offline LLM explanation fixture passes rubric; links expand to human names.

### Step 23 — Release path + L11 after-merge
- **Does:** Merge → staging; the owner takes prod via tag/`workflow_dispatch` (bot blocked by tag rules); pre-release list + full e2e; rollback = redeploy previous tag manually + envelope rollback_mode; feature flags optional per architect. L11: JSONL metrics; discoveries via script filter; abort discoveries via dossier script; journal delete; retrospective offer counter every 3–5 tasks (never auto-run).
- **Depends on:** Step 19, Step 20, Step 21, Step 22
- **Effort:** M
- **Done when:** Bot cannot create release tags; manual rollback documented and scripted; counter offers without auto-running retro; metrics written per task; journal gone after merge.

---

## Suggested parallel tracks (still one owner-yes PR each)

| Track | Steps |
|---|---|
| A — Isolation hardening | 1 → 2 → 3 |
| B — Context, memory, standards | 4 → 5 → 6 |
| C — Dispatcher, orchestration & skills | 7 → 8 → 9 → 10 |
| D — Build loop | 11 → 12 → 13 → 14 → 15 → 16 → 17 |
| E — Review, PR, QA, rollback | 18 → 19 → 20 |
| F — Journal, logging, release | 21 → 22 → 23 |

Track D needs isolation, context, and the dispatcher. Track C needs context for packaging and grilling, and isolation for mounts. Track E needs the build loop and rootless hardening. Track F needs the review-track hooks. The harness is already in this repository.

---

## Explicitly deferred (not steps above)

| Item | Status |
|---|---|
| Content fencing (package mounts mark repo, ADR, discovery, skill, and diff text as data) | Backlog |
| A context-free filter that judges every external input safe or dangerous | Backlog. An extra layer, not the only defence |
| Red Team on staging, started only by an explicit trigger, using the browser and API scripts against synthetic data | Backlog. The envelope may recommend it |
| A known-bad diff set for the L8 hardcode checklist | Backlog |
| Follow-up research on code review | Backlog |
| An agent that writes product requirements | Not part of v1 |
| A retrospective agent | Backlog. Step 23 only counts tasks and offers one |
| A real-time UI on the system log | After the log exists (Step 22) |
| Split threshold and review-chunk size | Open, to verify on real tasks |
| Product mutation tests beyond the green gate | Later. The green gate wires mutation for the change |
| Mid-turn priority interrupt or cancel | Backlog. Today, messages wait until the turn ends |
| Normalize comments and formatting before the circuit-breaker hash | Backlog, after measurements on real tasks |
| Per-task total budget: warning, then a hard limit | Backlog, after measurements. No invented numbers |

## Open questions

1. **PR split threshold:** ~200–400 LOC human norm (generated/lock excluded) — **to verify** per project before enforcing.
2. **AST review chunk size:** 50–150 lines — **to verify** (arXiv 2606.15689 unconfirmed).
3. **Mutation time box:** ~10 min then sampling — **our number**; confirm per language/runner on target hardware.
4. **Dependency quarantine:** 7 days kept with security-fix bypass — confirm vs registry/OSV freshness needs.
5. **CRAP:** block 30+ verified (Savoia 2007); warn 10–30 = **our choice** — calibrate warn band on first product baselines.
6. **Different-model critic/verifier/reviewers:** which model pairs are available/affordable; fallback prompt+checklist when only one model.
7. **Feature flags:** default off until architect opts in, or project-level default?
8. **Push step vs Step 10:** can skills process-files PRs ship before real push (manual owner path), or must Step 19 precede Step 10?
9. **Trivial depth N (LOC):** exact script allowlist thresholds — set after first measured tasks.
10. **Egress proxy:** single shared proxy image vs per-role profiles; how are allowlist updates reviewed?
11. **Budget calibration:** when to flip from warn-only to hard ≈2× median + iteration limit after 5–10 tasks.
12. **A/B for major stack skills:** metrics and traffic split without a UI?
13. **macOS:** still untested for isolation — Step 3/docs wording beyond "untested"?
14. **Red Team trigger UX:** envelope recommend only vs owner checklist item when auth/payments/user data touched.
15. **Dispatcher request-file / `keel_request` schema:** on-disk layout under the task service dir for requests and WAL; kinds already enum'd in [Orchestrator and dispatcher](orchestrator-dispatcher.md) — confirm final paths in the process-files PR.
16. **D1 confidence-notes log path:** the on-disk path is still open. The orchestrator writes and reads it. The auditor does not see it until the verdict.
17. **Mid-turn cancel:** how cancel interrupts an in-flight role or gate without losing the audit record. Today, mid-turn messages wait until the turn ends.
18. **L6 leftover pattern list location:** harness base path + project extend-only wiring in Step 16 (no numeric thresholds).

---
