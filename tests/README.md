# Tests

Product tests live in this folder. This layer does not enforce anything on `tests/`.

Ordinary product tests are visible to every role the harness starts today. The v1 design keeps tests visible; tester-written tests mount read-only for the developer. Honesty on fitting code to tests uses L7T mutation and the L8 hardcode checklist. Per-role deny mounts for secrets and `.keel/deny.local` are specified and not built yet. [Roles and visibility](../docs/roles.md).

The template's own check tests live in `scripts/tests/`, and the setup scripts' fake-`gh` tests live in `setup/tests/`. CI runs those from the pull request, so they are process paths. A pull request that changes them and a product file is mixed.
