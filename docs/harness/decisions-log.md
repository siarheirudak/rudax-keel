# Owner decisions log — rudax-keel harness

One consolidated log. Plain language. No personal logins or bot account names: say **the owner** / **the user**. Among AI runtimes, name **Pi** only. Numbers not yet measured are marked **starting value, measure**.

**Log rule:** on conflict the **later** entry wins. Obsolete rows are marked **[superseded]**. Sources: design docs under `docs/harness/`, the implementation plan, reviews, and owner chat decisions dated 2026-10-29.

## Label legend (IDs)

| Prefix | Meaning | Examples |
|---|---|---|
| **X3-*** | External **critique #3** owner triage (2026-10-29) | X3-1…X3-9 |
| **CR-C*** | Older pipeline **Critic** findings (C-series) | CR-C1…CR-C4 |
| **CR-M*** / **CR-m*** | Same Critic source: major / minor tags | CR-M1…CR-M15, CR-m1…CR-m8 |
| **B*** | Owner batch on orchestrator/dispatcher (2026-10-29) | B1…B7 |
| **H*** | Owner decisions on test visibility / honesty substitute | H1…H4 |
| **OD*** / **OD-C*** / **OD-M*** | Orchestrator–dispatcher design / OD critic | OD1…, OD-C1, OD-M1 |
| **V*** | Step 1 visibility / naming / chat decisions | V1…V8 |
| **P*** | Earlier pipeline / GitHub process decisions | P1…P10 |
| **T*** / **PLAN*** | Test-suite / plan-sync meta decisions | T1, T2, PLAN1 |
| **D-T*** | Dispatcher behavioral tests | D-T1…D-T28, D-T30…D-T33 (no D-T29) |
| **D0 / D1 / D2** | Brief fields (not the Critic C-series) | confidence D1; owner decision D2 |
| **L0…L11** | Pipeline stages | L3 tester, L5 developer, L6 static, … |

**Rule:** never use a bare unprefixed C-/M-/m-series tag in new text — always qualify with **X3-**, **CR-**, or **OD-**.

---

## 2026-10-29 (evening) — visible tests + B1–B7 + signals

| Id | Decision | Status |
|---|---|---|
| H1 | **Tests are visible.** Every role with a work tree sees ordinary tests. Tester-written tests mount **read-only** for the developer. The tester writes only into test directories. The developer gets full gate output and stacks. Public tests plus L7T mutation and the L8 hardcode checklist are the honesty surface. | **active** |
| H2 | Ordinary tests are **visible to every role** with a work tree. Tester-written tests are mounted **read-only** for the developer. The tester writes only into test directories; the host checks with `git diff --name-only` plus a test. **Extended by X3-1:** product tree RO mounts for L3; git diff is defense in depth (D-T30). The developer gets the **full** gate output and stacks. | **active** |
| H3 | Honesty substitute: **L7T mutation** + **L8**. English checklist item: `Code hardcoded to specific test values instead of implementing the behavior`. Mutation does **not** catch hardcoding. The suite is **behavioral** stubs only; **no** line-checks of instruction files. L8 checklist quality → backlog known-bad eval set. | **active** |
| H4 | Developer signal **`TEST_CONTRADICTS_BRIEF`** alongside `NEEDS_CONTEXT` / `NEEDS_DEPENDENCY`: do not fit code to a contradicting test; stop; return the signal with the test name and brief clause. The orchestrator decides whether to take edge `L5_test_contradicts_brief_to_L3` (budget). **Extended by X3-2:** verify vs brief; never forward developer prose to L3. Behavioral stubs D-T25 / D-T31. | **active** |
| B1 | Circuit breaker fires **only** on the same **diff-hash** across consecutive attempts. The same gate fail with a **different** diff spends the ordinary edge budget. | **active** (supersedes earlier OR gate-hash) |
| B2 | DEPS install runs in an **ephemeral** container with network, without host secrets and without control-plane mounts; cache/vendor then mount RO; `--ignore-scripts` by default. | **active** |
| B3 | Every `kind: back` edge has a **non-null** `budget_ref` (schema + D-T19 + mutant). Numbers are starting values — measure. | **active** |
| B4 | At most one `keel_request` per orchestrator turn; the dispatcher processes after rpc turn-end; a second request → refuse + audit. Mid-turn user messages are **queued, not dropped**. | **active** |
| B5 | Idempotency key from the extension: `hash(task, stage, attempt, kind, canonical payload)`. **Refined by X3-3:** two-phase WAL `IN_PROGRESS`/`COMMITTED` + reconcile; D-T18 / D-T32. | **active** (refined X3-3) |
| B6 | Deep back (to L2/L3): RO archive “previous attempt” in the task service directory **outside** the work tree/git; `work/$T` resets to the clean stage commit; archive deleted at task end. Shallow gate→L5: code stays. Test: archive never in commit/PR/work tree. | **active** |
| B7 | Intermediary: D2 answer **verbatim** + interpretation; if unclear or they diverge the orchestrator re-asks; raw text in audit. **No** `/approve`. | **active** |
| T1 | Dispatcher tests: stub-model, behavioral; wiring into `run-tests.sh` / keel-gate in the **Step 7 process-files PR**. D-T1…D-T28 + D-T30…D-T33 (no D-T29 line-check). Extended by T2. | **active** |

