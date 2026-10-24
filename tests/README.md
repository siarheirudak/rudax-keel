# Tests

Product tests live in this folder. This layer does not enforce anything on `tests/`. A later layer will protect this folder according to roles.

The template's own check tests live in `scripts/tests/`, and the setup scripts' fake-`gh` tests live in `setup/tests/`. CI runs those from the pull request, so they are process paths. A pull request that changes them and a product file is mixed.
