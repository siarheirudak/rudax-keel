# Tests

Product tests live in this folder. This layer does not enforce anything on `tests/`.

The v1 design will hide one class of tests, called holdouts, from the developer by not mounting them. That deny-list is not built. Ordinary product tests stay visible to every role the harness starts today. [Roles and visibility](../docs/roles.md).

The template's own check tests live in `scripts/tests/`, and the setup scripts' fake-`gh` tests live in `setup/tests/`. CI runs those from the pull request, so they are process paths. A pull request that changes them and a product file is mixed.
