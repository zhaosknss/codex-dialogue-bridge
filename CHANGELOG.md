# Changelog

## 0.2.0-alpha.1 — Unreleased

- Shared understanding, independent chat documents and a unified private index,
  with per-entry dependencies that identify affected interpretations for review.
- The common `dialogue-understand` skill joins relevant shared context, each chat's
  own view and original examples while preserving scope, disagreement and revisions.
- One runtime backs `bridge_*` MCP tools, lifecycle hooks, the local management
  page and file-based actions. Reader binding remains separate from source enrollment.
- Persistent incremental collection jobs, saved maintenance settings and recovery
  states. The active host model supplies interpretation by default; optional
  background JSON workers require explicit configuration and opt-in.
- Attributed shared proposals and preserved external document edits, with source
  checks, revision checks and explicit review before adoption into shared entries.
- Portable frozen bundles with SQLite snapshots, source evidence, document views,
  integrity manifests and bounded, validated import into a new or empty directory.
  Runtime settings, host bindings and worker commands are excluded. Restoring a
  retained interpretation creates a new revision rather than erasing later history.
- A fictional, model-free runtime walkthrough in an isolated temporary space.
  Alpha.7 history, saved-background and note commands remain supported.

This version has not been published. Runtime protocol checks do not establish
better understanding, actual replies from absent chats or verified later adoption.

## 0.1.0-alpha.7 — 2026-10-22

- Opt-in `--compact` CLI output reduces repeated index metadata and formatting;
  original excerpts, coverage gaps, source warnings and continuation controls stay
  available. Full diagnostic output remains the default.
- `context-revise` updates selected understanding entries or removes explicit keys
  while retaining unrelated entries. It uses the existing quote, scope, revision
  and human-document checks and preserves historical snapshots and retry safety.
- Continuation guidance reuses already opened results, avoids an unrelated group
  listing after an empty exact match, and completes requested private revisions
  with explicit source attribution. It does not enroll readers automatically.

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