**[superseded same day]** Earlier test-visibility ideas — replaced by **H1–H3**.

---

## 2026-10-29 — external critique #3 owner triage

Owner approved the critique #3 triage. Design sources: `docs/harness/orchestrator-dispatcher.md` §0 X3-1…X3-9, D-T30…D-T33; YAML notes; visibility mounts / L3 wording.

| Id | Decision | Status |
|---|---|---|
| X3-1 | L3 tester: product tree **RO** mounts; write only test dirs (FS). Keep `git diff --name-only` as defense in depth. Test D-T30. | **active** (v1) |
| X3-2 | On `TEST_CONTRADICTS_BRIEF`, orchestrator checks claim vs brief and decides. Developer arguments never forwarded to L3; only orchestrator reformulated finding. Extends H4. Tests D-T25 + D-T31. | **active** (v1) |
| X3-3 | Two-phase WAL for idempotency: `IN_PROGRESS` before execute, `COMMITTED` after; restart reconciles `IN_PROGRESS` (check side effect → complete or safe retry; never silent skip / blind re-run). **Refines B5.** Tests D-T18 + D-T32. | **active** (v1; refines B5) |
| X3-4 | Mid-turn user messages and cancel: top priority and interrupt the turn. | **backlog** (today: queued until turn end per B4) |
| X3-5 | Normalize diffs (comments/formatting) before circuit-breaker hash. | **backlog** (after measurements on real tasks) |
| X3-6 | Per-task total budget: warning → hard limit. | **backlog** (after measurements; no invented numbers) |
| X3-7 | Owner approval for new dependencies. | **already covered** by existing D2 / `WAITING_DEP_D2` (P6); no new design |
| X3-8 | Isolate raw previous-attempt from roles (structured reasons only). | **rejected** — developer **keeps read access** to previous-attempt folder; gates/review check the new result (B6 stands) |
| X3-9 | L6 mechanical check: leftover debug prints/breakpoints and temp/scratch/backup files in the diff; patterns configurable; no invented thresholds. Test D-T33. | **active** (v1) |
| T2 | Dispatcher behavioral suite adds D-T30…D-T33 (stub-model happy/attacks/mutate). D-T29 remains unused (no instruction-file line-check). | **active** |

**[superseded by X3-3]** B5 wording “executed keys on disk **before** side effects” as a single flat mark — replaced by phased WAL statuses.

---

## 2026-10-29 — implementation plan sync

| Id | Decision | Status |
|---|---|---|
| PLAN1 | Implementation plan synced to full-picture / this log / transitions YAML: Step 7 rewritten (warm `pi --mode rpc`, `keel_request`, B1–B7, X3-1/X3-2/X3-3/X3-9, D-T suite + `run-tests.sh`/keel-gate wiring, timeouts, recovery, pre-impl Pi smoke); Steps 1/12/13/15–19 updated for visible tests + RO developer mounts + L7T/L8 hardcode checklist. | **active** |
| LABEL1 | Label collision fix: critique #3 unprefixed C-series → **X3-1…X3-9**; older Critic C-/M-/m-series → **CR-C*/CR-M*/CR-m***. See **Label legend**. | **active** |

---

## 2026-10-29 (day) — orchestrator + dispatcher (Critic GO-WITH-FIXES)

| Id | Decision | Status |
|---|---|---|
| OD1 | Two planes: Pi reasons; the **host dispatcher** owns FSM, gates, mounts, journals. Agents do **not** peer-message. | **active** |
| OD2 | Orchestrator: one tool **`keel_request`**; argv fail-closed — no bash/write/edit/codemode; read/search + tool. | **active** |
| OD3 | **Warm** orchestrator per task (`pi --mode rpc` + session in the task folder); **rm** at task end; on wait — stop. Roles are ephemeral `--rm`. | **active** |
| OD4 | Machine FSM YAML (`docs/harness/dispatcher-transitions-v1.yaml` → `setup/dispatcher/…` in the Step 7 process-files PR); prose is not a second truth; cascade `invalidates`; mechanical FAIL → `dispatcher_only` without a model vote. | **active** |
| OD5 | Orchestrator reads everything **except** secrets and `.keel/deny.local`. D1 confidence-notes log is written/read by the orchestrator; hidden from the auditor until verdict. | **active** |
| OD6 | Journals are written **only by the dispatcher**; there is no scribe agent. | **active** |
| OD7 | Status line without an LLM; required fields; no secrets. | **active** |
| OD8 | Timeouts: DEFAULT wall + short start; values **measure**; D2 wait is not killed by those timeouts. | **active** |
| OD9 | Critic fixes: soft D-T5/D-T13 → explicit refusal+audit; hash-stability D-T21 done-when; CI mutate wiring in Step 7. | **active** |
| OD10 | **[superseded B1]** circuit breaker = diff-hash **or** gate-hash. | superseded |
| OD11 | **[superseded H1]** earlier orchestrator visibility ideas replaced by H1–H3. | superseded |

