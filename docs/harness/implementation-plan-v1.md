# rudax-keel implementation plan v1 — 2026-10-28

## Changes in this revision (2026-10-29)

- Naming: harness plan uses **the owner** / **the user** and **the bot**; no personal login or other-AI product names (Pi Agent only; `CLAUDE.md` only as Pi fallback filename).
- **Orchestrator + host dispatcher:** design section and **Step 7** match `full-picture-orchestrator-dispatcher-2026-10-29.md`, `DECISIONS-LOG-rudax-keel-harness.md`, and `dispatcher-transitions-v1.yaml`. Warm per-task Pi orchestrator (`pi --mode rpc` + session in the task folder); single `keel_request` tool (no bash/write/edit); host dispatcher owns the FSM, gates, mounts, journals. Owner decisions **B1–B7** and **X3-1/X3-2/X3-3/X3-9** are in scope for Step 7. Agents do not talk to each other directly.
- **Test visibility:** ordinary product tests are **visible** to roles that mount the work tree; the developer mounts tests **read-only**. Honesty backstop = **L7T mutation** + **L8** review with explicit English checklist item `Code hardcoded to specific test values instead of implementing the behavior`. L3 tester: product tree RO, writes only in test dirs (X3-1); host `git diff --name-only` defense in depth.
- **Orchestrator visibility:** may **read** everything except **secrets** and paths in **`.keel/deny.local`**. May read/write the D1 confidence-notes log (auditor-only hide until verdict). Write zone: brief, split plan, dispatcher requests via `keel_request`, D1 log, ADR/`docs/decisions.md`, discoveries.
- **Chat-first usage:** intermediary and/or direct Pi share one dispatcher inbox → warm orchestrator rpc stdin (dispatcher is the only writer). Intermediary: raw D2 text + interpretation (B7); mandatory per-relay checklist; never drop owner-critical items.
- **Step 1 answers:** no third decision log; flat `.keel/deny.local` (all agents, including orchestrator); CR-M5 fencing → backlog; secret patterns extend-only; tests visible + developer RO; tester write-scope.
- **D1 / D2 wording:** D1 = orchestrator confidence (not an owner decision). D2 = owner decides.
- Build steps after old Step 6 renumbered: former Steps 7–22 → **Steps 8–23**.
- **2026-10-29 (plan sync):** Step 7 and related steps rewritten to the current foundation design: visible tests, RO developer mounts, L7T+L8 hardcode checklist, warm `pi --mode rpc`, `keel_request`, B1–B7, X3-1/X3-2/X3-3/X3-9.

---

Each step is one future PR that needs the owner's yes before it lands. The bot opens PRs; the owner alone merges and approves. Effort: **S** small, **M** medium, **L** large (rough). Do not treat unverified research numbers as facts; thresholds marked **to verify**, **our choice**, or **our number** stay labelled until measured.

Depends on existing green base: agent isolation, host gate (prototype); move into repo already done via PR #6 / #7 (former Step 19 removed). Process-file and skill changes always go as separate `process-files` PRs after the owner's approval.

---

## Orchestrator and host dispatcher (design)

This is the control-plane wiring for chat-driven work. It is built as **Step 7**; grilling behaviour is **Step 8**. Authoritative detail: `full-picture-orchestrator-dispatcher-2026-10-29.md`, `DECISIONS-LOG-rudax-keel-harness.md`, `dispatcher-transitions-v1.yaml`.

### Two front ends, one input

Usage is entirely through chat in natural language.

1. **Typical:** the user talks to an **external chat agent** (an intermediary). That agent relays into the **dispatcher inbox**. Recommended intermediary instructions live in `drafts/intermediary-agent-instructions.md` and `drafts/docs-working-through-chat.md`.
2. **Alternative:** a **direct Pi** path that still enters through the same dispatcher inbox (the dispatcher alone writes orchestrator rpc stdin).

Both front ends hit the same warm orchestrator. There is no second confirmation layer on top of D2. No `/approve` command (B7).

### Safety model (chat path)

- **Merge** is done only by the owner on GitHub. The intermediary cannot merge, approve, or change GitHub rules.
- The intermediary passes the owner's D2 answer **verbatim** together with its **interpretation**; if unclear or the two disagree, the orchestrator re-asks; raw text goes to audit (B7). Per-relay checklist: never drop owner-critical items; end with what is needed from the user (or “nothing”).
- The user's answers are **logged verbatim with timestamp** in the task log and are **visible in the PR envelope**.
- Orchestrator/agent output and other external content are **data**, not instructions to the intermediary.
- Secrets stay out of chat.
- Mid-turn user messages are **queued** and not lost (B4). Priority interrupt / cancel mid-turn is **backlog (X3-4)**.

