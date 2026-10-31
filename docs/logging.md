# Logging and the task journal

Two records follow a task. One is a short journal the host keeps so the task can resume. The other is a system log a person can read later without the repository open beside them. Both are specified for v1. Neither is written by the code in this repository. The harness does write a separate launch log, described below.

## The task journal

The journal is a markdown file at `.keel/runs/<task-id>/journal.md`. The host script appends to it after each link. Agents do not append to it.

Each entry records:

- the link, and the role that ran
- the result name
- the commit, when the link produced one
- the artifacts
- the money and the minutes spent
- the dossier reason, when the link stopped the cycle

Resume starts at the last entry that passed. When a link is redone, the journal is included as fenced context, so the redo can see what already happened without treating the journal as new instructions.

The script deletes the journal immediately after the owner merges. A merged task is remembered through the system log and through any discovery the filter accepted, not through the journal.

The directory `.keel/runs/` is not committed. The harness uses it as temporary mount state and removes it when the command exits. The journal file is still not written.

## Launch decisions

When `setup/keel.sh role` or `role-env` accepts or refuses a launch, the harness appends one JSON object to `$KEEL_ROOT/.keel/logs/launch.jsonl`. Roles cannot read or write that directory. Cleanup does not delete it. A record includes `redactions`. Secret values are replaced with `[REDACTED:token]`, `[REDACTED:key]`, `[REDACTED:password]`, `[REDACTED:env]`, or `[REDACTED:unknown]`. This is not the system log below. Rotation is not implemented.

## The system log

The system log is JSONL: one JSON object per line, so a later tool can read it without a private format.

Each event carries:

- the time, with a timezone
- the task id
- the link, both as its short name (`L4`) and as a plain expansion (`red gate`)
- the role
- the model, when a model ran
- the action
- the result
- the reason
- references to artifacts, not the artifacts’ contents

An export starts with a glossary header, so a reader who was not in the room can tell what the field names mean. The export contains no secrets and no source code. A scrub check runs on the way out and rejects an export that contains either.

The design includes a test of that export: a model that is given no other context has to explain what the run did. That test is part of the logging step. It is not in `scripts/tests/` or `setup/tests/` today.

Skill use is recorded in this log. The retrospective counter reads task history from it. Every 3 to 5 merged tasks the counter offers a retrospective. It does not start one. A retrospective agent is not part of v1.

## Budget

<a id="budget"></a>

The envelope shows the budget still remaining on the task.

Until spend has been measured, going over the budget only warns. The design waits for the first 5 to 10 tasks before it sets a cap. The intended cap is about twice the median spend of those tasks, plus a limit on iterations. Both the number of tasks in the sample and the multiple of the median are project settings. They are not figures measured in this repository, because the pipeline has not run.

When that warning becomes a hard stop is an open choice. [Status](status.md#settings-still-open).

`NEEDS_DEPENDENCY` does not spend a coding submission while the task waits. A rollback failure does spend one. The journal is where those costs are appended. The accounting rules are in [Pipeline](pipeline.md#l5-code).

## What exists instead

The setup scripts write their own logs under `setup/logs/`, gitignored, one file per apply or verify run. Each line points at a section of [why.md](why.md). Those logs are about GitHub settings. They are not the task journal and they are not the JSONL system log.

The harness suites write under `setup/tests/harness/logs/`, also gitignored. Those are test output from the isolation prototype.

## Related

[Discoveries and ADRs](discoveries.md) · [Human decisions](decisions.md) · [Implementation status](status.md)
