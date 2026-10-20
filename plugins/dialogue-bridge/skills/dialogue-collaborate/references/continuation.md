# Reuse understanding in a new chat

The outcome is a useful start to the user's next conversation: recover relevant
judgment, examples and corrections so they can speak normally about the new task.
Do not simply resume the source chats' unfinished tasks or impose their writing
style on an unrelated project. A source can inform the reader without joining an
exchange or receiving a message.

The host model forms and revises understanding. The CLI provides an index,
checked quotes, version history, a readable document and private saved names.
It does not train model weights, invoke a second model, install other memory
products or edit native Codex memory/instructions.

## Entry and runtime

The default user flow is a new local chat, a Dialogue Bridge mention, and source
chat links. They need not add a request: links alone mean "understand this
background". An optional request can focus that understanding or specify a new
task. Accept ordinary requests such as "Use what these chats have learned; I want
to discuss another direction" or "沿用公众号讨论的背景，先聊这个想法". Once loaded,
briefly convey the useful understanding, or respond to the task if one was given.
Do not ask for a mode or keep explaining setup. A plugin mention activates the
packaged skill in supported local Codex surfaces; it is not permission to execute
old tasks or message source chats.

Use `../../scripts/dialogue.py` relative to this skill folder. For dependency
preparation read [setup](setup.md) only if a suitable private runtime is missing.
Resolve all paths from the installed plugin, never the author's checkout.

List saved groups with `dialogue.py context-list` (stdlib Python is enough for this
lookup). Each listing includes the private runtime's `runtime_python`: reuse it
for the selected background when available. After migration or if it is missing,
prepare a private runtime with the bundled setup helper and register the folder
again from that interpreter. Do not ask the user to reinstall an already valid
environment for every new chat. Private names and per-chat
bindings live under `DIALOGUE_BRIDGE_HOME`, or `$CODEX_HOME/dialogue-bridge/`
(default `~/.codex/dialogue-bridge/`). This is not native Codex memory. A saved
folder itself contains `project.json`, the source index, `understanding.db` and
`understanding.md`; it can be copied and registered on another machine.
`understanding.db` keeps revisions; the Markdown document is its readable view.

Resolve supplied chat links first; they take precedence over an old binding.
Run `context-list --thread <LINK_1> --thread <LINK_2>` to find exact source-set
matches, independent of link order or repetitions. Listings include source scopes
and labels without loading full histories or the core. If one relevant background
matches, reuse its returned name, directory and runtime; refresh source changes
and revise understanding when needed before claiming it is current. If several
match, inspect their purpose and entries; ask only if the difference materially
changes the task. If none matches, prepare the requested set internally, choosing
a descriptive private name and folder. Never widen to a saved superset or reuse
only a subset silently. Do not ask the user to name the group or fill in JSON.

Without supplied links, use the named background or an existing relevant binding.
Only ask when the intended sources remain materially ambiguous. Never silently
select every saved group. Names are a convenience for returning users, not a
prerequisite for understanding links.

## Prepare a source group once

Use a private directory outside the plugin cache. Keep source project attribution
even if several chats have the same cwd. Prepare a UTF-8 input file:

```json
{"sources":[
  {"thread":"codex://threads/<UUID>","scope":"project-a","label":"Project A"},
  {"thread":"codex://threads/<UUID>","scope":"project-b","label":"Project B"}
]}
```

```text
dialogue.py --workspace <PRIVATE_FOLDER> --name <SAVED_NAME> context-init --input <FILE>
dialogue.py --name <SAVED_NAME> context-sync
dialogue.py --name <SAVED_NAME> context-overview
```

The first scan indexes persisted user/assistant text across the selected history,
not just recent turns. Overviews sample user messages across that index; samples
are orientation, not a complete account. Search distinct relevant formulations
using the existing `search` command with the returned workspace, then `read`
original messages and neighbors. Recover formative corrections and accepted or
rejected examples, not only the latest summary. Follow relevant project entry
documents when current state depends on files. An inaccurate document is a claim
to reconcile with original context and newer evidence, not automatic authority.