### Orchestrator (reasoning plane)

- **Warm per-task** Pi container: `pi --mode rpc` with the **session file in the task folder**. Removed at task end (PR / cancel / fail / dossier); on owner wait → **stop** (not remove), resume from session.
- **One tool only:** `keel_request` (allowlisted kinds). Argv fail-closed: **no** bash, write, edit, or codemode. Read/search-class tools plus `keel_request` only.
- **Read:** everything except **secrets** and paths in **`.keel/deny.local`**. Reads/writes the **D1 confidence-notes log** (hidden from the auditor until verdict). Ordinary product **tests are visible**.
- **Write zone only (via dispatcher):** the brief; the split plan; `keel_request` payloads; the D1 log; ADR / `docs/decisions.md` and discoveries. Messages to the user (D2 cards: options + default) go through the dispatcher / intermediary.
- **Must not write:** product code, tests, process files, or gates.
- **Does not launch containers** and does not talk to other agents. Extension computes a deterministic `idempotency_key`; dispatcher applies a two-phase WAL (X3-3).
- **D1** = orchestrator **confidence** (high / medium / low), not an owner decision. Low confidence always raises a D2. **D2** is always an owner decision.
- On `TEST_CONTRADICTS_BRIEF`, the orchestrator **checks the claim against the brief** and decides; developer prose is **never** forwarded to L3 — only the orchestrator's reformulated finding (X3-2).

### Host dispatcher (control plane) — new component

A host script (not an agent) that:

- Owns **task state** and the machine FSM from `dispatcher-transitions-v1.yaml` (repo path after Step 7: `setup/dispatcher/transitions.v1.yaml`). Prose is not a second truth.
- Runs **gates**, journals, status line (no LLM), and role launches via `setup/keel.sh role` (**ephemeral** `--rm` role containers).
- Accepts at most **one** `keel_request` per orchestrator turn, only after rpc **turn-end** (B4); second request → refuse + audit.
- Idempotency WAL: write **`IN_PROGRESS`** before the side effect, then **`COMMITTED`** after; on restart reconcile `IN_PROGRESS` (never silent skip, never blind re-run) (B5 / X3-3).
- Circuit breaker: identical **diff-hash** on consecutive attempts only (B1). Every `kind: back` edge has non-null `budget_ref` (B3).
- Deep back to L2/L3: RO **previous-attempt** archive outside the work tree/git; developer **keeps read access** (X3-8 rejected isolation); shallow gate→L5 keeps the worktree (B6).
- L3 mounts: product tree **RO**, writes only in test dirs; host `git diff --name-only` defense in depth (X3-1). Developer tests mount **RO**; on FAIL the developer gets **full** gate output and stacks.
- Mechanical gate FAIL → `dispatcher_only` edges (no model vote).
- **Logs** every transition, rejection, gate result, timeout, circuit-breaker, and owner answer (raw D2 in audit).
- Is the only path from one role to the next: agents never message each other.

**Pi smoke (before implementation):** short rpc + tool-lock smoke proving `pi --mode rpc` session shape and that bash/write/edit are unavailable to the orchestrator image. This replaces the old “programmatic input to verify” open item.

Owner decisions (D2 answers, skill yes/no, split yes/no, irreversible ack, merge, release) are recorded in ADR / `docs/decisions.md` and discoveries. **No third decision-log location.** New dependencies still require owner D2 / `WAITING_DEP_D2` (X3-7 already covered / P6).

---

## Build order

### Step 1 — Visibility deny-list + mount policy
- **Does:** Enforce deny-list by not mounting: **secrets** (all roles); **D1 confidence-notes log** (**auditor** until verdict only — orchestrator writes and may read it); new implementation (tester → pre-implementation commit); developer skills (auditor until verdict). Ordinary product **tests are visible** to roles that mount the work tree; **developer** mounts tests **read-only**. Harness-fixed paths + **`.keel/deny.local`** as a **flat list** of extra paths denied to **all** agents (including the orchestrator; e.g. user/customer data), enforced at **container mount** level, documented; project file may only **add** denies. Harness **base secret-pattern list**; projects may only **extend** it (cannot narrow). Tester write-scope and L3 product-RO / test-RW mounts are finalized in **Step 7** (X3-1) on top of this matrix. **CR-M5 content fencing is not in this step** (backlog). See `step1-visibility-2026-10-29.md`.
- **Depends on:** isolation (green), gate (green)
- **Effort:** M
- **Done when:** Developer can read tests but cannot write them (RO mount); orchestrator can read the D1 log and cannot see secrets/`deny.local` paths; auditor cannot see developer skills or D1 log before verdict; `deny.local` is flat and extend-only; secret-pattern base cannot be narrowed; docs state the matrix (no CR-M5 fence fixtures required here).

