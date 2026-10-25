# Understanding runtime

Use the installed plugin's MCP tools named `bridge_<action>`. If the host does
not expose them, run the same action through the installed plugin:

```text
<PYTHON> <PLUGIN>/scripts/bridge_service.py action <ACTION> --input <INPUT_FILE>
```

`<INPUT_FILE>` is a private UTF-8 JSON file containing the same parameters as the
MCP call. Resolve `<PLUGIN>` from this skill's installed location, not an author's
checkout. Reuse the prepared private Python environment; follow the existing
[setup reference](../../dialogue-collaborate/references/setup.md) if it is missing.
Do not require users to type these calls or write JSON themselves.

## Select sources and open context

Use `list_spaces` to locate a named background or the current chat's binding.
Supplied links take precedence. Compare the selected source set rather than
silently using a saved superset. If no selection matches, choose a descriptive
private name and a directory outside the plugin cache and version control.

`connect` accepts:

```json
{
  "name": "design-background",
  "sources": [
    {"thread": "codex://threads/<CHAT_UUID>", "scope": "design", "label": "Design discussion"}
  ],
  "directory": "<NEW_PRIVATE_DIRECTORY>",
  "bind": true,
  "participate": false
}
```

With links alone, bind the current reader and keep `participate` false. An explicit
request to keep selected chats connected permits ongoing collection of the selected
sources; enrollment of the current reader remains a separate choice. Check the
returned membership rather than assuming that binding enrolled it.

For that ongoing connection, pass `mode: "collaborator"`. Selected source chats
receive a scoped binding for their next check-in; another space's existing primary
binding is kept. `related_spaces` lets a returning source discover other connected
spaces without mixing their contents. No source chat is resumed or messaged.
`participate: true` enrolls the actual current chat too; use it only when that is
part of the request. With multiple project scopes, include the current chat in
`sources` with its intended scope before using this option.

`open` accepts `name` or `directory`, optional `query`, `scopes` and `actor`.
Normally let the actor resolve from the host's current chat. Do not pass another
chat's identity to author its document. Open returns the saved context and review
state; it does not prove complete interpretation of every indexed message.

Use `sync` when fresh source text is needed. Inspect source coverage, errors and
pending jobs. A failed source read is not an empty conversation, and indexing
history does not mean that a model has semantically reviewed all of it.

## Expand evidence only as needed

`search` accepts `{name, query, role?, limit?, chars?}` and searches indexed original
text. Use distinct formulations for a conceptual question; this index does not
promise semantic retrieval. `evidence` accepts `{name, ref, offset?, chars?, before?,
after?}`. Use the exact returned references and original quotes in revisions.

The source archive covers persisted user/assistant text; it is not a complete index
of attachments, tool results or current project files. Read relevant current files
with host tools when a conclusion depends on actual state. Do not reread the same
material through a second source reader unless content is missing or needs checking.

## Revise shared understanding

`shared_update` uses the existing partial-revision contract. It accepts the following
fields alongside `name` (also supported inside a `payload` object):

```json
{
  "name": "design-background",
  "operation_id": "revise-one-interpretation",
  "expected_revision": 3,
  "coverage_token": "<CURRENT_COVERAGE_TOKEN>",
  "reason": "The later example limits this judgment to the review stage.",
  "entries": [{
    "key": "review-stage",
    "scope": "design",
    "status": "working",
    "text": "A scoped interpretation, including its conditions and remaining uncertainty.",
    "sources": [{"ref": "<SOURCE_REF>", "quote": "<EXACT_SOURCE_EXCERPT>"}]
  }],
  "remove_keys": []
}
```

Entries are complete replacements for those keys; unrelated keys remain. Scope is
a selected source scope or `shared`; status is `working` or `tentative`, neither
of which implies user endorsement. Reuse the revision and coverage token loaded
this turn if still current. On a conflict, reopen and reconsider relevant changes
before retrying. Keep the same operation ID only for an identical retry.

The older `context-save` operation replaces the whole snapshot. Do not build such
a replacement from a limited search or scope-filtered view and drop omitted entries.

## Keep a chat document and contribute

