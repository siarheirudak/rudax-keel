# Full picture: orchestrator, dispatcher, and role containers (v1)

Owner-facing design. Plain language. Numbers not yet measured are marked **starting value, measure**. No personal logins or bot account names — say **the user** / **the owner**. Among AI runtimes, name **Pi** only. Paths and identifiers use `code spans`.

Sources (read-only while this design was written): `docs/harness/implementation-plan-v1.md` (Step 7), visibility notes, research proposals, Critic reviews, and owner decisions dated 2026-10-29 (visible tests; one tool `keel_request`; warm orchestrator; FSM with cascade; B1–B7 and X3-1…X3-9 below). Those decisions supersede earlier plan wording.

Status: **design** for the Step 7 layer. The repository today has role isolation and a host-gate prototype; the dispatcher and the orchestrator container are not built yet. Critic GO-WITH-FIXES edits are kept, plus the 2026-10-29 owner decisions (A/B + critique #3).

---

## 0. Owner decisions 2026-10-29 (A + B) — short

**A — No hidden-test class.** There is no separate host-only test store, no dedicated gate for that class, no verbatim-body check against such a store, and no “rule text only” failure sanitization for that reason. Tests are visible to every role with a work tree. Tester-written tests mount **RO** to the developer. The tester writes only into test directories (host check: `git diff --name-only` + a test). The developer gets full gate output and stacks. Honesty substitute: mutation (L7T) + L8 review. L8 checklist (English, in the instruction file) includes: `Code hardcoded to specific test values instead of implementing the behavior`. Checking that item is **behavioral only** through a backlog known-bad reviewer eval set; the suite does **not** line-check instruction files. Mutation does **not** catch hardcoding. Developer signal `TEST_CONTRADICTS_BRIEF` (alongside `NEEDS_CONTEXT` / `NEEDS_DEPENDENCY`): do not fit the code; stop and return the signal with the test name and brief clause; the orchestrator decides whether to take edge `L5_test_contradicts_brief_to_L3` (budget).

**B1.** Circuit breaker fires **only** on the same **diff-hash** across consecutive attempts. The same gate fail with a **different** diff spends the ordinary edge budget.

**B2.** DEPS install runs in an ephemeral container with network, **without** host secrets and **without** control-plane mounts; cache/vendor then mount RO into roles. Default `--ignore-scripts`.

**B3.** Every `kind: back` edge has a **non-null** `budget_ref` (schema + D-T19 + mutant). Numbers are starting values — measure.

**B4.** At most one `keel_request` per orchestrator turn. The dispatcher processes the request only after rpc turn-end; a second in the same turn → refuse + audit. Mid-turn user messages are queued, not dropped.

**B5.** Idempotency key from the extension, deterministically: `hash(task, stage, attempt, kind, canonical payload)`. **Refined by X3-3:** two-phase WAL (`IN_PROGRESS` → execute → `COMMITTED`); D-T18 / D-T32.

**B6.** Deep back (to L2 or L3): archive prior work into a RO “previous attempt” folder in the task service directory (**outside** the work tree and git); `work/$T` resets to the clean stage commit. Shallow gate return to L5 keeps the code for edits. Archive deleted at task end. Test: archive never in commit/PR/work tree and gone after task end.

**B7.** The intermediary passes the user’s D2 answer **verbatim** together with its interpretation; the orchestrator re-asks if the answer is unclear or the two diverge; raw text goes to the audit log. There is no `/approve` command.

### X3 — External critique #3 (owner-approved 2026-10-29)

IDs use the **X3-*** prefix (not bare C#) so they do not collide with older Critic **CR-C*** tags. See the decisions-log label legend.

**X3-1 (v1).** L3 tester mounts: product tree **read-only**; write only into allowed test directories (FS mount enforcement). Keep host `git diff --name-only` as defense in depth. Behavioral: D-T30.

**X3-2 (v1).** On `TEST_CONTRADICTS_BRIEF`, the orchestrator checks the claim against the brief itself and decides. Developer arguments are **never** forwarded to the tester. Only the orchestrator’s own reformulated finding goes to L3. Behavioral: D-T31 (extends H4 / D-T25).

**X3-3 (v1).** Two-phase WAL for idempotency keys: write `IN_PROGRESS` before executing, then `COMMITTED` after. On restart, an `IN_PROGRESS` entry is reconciled: the dispatcher checks the side effect, then completes or retries it safely — never silently skipped and never blindly re-run. **Refines B5.** Behavioral: D-T32 (extends D-T18).

**X3-4 (backlog).** Mid-turn user messages and cancel get top priority and interrupt the turn. Today they are queued until the turn ends (B4 / D-T23).

**X3-5 (backlog).** Normalize diffs (comments and formatting) before the circuit-breaker hash — only after measurements on real tasks (extends §10 / D-T21).

**X3-6 (backlog).** Turn the per-task total budget from a warning into a hard limit — after measurements (no invented numbers).

**X3-7 (already covered).** Owner approval for new dependencies is already required via the existing D2 / `WAITING_DEP_D2` path (P6 / B2). No new design.

**X3-8 (rejected by owner).** Do **not** isolate the raw previous-attempt archive from the developer. The developer keeps read access to the previous-attempt folder. Gates and review still check the new result regardless (B6 stands).

**X3-9 (v1).** L6 mechanical check for leftover debug and temp artifacts: debug prints or breakpoints added in the diff, and temp / scratch / backup files. Patterns stay configurable; do not invent numeric thresholds. Behavioral: D-T33.

---

## 1. Two planes in plain words

| Plane | Who | Does | Does not |
|---|---|---|---|
| **Reasoning** | Orchestrator (Pi in its own container) and roles (architect, tester, developer, …) | Understand the task, write the brief, choose *where* to request a transition, ask D2, read what is allowed | Launch containers, write product code, bypass gates, message peer agents |
| **Control** | Host dispatcher (a script, not an agent) | Store task state, check transitions, mount, launch roles via `setup/keel.sh role`, run gates, write journals and the status line | “Think” for the model; merge the PR |

Rule: **agents do not talk to each other**. Everything goes through the dispatcher. There is no scribe agent: append-only journals are written only by the dispatcher.

D2 questions go **only** through the chat intermediary (or a direct Pi terminal into the same dispatcher inbox). There is no second “confirm again” layer on top of D2. There is no `/approve` (B7).

---

## 2. Path of one task: from a chat message to a PR

### Mermaid

```mermaid
flowchart TD
  classDef owner fill:#ef6c00,color:#fff,stroke:#e65100
  classDef mid fill:#546e7a,color:#fff,stroke:#37474f
  classDef orch fill:#1565c0,color:#fff,stroke:#0d47a1
  classDef disp fill:#2e7d32,color:#fff,stroke:#1b5e20
  classDef role fill:#0277bd,color:#fff,stroke:#01579b
  classDef gate fill:#558b2f,color:#fff,stroke:#33691e
  classDef stop fill:#c62828,color:#fff,stroke:#8e0000
  classDef note fill:#eceff1,color:#000,stroke:#90a4ae

  U["User: chat message"]:::owner
  I["Intermediary: raw D2 + interpretation<br/>no /approve"]:::mid
  D["Host dispatcher<br/>only writer to rpc stdin<br/>≤1 keel_request per turn after turn-end"]:::disp
  O["Warm orchestrator<br/>pi --mode rpc + session in task folder"]:::orch
  KR["keel_request kind=…<br/>key = hash(task,stage,attempt,kind,payload)"]:::orch
  SL["Status line without LLM<br/>→ intermediary → user"]:::disp

  U --> I --> D
  D -->|"rpc prompt"| O
  O --> KR --> D
  D --> SL --> I --> U

  D -->|L0 brief ready| L1["L1 context pack<br/>script"]:::disp
  L1 --> L2["L2 architect + critic"]:::role
  L2 --> DEPS["DEPS: ephemeral container<br/>network, no secrets/CP mounts"]:::disp
  DEPS --> L3["L3 tester<br/>product RO; RW test dirs; git diff depth"]:::role
  L3 --> L4["L4 red gate<br/>container --network none"]:::gate
  L4 --> L5["L5 developer<br/>tests RO; full gate output"]:::role
  L5 --> L6["L6 static gate<br/>+ debug/temp leftovers"]:::gate
  L6 --> L7["L7 green + mutation L7T<br/>tree hash"]:::gate
  L7 --> L8["L8 review<br/>checklist: hardcoded to test values"]:::role
  L8 --> L9["L9 QA / skip"]:::role
  L9 --> L9B["L9b rollback rehearsal"]:::gate
  L9B --> L10["L10 PR envelope<br/>bot opens PR"]:::disp
  L10 --> MERGE{"Owner merges"}:::owner
  MERGE --> L11["L11 after merge<br/>journal + previous-attempt deleted"]:::disp

  D2{"D2: question to owner"}:::owner
  WAIT["Waiting for answer<br/>orchestrator may stop"]:::note
  O -.->|keel_request ask_d2| D2
  D2 -->|raw + interpretation| D
  D2 -->|no answer| WAIT
  WAIT -.-> D2

  BACK["FSM back edge<br/>deep → archive previous attempt"]:::note
  L5 -.->|orchestrator chose target| BACK
  L4 -.->|mechanical FAIL:<br/>dispatcher returns alone| L3
  L6 -.->|mechanical FAIL shallow| L5
  L7 -.->|mechanical FAIL shallow| L5
  BACK --> D

  CB["Circuit breaker:<br/>same diff-hash only"]:::stop
  TO["timeout: stop container,<br/>status=timeout"]:::stop
  DOS["Dossier"]:::stop
  CB --> DOS
  TO --> D
```

### In words, step by step

1. The user writes to the intermediary (typical path) or into a direct Pi session (same inbox).
2. Intermediary: for D2, passes the **raw answer text** and its **interpretation**; if unclear or they diverge, the orchestrator re-asks; raw text in audit (B7). Relay checklist: critical content is not lost; end with what the user must do (or “nothing”). No `/approve`.
3. The message lands in the **dispatcher inbox**. Only the dispatcher writes to the warm orchestrator’s stdin (`pi --mode rpc`). The intermediary **never** holds the rpc stdin fd. Mid-turn messages go into a **queue** and are not dropped (B4). Priority interrupt / cancel mid-turn is **backlog X3-4** (today: wait until turn end).
4. The orchestrator reads what is allowed (see §4), thinks, and calls **at most one** `keel_request` per turn. The extension computes a deterministic `idempotency_key` (B5). The tool validates fields and atomically writes the request file (`.tmp` → `rename`).
5. The dispatcher processes the request **only after** rpc turn-end; a second request in the same turn → refusal + audit `second_request_same_turn` (B4). It checks the allowlist and the YAML FSM; writes WAL `IN_PROGRESS` before the side effect, then `COMMITTED` after (X3-3); writes the status line; launches a role/gate when needed; journals and audits.
6. The L0…L11 chain is as in `docs/architecture.md` / `docs/pipeline.md`; routing goes through the dispatcher FSM.
7. At task end (PR created, cancel, fail/dossier) the orchestrator container is **removed**; the previous-attempt folder is **deleted** (B6). While waiting on the user — only **stop**, resume from the session file.
8. Merge and release — owner only. The intermediary does not merge and does not change GitHub rules.

---

## 3. Who decides what

| Decision | Who |
|---|---|
| Task meaning, brief text, D1 (confidence high/medium/low), D2 wording, choice of **target** back edge; on `TEST_CONTRADICTS_BRIEF` — verify claim vs brief, reformulate finding for L3 (never forward developer prose) (X3-2) | Orchestrator (request) |
| Whether to allow a transition / return; whether to execute `keel_request`; launch role/gate; invalidate artifacts; deep archive / shallow keep; status line; journal; circuit breaker (diff-hash); timeout stop; **auto-return on mechanical FAIL**; refuse a second request in the same turn | Dispatcher |
| D2 answers, split yes/no, new dependency, irreversible ack, skill yes/no, merge, release | Owner / user |
| Relay: raw D2 + interpretation; show status line; **not** a second confirmation layer; **not** `/approve` | Intermediary |
| Own work within the role; L5 signals `NEEDS_CONTEXT` / `NEEDS_DEPENDENCY` / `TEST_CONTRADICTS_BRIEF` / … | Role container (developer) |
| Gate pass/fail from evidence | Gate script in a container with `--network none`, no secrets |

The orchestrator does **not** choose “skip the gate”. On mechanical FAIL the dispatcher **itself** takes the YAML edge with `initiator: dispatcher_only` and returns the task — without a model vote.

---

## 4. Visibility: tests for everyone, no hidden-test class

There is **no** separate host-only test store and **no** dedicated gate for such a class.

| Who | Product tests |
|---|---|
| Every role with a work tree | Sees ordinary tests |
| Tester | Product tree **RO** mounts; writes **only** test dirs (FS); host `git diff --name-only` defense in depth (X3-1 / D-T30) |
| Developer | Tests **RO**; full gate output + stacks on FAIL |
| Orchestrator | Reads tests (like everything else except secrets / `deny.local`) |

Honesty substitute: **L7T mutation** + **L8** (English checklist item above; mutation does not catch hardcoding). The L8 item is **not** verified by a line-check of the instruction file — only behaviorally through a backlog known-bad eval set.

### 4.2 Developer result signals (L5)

Alongside `NEEDS_CONTEXT`, `NEEDS_DEPENDENCY`, `SIGNATURE_CHANGE_NEEDED`, `BRIEF_CONFLICT` — signal **`TEST_CONTRADICTS_BRIEF`**.

Developer instruction (sense; English wording in the role skill/instruction file): *if a test contradicts the brief, do not fit the code to it; stop and return `TEST_CONTRADICTS_BRIEF`, naming the test and the brief clause.*

The dispatcher accepts the signal as `result_name`. The orchestrator **checks the claim against the brief itself** and **decides** whether to call `return_to` L3 on YAML edge `L5_test_contradicts_brief_to_L3` (`budget_ref: L5_test_contradict_returns`, starting value, measure; deep_reset) (X3-2 / H4). Developer arguments are **never** forwarded to the tester; only the orchestrator’s own reformulated finding (test id + brief clause + verdict) goes to L3. Behavioral stubs: D-T25 (routing/budget), D-T31 (developer text absent from L3 input).

### 4.1 Failure schema for routing (closed enum)

The dispatcher puts a structured object into the orchestrator inbox for **routing/audit**. Fields:

| Field | Type | Rule |
|---|---|---|
| `pass` | bool | required |
| `failure_category` | enum from `failure_categories` in `dispatcher-transitions-v1.yaml` | required on fail; **not** a free string |
| `rule_id` | short brief rule id (if any) | optional |
| `gate` | gate id (`L4` / `L7` / …) | optional |

In parallel, on gate FAIL the developer receives the **full** output and stacks.

The orchestrator reads everything else **except** secrets and paths from `.keel/deny.local`.

Control-plane writes: only through `keel_request` → dispatcher. Orchestrator argv is fail-closed: read/search class + `keel_request`; `bash` / `write` / `edit` / `codemode` off; mounts read-only except dispatcher channels.

---

## 5. FSM: machine table, transitions, invalidation

**Sole source of edges** — the machine file:

| Where now (design) | Where in the repo after Step 7 (process-files PR) |
|---|---|
| `docs/harness/dispatcher-transitions-v1.yaml` | `setup/dispatcher/transitions.v1.yaml` |

The dispatcher and its tests **load the same file**. Prose tables below are a human overview; on conflict the YAML wins. Test D-T20 loads the YAML and checks edges directly (forbidden/allowed, `invalidates`, `initiator`, **every `kind:back` has non-null `budget_ref`** — B3 / D-T19).

### 5.1 File schema

```text
schema_version: 1
format: keel_dispatcher_transitions
failure_categories: [enum…]      # closed list, no free text
budget_refs: [names…]             # numbers — starting values, measure; do not duplicate here
stages: [start, L0, …, dossier]
edges:
  - id: string
    from: stage | "*"
    to: stage | "*"
    kind: forward | back | terminal | reject | side_effect
    initiator: dispatcher_only | orchestrator | owner | script
    when: { … }
    invalidates: [stage…]
    budget_ref: name | null       # null FORBIDDEN when kind: back (schema + D-T19 + mutant)
    spends_submission: bool?
    deep_reset: bool?             # → archive previous attempt + reset work/$T (B6)
    shallow_keep_worktree: bool?  # gate → L5: code stays
    note: string?
```

Invalidation: dependent stages → `stale`. Role re-entry: **prior work + reason** (or archive previous attempt on deep). Gates **always** re-run fully. A current PASS exists only for non-stale. PR/envelope with a stale `gated_tree_sha` — **refuse**.

**Deep vs shallow (B6):**
- Deep back to L2 or L3 (`deep_reset: true`): archive into RO `previous attempt` in the task service directory (outside work tree and git); `work/$T` → clean stage commit; archive deleted at task end; tests D-T26. **X3-8 rejected isolation:** developer **keeps read access** to the previous-attempt folder; gates/review still judge the new result.
- Shallow (gate → L5): code in the work tree stays for further edits. L6 also fails on leftover debug/temp artifacts in the diff (X3-9 / D-T33).

Budgets: named refs; **numbers are starting values — measure**. Exhaustion → `budget_exhausted` → dossier.

Depth `light` / `trivial` — profiles of the same FSM (some nodes skipped), not a separate product.

### 5.2 Forward edges overview (human)

See the YAML. Short: `start→L0→…→L1→L2→L2C→DEPS→L3→L4→L5→L6→L7→L8→L9→L9B→L10→WAITING_MERGE→L11`, plus waits for D2 / brief v2 / split / dep / irreversible. There are **no** edges for a separate hidden-test class.

### 5.3 Back edges and cascade overview

| Edge (id in YAML) | Initiator | Invalidates | Note |
|---|---|---|---|
| `L4_fail_to_L3` | `dispatcher_only` | L4+ | mechanical FAIL; deep |
| `L2C_return_L2` | orchestrator | L2C and after | `L2_critic_returns`; deep |
| `L5_to_L1_context` | orchestrator | L1 pack | `L5_context_returns`; does not spend submission |
| `L5_to_L2_signature` | orchestrator | after L2 | `signature_change_once`; deep |
| `L5_to_DEPS` | orchestrator | — | `L5_deps_returns`; does not spend submission |
| `L5_test_contradicts_brief_to_L3` | orchestrator | L3+ | `L5_test_contradict_returns`; deep |
| `L6_fail_to_L5` / `L7_fail_to_L5` / `L9B_fail_to_L5` | `dispatcher_only` | gates+after; tree stale | mechanical FAIL; **shallow** |
| `L7_to_L7T` | `dispatcher_only` | L7 | `L7_mutation_gap`; mutation ≠ hardcode catch |
| `L8_blocking_to_L5` | orchestrator | L6+ | `L8_review_rounds`; shallow; hardcode checklist |
| `L9_bug_path` | orchestrator | QA-dependent | `L9_qa_bug_returns`; deep |
| `L10_refuse_stale_tree` | `dispatcher_only` | — | reject, do not open PR |
| `*_budget_dossier` / `any_circuit_breaker` | `dispatcher_only` | — | stop; CB diff-hash only (B1) |

**Forbidden:** jump over stale; accept an old gate PASS after a back-edge; open a PR with a stale bind; a back edge without `budget_ref`.

---

## 6. Tool `keel_request`: kinds and fields

One custom Pi tool, enum `kind`. Validation in the extension; atomic write (`.tmp` → `rename`). Raw model `write` is not authoritative and is **unavailable** (argv + mounts fail-closed).

Common fields:

| Field | Meaning |
|---|---|
| `schema_version` | Schema version |
| `task_id` | Task id |
| `kind` | Enum below |
| `idempotency_key` | Computed by the **extension** deterministically: `hash(task, stage, attempt, kind, canonical payload)` (B5). WAL: `IN_PROGRESS` before execute, `COMMITTED` after (X3-3). Replay of `COMMITTED` → no second execution; audit `idempotent_replay`. Restart with `IN_PROGRESS` → reconcile side effect, then complete or safe retry (D-T18 / D-T32) |
| `payload` | Kind fields |
| `created_at` | Timestamp with zone |

### Kinds (v1 allowlist)

| `kind` | Purpose | Key `payload` fields |
|---|---|---|
| `ask_d2` | Question to the owner | `question`, `options[]`, `default`, `trigger_reason` |
| `brief_upsert` | Brief | D0/D1/D2/oos sections; `version` |
| `record_d1` | Confidence notes | `level` (enum high/medium/low), `notes` |
| `propose_split` | Split | `parts[]`, `estimate_ref`, `reason` |
| `advance` | Move forward | `to_stage`, `result_name` |
| `return_to` | Back edge | `to_stage`, `failure_category` (enum) |
| `run_role` | Launch a role | `role`, `stage`, `inputs_ref` |
| `wait_user` | Wait | `reason` enum: `d2` / `brief_v2` / `dep` / `irreversible` / `skill` |
| `dossier` | Stop | `failure_category` enum, `artifact_refs[]` |
| `record_decision` | ADR / decisions / discovery candidate | `target`, `body_ref` |

`inject_summary_ack` is **not** in the v1 enum (backlog). In v1 the dispatcher pushes the summary through rpc `prompt`.

The dispatcher rejects an unknown `kind`, a broken schema, a transition outside the YAML, a budget overrun, a second request in the same turn, and a `COMMITTED`-key replay. Every refusal is an **explicit refusal** + **audit entry**.

**One request per turn (B4):** the dispatcher accepts a request only after the rpc turn-end event; a second → `second_request_same_turn`.

Extension: orchestrator image or harness mount (`-e`); **never** only a project `.pi/` as control-plane IPC. Idempotency WAL on disk: `IN_PROGRESS` before side effects, `COMMITTED` after (B5 / X3-3).

---

## 7. Status line

The dispatcher writes a deterministic line (no LLM) into the intermediary inbox.

Fields: `task_id`, `stage`, `attempt`, `waiting_reason`, `container_alive`, `last_result` (result name or `timeout` / `rejected_request` / `idempotent_replay` / `second_request_same_turn`), `updated_at` (with zone).

Secrets never appear. Not an rpc side-channel into the model and not a second confirmation UX.

---

## 8. Sessions, warm vs cold, parallel tasks

| | Orchestrator | Role |
|---|---|---|
| Lifetime | Warm per task; **rm** on terminal (PR / cancel / fail/dossier) | Ephemeral `--rm` per stage |
| Pi mode | `--mode rpc` + session on disk | One-shot `--mode json` / print (argv — smoke) |
| Pause | stop while waiting on the user; resume from session | New container |
| Rpc stdin | Dispatcher only | — |

Parallelism: already in `setup/keel.sh` — own `TASK`, `work/$T`, `shadow/$T.git`; objects RO alternates; pointer `.git` RO. Not reopened here.

The orchestrator session is **not** mounted into roles (explicit assert in D-T6 / D-T10).

---

## 9. Gates with product code and DEPS

Any product-code run in gates uses a HARDEN container (`--network none`, no secrets, cap-drop, read-only root + tmpfs, limits) as in `setup/keel.sh`. The dispatcher/doctor **refuse** a script that runs pytest/build on the host OS (D-T17). After `GREEN_PASS` — `gated_tree_sha`; stale bind → refuse PR (D-T15).

**DEPS (B2):** install in an **ephemeral** container **with network**, without host secrets and without control-plane mounts; result (cache/vendor) mounts **RO** into later roles. Default `--ignore-scripts`. Test D-T22.

Green gate: new + old tests + mutation (L7T). L6 static gate also checks leftover debug prints/breakpoints and temp/scratch/backup files in the diff (X3-9 / D-T33; patterns configurable, no invented thresholds).

---

## 10. Circuit breaker and hash stability

Inside existing attempt budgets. Two **consecutive** attempts of the same edge:

1. **Diff-hash** — normalized hash of the role patch (stable file order; ignore harness-rewritten fields per a fixed list in the normalizer).
2. Gate-output hash is **not** a circuit-breaker trigger (B1). The same gate fail with a **different** diff spends the ordinary edge budget, not CB.

Match of the **same** consecutive diff-hash only → `failure_category: circuit_breaker` → dossier.

**Done-when for §10:** CI has a **hash-stability fixture** (D-T21): the same normalized input → the same diff-hash across repeats; a mutant that breaks normalization goes red. D-T12: CB only on diff-hash; different diff with the same gate fail → **not** CB. **Backlog X3-5:** normalize comments/formatting before the CB hash only after measurements on real tasks (do not invent aggressiveness).

---

## 11. Timeouts

Each stage: DEFAULT wall timeout + short container-start timeout. Seconds in config: **starting value, measure**. On fire: stop the container, `status=timeout`, `failure_category: timeout`. Then follow YAML and budgets. Owner D2 wait is not killed by these timeouts.

---

## 12. Crashes and recovery

Truth is on disk. On start: rehydrate store → last clean SHA → orphan cleanup by name/label `task_id` → orchestrator resume from session if needed; do not resurrect mid-flight roles. The Docker-label graph is not the source of truth (v1). Idempotency WAL survives crash (B5 / X3-3): `COMMITTED` keys → idempotent replay; `IN_PROGRESS` → reconcile side effect then complete or safe retry — never silent skip, never blind re-run (D-T18 / D-T32).

---

## 13. Context rot and monitoring

Stage summaries to the orchestrator (structured), not full logs. Pi compaction is not the only defense. The session path is absent from role mounts.

Monitoring: transition/reject/timeout/circuit-breaker journal; status line; attempt/stale; alert on circuit breaker and `second_request_same_turn`; mid-turn message queue must not be lost (manual check on first tasks + D-T23). Priority interrupt / cancel mid-turn — backlog X3-4.

Journals are written by the host/dispatcher. Raw D2 text is in audit (B7).

---

## 14. L8 checklist and mutation

In the L8 reviewer checklist (English, in the instruction file) an explicit item:

`Code hardcoded to specific test values instead of implementing the behavior`

Mutation (L7T) does **not** replace this item: mutation does not catch hardcoding. The item is **not** in the automated suite as an instruction-file text check. The suite holds **only behavioral** tests (stub model + host fixtures); there are no line/verbatim checks of instruction files. L8 hardcode quality is checked **only** through a backlog known-bad example in a future reviewer eval set.

---

## 15. Risks (open)

- Hardcoding to visible tests — mitigation: L8 English checklist item + known-bad eval backlog (behavioral); not mutation; not instruction-file line-checks.
- Paraphrase / divergence of raw D2 and interpretation — orchestrator re-asks (B7).
- Deep archive leak into git/PR — D-T26; path outside the work tree.
- Budget numbers — starting values, measure. Per-task total budget still warn-only until X3-6 (after measure).
- Mid-turn cancel waits for turn end until X3-4.
- Aggressive comment-strip before CB hash deferred (X3-5) — measure FP/FN first.
- Developer may read previous-attempt (X3-8 rejected isolation); anchoring risk accepted; gates/review still check the new result.

---

## 16. Dispatcher tests (stub-model), wiring into `run-tests.sh` / keel-gate

Style: stub model + host fixtures; mutants like `mutate.py` (remove a protection → expected D-T* go red). Step 7 process-files PR: add calls in `run-tests.sh` / keel-gate (mutate wiring is part of Step 7 done-when).

| Id | Checks |
|---|---|
| D-T1 | Forbidden transition → **explicit refusal** + audit; stage unchanged |
| D-T2 | Allowed YAML transition executes; journal append |
| D-T3 | Invalidation: stale; old PASS not accepted; gate re-run |
| D-T4 | Broken request → refusal + audit; not executed |
| D-T5 | No write/bash on orchestrator → explicit refuse + audit; mutant “restore write” goes red |
| D-T6 | Session isolation: orchestrator session path **absent** from role mounts; secrets/`deny.local` not visible to orchestrator |
| D-T7 | Tester write-scope (host): path outside test dirs → refuse + `test_write_scope_violate`; tests RO for developer (write → EROFS). Mount-level product RO for L3: see D-T30 (X3-1) |
| D-T8 | Timeout: DEFAULT fixture (**starting value, measure**) → stop, `status=timeout` |
| D-T9 | Crash recovery: rehydrate + last clean SHA; orphan removed |
| D-T10 | Parallel tasks: two TASKs isolated; session A not in mount B |
| D-T11 | Status-line: required fields; no secrets |
| D-T12 | Circuit breaker: two identical **diff-hash** in a row → dossier; same gate fail with **different** diff → **not** CB, spends budget |
| D-T13 | Stdin ownership: second writer to rpc stdin → refuse + audit |
| D-T14 | Mechanical FAIL auto-return without orchestrator `keel_request` |
| D-T15 | Stale `gated_tree_sha` → refuse PR; audit |
| D-T16 | Orchestrator rm at end; after D2-wait — stop, not rm |
| D-T17 | Host product-code gate refuse |
| D-T18 | Idempotency: replay of `COMMITTED` key → no second execution; audit `idempotent_replay`; crash after commit before session flush still safe (B5 / X3-3). Mid-effect crash / `IN_PROGRESS` reconcile: D-T32 |
| D-T19 | Budget: every `kind:back` has non-null `budget_ref` (schema + loader); exhaustion → dossier; mutant “null budget on back” goes red (B3) |
| D-T20 | YAML FSM directly: forbidden/allowed edges; `invalidates`; no edges for a separate hidden-test class |
| D-T21 | Hash-stability: fixed input → stable **diff-hash**; normalizer mutant goes red |
| D-T22 | DEPS ephemeral: network present; no host secrets / control-plane mounts; cache/vendor RO afterward; `--ignore-scripts` by default (B2) |
| D-T23 | One `keel_request` per turn: second before turn-end → `second_request_same_turn`; mid-turn user message stays queued (B4) |
| D-T24 | Deterministic idempotency key: same `(task, stage, attempt, kind, canonical payload)` → one key; different payload → different (B5) |
| D-T25 | Behavioral stub: stub-developer returns `TEST_CONTRADICTS_BRIEF` (test name + brief clause); orchestrator chooses `return_to` L3 → dispatcher takes `L5_test_contradicts_brief_to_L3`, spends `L5_test_contradict_returns`, deep archive; repeat to exhaustion → dossier |
| D-T26 | Deep archive previous-attempt: outside work tree/git; not in commit/PR; deleted after task end; shallow L5 keep worktree (B6) |
| D-T27 | Intermediary D2: raw text + interpretation arrive; on divergence — re-ask; raw in audit; no `/approve` path (B7) |
| D-T28 | Developer on FAIL receives full gate output / stacks (not sanitized “rule text only”) |

**No D-T29.** The L8 hardcode item lives in the English checklist instruction; its presence is **not** tested by a line-check of the instruction file. Suite = behavioral stubs only. Item quality — backlog known-bad eval set.

| D-T30 | L3 mounts (X3-1): product tree read-only; writes only in test dirs. Stub: tester tries to write a product file → write fails (EROFS / equivalent). Host `git diff --name-only` still refuses out-of-scope paths (defense in depth with D-T7). Mutant: RW product mount → D-T30 red |
| D-T31 | `TEST_CONTRADICTS_BRIEF` (X3-2): stub-developer returns signal with distinctive developer prose; orchestrator reformulates; L3 input must **not** contain the developer text (only orchestrator finding). Mutant: forward raw developer args → D-T31 red |
| D-T32 | Two-phase WAL (X3-3): write `IN_PROGRESS`, kill dispatcher before `COMMITTED`, restart; side effect happens **exactly once** (reconcile then complete or safe retry — never silent skip, never blind double-run). Mutant: skip reconcile / blind re-run → D-T32 red |
| D-T33 | L6 leftover debug/temp (X3-9): diff with a leftover breakpoint or temp/scratch/backup file → L6 FAIL (`static_debug_leftover` or configurable pattern hit). Patterns configurable; no invented thresholds. Mutant: disable leftover check → D-T33 red |

**Mutants (examples):** drop YAML check; drop stale; accept any JSON; restore write/bash; let tester write outside test dirs; RW product mount for L3; RW tests for developer; no stop on timeout; no orphan cleanup; shared shadow; no status write; CB on gate-hash (must go red on D-T12); second stdin fd; skip auto-return; PR on stale tree; no orchestrator rm; host gate; ignore idempotency / skip WAL reconcile; null `budget_ref` on back; break normalizer; skip turn-end gate; mount secrets into DEPS; leave previous-attempt in work tree; accept second request same turn; forward developer prose to L3; disable L6 leftover patterns.

Hash-stability (D-T21) and mutants belong in dispatcher attacks / the same `run-tests.sh`.

---

## 17. Status of OD / Critic findings (design)

| Id | Status | Where |
|---|---|---|
| OD-C1 / OD-C2 | **Closed (design + test spec)** | §6 argv fail-closed; D-T5/D-T13 |
| OD-M1 INVALIDATION | **Closed (design)** | YAML `invalidates` + D-T3 + D-T15 + D-T20 |
| OD-M4 session / rot | **Closed (design)** | session not in role mounts; D-T6/D-T10; §13 |
| OD-M5 host gate | **Closed (design)** | §9 + D-T17 |
| OD-M6 hash | **Closed (design)** | §10 + D-T21; CB = diff-hash only (B1) |
| Prior Critic **CR-C2** | Open at pipeline level | stale bind D-T15; full envelope — Step 19 |
| External critique #2 | Partly closed by B1–B7 | research triage (foundation) |
| External critique #3 | Owner triage applied: X3-1/X3-2/X3-3/X3-9 **v1**; X3-4/X3-5/X3-6 **backlog**; X3-7 already covered; X3-8 **rejected** | §0 X3; D-T30…D-T33 |
| Separate hidden-test class / verbatim-body checks | **Withdrawn** — removed (H1 / A) | this file + visibility design |

---

## 18. Non-negotiable rules for this layer

1. Agents do not peer-message; only through the dispatcher.
2. Mechanical FAIL → only `dispatcher_only` YAML edges (D-T14).
3. Sole FSM source = YAML; prose is not a second truth.
4. Circuit breaker = same consecutive **diff-hash** (B1); hash-stability fixture in CI is done-when.
5. No separate hidden-test class; tests visible; tester write-scope; developer RO tests + full stacks; L7T+L8 as honesty substitute.
6. Every `kind:back` — non-null `budget_ref` (B3).
7. ≤1 `keel_request` per turn after turn-end (B4).
8. Idempotency key deterministic from the extension; two-phase WAL `IN_PROGRESS`/`COMMITTED` with reconcile on restart (B5 / X3-3).
9. Deep → previous-attempt archive outside git; developer keeps RO read of archive (X3-8); shallow L5 keeps code (B6).
10. D2: raw + interpretation; no `/approve` (B7).
11. L3: product RO + RW test dirs at mounts; `git diff` defense in depth (X3-1).
12. `TEST_CONTRADICTS_BRIEF`: orchestrator verifies vs brief; never forward developer prose to L3 (X3-2).
13. L6 fails leftover debug/temp artifacts in the diff; patterns configurable (X3-9).

---

## 19. Link to the plan and the repo

Main implementation is **Step 7**. Step 7 (dispatcher, extension, FSM YAML, tests, `run-tests.sh` edits, visibility mounts, DEPS ephemeral, archive previous-attempt) is a **process-files PR** (touches `setup/`, and if needed wiring under `.github/`); **do not** mix with product code.

Design docs for this layer live under `docs/harness/` in this repository. The machine YAML ships here for review; the process-files PR will place the runtime copy under `setup/dispatcher/`.

## Known residual risk: fitting code to tests

Protection against fitting code to visible tests is incomplete in v1:
- mutation tests (L7T) do not catch fitting;
- L8 item `Code hardcoded to specific test values instead of implementing the behavior` is an English instruction; the suite **intentionally** does not line-check instruction files; item quality is checked only via a known-bad eval set (backlog);
- `TEST_CONTRADICTS_BRIEF` fires on the developer signal; the orchestrator verifies vs brief and reformulates for L3 (X3-2; D-T25 + D-T31).

Helps: tests RO for the developer; L3 product RO + write-scope (X3-1 / D-T7 / D-T30). Further risk reduction — known-bad hardcode in the reviewer eval set (backlog).

## Test status

Tests D-T1…D-T28 plus D-T30…D-T33 are planned (behavioral only; no instruction-file line-checks; D-T29 reserved unused). Today `run-tests.sh` runs only happy, attacks, and doctor; `mutate.py` runs only offline; `setup/dispatcher` does not exist yet. Wiring those tests into `run-tests.sh` / keel-gate is part of the Step 7 process-files PR. Until then, claiming they are a mandatory CI check would be wrong.