### Step 2 — Egress allowlist proxy
- **Does:** Harness proxy allowlist; developer has no network except model API (`network none` + proxy); other roles per design (researcher internet; QA only local app; critic no network).
- **Depends on:** Step 1
- **Effort:** M
- **Done when:** Developer egress test shows only model API; unauthorized destinations blocked; proxy logs denials.

### Step 3 — Rootless hardening + startup verification (CR-M13, mandatory v1)
- **Does:** Make rootless Docker or Podman mandatory. Containers: `--cap-drop=ALL`, `no-new-privileges`, read-only rootfs + tmpfs, memory/cpu/pids limits, workdir quota; developer network none; secrets under a separate user. Startup verification script refuses to run if hardening is not in place. Chromium sandbox ON (no `--no-sandbox`); seccomp profile for Chrome; verify Playwright on the host first.
- **Depends on:** Step 1, Step 2, isolation green
- **Effort:** L
- **Done when:** Doctor/startup script fails closed on rootful or missing caps/limits; Playwright host check documented; Chromium runs without `--no-sandbox` under rootless; fixture refuses weak config.

### Step 4 — L1 context packaging script
- **Does:** Package allowed paths + one import level; ADR/discoveries one-file-per-entry; in-memory index (newest first); full text for path/tag/critical matches; token limit → `NEEDS_SPLIT`; CI path-exist / rename-follow / stale-deleted. (Content fencing CR-M5 remains backlog; packaging still treats packaged text as data in the design sense once fences land.)
- **Depends on:** Step 1
- **Effort:** M
- **Done when:** Fixture repo packages correctly under token budget; over-limit returns `NEEDS_SPLIT`; stale/renamed paths reported; index not stored on disk.

### Step 5 — Discoveries store (script filter accept/discard) (CR-C3)
- **Does:** Date-prefixed discovery files with front matter; agents may append candidates; host script filter auto-accepts only if schema, existing paths, size, no bypass imperatives, and significance check pass (concrete paths or a rule + non-obvious pitfall/decision). Failures **DISCARDED** (no proposed list). Dossier script writes abort-cause entries. Only harness edits/deletes accepted files. Owner decisions that belong in product memory go into ADR/`docs/decisions.md` and discoveries — **not** a separate decision log.
- **Depends on:** Step 4
- **Effort:** M
- **Done when:** Filter rejects bypass-imperative and insignificant fixtures; abort path writes cause via dossier script; L1 indexes only accepted discoveries; no proposed queue exists; no third decision-store path is introduced.

### Step 6 — Standards generator (`standards/rules.md` → per-role views)
- **Does:** Single source `standards/rules.md`; generate per-role views mounted read-only as harness skills: developer (all rules; REA-01/02/04 only here), architect (DES/CMP/SCO/TYP-03/REL-01), tester (TST/COR-02/COR-04), auditor (COR/TST/ERR/TYP-02/03/SEC/SCO/REL/DOC), design reviewer (DES/CMP), static gate (STY/TYP-01/DUP/CX/REA-03/ERR-03/SEC-03). Apply merges DES-02→DES-01, CMP-03→CX-01, TST-04→COR-04. Move SEC-08 to NOT-to-flag. Each judgment rule gets flag / do-not-flag examples.
- **Depends on:** quality-standard research (done as input)
- **Effort:** M
- **Done when:** Generator produces views from one source; role mounts get only their subset; SEC-08 absent from emit-able ids; flag/do-not-flag examples present for judgment rules.

