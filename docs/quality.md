# Quality standard

Reviewers and gates in the v1 design share one written standard. They do not each invent rules, and they do not comment on style.

**Status.** Specified. The file `standards/rules.md` is not in this repository. No generator runs. No per-role view is mounted. The static gate described here is not the host gate in `setup/keel.sh`. The host gate checks paths, history, and a test entry. It does not score complexity and it does not run a linter.

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

The individual sentences of those rules are not in this repository. This page records who will see which family once the generator exists. It does not invent the rule text.

Judgment rules carry two examples in the generated view: one the reviewer should flag, because behaviour is wrong, and one the reviewer should leave alone, because it is a nitpick. That pair is how a reviewer tells a bug from a preference.

## Who sees which rules

| Consumer | Families in its view |
|---|---|
| Developer style guide | All rules. REA-01, REA-02, and REA-04 appear only here |
| Architect | DES, CMP, SCO, TYP-03, REL-01 |
| Tester | TST, COR-02, COR-04 |
| Auditor | COR, TST, ERR, TYP-02, TYP-03, SEC, SCO, REL, DOC |
| Design reviewer | DES, CMP |
| Static gate | STY, TYP-01, DUP, CX, REA-03, ERR-03, SEC-03 |

The auditor’s view includes the SEC family because security judgment sits with the auditor. There is no separate hacker role on the pull-request path.

Light depth runs the auditor only. Full depth also runs the design reviewer. [Architecture](architecture.md#depth).

A project may also keep a `REVIEW.md` that lists what not to flag in that project. Reviewers receive it with the diff. This repository does not have that file.

## What reviewers leave alone

Reviewers do not flag formatting, style, or naming. The static gate owns formatting: it applies the formatter and fails the submission on the mechanical families in the table above. A readability reviewer is not part of the chain.

A finding that reaches the developer must name a file and a line, a rule id, and the effect on behaviour. The verifier drops a finding that lacks any of those, and drops a finding that repeats one already rejected in an earlier round.

`SEC-08` is not a rule id the generator emits. It is a standing “do not flag” policy about the standard itself. It does not appear in a role’s list of rules to apply.

## Rules that were folded together

The generator treats three ids as already merged, so they are not emitted as separate rules:

- DES-02 is part of DES-01
- CMP-03 is part of CX-01
- TST-04 is part of COR-04

## How this meets the gates

The static gate blocks on its families and lists warnings in the envelope. The complexity warn band and the block line are specified in [Pipeline](pipeline.md#l6-static-gate). Reviewers see those warnings. They do not re-open a formatting question the gate already settled.

A suppression of a pattern-scan finding needs a reason. Reviewers check the reason. The gate checks that a reason is present.

## Related

[Pipeline](pipeline.md#l8-review) · [Roles and visibility](roles.md) · [Implementation status](status.md)
