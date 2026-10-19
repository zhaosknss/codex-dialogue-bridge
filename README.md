# Dialogue Bridge

**Your chats know different things. Help them compare notes.**

A Codex plugin for existing conversations to exchange evidence, correct their
understanding, and carry useful discoveries back into their own work.

[中文说明](README.zh-CN.md) · [Install](#install-in-codex) · [Try an example](#try-a-small-example) · [Share feedback](https://github.com/zhaosknss/codex-dialogue-bridge/issues/new/choose)

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
codex plugin marketplace add zhaosknss/codex-dialogue-bridge --ref v0.1.0-alpha.5
codex plugin add dialogue-bridge@dialogue-bridge
```

Open a new conversation and ask, for example:

> Use Dialogue Bridge to revisit these existing chats, compare what they currently
> understand, and identify what each should do next: <chat links>.

You can also explicitly invoke `$dialogue-collaborate`. The skill handles the
private data directory, script paths and record format. Its bundled setup helper
can prepare the pinned dependency in a private environment.

The [OpenAI plugin guide](https://developers.openai.com/plugins/build/plugins)
describes Git-backed marketplaces. This repository is the installation source.

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

The tests use fictional data. Local trials cover original-chat exchange and
installed scripts; comparative improvements in understanding, feedback count and
total token cost are still questions we want real use to help answer.

See [contributing](CONTRIBUTING.md), [dependency and design references](UPSTREAM.md)
and the [changelog](CHANGELOG.md). MIT License.
