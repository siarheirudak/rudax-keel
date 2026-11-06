# Quality standard

Reviewers and gates in the v1 design share one written standard. They do not each invent rules, and they do not comment on style.

**Status.** The source file is `standards/rules.md`. The generator is `setup/standards/gen.py`. It writes one view per role under `setup/standards/views/`. Each model role mounts only its own view, read-only, as `keel-standards-<role>`. The static gate view is generated and is not mounted into a model role. The host gate in `setup/keel.sh` is still the path gate. It does not score complexity and it does not run a linter. A hand-edited view fails `gen.py --check`.

## One source file

`standards/rules.md` is the only place a rule is written. A generator turns that file into a view per role. Each view is mounted read-only, as a harness skill, into the role that should see it. A role does not receive the other roles’ views.

A rule id is a short code such as `DES-01` or `SEC-03`. The letters are the family. The families the generator knows are:

| Family | What the design uses it for |
|---|---|
| DES | Design of the change |
| CMP | How the pieces are composed |
| SCO | Scope, staying inside the brief |
| TYP | Types. TYP-01 is mechanical and sits on the static gate. TYP-02 and TYP-03 are judgment |
| REL | Reliability. The architect’s view includes REL-01 |
| TST | Tests |
| COR | Correctness |
| ERR | Error handling. ERR-03 is mechanical and sits on the static gate |
| SEC | Security judgment, plus SEC-03 on the static gate for secrets |
| DOC | Documentation that the change requires |
| STY | Formatting and style, owned by the static gate |
| DUP | Duplication, owned by the static gate |
| CX | Structural complexity, owned by the static gate |
| REA | Rules about readable structure. REA-01, REA-02, and REA-04 appear only in the developer guide. REA-03 sits on the static gate |
| DAT | Persisted state through partial failure, retry, and migration |
| API | Supported request, response, event, and serialized contracts |
| RES | Bounded work, retries, waits, and resource lifetime |

Assignment is per rule in the source. A family name is not a view. The sentences live in `standards/rules.md`.

Judgment rules carry two examples in the generated view: one the reviewer should flag, because behaviour is wrong, and one the reviewer should leave alone, because it is a nitpick. That pair is how a reviewer tells a bug from a preference.

## Who sees which rules

| Consumer | What its view is for |
|---|---|
| Developer | Authoring guidance, including REA-01, REA-02, REA-04, and local control flow. No mechanical rule body |
| Architect | Design-time rules, including fail-closed defaults. No local naming, nesting, or style |
| Tester | Pre-implementation authoring, including security scenarios. Not the final judge of its own tests |
| Auditor | Independent judgment. Primary blocker for an unsupported contract break. Keeps the meaningful-oracle rule |
| Design reviewer | Implementation fit, including simple over clever as advice. Interface fit is advice, not the contract block |
| Static gate | Mechanical facets only. No “do not flag” prose |

The auditor’s view includes the SEC family because security judgment sits with the auditor. There is no separate hacker role on the pull-request path.

Light depth runs the auditor only. Full depth also runs the design reviewer. [Architecture](architecture.md#depth).

A project may also keep a `REVIEW.md` that lists what not to flag in that project. Reviewers receive it with the diff. This repository does not have that file.

## What reviewers leave alone

Reviewers do not flag formatting, style, or naming. The static gate owns formatting: it applies the formatter and fails the submission on the mechanical families in the table above. A readability reviewer is not part of the chain.

A finding that reaches the developer must name a file and a line, a rule id, and the effect on behaviour. The verifier drops a finding that lacks any of those, and drops a finding that repeats one already rejected in an earlier round.

`SEC-08` is not a rule id the generator emits. It is a standing “do not flag” policy about the standard itself. It does not appear in a role’s list of rules to apply.

## Rules that were folded together

The generator does not emit a merged id as its own rule:

- DES-02 is part of DES-01
- CMP-03 is part of CX-01
- TST-04 is part of COR-04
- CMP-02 is advice inside DES-01
- CMP-04 is authoring guidance inside CMP-01
- STY-03 is part of the formatter and lint facets

## How this meets the gates

The static gate blocks on its families and lists warnings in the envelope. The complexity warn band and the block line are specified in [Pipeline](pipeline.md#l6-static-gate). Reviewers see those warnings. They do not re-open a formatting question the gate already settled.

Suppression syntax is not accepted in the source. A comment is not authorization. The review step needs an owner-controlled approval path before a suppression can be authorized. Until that path exists, a suppression blocks. Advice does not by itself send the change back to the developer.

A rule that can block names one evidence bar. A rule with no bar is advice. An unknown requirement is advice plus a question for the owner. A required gate adapter with no tool behind it blocks. An optional adapter that is not supported is advice, and it is not a passing check. Project budgets and advisory policy are project policy. This standard does not set a universal number. Citations that are not confirmed are marked to verify.

## Related

[Pipeline](pipeline.md#l8-review) · [Roles and visibility](roles.md) · [Implementation status](status.md)
