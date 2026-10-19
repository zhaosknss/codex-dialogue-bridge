# Working on Dialogue Bridge

Read README.md and UPSTREAM.md. This is an early Codex plugin layered
above the generic agent-state-core; keep conversation policies out of the core.

Use fictional transcripts in committed tests. Keep actual chat archives,
locators, records and credentials in ignored per-project data directories.
Read-only access to a chat does not authorize messaging, resuming or editing it.

Distinguish central history analysis, actual replies from original conversations,
and adoption verified in subsequent work. Do not claim one from another's test.
Do not disguise a replacement subagent or a fresh consult session as the original
conversation. Retrieval coverage and interpretation quality are separate.

Use project-scoped data and explicit recipients. Preserve source quotes and old
interpretations. Shared records do not become authoritative user preferences or
instructions automatically. Respect later feedback without treating every new
idea as a confirmed change of direction.

Use Python 3.11+; base scripts use stdlib. For record tests, install the pinned
core or set AGENT_STATE_CORE_PATH. Run `python -B -m unittest discover -s tests -v`.
Do not start model turns, install plugins globally or publish as part of tests.