### Step 7 — Host dispatcher + warm orchestrator (process-files PR)
- **Pre-impl smoke (required first):** short Pi smoke on the target image — `pi --mode rpc` session start/stop, and **tool lock** proving bash / write / edit / codemode are unavailable while `keel_request` is present. Fail closed if smoke fails. This replaces any “programmatic input to verify” wording; Step 7 assumes **rpc**.
- **Does:**
  - **Warm per-task orchestrator:** Pi in its own container with `pi --mode rpc` and the **session file under the task folder**; **rm** container at task end; **stop** (keep session) while waiting on the owner. Mounts per Step 1 (secrets + `.keel/deny.local` denied; D1 confidence-notes log readable/writable by orchestrator; tests visible). Skills/argv forbid writing product code, tests, process files, or gates.
  - **Single tool `keel_request`:** allowlisted kinds only (`ask_d2`, `brief_upsert`, `record_d1`, `propose_split`, `advance`, `return_to`, `run_role`, `wait_user`, `dossier`, `record_decision`, …). Extension computes deterministic `idempotency_key = hash(task, stage, attempt, kind, canonical payload)`. Atomic request write (`.tmp` → `rename`).
  - **Host dispatcher FSM:** load `dispatcher-transitions-v1.yaml` → install as `setup/dispatcher/transitions.v1.yaml`; task state store; gate runners; `setup/keel.sh role` for **ephemeral** roles; journals and status line (no LLM); allowlist reject + audit; agents never peer-message. Mechanical FAIL uses `dispatcher_only` edges.
  - **Owner decisions in this step:** **B1** circuit breaker = identical diff-hash only; **B2** DEPS install path = ephemeral networked container without host secrets/control-plane mounts (wire; detailed install policy lands with Step 12); **B3** every `kind:back` has non-null `budget_ref`; **B4** ≤1 `keel_request` per turn after rpc turn-end; mid-turn user messages queued; **B5/X3-3** two-phase WAL (`IN_PROGRESS` → execute → `COMMITTED`) with restart reconcile; **B6** deep previous-attempt archive outside git (developer keeps RO read); **B7** intermediary raw D2 + interpretation, re-ask on mismatch, no `/approve`; **X3-1** L3 product RO + RW test dirs + `git diff --name-only` defense in depth; **X3-2** orchestrator verifies `TEST_CONTRADICTS_BRIEF` vs brief and never forwards developer prose to L3; **X3-9** L6 mechanical leftover debug/temp/scratch/backup check (patterns configurable; no invented thresholds).
  - **Timeouts:** per-stage DEFAULT wall timeout + short **container-start** timeout; values are **starting values, measure later**. Owner D2 wait is not killed by these timeouts.
  - **Recovery & monitoring:** rehydrate store → last clean SHA → orphan cleanup by `task_id`; resume orchestrator from session; do not resurrect mid-flight roles; WAL reconcile on `IN_PROGRESS`; journals for transitions / reject / timeout / circuit-breaker / `second_request_same_turn`; status-line fields without secrets.
  - **Tests:** implement behavioral stub-model suite **D-T1…D-T28** and **D-T30…D-T33** (D-T29 unused — no instruction-file line-checks). Happy / attacks / mutate style as in full-picture §16. **Wire D-T tests and mutants into `run-tests.sh` / keel-gate in this same process-files PR** (done-when for Step 7).
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
- **Does:** First message = task understanding, D0, **D1 confidence** (not an owner decision), **D2** options+default for the owner, out-of-scope; hard D2 triggers (incl. irreversible); unanswered D2 waits (via chat or direct Pi — no extra confirmation layer); wrong brief → stop for brief v2 diff; bugfix lighter path; show size + estimated cost (the owner may raise depth — CR-M15). Dispatcher persists wait state; intermediary path requires verbatim D2 surface then paraphrase (documented, not enforced inside this PR alone).
- **Depends on:** Step 4, Step 7
- **Effort:** L
- **Done when:** Golden chat fixtures produce briefs with required sections; D1 labelled as confidence; hard triggers force D2; wait state persists; brief v2 requires an owner-shaped approval artifact; cost/size surfaced; D2 answers appear verbatim in the task log fixture.

### Step 9 — Stack-detect script + skills skeleton + suspicious-skill D2 (CR-M12, CR-m7)
- **Does:** Deterministic stack-detect (manifests/lockfiles + file→tech map); skill layout under `.agents/skills/` (no hard length limit — show size); harness-level critic/reviewer checklist exception (from Step 6); usage log hooks; trigger hooks (project start, stack change, pitfall×2, chat order). Suspicious-skill scan: install commands, network, secrets, gate bypasses → D2 card with lines highlighted; not enabled without the owner's yes. Pi instruction filenames: project agents follow Pi conventions; `CLAUDE.md` only as Pi fallback filename if the runtime expects it — no other AI-tool product names in harness docs.
- **Depends on:** Step 5, Step 6, Step 8
- **Effort:** M
- **Done when:** Detect fixtures for major stacks; skill create path stops at owner approval card; suspicious fixtures escalate with highlighted lines; size shown; no skill lands without approval; usage logged.