---

## 2026-10-29 (day) — Step 1 visibility / naming / chat

| Id | Decision | Status |
|---|---|---|
| V1 | Naming: in docs and chat — **owner/user**; **no logins** or bot account names; among runtimes — **Pi only**. | **active** |
| V2 | Chat-first: typical path is an **intermediary**; same inbox as direct Pi. **No** second confirmation layer on top of D2. | **active** |
| V3 | Intermediary instructions are **English** in docs; D2 first verbatim (options+default), then paraphrase; checklist on every relay. Clarified by **B7** (raw + interpretation, re-ask, audit). | **active** |
| V4 | `.keel/deny.local` — flat extend-only list; mount-level; applies to **all** agents including the orchestrator. | **active** |
| V5 | Base **secret patterns** are harness-owned; a project may **extend**, never narrow. | **active** |
| V6 | No third owner-decision log: ADR / `docs/decisions.md` + discoveries. | **active** |
| V7 | CR-M5 content fencing → **backlog**. Context-free external-input filter → **backlog**. | **active** (backlog) |
| V8 | **[superseded H1]** earlier test-visibility ideas replaced by H1–H3. | superseded |

---

## Earlier (plan / pipeline / GitHub) — still in force unless superseded

| Id | Decision | Status |
|---|---|---|
| P1 | Process-files always a **separate PR** (label `process-files`); never mixed with product. Scope check / `keel-process-files-separate`. | **active** |
| P2 | **Critic** reviews every PR **before** the owner (harness process). | **active** |
| P3 | Status markers for readiness orientation. | **active** |
| P4 | Ruleset **`require-checks`** active (requires `keel-gate` and `keel-process-files-separate`, strict, no bypass, GitHub Actions only). | **active** |
| P5 | Merge and release — owner only; tags protected by `protect-tags`. | **active** |
| P6 | New dependency → **WAITING_DEP_D2** / D2 to the owner (package, version, license, reason); unanswered waits; `NEEDS_DEPENDENCY` from L5 does not spend a submission. Install `--ignore-scripts` where possible (strengthened by **B2**). | **active** |
| P7 | Envelope fail-closed without D0/D1/D2/oos; `gated_tree_sha` bind; CI blocks tree mismatch. | **active** (implementation Step 19) |
| P8 | Red Team recommendation in the envelope for auth/payments/user data → **backlog**. | **active** (backlog) |
| P9 | Depth light/trivial — profiles of the same FSM; script overrides. | **active** |
| P10 | Parallel tasks: already `TASK` / `work/$T` / `shadow/$T.git` in `setup/keel.sh`. | **active** |

---

## Backlog (explicit)

- CR-M5 content fencing
- Context-free external-input filter agent/tool
- Red Team (envelope recommend)
- Known-bad hardcode example in the reviewer eval set (replaces unused D-T29)
- `inject_summary_ack` kind (not v1)
- Pi programmatic message input — **to verify**
- Numeric budgets/timeouts — measure after first real tasks
- **X3-4:** mid-turn user messages and cancel get top priority and interrupt the turn (today queued until turn end)
- **X3-5:** normalize diffs before the circuit-breaker hash — after measurements
- **X3-6:** per-task total budget warning → hard limit — after measurements (no invented numbers)

Closed into v1: two-phase WAL (X3-3); L3 FS product RO / test RW (X3-1); orchestrator verify `TEST_CONTRADICTS_BRIEF` (X3-2); L6 debug/temp leftovers (X3-9). Rejected: isolate previous-attempt from developer (X3-8).

---

## Open questions / next steps

1. Step 7 process-files PR: dispatcher, YAML under `setup/`, D-T* including D-T30…D-T33, wiring `run-tests.sh`/keel-gate, mutate.
2. Measure edge budgets and DEFAULT/start timeouts after first real tasks; then decide X3-5 and X3-6.
3. Pi: confirm programmatic input for the intermediary.
4. Critic on design docs after large edits.
5. **X3-4 backlog design:** how cancel interrupts an in-flight turn without losing audit — after queue+turn-end stubs are stable.
6. Confirm configurable L6 leftover pattern list location (harness base, project extend-only) in Step 16 wiring — no numeric thresholds.

---

## Superseded map (short)

| Was | Became |
|---|---|
| Separate tests class with restricted mounts | Removed (H1); tests visible; RO for developer |
| CB = diff **or** gate-hash | CB = diff-hash only (B1) |
| `/approve` as an external-critique idea | Rejected (B7) |
| D-T29 line-check of L8 checklist | Dropped; known-bad eval backlog (H3) |
| B5 flat “key before side effects” | Two-phase WAL IN_PROGRESS/COMMITTED (X3-3) |
| Critique #3 isolate previous-attempt | Rejected (X3-8); developer keeps RO read |
| Critique #3 bare unprefixed C-series labels | Renamed to X3-1…X3-9 (LABEL1) |
| Bare Critic C-/M-/m-series in plan | Prefixed CR-C* / CR-M* / CR-m* (LABEL1) |
