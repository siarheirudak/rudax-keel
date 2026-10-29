# Harness design (Step 7)

Design documents for the warm Pi orchestrator, host dispatcher, and FSM. These are **design** — the dispatcher is not built in the repository yet. Implementation is Step 7 of the plan and ships as a **process-files** pull request (do not mix with product code).

| Document | What it is |
|---|---|
| [Orchestrator and dispatcher](orchestrator-dispatcher.md) | Full-picture design: planes, visibility, FSM, `keel_request`, B1–B7, X3-*, D-T* |
| [Implementation plan v1](implementation-plan-v1.md) | Ordered steps for the harness |
| [Dispatcher transitions YAML](dispatcher-transitions-v1.yaml) | Machine FSM table (runtime copy will live under `setup/dispatcher/` after Step 7) |
| [Decisions log](decisions-log.md) | Owner decisions with label legend |

Related public docs: [Architecture](../architecture.md), [Pipeline](../pipeline.md), [Roles](../roles.md), [Status](../status.md).