### Step 10 — Skills research → critic → approval → process-files PR
- **Does:** Researcher (internet, no code/tokens; official first; secondary alongside; forums forbidden; version+access date); block-list; critic without network; suspicious scan; owner "yes to all"; process-files PR.
- **Depends on:** Step 2, Step 9, push stub→real push (or land with Step 19 if push still stub)
- **Effort:** L
- **Done when:** End-to-end skill proposal on a fixture stops for owner card; rejected skills do not merge; approved skills open labeled process-files PR only via the bot; suspicious path requires D2 yes.

### Step 11 — L2 architect stubs + critic + AST verify + split-after-estimate (CR-M1, CR-m1)
- **Does:** Architect proposes depth full/light/trivial; script picks/overrides (light = no new deps/API/UI/data → tests+gates+auditor only; trivial by script rules only); dependency list (name+purpose, no version); size estimate; script verifies depth vs diff (mismatch→full; D2 never trivial); AST stubs (TS, Python); critic with metrics, adversarial, different model if possible (else different prompt+checklist — CR-m4), max 2 returns; `SIGNATURE_CHANGE_NEEDED` logged as miss, **once then dossier (CR-M10)**. Split gate immediately after estimate if over per-project threshold (~200–400 LOC human norm, **to verify**). Split proposals are written by the orchestrator (via dispatcher), not by peer agent chat.
- **Depends on:** Step 4, Step 6, Step 7, Step 8
- **Effort:** L
- **Done when:** Depth mismatch forced to full; trivial blocked when D2/API/UI present; AST rejects bad stubs; critic return counter stops at 2 with dossier; split wait fires after estimate before deps/L3; signature-change second hit → dossier.

### Step 12 — Dependency resolve + install (ephemeral) before L3 (CR-M2, B2)
- **Does:** Latest stable via registry; package-manager resolve; OSV/audit; **7-day quarantine with security-fix bypass**; new dep **D2** card (`WAITING_DEP_D2` — already required; X3-7). Install in an **ephemeral** networked container **without** host secrets or control-plane mounts (B2); cache/vendor mounted **RO** into later roles; lockfile+checksums; `--ignore-scripts` by default (exceptions in envelope). L3 depends on `DEPS_READY` when new deps listed. `NEEDS_DEPENDENCY` from L5 does not spend a submission.
- **Depends on:** Step 2, Step 7 (dispatcher DEPS edges), Step 11
- **Effort:** L
- **Done when:** New dep blocks on D2 card; install is not on the host OS and not in the developer container; L3 fixture with new deps waits for DEPS_READY; quarantine+bypass documented; ignore-scripts default with exception list in envelope; D-T22-class checks covered or reused from Step 7.

### Step 13 — L3 tester + write-scope
- **Does:** Unit+integration on pre-implementation commit after deps when needed. Tester sees the **pre-implementation** tree; mounts product **RO** and may write only under allowed **test directories** (X3-1; Step 7 mounts). Host `git diff --name-only` refuses out-of-scope paths (`test_write_scope_violate`). Old-test changes listed with brief-rule reasons; envelope "old tests changed: N". Bugfix repro must fail on clean main assertion. No test critic. Content treated as data (CR-M5 fences when backlog item lands).
- **Depends on:** Step 1, Step 7 (L3 mounts), Step 11, Step 12
- **Effort:** L
- **Done when:** Tester cannot see new implementation; product-path write fails at mount and/or host write-scope; developer mounts tests RO; bugfix repro gate fails if test passes on main; envelope counts old-test edits; deps-before-tests ordering held.

### Step 14 — L4 red gate (assertion/NotImplemented class) (CR-C4)
- **Does:** Run tests on stubs (current code in light mode); JUnit XML/JSON adapters (pytest, Vitest/Jest); reject pass-on-empty; tag coverage 100%; old tests green; **count only assertion/NotImplemented as honest red**; import/build errors → return to tester; max 2 returns then dossier; light bugfix skips main recheck; trivial skips gate. Reuse shared path-check library (CR-m8).
- **Depends on:** Step 13
- **Effort:** M
- **Done when:** Adapters classify failure class; import-error fixtures return to tester not RED_PASS; empty-pass rejected; return counter and dossier path work; trivial/light skip rules match depth from L2; shared lib linked.

