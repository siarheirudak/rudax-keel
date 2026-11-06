---
name: keel-write-memory
description: Append a discovery or ADR candidate through the shared read-only script. The host accepts or discards it after the iteration. This does not promote memory and does not grant tools.
---

# Write memory

Use this when a later task should keep a pitfall (a discovery) or a decision (an ADR).

Call the shared script mounted read-only at `.keel/tools/write-memory-candidate.py`.

```bash
python3 .keel/tools/write-memory-candidate.py \
  --work /work \
  --task TASK \
  --kind discovery \
  --title "Short title" \
  --severity normal \
  --date 2026-11-05 \
  --tags pitfall \
  --paths src/example.py \
  --body-file ./note.md
```

`--kind` is `discovery` or `adr`. An ADR body uses the headings `## Context`, `## Decision`, and `## Consequences`.

The script only writes a file under `.keel/candidates/`. It does not accept the note, does not call a model, and does not read secrets.

Do not write into `.keel/memory/`. Do not read other candidates. Accepted memory stays as it was until every role in the iteration has finished. The host filter then accepts or discards each candidate. A discarded candidate is deleted. There is no queue of rejected notes.
