# A small comparison with a complete handoff

Recorded on 2026-10-21 with alpha.6. All source conversations are fictional.

**Both conditions passed the 12 selected checks. This trial found no
understanding-quality advantage for Dialogue Bridge over a complete handoff.**

The useful question for further trials is whether managing sources, later
corrections and repeated reuse takes less effort in a real workflow.

## What was compared

Two fictional projects cover a reading-progress app, a local writing edit,
separate project audiences and conflicting reports about an export fix.
Each condition receives the same original messages, coordinator-prepared
interpretations and later user corrections:

- **Ordinary handoff:** a deliberately complete Markdown handoff with all original messages.
- **Bridge:** exports from the actual alpha.6 context store, with checked quotes,
  source attribution and changed-source information, plus the same original messages.

The protocol and input hashes were saved before model responses were requested.
There were four fresh Codex CLI responses: one per condition for each phase.
The order was handoff initial, Bridge initial, Bridge update, handoff update.
No response was discarded or rerun. The response subjects used no tools.

## Results

The coordinating model manually reviewed the recorded responses against these
predeclared checks. This was not an independent or blinded assessment.

| Check | Complete handoff | Bridge export |
|---|---|---|
| Discussion does not authorize coding | Preserved | Preserved |
| Science fiction remains an example | Preserved | Preserved |
| Sharing remains undecided initially | Preserved | Preserved |
| Branch exploration is not merged automatically | Preserved | Preserved |
| A local shortening request is not a permanent preference | Preserved | Preserved |
| A patch remains unverified while reproduction fails | Preserved | Preserved |
| The later message authorizes a local prototype | Preserved | Preserved |
| Accounts and sharing remain excluded | Preserved | Preserved |
| Club tags remain a candidate | Preserved | Preserved |
| The accepted workplace article stays unchanged | Preserved | Preserved |
| Work on the engineering guide is discussion only | Preserved | Preserved |
| A passing CSV case does not verify all formats | Preserved | Preserved |

The real context store marked `needs_review: true` after the later source
messages were indexed. Its quote validation and change records were exercised.
The model then explained the updated meaning; it did not save a new understanding
revision or perform either project's work during this response trial.

## Inspect the record

Files in [trials/2026-10-21](trials/2026-10-21/) contain:

- [Protocol](trials/2026-10-21/protocol.json) and [assessment](trials/2026-10-21/assessment.json).
- [Handoff initial input](trials/2026-10-21/handoff-initial.prompt.txt) and [response](trials/2026-10-21/handoff-initial.response.md).
- [Bridge initial input](trials/2026-10-21/bridge-initial.prompt.txt) and [response](trials/2026-10-21/bridge-initial.response.md).
- [Handoff update input](trials/2026-10-21/handoff-update.prompt.txt) and [response](trials/2026-10-21/handoff-update.response.md).
- [Bridge update input](trials/2026-10-21/bridge-update.prompt.txt) and [response](trials/2026-10-21/bridge-update.response.md).
- Per-run receipts and a [capture manifest](trials/2026-10-21/manifest.json).

The CLI was `0.163.0-alpha.10.2`. Runs were ephemeral, used the same CLI defaults,
excluded user configuration and project documents, and had no model override.
The effective server-selected model ID was not captured. Model responses use
normal account inference; this was not a model-free test.

To request another response from a captured prompt in PowerShell:

```powershell
Get-Content -Raw docs/trials/2026-10-21/handoff-initial.prompt.txt |
  codex exec --ephemeral --ignore-user-config -c project_doc_max_bytes=0 --sandbox read-only --skip-git-repo-check -
```

Repeat with the other prompt files under the same configuration. This replays the
response comparison; it does not reproduce the history transport or measure a
complete installation workflow. Review prompts before sending them to a model.

## What this cannot establish

One response per condition and phase cannot establish general reliability.
The coordinator prepared the saved entries; the subjects did not autonomously
extract them or invoke the plugin. History transport used a labeled fictional
adapter rather than live Codex chat access. Native memory, GUI onboarding,
original-chat participation, user correction counts and complete workflow costs
were not compared. Per-run token usage and elapsed time include CLI overhead
and are not evidence of token savings or an end-to-end speed advantage.

A good handoff can work well. Dialogue Bridge offers source lookup, scoped reuse,
revision history and incremental refresh as a workflow to try. Whether that
combination helps enough in daily use remains a question for users and further trials.
