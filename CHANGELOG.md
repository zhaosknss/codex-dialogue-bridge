# Changelog

## 0.1.0-alpha.6 — 2026-10-20

- Mention the plugin with chat links to default to understanding their background.
  Exact source-set lookup reuses saved context without asking for a group name.
- Saved background groups separate source chats from new readers and retain
  relevant project-scoped entries.
- Sourced working understanding has revision checks, retained history, visible
  source changes, a portable readable document and protection for human edits.
- Initial complete text indexing followed by new-turn refresh with the previous
  boundary rechecked; missing boundaries fall back to full scans. Earlier edits
  can be audited with an explicit full refresh.
- One existing skill routes between background continuation and original-chat
  exchange. No new service or model SDK dependency; the core pin is unchanged.
- Refresh and open saved understanding with one operation, including a bounded
  source-change page when review is needed. An unprepared group starts with a full
  index and overview; an existing group reuses current entries without resampling.
- Retrieval help exposes actual limits; project files are located through entry
  documents and file search. Ambiguous changes remain provisional until grounded
  in the user's purpose. Background loading does not alter source conversations.
- Fictional saved-background example. Model judgment is still supplied by the host;
  these checks do not establish fewer corrections or better writing.

## 0.1.0-alpha.5 — 2026-10-20

First public preview of Dialogue Bridge.

- GitHub-backed Codex marketplace and an installable local-execution plugin.
- Selected stored-history indexing, literal search, original excerpts and context.
- Scoped contributions with checked message/note citations and retained revisions.
- Idempotent submissions, explicit unknown-field errors and custom JSON metadata.
- Shared inbox pagination, saved positions and a combined start entry.
- Private environment setup with a pinned Agent State Core commit and a fictional
  executable example.
- English/Chinese introduction, feedback forms and links to the separate core.

The preview is intended for hands-on feedback on setup, context quality and the
exchange between existing chats. Smoother onboarding, chat selection and built-in
wake-up are ongoing areas of work.
