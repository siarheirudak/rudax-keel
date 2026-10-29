# Discoveries and ADRs

The pipeline keeps two kinds of notes between tasks. Both are specified for v1 and neither exists in this repository. There is no `.keel/` directory, no discoveries directory, and no ADR directory.

## Two kinds of memory

A **discovery** is a note about a pitfall: something that went wrong, or nearly did, in a concrete place, and that a later task should not rediscover by accident.

An **ADR** (architecture decision record) is a note about a decision: a choice later tasks have to respect, with the context that led to it.

Agents may propose a discovery. They do not approve one. A host script accepts the candidate or discards it. An ADR is packaged for later tasks the same way, one file per decision.

## File shape

One file per entry. The filename starts with the date. The front matter carries:

- an id
- a title
- tags
- paths in the repository the note refers to
- a severity

The body is the note. When L1 builds a context package, an entry is included in full if it matches the task’s paths or tags, or if it is marked critical. Other entries become a single index line, newest first. The index is built in memory and is not written to disk. The body is fenced as data, so the note cannot act as a fresh instruction to the agent. [Pipeline](pipeline.md#l1-context-packaging).

A CI check watches the paths named in the front matter.

- The path must exist.
- If the file was renamed, the check suggests the new path from `git log --follow`.
- If the path was deleted, the entry is stale.

## Who may write

The developer, and other agents that see a pitfall, may submit a candidate. The host filter accepts it only when all of the following hold:

- The file matches the schema.
- The paths it names exist.
- The size is within the filter’s limit. The design names a size check and does not fix a number in the planning notes, so this page does not invent one.
- The text does not contain an instruction to bypass a gate.
- The note is significant: it points at concrete paths or at a rule, and it describes a pitfall or a decision that would not be obvious from the code alone.

A candidate that fails is discarded. The filter does not keep a list of rejected proposals for a person to approve later.

An accepted file is edited or deleted only by the harness, not by an agent role.

When a cycle aborts, the dossier script writes the abort-cause entry. The agent that was running does not write it.

The same pitfall accepted twice is one of the triggers for the skills side path: improve the skill that should have prevented it, or propose a new skill. That proposal still waits for the owner. [Human decisions](decisions.md#approvals).

## What is not a discovery

The task journal is not a discovery. The journal is the working log of one task and is deleted when the owner merges. Discoveries are what remains after that, and only after the filter accepts them.

The system log is not a discovery either. The log is the operational record of actions. A discovery is a conclusion someone might need on a later task. [Logging](logging.md).

## Related

[Logging and the task journal](logging.md) · [Pipeline](pipeline.md#l11-after-the-merge) · [Roles and visibility](roles.md)