### Step 15 — L5 developer loop + task journal hooks (CR-M4)
- **Does:** Named submission / edge budgets (starting values, measure; hard per-task total budget is backlog **X3-6**). Stop early on identical **diff-hash** circuit breaker (B1) within edge budgets; same gate fail with a **different** diff spends normal budget. On FAIL the developer gets **full gate output and stacks** (not a sanitized rule-text-only report). Exits include: `NEEDS_CONTEXT`, `SIGNATURE_CHANGE_NEEDED` (once→dossier), `NEEDS_DEPENDENCY` (pause, no submission spend), `BRIEF_CONFLICT`, **`TEST_CONTRADICTS_BRIEF`** (do not fit code to a contradicting test; orchestrator verifies vs brief per X3-2). Tests mounted **RO**. Lint/type tools same as static gate; developer style guide; discovery candidates to filter. Journal append after each link (see Step 21).
- **Depends on:** Step 5, Step 7, Step 12, Step 14
- **Effort:** L
- **Done when:** Attempt accounting matches exits; `NEEDS_DEPENDENCY` does not consume submission; CB only on identical diff-hash; developer FAIL fixture includes stack markers; `TEST_CONTRADICTS_BRIEF` fixture routes per YAML when orchestrator chooses L3; budget warn-only for the global task cap until X3-6 calibration.

### Step 16 — L6 static gate + shared path lib (CR-m8) + envelope warnings (CR-M8) + leftovers (X3-9)
- **Does:** Block: lint, types, signature immutability (AST vs stubs), path boundaries via shared prototype path-check library, gitleaks (SEC-03), lockfile matches approved, and **leftover debug / breakpoint / temp / scratch / backup artifacts** in the diff (**X3-9**; patterns configurable harness base, project extend-only; **no invented numeric thresholds**). Warn: CRAP 10–30 (**our choice**), duplicates — all warnings listed for envelope. Block: CRAP 30+ (**verified**, Savoia 2007). Changed files + project-wide types; legacy baseline; auto-format; basic semgrep with reasoned suppressions. Owns STY/TYP-01/DUP/CX/REA-03/ERR-03/SEC-03. Failure consumes attempt (`static_debug_leftover` among L6 fail categories).
- **Depends on:** Step 15
- **Effort:** L
- **Done when:** Each block rule has a failing fixture (including leftover breakpoint/temp → L6 FAIL / D-T33); warn vs block thresholds behave; warnings appear in envelope fixture; auto-format applied; attempt decrements; path-lib mutations (A17–A22b / CR-M35–CR-M44 class) still fail closed.

### Step 17 — L7 green gate + mutation (L7T) + tree-hash bind (CR-M6, CR-M11)
- **Does:** New tests + old tests. **Mutation (L7T)** on changed files (Stryker, mutmut; other languages skipped, shown in envelope); block only unexplained surviving mutant on changed logic; **mutation-killing tests must cite brief rule id (CR-M6)**; trend %. Mutation does **not** catch hardcoding to specific test values — that is an **L8** checklist item (English: `Code hardcoded to specific test values instead of implementing the behavior`) verified later via known-bad eval backlog, not instruction-file line-checks. Tester closes mutation gap max 1 return; coverage shown not blocking; flaky: host heuristic — task-related iff tester changed that test file this task (CR-M11); ~10 min fuse (**our number**) then sampling; equivalent mutants with reason; record `gated_tree_sha` after GREEN_PASS.
- **Depends on:** Step 14, Step 16
- **Effort:** L
- **Done when:** Dishonest-impl fixtures are caught by visible tests and/or mutation as designed; kill without rule id blocked; flaky task-related decision is script-only; time-box switches to sampling; tree sha recorded; one tester gap return then dossier/developer path; L8 hardcode checklist item is present in the reviewer instruction (behavioral quality via backlog eval set).

### Step 18 — L8 review agents + verifier + diff chunking (L8 final, CR-M9, CR-m3, CR-m4)
- **Does:** Parallel auditor + design reviewer only (readability removed; hacker removed — SEC on auditor); verifier on different model (model inversion: reviewers ≠ developer model; verifier third if available; else different prompt+checklist; model ids in envelope). Diff chunking: 50–150-line AST chunks (**to verify**) enriched with neighbouring types/signatures + brief; parallel calls; verifier merges/dedupes and remembers rejected findings across rounds; auditor one cross-file pass over diff summary. Findings need file:line + rule id + behavioral impact; drop style/naming/formatting; checklists include flag/do-not-flag examples and the explicit item `Code hardcoded to specific test values instead of implementing the behavior` (with L7T mutation; not proven by instruction-file line-checks). Blocking → developer → L6–L7 → rebind tree sha → diff-only re-review; max 3 rounds then dossier; yellow in PR; diff fenced when CR-M5 lands; injected instructions = red; light mode = auditor only.
- **Depends on:** Step 6, Step 16, Step 17
- **Effort:** L
- **Done when:** Missing file:line/rule id/behavioral impact dropped; repeats auto-dropped; injected-instruction fixture is red; 3-round dossier fires; light mode runs auditor only; chunker produces AST units in 50–150 band (labelled to verify); no readability/hacker agents in chain.

