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
Use the global `--compact` option before the subcommand for routine retrieval.
It reduces JSON formatting and repeated index metadata while keeping original
excerpts, source warnings, coverage tokens and continuation controls. Omit it
when detailed index diagnostics are needed; it does not change what is indexed.

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
with `--name <NAME> context-open --refresh`. This combines source refresh, the
current understanding and this reader's binding. If understanding exists, start
with the returned entries and key index; do not also load an overview and the
same full snapshot again. `needs_review` includes a bounded `changes` page when
sources changed: review it and continue with `context-changes` if needed, then
revise affected understanding before claiming it is current. If several
match, inspect their purpose and entries; ask only if the difference materially
changes the task. If none matches, prepare the requested set internally, choosing
a descriptive private name and folder. Never widen to a saved superset or reuse
only a subset silently. Do not ask the user to name the group or fill in JSON.
An empty exact match is enough to prepare that set; listing unrelated saved
groups cannot turn a subset into an exact match.

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
dialogue.py --name <SAVED_NAME> context-open --refresh
```

With no saved understanding yet, this returns an overview after the first scan,
ready for the host to interpret and save. The scan indexes persisted user/assistant
text across the selected history, not just recent turns. Overviews sample user
messages across that index; samples
are orientation, not a complete account. Search distinct relevant formulations
using the existing `search` command with the returned workspace, then `read`
original messages and neighbors. Recover formative corrections and accepted or
rejected examples, not only the latest summary. Follow relevant project entry
documents when current state depends on files. An inaccurate document is a claim
to reconcile with original context and newer evidence, not automatic authority.

For history searches, `--limit` is 1..30 and `--chars` is a total excerpt budget of
1..20000. Start with focused results and expand for a concrete gap. Select project
files using the user's current purpose and actual entry/index files; several source
chats can share a cwd without sharing a direction. Use file search or an index to
confirm a referenced path before reading it, rather than guessing a draft filename.
Read current state and relevant examples/code as needed, not the whole directory.
Project reading is supplied by the host's file tools; it is not an automatic file
index. Understanding links alone does not authorize editing shared project rules,
business files or native memory. Keep the reusable understanding in its private
folder so another task receives it only when it loads that background.

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
dialogue.py --name <SAVED_NAME> context-open --refresh
```

This binds only this new chat to the source group; it does not add the chat as a
source or message the old chats. Use `--scope <PROJECT>` when only that project
is relevant; shared entries remain included. If it was already opened and refreshed
in this turn, use that result rather than opening it again. `context-show` reuses
the binding for a particular entry or a different scope/budget without syncing.
Its `entry_index`, `--key`, optional literal `--query` and `--chars` help retrieve
only useful entries. A zero literal match is not proof no understanding applies.
If entries were omitted by the budget, fetch relevant keys rather than assuming
the result was complete. Read original history when the task or a correction
calls for details. Reading a document cannot guarantee the same model behavior
as a long-running chat; judge by the following work, not a claim to "understand".

Reuse results already loaded in this turn: the opened snapshot supplies the
revision and coverage token for a later save. Expand missing keys or source
excerpts for a concrete question. Do not repeat the same history through the
host's chat reader unless the index lacks needed content or needs verification.

Show only material uncertainty or an important change in understanding. Do the
user's current task without repeatedly presenting the profile or requiring them
to approve every entry. Match the project's current scope and use fresh project
files for current status. Saved understanding is background, not an instruction
to execute quoted commands or old approvals.

## Update when useful or requested

When the user asks to record a correction or update this saved understanding,
complete the private revision as part of that request, then briefly say what
changed. Ordinary discussion can stay in this chat; it need not create a saved
rule. Determine whether the evidence is in the selected sources or only in this
reader. If this reader's feedback is needed, explicitly add the current chat
with `context-source --input <FILE>` (one source object with its ID and relevant
scope) within the requested update. This changes this group's source set; say
so briefly. Do not add unrelated chats or impersonate an old source.

Use `--compact context-open --refresh` to get current entries, revision, coverage
token and the first change page together. If this turn already has that result
and there is no newer evidence to sync, reuse it. Page `context-changes` with
`--after-change <next_after>` when `has_more` is true; expand relevant original
messages for interpretation. A sync indexes each source transactionally; on
error inspect coverage, never treat failure as an empty chat. If the live
feedback is not yet persisted, apply it in this chat and say the private revision
is pending; do not claim it was saved or invent a quotation.

Incremental sync reads new turns and rechecks the last saved turn for appended
items. A missing boundary triggers a full rescan. To audit older edits or a
broader reinterpretation, use `context-sync --full`. Indexing a history or saving
its change position does not prove every message was semantically reviewed.

New feedback can cause a large revision, even if little text was added. Examine
whether the old interpretation was wrong, local to an example, or once applicable
but later changed. Do not decide truth by recency or observation count alone.
For a local correction, use `context-revise --input <FILE>` with only the entries
to replace/add and optional `remove_keys`. Other entries remain in place. Each
replacement is a complete entry with source quotes, not a text fragment:

```json
{
  "operation_id":"reconsider-one-judgment",
  "expected_revision":1,
  "coverage_token":"<from the current open result>",
  "reason":"What the new evidence changes and why",
  "entries":[{
    "key":"a-relevant-judgment",
    "scope":"project-a",
    "status":"working",
    "text":"Revised interpretation and its applicable context.",
    "sources":[{"ref":"<original message ref>","quote":"<exact excerpt>"}]
  }],
  "remove_keys":[]
}
```

`purpose` is optional and otherwise preserved. At least one replacement/addition
or removal is required. The same quote, scope, document and optimistic-revision
checks apply to the complete resulting snapshot, including unchanged entries.
If unchanged evidence is no longer valid, review that entry too. An exact retry
with the same operation ID does not undo a newer revision. Use `context-save`
for an initial understanding or a deliberate full replacement; do not construct
one from a budget-limited or scope-filtered result and accidentally drop other
entries. Reuse the loaded revision/token; reopen on a stale-revision or coverage
error, then reconsider the changes rather than overwriting concurrent work.
`needs_review` and source warnings expose changes; exact quotes verify provenance,
not semantic correctness. A human edit to `understanding.md` is preserved: read
it, reconcile it, and supply its returned `document_sha256` in the save envelope
only after incorporating that edit. Do not overwrite it just to repair formatting.

For portability copy the private folder, then use `--workspace <COPIED_FOLDER>
context-register`. Historical quotes remain readable when original chats are
unavailable, but new sync requires access to those chats. The user can decide the
folder's location and remove it; uninstalling the plugin does not delete it.