`chat_update` accepts `{name, operation_id, expected_revision, text, dependencies,
reason?, title?}`. Use the current global Ledger revision returned by `open` or
`documents`, not the chat document's own revision. `dependencies` contains the shared entry keys this interpretation
actually relies on. Keep existing useful continuation and meaningful differences
when replacing the document. Service notices identify affected dependencies; the
chat decides whether to retain, revise or challenge its interpretation.

`propose` accepts `{name, operation_id, expected_revision, text, scope, reason?,
sources?, dependencies?, entries?}`. `sources` uses `{ref, quote}`; `entries` can
carry proposed shared entries. Use this for a contribution awaiting review or for
a different interpretation that should remain attributed rather than overwriting
the shared view. `proposals` lists proposals. `review_proposal` accepts `{name, id,
decision, reason?}` with `decision` equal to `accept` or `reject`. Acceptance also
needs current `operation_id`, `expected_revision`, `coverage_token` and valid
`entries`/`remove_keys` for the resulting shared revision. A proposal's existence
does not make it an adopted conclusion.

Read `inbox` for the resolved actor and process relevant changes. The new runtime
uses contribution IDs rather than a paging cursor: `ack` accepts `{name, id, stage,
evidence?}`, with `stage` equal to `received`, `read`, `replied` or `adopted`.
Replies and adoption need evidence of the actual subsequent work. Acknowledge only
what this chat processed. Delivery and acknowledgments do not prove understanding
or execution. Legacy `dialogue.py` inbox cursors remain a separate contract.

## Inspect, edit and maintain private documents

`documents` accepts `{name, scope?, actor?}` to inspect shared or chat documents.
The private space exposes a common index, shared understanding and separate chat
documents. These are readable views of versioned records, not public skill assets.
Use `import_document` after an external edit so the service can preserve provenance
and reconcile the change. Do not overwrite a detected edit to repair formatting.
Unverified external edits should remain attributed as external, not automatically
as the user's approval. Inspect pending proposals before claiming an edit was adopted.

`settings` reads maintenance choices with `{name}` and changes them with
`{name, updates: {auto_sync?, auto_understand?, model_command?, model_timeout?, model_chars?}}`.
History sync and saved-context retrieval
are separate from generating an interpretation. Automatic understanding requires
an explicitly configured model worker and its enabled setting; a queued job or
successful hook is not proof that understanding was revised. A configured worker
is a background author, not the original source chat. Keep the configured model
and reasoning choices unless the user requests a change.

Use `jobs` to inspect work and `process_jobs` to run work within the existing
maintenance authorization. Do not enable `auto_understand` or set a `model_command`
merely because the user supplied links. Those operations can start model calls.
Routine hooks prepare saved context and queue incremental collection; actual
interpretation can be revised by this host model while doing the current task.

Background model calls release the space lock while waiting for their provider.
A concurrent document revision or source change rejects uncommitted stale output.
Completed responses are saved privately before application; retry after a committed
patch can repair maintenance progress without invoking the provider again. If the
process stops before the response is persisted, an explicit retry may still call
the provider again. This is not exactly-once external model execution.

Partial shared revisions preserve unchanged entries' original evidence versions.
Source-change warnings remain until those entries are explicitly reconsidered;
an unrelated project update does not acknowledge their evidence as reviewed.

`export` accepts `{name, path}` for a new ZIP destination; `import` accepts
`{path, directory}` for a new or empty target. `restore` accepts `{name, revision,
operation_id?}` to restore retained shared understanding. Bundles contain selected
source metadata, original indexed evidence, versioned understanding and allowlisted
document views, including pending external edits. Runtime settings, host bindings,
credential configuration files and worker commands are excluded. Original source
text is preserved as private evidence rather than automatically redacted. A migrated space can use preserved evidence
while original chats are unavailable; fresh source sync still requires access.
Restore recovers shared understanding as a new revision, leaving chat documents
and intervening history in place; import a bundle for full-space recovery. Inspect
the operation's returned source and coverage state before claiming live continuation.

## Alpha.7 compatibility

Existing `dialogue.py context-*`, history and shared-record commands remain valid
for prior workflows. The detailed [continuation contract](../../dialogue-collaborate/references/continuation.md)
documents those calls. Keep old data and revisions when moving into the runtime;
do not rewrite the source conversations or manually rename databases to imitate
a migration. A readable export is not evidence that another tool automatically
resumes synchronization or model work.