### Step 19 — Real push + L10 PR envelope (CR-C2, CR-M7, CR-M8)
- **Does:** Token only in push step; PR under the bot account. CI reruns script gates (mutation: trend only) and **blocks `HEAD^{tree} != gated_tree_sha`**; script envelope (brief with D0/D1 confidence/D2 answers/out-of-scope — fail closed if missing CR-M7; gates; old tests changed; mutation trend; all warnings CR-M8; suppressions; QA media; rollback_mode; tokens/time/budget; model ids; **verbatim D2 Q&A with timestamps**). Commits per link; script rebase; conflict → developer + L6–L7 + rebind; process-files separate PR. Split already decided at L2. Envelope may recommend Red Team (backlog) when auth/payments/user data touched. Tests written by L3 are ordinary suite tests.
- **Depends on:** Step 17, Step 18, existing push stub
- **Effort:** L
- **Done when:** Agent/gate paths have no token; envelope fields present and fail closed on missing D0/D1/D2/oos; D2 verbatim answers visible; CI rejects tree mismatch; rebase-conflict re-enters L6–L7; process-files PRs labeled and separate.

### Step 20 — L9 QA/e2e + L9b rollback rehearsal (CR-C1, CR-M3)
- **Does:** L9: isolated rootless container; Chrome DevTools MCP; Chromium sandbox ON; network only to local app; Playwright for brief scenarios; affected + smoke per PR; full run daily/pre-release; bugs → tester → developer → L6 → L7 → diff re-review → QA (max 2); visual diffs shown not blocking; synthetic data; externals stubbed. L9b: after L9/QA_SKIP, script picks rollback type from diff — plain (skip); feature flag (old tests+smoke flag off); migration (up→down→old tests→up); API change (previous version over new data + smoke); irreversible → D2. Failure → developer, costs attempt. Envelope records `rollback_mode` + evidence.
- **Depends on:** Step 3, Step 19, Step 13
- **Effort:** L
- **Done when:** Non-UI/API or light/trivial → `QA_SKIP`; QA cannot reach external net; CR-M3 path hits L6–L7; each rollback mode has a fixture; irreversible waits on D2; failure consumes attempt; media + rollback rows in envelope.

### Step 21 — Task journal (CR-M4)
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

Track D needs A+B+C(dispatcher); C needs B for packaging/grilling context and A for mounts; E needs D+A(rootless); F needs E hooks. Former Step 19 (move into repo) removed — already done via PR #6/#7.

---

## Explicitly deferred (not steps above)

| Item | Status |
|---|---|
| CR-M5 content fencing (package mounts fence repo/ADR/discovery/skill/diff text as data) | **Backlog** (moved out of Step 1 on 2026-10-29) |
| Context-free filter agent/tool: all external input judged safe vs dangerous | **Backlog** (extra layer, not the only defence) |
| Red Team stage (staging; explicit trigger; browser + API scripts; synthetic data) | Backlog (CR-m3); envelope may recommend |
| Known-bad-diff / hardcode review eval set (L8 checklist quality) | Backlog |
| Code-review research follow-ups | Backlog |
| PRD agent / PRD skills | Backlog |
| Retrospective agent | Backlog (counter only in Step 23) |
| Real-time UI | After system log (Step 22) |
| Verify PR-size (~200–400 LOC) and AST chunk (50–150) | Open; **to verify** |
| Product mutation tests beyond L7 wiring | Method proven on harness; product modules later |
| Hacker in PR chain | **Removed** (CR-m3) |
| Readability reviewer | **Removed** (CR-M9) |
| Hard skill-length limit | **Not adopting** (CR-m7; show size; owner approval already mandatory) |
| Rootless Docker | **Moved into v1** as Step 3 (no longer backlog) |
| Harness² | **Not adopting** |
| Separate owner-decision log (third store) | **Not adopting** — use ADR/`docs/decisions.md` + discoveries |
| X3-4 mid-turn priority interrupt / cancel | **Backlog** (today: queue until turn end, B4) |
| X3-5 normalize comments/formatting before CB diff-hash | **Backlog** (after measurements on real tasks) |
| X3-6 per-task total budget warning → hard limit | **Backlog** (after measurements; no invented numbers) |