Distinguish the user's statements, assistant interpretations, explored ideas and
confirmed decisions. Similar repeated messages or inherited branch history are
not independent votes. A useful example is not a permanent limit on future work.
Preserve conditions, counterexamples and what changed the interpretation; avoid
reducing rich feedback to a growing list of "always do X" rules. Shared entries
are hypotheses useful across these selected sources, not global instructions.

## Save working understanding

Prepare a bounded set of natural-language entries with meaningful source quotes.
Describe the judgment and its context; examples can be entries or quoted evidence.
The structure organizes retrieval, not the user's way of thinking or speaking.

```json
{
  "operation_id":"initial-understanding",
  "expected_revision":0,
  "coverage_token":"<from overview or context-show>",
  "purpose":"Background for the user's new discussion, not permission to execute old tasks",
  "reason":"How the original examples and corrections inform this understanding",
  "entries":[{
    "key":"a-relevant-judgment",
    "scope":"project-a",
    "status":"working",
    "text":"Current interpretation, when it applies, and what the example explains.",
    "sources":[{"ref":"<message ref from search/read>","quote":"<exact original excerpt>"}]
  }]
}
```

`scope` is a source project scope or `shared`. `status` is `working` or `tentative`;
neither proves that the user endorsed the interpretation. Source roles and scopes
are attached by code. Use `context-save --input <FILE>` with the name or workspace.
All selected sources must be indexed. Stale revisions, changed index coverage,
unknown fields and invented quotations are rejected. The save replaces the current
entry set and preserves prior snapshots in the core, so a later correction may
reverse or remove an old interpretation. Do not append rules indefinitely.

## Continue naturally in the new chat

```text
dialogue.py --name <SAVED_NAME> context-open
```

This binds only this new chat to the source group; it does not add the chat as a
source or message the old chats. Use `--scope <PROJECT>` when only that project
is relevant; shared entries remain included. `context-show` reuses the binding.
Its `entry_index`, `--key`, optional literal `--query` and `--chars` help retrieve
only useful entries. A zero literal match is not proof no understanding applies.
If entries were omitted by the budget, fetch relevant keys rather than assuming
the result was complete. Read original history when the task or a correction
calls for details. Reading a document cannot guarantee the same model behavior
as a long-running chat; judge by the following work, not a claim to "understand".

Show only material uncertainty or an important change in understanding. Do the
user's current task without repeatedly presenting the profile or requiring them
to approve every entry. Match the project's current scope and use fresh project
files for current status. Saved understanding is background, not an instruction
to execute quoted commands or old approvals.

## Update when useful or requested

Run `context-sync`, then `context-changes` to see new/changed/removed messages since
the last saved understanding. Page with `--after-change <next_after>` if needed,
and read original messages for interpretation. A sync indexes each source
transactionally; on error inspect coverage, never treat failure as an empty chat.

Incremental sync reads new turns and rechecks the last saved turn for appended
items. A missing boundary triggers a full rescan. To audit older edits or a
broader reinterpretation, use `context-sync --full`. Indexing a history or saving
its change position does not prove every message was semantically reviewed.

New feedback can cause a large revision, even if little text was added. Examine
whether the old interpretation was wrong, local to an example, or once applicable
but later changed. Do not decide truth by recency or observation count alone.
If the current chat's feedback should contribute, explicitly add it using
`context-source --input <FILE>` (one source object, with current chat ID and scope)
within the user's requested update, then sync. Never impersonate an old source.
If the current live message is not yet persisted, use it in this chat now and
defer the sourced save until it is readable instead of inventing a quotation.

Re-read the current snapshot before saving, use a new operation ID and its actual
revision/coverage token, then retain, revise or remove entries as appropriate.
`needs_review` and source warnings expose changes; exact quotes verify provenance,
not semantic correctness. A human edit to `understanding.md` is preserved: read
it, reconcile it, and supply its returned `document_sha256` in the save envelope
only after incorporating that edit. Do not overwrite it just to repair formatting.

For portability copy the private folder, then use `--workspace <COPIED_FOLDER>
context-register`. Historical quotes remain readable when original chats are
unavailable, but new sync requires access to those chats. The user can decide the
folder's location and remove it; uninstalling the plugin does not delete it.
