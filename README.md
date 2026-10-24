# Dialogue Bridge

**Carry understanding forward. Let each chat keep its own view.**

A Codex plugin for carrying context, corrections, and useful discoveries across
existing conversations. Find the original discussion, reuse what was worked out,
and revise the understanding as your work develops.

You worked through an idea in one chat. Another has already tried an approach.
A new conversation can build on both, with the original examples still available
when a summary needs checking.

[Install](#install-in-codex) · [See the walkthrough](docs/WALKTHROUGH.md) · [Try an example](#try-a-small-example) · [Share feedback](https://github.com/zhaosknss/codex-dialogue-bridge/issues/new/choose)

After installing, open a local Codex chat, select `@Dialogue Bridge`, and paste
the conversations you want it to understand:

```text
@Dialogue Bridge
codex://threads/<FIRST_CHAT_UUID>
codex://threads/<SECOND_CHAT_UUID>

Understand why the direction changed and what matters for this discussion.
```

The final sentence is optional. With links alone, Bridge first understands the
selected background. You can then discuss your next task in ordinary language.

## The problem we focus on

Useful context often lives between conversations: why an idea was rejected,
what a correction actually meant, which approach failed, or which question is
still open. Moving to another chat can mean explaining all of that again.

Dialogue Bridge gives selected, independent chats a way to reuse that context
with its sources, compare interpretations, and bring discoveries back into
their own work. A coordinator's reading can be challenged too. Different
projects can consider one another's findings while keeping their own goals.

| When you want to… | Use Bridge to… |
|---|---|
| Continue a long discussion in a new chat | Recover relevant background, decisions, examples, and unresolved questions |
| Revisit a misunderstanding | Check the original exchange and revise the affected understanding |
| Compare work from different chats | Share findings with their sources and retain different interpretations |
| Reuse a discovery in another project | Find its context and decide how it applies to the new work |

The same workflow can support product discussions, writing, research, project
continuation, and reviews from different perspectives.

**Find original context → compare views → revise understanding → continue the work.**

## Install in Codex

**Current public preview: alpha.7.** Requires a local Codex environment with
plugin marketplace support, Python 3.11+, and Git. First-use dependency setup
needs Internet access.

```text
codex plugin marketplace add zhaosknss/codex-dialogue-bridge --ref v0.1.0-alpha.7
codex plugin add dialogue-bridge@dialogue-bridge
```

Open a new local conversation, type `@`, select Dialogue Bridge, and paste your
`codex://threads/…` links. You can also invoke `$dialogue-collaborate`.

The skill handles the private source index, script paths, and working records.
Its setup helper prepares the pinned dependency in a private environment. You
do not need to write a handoff document, choose internal roles, or prepare JSON.

See the [setup guide](plugins/dialogue-bridge/skills/dialogue-collaborate/references/setup.md)
for first-use details and the [OpenAI plugin guide](https://developers.openai.com/plugins/build/plugins)
for Git-backed marketplaces.

## What you can use today

- **Selected conversation history.** Index stored user/assistant text, search it,
  and open exact passages with neighboring messages.
- **Understanding you can revisit.** Save entries with original quotes, refresh
  their sources, and revise selected entries while preserving earlier versions.
- **Independent contributions.** Keep authors, recipients, sources, and revision
  relationships when chats compare notes or question another interpretation.
- **Continuation.** Reuse saved background in a new reader and track which shared
  contributions each participating chat has processed.
- **Private storage.** Keep archives, sources, and records in a local directory
  separate from the plugin. Copy and register that background on another machine.

The model interprets what matters. The software checks quotes, scope, versions,
and storage. An exact quotation helps you inspect a judgment; later context can
still change that judgment.

## Saved background for a new chat

Give Bridge the source links and, if useful, a focus:

```text
Understand how we reached this design and which alternatives are still open.
```

First use prepares an index of the selected persisted text. Later refreshes read
new turns and recheck the last saved turn. An explicit full refresh can audit
earlier edits. Saved understanding and original passages remain available for
corrections and a different reading of the same discussion.

You can later say:

```text
That interpretation sounds too permanent. Revisit the example and narrow it
to the situation we were discussing.
```

Relevant changes can revise the affected entries while unrelated entries stay
intact. Feedback that exists only in the new reader can join shared evidence
when that conversation is explicitly added as a source.

Reading background leaves the source chats asleep. A new reader can use the
selected material without joining the original group. Bridge keeps its private
records separate from native Codex memory and project instructions; the current
request determines what work to do next.

See the [continuation guide](plugins/dialogue-bridge/skills/dialogue-collaborate/references/continuation.md)
for the source, revision, and CLI contracts.

## How the exchange works

1. Select the existing conversations relevant to the question.
2. Read original examples and corrections, then save a view with its evidence.
3. Let participating chats compare, challenge, or revise their interpretations.
4. Carry useful findings back into each chat's task and inspect what changes.

Contributions can wait in the shared inbox for a chat's next check-in. Immediate
requests to original chats use an available host messaging tool with the user's
authorization. Reading history, storing a contribution, receiving a reply, and
seeing the result used in later work are separate steps.

A different interpretation can remain visible. The workflow does not require
every conversation to agree or turn every correction into a permanent rule.

## Try a small example

From a checkout, prepare a private environment:

```text
git clone https://github.com/zhaosknss/codex-dialogue-bridge.git
cd codex-dialogue-bridge
python plugins/dialogue-bridge/scripts/setup.py --environment ./local-data/bridge-env
```

Setup prints the environment's Python path. On Windows:

```powershell
./local-data/bridge-env/Scripts/python.exe plugins/dialogue-bridge/scripts/demo.py --directory ./local-data/demo
```

On Linux/macOS, the environment interpreter is `./local-data/bridge-env/bin/python`.
The fictional example demonstrates source retrieval, a peer correction, retained
revisions, retry handling, and reading new records. It makes no model calls. Use
a fresh data directory when repeating it.

For a saved-background example, use that Python from the plugin folder:

```text
python scripts/context_demo.py --directory <NEW_PRIVATE_DIRECTORY>
```

Keep actual chat archives and databases outside version control.

## Built on Agent State Core

[Agent State Core](https://github.com/zhaosknss/agent-state-core) provides the
general Python + SQLite layer for versioned state, scoped records, sources, and
history. Dialogue Bridge uses a [fixed core commit](plugins/dialogue-bridge/requirements.txt)
and supplies conversation access, interpretation guidance, and the Codex workflow.

The core can also be combined with other models, memory systems, retrieval,
tools, and orchestrators. Dialogue Bridge is one application of those building
blocks. Suggestions for other combinations are welcome.

## Help shape the next version

Tell us where you had to explain something again, which context was missed, or
whether another conversation's contribution changed your next step. A short
impression or an installation snag is useful feedback; a complete transcript
or a technical diagnosis is unnecessary.

[Share an experience or suggestion](https://github.com/zhaosknss/codex-dialogue-bridge/issues/new/choose).
Include a redacted excerpt and your Codex version if they help explain it.

Work toward the next version includes shared and per-chat understanding
documents, review of affected dependencies, and a local management page.
These additions are being prepared separately from the public alpha.7 preview.

## Development and evidence

After preparing the environment, use its Python to run:

```text
python -B -m unittest discover -s tests -v
```

Tests use fictional data. Existing-chat trials have exercised sourced exchanges
and concrete follow-up checks; the [walkthrough](docs/WALKTHROUGH.md) shows the
workflow. These trials do not establish generally better reasoning or lower
model cost.

In the [published handoff comparison](docs/COMPARISON.md), a complete handoff and
Bridge exports both passed the 12 selected checks. That trial did not show an
understanding-quality advantage. Inputs, responses, and limitations are available
for inspection.

See [contributing](CONTRIBUTING.md), [dependency and design references](UPSTREAM.md),
and the [changelog](CHANGELOG.md). [MIT License](LICENSE).
