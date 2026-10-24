# Shared understanding across independent chats

Dialogue Bridge keeps useful understanding available while each chat continues
its own work. Shared background can include why a goal changed, what an example
clarified, which approach failed and where interpretations still differ. It is
revisable working context, not a permanent personality profile.

## Start with links

In a local Codex chat, select `@Dialogue Bridge` and paste the source chat links:

```text
@Dialogue Bridge
codex://threads/<FIRST_CHAT_UUID>
codex://threads/<SECOND_CHAT_UUID>
```

With links alone, Bridge understands the selected background for this reader and
briefly explains what is useful. Add a focus or a task in ordinary language if
you have one. You do not need to prepare a handoff, choose internal roles, name
a database or type service commands.

To keep selected chats connected as their work develops, say so:

```text
Keep these two chats connected. Use their later discussion to update the shared
understanding, and let each keep its own interpretation for its work.
```

The source selection is remembered. Opening background in a new reader does not
silently enroll that reader's future conversation. If a correction in the reader
should join the shared sources, you can ask to include this chat. Installing the
plugin does not select your whole account or rewrite native memory, personalization
or project instructions.

## One method, changing private documents

The public `dialogue-understand` skill supplies the common method. The selected
private understanding space holds the changing content:

- A shared document records useful common context, scoped interpretations and
  unresolved differences, with source references and revision history.
- Each chat's document records its current work, the shared entries it uses, its
  own interpretation, exceptions and continuation. A chat can question a shared
  conclusion or the coordinator's reading.
- The index helps find relevant entries, chat documents and original evidence.
  Dependency records help identify which chats should reconsider a changed entry.

Only the material relevant to the current question needs to be loaded. Related
examples or original messages can be opened when a summary is insufficient. An
index or a completed history scan describes coverage; it does not prove that every
message has been understood.

For example, a product chat and a writing chat may both use the observation that
the user often clarifies an idea through discussion. The product chat might keep
two design candidates open; the writing chat might preserve an approved paragraph
while discussing its ending. They use a common understanding for different work.
A later correction in one direction does not automatically become a rule for both.

## Corrections change the interpretation

You can ask:

```text
That summary makes my preference sound permanent. Revisit the examples and narrow
it to the situation we were discussing.
```

The model should compare the existing interpretation, the original examples,
your correction and any contrary evidence. A later message may change a goal,
correct an earlier misunderstanding or describe a different situation. Newest
does not automatically mean most accurate, and several AIs repeating one summary
do not supply several independent pieces of evidence.

A useful update may revise one entry, split its scope, withdraw it or retain two
possible explanations. Unrelated entries stay intact and older revisions remain
available. The user need not approve every ordinary maintenance step within an
already authorized connection. A consequential ambiguity can still need a question.

External edits to the private documents are preserved and brought into the revision
process. An unexplained file edit is attributed as an external edit; it is not
silently treated as the user's endorsement or overwritten by the next refresh.

## Bring findings back to actual work

You can ask the selected original chats to compare an issue or bring a finding
back into their own directions. Each contribution retains its author, scope and
evidence. Agreement is optional; a substantive difference can remain visible.

Original chats can collect relevant pending changes when they next enter the
space. Immediate requests use an available host messaging channel only within
the user's authorization. Reading stored history or writing an inbox item does
not itself wake the original chat. When no suitable transport is available,
the update remains pending for that chat to collect.

Bridge distinguishes these outcomes: a change was delivered, a chat read it, the
chat responded, it reported adopting the idea, and subsequent work demonstrated
that adoption. A background worker's analysis is labeled as that worker's work;
it is not a reply from an absent original chat. A saved document alone cannot
prove that the next result will reflect it.

## Maintenance and model work

Within connected scopes, hooks prepare saved context and queue incremental source
collection. Source sync and interpretation are separate operations. The model in
the current chat can revise relevant shared entries and its own document while
working with you. Routine maintenance should stay quiet unless an important
interpretation changes, current work is affected or a decision needs your input.

Background understanding is optional and requires a configured model worker and
an enabled setting. Its calls can consume the configured account's quota or local
compute. Queuing a job is not proof that it completed; successful indexing is not
proof that the understanding was updated. The activity view exposes pending work
and failures. Model and reasoning choices are preserved unless you request a change.

## Inspect and move your data

Ask to see the current understanding, its sources, a chat's interpretation or
what changed. The local management page provides an overview, understanding and
activity views. Keep private data outside the installed plugin directory so a
plugin update does not replace it.

Export includes versioned understanding, selected private documents and preserved
evidence. Runtime settings, credential configuration files and worker commands are
excluded; original source text stays intact in this private package. Import uses a
new or empty target without replacing existing work. Historical evidence can remain
readable when original chats are unavailable; fresh collection requires access
to those chats. Restore recovers shared understanding as a new revision; existing
chat documents and intervening history remain in place. Import a bundle into a
new space for full recovery.
Moving a bundle to a different tool does not itself give that tool automatic sync
or the ability to wake original conversations.

Existing alpha.7 `dialogue.py context-*` and shared-record workflows remain
available. See the [continuation guide](../plugins/dialogue-bridge/skills/dialogue-collaborate/references/continuation.md)
for that contract and the [runtime reference](../plugins/dialogue-bridge/skills/dialogue-understand/references/runtime.md)
for MCP and CLI operations.

The software checks provenance, scope, versions and storage behavior. Understanding
quality still depends on the model and the evidence retrieved. Its value is best
judged in the work that follows: what no longer needed explaining, what was missed
and whether a relevant correction actually changed the result.
