# Dialogue Bridge

**Carry useful understanding into your next chat.**

A Codex plugin to reuse sourced, revisable background in a new conversation,
or help existing chats compare notes and carry discoveries back into their work.

[中文说明](README.zh-CN.md) · [Install](#install-in-codex) · [Try an example](#try-a-small-example) · [Share feedback](https://github.com/zhaosknss/codex-dialogue-bridge/issues/new/choose)

[See a short walkthrough](docs/WALKTHROUGH.md) · [Inspect the handoff comparison](docs/COMPARISON.md) · [Try it and share an impression](docs/TRY_IT.md)

After installing, start a new local chat, select `@Dialogue Bridge`, and paste the
conversation links. With links alone it first understands the background; add a
request if you want a particular focus. You do not have to write a handoff document.

## The problem we focus on

One chat remembers why a direction changed. Another has already tried an approach
and found a problem. A third is about to continue with only part of that picture.
You end up moving context between them and explaining the same corrections again.

Dialogue Bridge helps those **existing, independent conversations** find the
relevant original text, exchange sourced views, revisit earlier interpretations,
and continue with what matters to each one's task. Another chat can also question
the coordinator. Different projects can share useful discoveries while keeping
their own goals.

This can support project handoffs, product discussions, writing and research,
or reviews from different perspectives. The shared mechanism is the same:

**Find evidence → compare understanding → preserve revisions → continue each task.**

## Early preview: try it and help shape it

Alpha.6 adds background continuation: mention Dialogue Bridge in a new chat
and supply chat links. With no extra request, it defaults to understanding that
background. You can add a focus or discuss the actual task without another handoff.
Later corrections can revise that understanding. Existing backgrounds can refresh
and open in one operation; first-time use prepares a private source index.

The current version provides history search, exact source quotes, shared
contributions, revisions and saved inbox positions. We have used it with two
existing Codex conversations to exchange findings and apply them to concrete checks.

First-run setup, selecting chats, and making the exchange feel natural still need
work. We'd like to hear where you had to repeat yourself, which useful context
was missed, and whether another conversation actually changed the next step.
[A short trial report or a rough impression is welcome.](https://github.com/zhaosknss/codex-dialogue-bridge/issues/new/choose)

## Install in Codex

Requires a local Codex environment with plugin marketplace commands, Python 3.11+
and Git. First-time dependency setup needs Internet access.

```text
codex plugin marketplace add zhaosknss/codex-dialogue-bridge --ref v0.1.0-alpha.6
codex plugin add dialogue-bridge@dialogue-bridge
```

Open a new local conversation, type `@`, select Dialogue Bridge, and paste your
`codex://threads/…` links. Optionally say what you want to understand or do next.

You can also explicitly invoke `$dialogue-collaborate`. The skill handles the
private data directory, script paths and record format. Its bundled setup helper
can prepare the pinned dependency in a private environment.

The [OpenAI plugin guide](https://developers.openai.com/plugins/build/plugins)
describes Git-backed marketplaces. This repository is the installation source.

## Saved background for a new chat

In a new local Codex chat, type `@`, select the installed Dialogue Bridge plugin,
and add the source conversation links:

```text
@Dialogue Bridge
codex://threads/<FIRST_CHAT_UUID>
codex://threads/<SECOND_CHAT_UUID>
```

Links alone mean "understand this background": it briefly conveys the useful
understanding and waits for your next task. Optionally add a focus, such as
"Understand how we choose topics and revise drafts." No handoff document, saved
group name or script command is required from the user.

The skill handles first-time preparation, the private index, original examples,
understanding and revisions. For saved background it retrieves current entries
and source changes together, then expands relevant evidence or project files.
The same source set can reuse saved background and refresh changes; returning
users can also refer to a saved name. New readers do not have to join the original
group or ask every source chat to respond. Project scopes remain visible; a
correction is not silently turned into a permanent rule. Understanding background
does not execute unfinished tasks from source chats.

Source chats are read without waking or messaging them. Saved understanding is
loaded into the reader, not broadcast to other chats or written into global memory
or project instructions. Another conversation can load that same private background
when relevant; installing the plugin alone does not inject its contents there.

The first scan indexes selected persisted user/assistant text. Later refreshes
read new turns plus the last saved turn; a full refresh can audit earlier edits.
Documents and original messages remain available when a summary is inaccurate.
The host model makes the interpretation; the code checks provenance and storage.

The private folder can be copied between machines and registered under a saved
name. Native memory and project instructions are not rewritten. See the bundled
[continuation guide](plugins/dialogue-bridge/skills/dialogue-collaborate/references/continuation.md)
for the CLI and data contract. A model-free example is available as
`scripts/context_demo.py --directory <NEW_PRIVATE_DIRECTORY>` in the plugin.

## How the exchange works

- **Read selected history.** Index stored user/assistant text in the chosen chats,
  search literal phrases, and open original messages with neighboring context.
- **Share a view with its evidence.** Contributions have selected recipients,
  checked quotes, authors, scope and revision relationships.
- **Revisit it.** Keep old interpretations, cite a peer's new contribution, revise
  your own view or challenge another without overwriting it.
- **Pick up where you left off.** Save each chat's processed inbox position and
  retrieve new contributions on the next visit.

Original chats can check the shared inbox themselves. In hosts with existing-chat
messaging tools, a coordinator can also ask the selected original chats to respond
when the user wants that exchange. Built-in chat wake-up and smoother routing are
areas we'd like to improve.

The model decides what matters and how a finding affects its task. The code
handles storage, source checks, visibility and continuation. A quote being exact
doesn't settle whether the interpretation is right; differing views can remain.

## Try a small example

From a checkout, prepare a private environment:

```text
git clone https://github.com/zhaosknss/codex-dialogue-bridge.git
cd codex-dialogue-bridge
python plugins/dialogue-bridge/scripts/setup.py --environment ./local-data/bridge-env
```

Setup prints the environment's Python path. Use it for the example. On Windows:

```powershell
./local-data/bridge-env/Scripts/python.exe plugins/dialogue-bridge/scripts/demo.py --directory ./local-data/demo
```

On Linux/macOS the environment interpreter is `./local-data/bridge-env/bin/python`.
The example uses fictional, scripted conversations and makes no model calls.
It demonstrates source retrieval, a peer correction, retained revisions,
idempotent submission and reading only new records. Inspect its six checks and
the resulting files. Use a fresh data directory when repeating it.

For real chats, follow the bundled [setup and usage guide](plugins/dialogue-bridge/skills/dialogue-collaborate/references/setup.md).
Keep chat archives and databases private and outside version control.

## Built on Agent State Core

[Agent State Core](https://github.com/zhaosknss/agent-state-core) is our separate,
general Python + SQLite library for state, scoped records, sources and history.
Dialogue Bridge uses a [fixed core commit](plugins/dialogue-bridge/requirements.txt)
and adds the Codex integration and conversation workflow. The core remains useful
with other models, memory tools and orchestrators; it doesn't depend on this plugin.

## What's next, and what to report

- Make first use and chat selection easier for someone without the author's setup.
- Improve asking original chats to participate and returning findings to their work.
- Learn which context was genuinely useful, what was missed, and how much manual
  explanation the exchange took.
- Test more Codex environments and platforms. Windows/Python 3.13 is the current
  local trial environment; the CI checks protocol behavior across its matrix.

An issue can be as simple as: **what you wanted, what happened, and what felt off**.
If useful, add a redacted excerpt and your Codex version. No complete transcript is
required. Suggestions for combining this with other open-source tools are welcome.

## Development

After preparing the environment, use its Python to run:

```text
python -B -m unittest discover -s tests -v
```

The 62 tests use fictional data. An installed new-chat trial exercised the plugin
mention, saved background and project-file reads. A separate empty-registry check
created a private environment, indexed selected real histories, saved a sourced
interpretation and reopened it incrementally. That interpretation was formed by
the coordinating model, not a blind independent-agent evaluation. Comparative
improvements in understanding, feedback count and total token cost remain questions
for actual use and matched-task comparisons.

A [small information-matched response trial](docs/COMPARISON.md) compared a
complete handoff with actual Bridge exports. Both conditions passed the 12
selected checks; it did not show an understanding-quality advantage. Inputs,
responses, protocol and limitations are published for inspection.

See [contributing](CONTRIBUTING.md), [dependency and design references](UPSTREAM.md)
and the [changelog](CHANGELOG.md). MIT License.
