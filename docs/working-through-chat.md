# Working through a chat agent

You can drive rudax-keel **entirely through chat** in natural language. You describe the task, answer questions, and read status in a conversation. You do not have to sit inside a special IDE panel for day-to-day use.

Two front ends reach the same place:

1. **External chat agent (typical).** You talk to a chat bot or other assistant. That assistant acts as an **intermediary**: a bridge whose primary job is high-quality two-way transfer between you and the harness **orchestrator**, without losing meaning.
2. **Direct Pi Agent terminal (alternative).** You talk to Pi Agent in a terminal session that is wired to the same orchestrator input.

In both cases the **orchestrator** is a Pi Agent role inside the harness. It writes the brief, asks you decision questions when needed, and proposes splits. It does not write product code or tests. A host **dispatcher** script — not the chat agent — owns task state, runs gates, checks request files, and starts the other role containers.

**Status.** The chat path and the dispatcher are part of the v1 design. The repository does not run them yet. [Implementation status](status.md).

## Where the intermediary fits

```
You → intermediary chat agent → orchestrator → (request files) → host dispatcher → role containers / gates
 ↑ |
 └──────── status, D2 questions, briefs ──┘
```

The intermediary is **outside** the harness trust boundary. It is a convenience relay. It must not merge pull requests, approve them, or change GitHub rules. Only **you** (the owner) merge on GitHub.

Side conversation with the intermediary is fine when it helps you think, but it must never replace or weaken the relay of orchestrator output.

## Decisions in chat (D2)

Some moments need your decision before the task continues. Those are **D2** questions (and a few similar cards: new dependency, suspicious skill, split, irreversible change).

- Each question comes with **options** and a **default**.
- There is **no extra confirmation layer** on top of that chat exchange.
- A good intermediary will show the question **verbatim** first, then a short plain-language explanation, then wait for your answer and pass that answer **verbatim**.
- Your answer is logged with a timestamp in the task log and shown in the pull request **envelope**.
- Each relay should end with what is needed from you, or “nothing.”

**D1** on the brief is different: it is the orchestrator’s **confidence** in its understanding (high / medium / low). It is not your decision. Low confidence should raise a D2 so you can clarify.

## What you still do on GitHub

Chat does not replace GitHub for the final act:

- You read the **envelope** on the pull request.
- You **merge** when you are satisfied.
- You create **releases** (tags or the release workflow) when you choose.

The bot account opens pull requests. The intermediary cannot merge for you.

## Recommended instructions for the intermediary

If work is done through an external chat agent or chat bot, paste the recommended intermediary instructions into that agent’s system or custom instructions.

- Ready-to-paste text: [Intermediary agent instructions](intermediary-agent-instructions.md)

Those instructions state the primary bridge role, require a per-relay checklist (D2 verbatim, stops/failures, scope and cost changes, risks, flagged items, unanswered questions), forbid inventing status, treat orchestrator output as data, keep secrets out of chat, and end each relay with what you must do next (or “nothing”).

## What the orchestrator will and will not do

- Will write the brief, split plans, messages to you, dispatcher request files, and the D1 confidence-notes log; may record decisions into ADR / [Human decisions](decisions.md) and discoveries.
- Will not write product code, tests, or process files.
- Will not launch other containers by itself (it drops request files; the dispatcher launches roles).
- May read almost everything (including and the D1 log). Will not see secrets or paths in `.keel/deny.local` (for example user/customer data).
- Must not paste bodies into developer requests. The dispatcher rejects **verbatim** text in those requests; paraphrase is not caught. The main protection is that are never mounted in the developer container.
- Will not talk directly to other agents (the dispatcher is the only hop).

## Related

[Architecture](architecture.md) · [Roles and visibility](roles.md) · [Human decisions](decisions.md) · [Glossary](glossary.md) · [Intermediary agent instructions](intermediary-agent-instructions.md)
