---
name: dialogue-understand
description: Use and revise an existing Dialogue Bridge understanding space across ongoing chats. Load relevant shared understanding, keep this chat's own interpretation, and return sourced discoveries. Use for continued understanding, corrections and task continuation; use dialogue-collaborate for first-time chat links or asking original chats to exchange views.
---

# Shared understanding, independent chats

Help the user continue normally with less repeated explanation. The common method
lives in this skill; changing personal and project understanding stays in the
selected private space. A simple recap of the current chat needs no setup.

## Begin with the current task

Recover what the user is trying to do and what the latest clarification changes.
Use the named space or this chat's existing binding. Supplied source links take
precedence over an old selection; use [dialogue-collaborate](../dialogue-collaborate/SKILL.md)
to resolve a new selection. Ask only when ambiguity materially changes the work.
Do not silently collect every chat or enlarge the selected sources.

Use the runtime's `open` result as the entry point: inspect its index, relevant
shared entries, this chat's document, changes and source coverage. Reuse material
already loaded this turn. Expand relevant entries and original examples when a
specific gap warrants it, rather than loading every document. Read
[runtime operations](references/runtime.md) for exact calls and private documents.
For an explicit ongoing connection, use its collaborator mode; inspect relevant
`related_spaces` when this chat already has a different primary connection.

Shared understanding informs this chat's task. It does not replace the user's
current instructions, project rules or permission to act. Links alone request
background understanding; they do not resume unfinished source tasks.

## Reconsider using experience

Build a cumulative, revisable interpretation from actual examples, corrections,
accepted and rejected proposals, and subsequent results. Recover why an earlier
judgment formed and which conditions it depended on. A summary is a useful claim
to investigate, not a substitute for original messages when a judgment is disputed.

Keep the user's words, an AI's explanation, a candidate, a confirmed decision and
an observed outcome distinguishable. Repeated inherited summaries are not new
independent evidence. An exact quote establishes provenance, not the truth of an
interpretation. Seek relevant opposing examples and later corrections, and read
neighboring messages before generalizing a small incident.

A newer statement may correct a misunderstanding, change a goal, explore an idea
or apply to a different situation. Explain which interpretation the evidence
supports; do not decide by recency, frequency or agreement among AIs. Retain
competing explanations when necessary. Avoid turning examples into fixed
personality tags or accumulating permanent rules after every correction.

Broaden a local judgment only when its evidence and scope support that use. Keep
uncertainty proportional to the decision: ask the user about a consequential gap,
and continue independent work when the gap does not affect it.

## Maintain this chat's own view

The shared document provides common context; each chat keeps its own task,
interpretation, exceptions and continuation in its own document. Reference the
shared entry keys actually used, with the service tracking versions and affected
dependencies. Avoid copying the entire shared document into each chat.

Use `chat_update` for a material change in this chat's understanding or work
continuation, within the connected maintenance scope or an explicit update request.
Keep the current task, adopted reasoning, unresolved differences and useful next
step in natural prose; no mandatory personality form is needed. Another chat can
question the coordinator. Do not overwrite a peer's view to manufacture agreement.

A history analyst or background worker may draft an interpretation about another
chat, but label the real author. Only a contribution from the actual original chat
counts as its participation. Do not substitute its actor identity or treat a fresh
worker with its transcript as that original conversation.

## Return useful changes

When evidence affects the common context, submit a scoped shared revision or a
proposal with original references, the reason for change, and any contrary evidence.
Revise the affected entries; preserve unrelated understanding and previous versions.
Shared updates and dependency notices invite each relevant chat to reconsider;
they do not require the same conclusion or authorize another project's execution.

Source membership and reader binding are separate. Reading a space does not make
this chat a continuing source. If a requested shared correction depends on words
only in this reader, explicitly enroll this chat within that request before using
its persisted messages as evidence; explain that source change briefly. A reader
can keep a local interpretation without quietly enrolling its future conversation.

Read relevant inbox changes and acknowledge only the contributions actually
processed, using their IDs and the observed stage. Delivery, reading, an interpretation response, claimed adoption and
verified later work are different outcomes. Do not claim a change was applied
because it was delivered or saved. Use the current task's actual result when judging
whether the understanding helped.

Present the useful result, material change and remaining uncertainty. Keep routine
maintenance quiet. Installing the plugin, loading this skill or opening its index
does not authorize messaging original chats, starting model turns, changing global
personalization or rewriting project instructions.
