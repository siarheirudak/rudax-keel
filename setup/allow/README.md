# Folder allowlists

`setup/keel.sh role <name>` and `role-env <name>` mount only the folder roots in `setup/allow/<name>.paths`. One folder root per line. Blank lines and `#` comments are ignored. Globs, absolute paths, and `..` are refused. An empty list, a missing file, or an unknown name refuses the launch.

Read-only and read-write are fixed in `setup/lib/visibility.py`. `tests/` is read-only for the developer. The tester is mounted from the commit recorded at setup, and can write only `tests/` in that snapshot.

`setup/deny/base` is the immutable withhold list (secret basenames and harness paths). `.keel/deny.local` may add paths. A line that tries to remove a base entry refuses the launch. The project file is read once per task, at the first launch, and later edits are ignored. Roles cannot read or write `.keel/deny.local`, `.keel/logs/`, or `.keel/runs/`.

`.keel/decisions/<task-id>/` is mounted for the orchestrator (read-write) and the architect (read-only). Every other role is withheld, including the developer, the tester, and the auditor. `.agents/` is withheld from every role except the skills auditor.

Launch decisions are appended to `$KEEL_ROOT/.keel/logs/launch.jsonl` by one writer. Records are JSONL with `redactions` set to the number of replacements. Replacements use `[REDACTED:token]`, `[REDACTED:key]`, `[REDACTED:password]`, `[REDACTED:env]`, or `[REDACTED:unknown]`. The writer refuses the record if a secret would remain. Role stdout is not copied into the log.

`$KEEL_ROOT/.keel/runs/` holds the tester snapshot and mount masks for one command and is removed when that command exits. The task deny snapshot is removed by `cleanup` and when `setup` fails. Logs are not removed by `cleanup`.

`proto` and `proto-env` are the host gate suite's work-tree containers. They are not roles. `role` does not call them, and an environment variable cannot select them.

A secret file created inside an already mounted read-write root during that same command can be read until the command ends. The next launch withholds a matching basename. Renaming a secret so the basename is outside `setup/deny/base` is outside this step. There is no size cap on `.keel/logs/` here.

Changing what a role can see is a process-files change, reviewed, then merged by the owner.