---

## Open questions

1. **PR split threshold:** ~200–400 LOC human norm (generated/lock excluded) — **to verify** per project before enforcing.
2. **AST review chunk size:** 50–150 lines — **to verify** (arXiv 2606.15689 unconfirmed).
3. **Mutation time box:** ~10 min then sampling — **our number**; confirm per language/runner on target hardware.
4. **Dependency quarantine:** 7 days kept with security-fix bypass — confirm vs registry/OSV freshness needs.
5. **CRAP:** block 30+ verified (Savoia 2007); warn 10–30 = **our choice** — calibrate warn band on first product baselines.
6. **Different-model critic/verifier/reviewers:** which model pairs are available/affordable; fallback prompt+checklist when only one model (CR-m4).
7. **Feature flags:** default off until architect opts in, or project-level default?
8. **Push step vs Step 10:** can skills process-files PRs ship before real push (manual owner path), or must Step 19 precede Step 10?
9. **Trivial depth N (LOC):** exact script allowlist thresholds — set after first measured tasks (CR-m1).
10. **Egress proxy:** single shared proxy image vs per-role profiles; how are allowlist updates reviewed?
11. **Budget calibration:** when to flip from warn-only to hard ≈2× median + iteration limit after 5–10 tasks.
12. **A/B for major stack skills:** metrics and traffic split without a UI?
13. **macOS:** still untested for isolation — Step 3/docs wording beyond "untested"?
14. **Red Team trigger UX:** envelope recommend only vs owner checklist item when auth/payments/user data touched.
15. ~~Pi programmatic message input~~ — **closed for planning:** Step 7 uses **`pi --mode rpc`** with a required pre-impl rpc + tool-lock smoke (no separate “to verify” programmatic-input track).
16. **Dispatcher request-file / `keel_request` schema:** on-disk layout under the task service dir for requests and WAL; kinds already enum'd in full-picture — confirm final paths in the process-files PR.
17. **D1 confidence-notes log path:** exact on-disk path (orchestrator writes/reads; denied to the auditor until verdict only — not an owner-decision log).
18. **X3-4 cancel semantics:** how cancel interrupts an in-flight role/gate without losing audit — design after queue+turn-end stubs are stable.
19. **L6 leftover pattern list location:** harness base path + project extend-only wiring in Step 16 (no numeric thresholds).

---

## Changelog

- 2026-10-29 (label sync): Renamed critique #3 tags to **X3-1…X3-9** and older Critic tags to **CR-C*/CR-M*/CR-m*** to remove collisions with bare C/M numbers (see DECISIONS-LOG label legend / LABEL1).
- 2026-10-29 (plan sync): Rewrote design section + **Step 7** to match full-picture / DECISIONS-LOG / YAML (warm rpc orchestrator, `keel_request`, B1–B7, X3-1/X3-2/X3-3/X3-9, D-T suite + `run-tests.sh`/keel-gate wiring, timeouts, recovery, pre-impl Pi smoke). Updated Steps 1, 12, 13, 15, 16, 17, 18, 19 and open questions for visible tests + RO developer mounts + L7T/L8.
- 2026-10-29 (afternoon, corrected): Orchestrator reads all except secrets + `.keel/deny.local`; D1 log readable (auditor-only hide until verdict). Intermediary checklist. Repo-docs drafts under `drafts/repo-docs/`. **Superseded same day** by the plan-sync entry above for test-visibility and dispatcher checks.
- 2026-10-29: Owner decisions applied: orchestrator + host dispatcher (design + Step 7); chat intermediary / direct Pi front ends; Step 1 visibility answers (flat `deny.local`, no third decision log, secret patterns extend-only); CR-M5 fencing and external-input filter to backlog; D1 = confidence, D2 = owner; naming scrub (owner/user/bot; Pi only). Renumbered former Steps 7–22 → 8–23. Draft docs: intermediary instructions + working-through-chat.
- 2026-10-28: First implementation plan from pipeline-chain v1 decisions. Nineteen owner-yes steps; deferred list; open questions. No unverified research numbers recorded as facts.
- 2026-10-28 (evening): Removed Step 19 (move into repo — done via PR #6/#7). Added Steps for rootless hardening+verify, standards generator, rollback rehearsal (with L9), task journal, self-describing logging, diff chunking (inside L8). Applied CR-C1–CR-C4, CR-M1–CR-M15, CR-m1–CR-m8, L8 final, thresholds, discoveries filter, CR-M12 suspicious skills. Renumbered to Steps 1–22.
