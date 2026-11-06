# Discoveries and ADRs

The pipeline keeps two kinds of notes between tasks. The host filter that accepts or discards them is in the harness. This repository does not commit the notes themselves. Candidates live under `.keel/candidates/` at runtime. Accepted files live under `.keel/memory/discoveries/` and `.keel/memory/adr/`.

## Two kinds of memory

A **discovery** is a note about a pitfall: something that went wrong, or nearly did, in a concrete place, and that a later task should not rediscover by accident.

An **ADR** (architecture decision record) is a note about a decision: a choice later tasks have to respect, with the context that led to it.

The developer and the orchestrator may propose a discovery or an ADR. They do not approve one. A host script accepts the candidate or discards it after every role in the iteration has finished. An accepted ADR is packaged for later tasks the same way, one file per decision.

## File shape

One file per entry. The filename starts with the date. The front matter carries:

- an id
- a title
- tags
- paths in the repository the note refers to
- a severity

The body is the note. `kind` is `discovery`, `adr`, or `abort-cause`. `severity` is `critical`, `normal`, or `low`. An ADR body has the headings Context, Decision, and Consequences.

When a role starts, the harness builds an index from accepted files only and fences each line as data. Candidates are not in that index. The fuller L1 package, which would include a matching note in full, is still specified and not built. [Pipeline](pipeline.md#l1-context-packaging).

The host filter refuses a candidate whose paths do not exist. A later CI check is specified, and not built, to watch those paths after acceptance: suggest a rename from `git log --follow`, and mark the entry stale if the path was deleted.

## Who may write

The developer and the orchestrator may submit a candidate. The skill `keel-write-memory` tells them to call `.keel/tools/write-memory-candidate.py`. That script only writes the candidate. Other roles do not see the skill, and they do not receive the candidates directory. A file written without the script is still checked. The host filter does not trust the path the bytes arrived by.

The filter accepts a non-critical candidate only when all of the following hold:

- The file matches the schema, including the date and the enums above.
- The paths it names exist in the work tree and do not escape it.
- The file is at most 32 KiB. That cap is our choice. It applies to candidates only, not to briefs or the append file.
- The text does not contain a phrase that tells a role to bypass a gate.
- The note is significant: it names at least one existing path, or it names a rule and the body is at least 40 characters. The 40-character floor is our choice.
- The judge returns a typed score of at least 0.70. That threshold is our choice, to tune from the audit log, not a measured result.

The judge is `typesafe/jev-1.14` through the Decisions API. The question is fixed by the harness. The candidate is only the text being scored. A score below 0.70, an error, a timeout, or a response that is not a typed number in the expected shape is a discard. CI uses a stub of that call and does not contact the API. The stub is refused outside CI.

A candidate that fails is deleted. The filter does not keep a list of rejected proposals. `severity: critical` is not promoted until the owner says yes. Silence is not a yes.

An accepted file is edited or deleted only by the harness, not by an agent role. The harness may set `superseded_by`.

When a cycle aborts, the dossier helper writes the abort-cause entry. The agent that was running does not write it.

Every accept, reject, error, and timeout appends one JSON line under `$KEEL_ROOT/.keel/logs/`. The line records the verdict and, when the judge ran, the score. It does not record a key or an environment value.

The same pitfall accepted twice is one of the triggers for the skills side path: improve the skill that should have prevented it, or propose a new skill. That proposal still waits for the owner. [Human decisions](owner-decisions.md#approvals).

## What is not a discovery

The task journal is not a discovery. The journal is the working log of one task and is deleted when the owner merges. Discoveries are what remains after that, and only after the filter accepts them.

The system log is not a discovery either. The log is the operational record of actions. A discovery is a conclusion someone might need on a later task. [Logging](logging.md).

## Related

[Logging and the task journal](logging.md) · [Pipeline](pipeline.md#l11-after-the-merge) · [Roles and visibility](roles.md)
