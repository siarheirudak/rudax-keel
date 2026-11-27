# Harness design (Step 7)

Design documents for the host Pi orchestrator (a guard and one `keel` tool), the host dispatcher, and the FSM. These are **design** — planned; nothing in this layer is built. The implementation will ship as **process-files** pull requests (do not mix with product code).

| Document | What it is |
|---|---|
| [Orchestrator and dispatcher](orchestrator-dispatcher.md) | Planes, visibility, FSM, the `keel` tool, keys and model access, layout, push and cleanup, and the D-T* tests |
| [Implementation plan v1](implementation-plan-v1.md) | Ordered steps for the harness |
| [Dispatcher transitions YAML](dispatcher-transitions-v1.yaml) | Machine FSM table (runtime copy will live under `setup/dispatcher/` after Step 7) |

Related public docs: [Architecture](../architecture.md), [Pipeline](../pipeline.md), [Roles](../roles.md), [Status](../status.md).
