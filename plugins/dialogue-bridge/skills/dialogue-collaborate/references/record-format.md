# Collaboration record

Use a UTF-8 JSON file, not text interpolated into a shell command:

```json
{
  "operation_id": "a-stable-unique-id-for-this-contribution",
  "kind": "understanding",
  "key": "current-goal",
  "text": "My current interpretation, and what the source changes.",
  "scope": "This project's present discussion; not a permanent preference.",
  "recipients": ["selected-recipient-thread-uuid"],
  "sources": [{"ref": "thread-id/turn-id/item-id", "quote": "Exact source text"}],
  "supersedes": null,
  "relates_to": null
}
```

- `kind`: `request`, `response`, `understanding`, `correction`, `adoption`, or
  `withdrawal`. All interpretations remain candidates; the core does not certify
  agreement. Requests may omit sources; other kinds require verified source quotes.
- A source without `kind` (or with `kind: "message"`) refers to indexed original
  chat text. A source with `kind: "note"` refers directly to a visible contribution:
  `{"kind": "note", "ref": "3:0", "quote": "Exact text from that note"}`.
  This lets a conversation cite a newly received contribution without reindexing
  the peer's chat. The CLI checks visibility and the quote, then preserves its
  author, revision, kind, candidate/withdrawn status and body hash. These values
  describe an immutable record, not whether its claims are currently correct.
- `key` groups the author's interpretations within this project. `supersedes`
  references the author's previous record with that key; withdrawal requires it.
  Other authors' views can be challenged without deleting them.
- `relates_to` points to a visible question, response or disputed record.
- `operation_id` stays the same when retrying exactly the same file. Changed
  content with that ID is rejected. A new contribution gets a new ID.
- Recipients must be selected in the same workspace. The author is included
  automatically. Superseding a record does not retroactively change its audience;
  include relevant earlier recipients when sending them a correction.
- Optional `metadata` preserves application-specific JSON, such as a list of
  evidence files, hashes or checks. It is retained without interpreting it as
  proof of execution or verified facts. Unknown top-level fields are rejected
  with their names; put custom data inside `metadata` instead of adding fields
  the caller might mistakenly assume were saved. Old records with previously
  ignored fields cannot recover those values automatically.
- `CODEX_THREAD_ID` supplies a local author label, not cryptographic identity.
  All processes with access to the local databases remain trusted host processes.

`inbox` returns short previews and an opaque `next_cursor`. Use `note --id` for
the complete record and its sources. Pass a saved cursor on the next `inbox`
call, using the same workspace and participant. Finish all pages before switching
to newly committed updates. The cursor is a read position, not an acknowledgment
that a request was performed.
