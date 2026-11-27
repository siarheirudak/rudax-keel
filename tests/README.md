# Tests

Product tests live in this folder. The harness mounts `tests/` only for the developer, the tester, and the orchestrator.

The developer's mount is read-only. The tester writes `tests/` in the snapshot recorded at setup. `setup/deny/base` and `.keel/deny.local` are enforced. The Step 7 design keeps ordinary tests visible to every role with a work tree; tester-written tests stay read-only for the developer. Honesty on fitting code to tests uses L7T mutation and the L8 hardcode checklist. [Roles and visibility](../docs/roles.md).

The template's own check tests live in `scripts/tests/`, and the setup scripts' fake-`gh` tests live in `setup/tests/`. CI runs those from the pull request, so they are process paths. A pull request that changes them and a product file is mixed.
