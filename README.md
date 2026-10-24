# Dialogue Bridge

**Carry understanding forward. Let each chat keep its own view.**

A Codex plugin for carrying context, corrections, and useful discoveries across
existing conversations. Find the original discussion, reuse what was worked out,
and revise the understanding as your work develops.

One chat remembers why the direction changed. Another has already tried an
approach. Bridge connects that background through shared understanding, each
chat's own working document, and original sources you can revisit.

[Install](#install-in-codex) · [How understanding works](docs/UNDERSTANDING.md) · [Try the walkthrough](#try-the-fictional-walkthrough) · [Share feedback](https://github.com/zhaosknss/codex-dialogue-bridge/issues/new/choose)

## Use it in ordinary conversation

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

To keep selected chats connected as their work develops:

```text
Keep these chats connected. Let each maintain its own interpretation and bring
useful findings back to its own work.
```

| When you want to… | Use Bridge to… |
|---|---|
| Continue a long discussion | Recover relevant context, decisions, corrections, and unresolved questions |
| Revisit a misunderstanding | Read original examples and revise the affected understanding |
| Compare work from different chats | Exchange sourced views while retaining different interpretations |
| Reuse a discovery in another project | Consider its context while keeping the project's own goal |

You do not need to write a handoff document, fill in roles, or prepare JSON.
Opening background as a reader keeps future source enrollment a separate choice.

## What stays connected

The shared understanding records goals, formative examples, corrections, scoped
judgments and unresolved differences. Each chat's document records its own work,
the shared entries it uses, its interpretation and what should happen next.
The index joins these documents to their sources and dependency versions.

When a shared entry changes, dependent chat documents are marked for review.
An unrelated entry changing does not require every chat to rewrite its view.
A chat can challenge the coordinator or retain a different interpretation.

Understanding grows from actual examples and results. A newer message may correct
an error, change a goal or describe a different situation; it does not automatically
win because it is newer. Multiple AIs repeating one summary do not create multiple
independent sources. Original text remains available when a summary needs checking.

You can ask:

```text
That sounds too permanent. Revisit the examples and narrow the interpretation.
```

Corrections can become attributed proposals before they change shared entries.
Edits to local documents are preserved for review rather than silently overwritten.
Version checks protect concurrent work, and earlier interpretations remain available.

## Collection, interpretation and actual participation

The first collection indexes selected persisted user/assistant text. Later
collections read new turns and recheck the previous boundary; a full refresh can
audit earlier edits. Coverage and errors remain visible. Search opens exact
source passages and neighboring messages; the current index uses literal matching.
The model chooses relevant formulations and interprets what it retrieves.

By default, the model in the active Codex chat forms and revises understanding
through the common skill. Hooks prepare saved context and queue incremental
collection. A running local service processes eligible collection jobs. There is
no default background model silently generating new interpretations.

Optional background interpretation requires an explicitly configured and enabled
`model_command`. It is an executable argument list: the worker receives a prompt
and evidence packet on stdin and returns a JSON object with `reason`, `entries`
and `remove_keys` on stdout. It uses the configured account or local compute.
Model and reasoning choices stay with the current host unless you request a change.
The [runtime reference](plugins/dialogue-bridge/skills/dialogue-understand/references/runtime.md)
describes the provider and action contracts.

Stored history analysis and replies from the original chats are distinct. Pending
contributions can be collected when a chat next checks in. Immediate requests need
an available host messaging channel and the user's authorization. A background
worker is identified as its actual author, never as an absent original chat.
Delivery, reading, reported adoption and verified subsequent work remain separate.

## Install in Codex

Requires a local Codex environment with plugin marketplace support, Python 3.11+
and Git. Dependency setup needs Internet access the first time.

Install the current early release:

```text
codex plugin marketplace add zhaosknss/codex-dialogue-bridge --ref v0.2.0-alpha.1
codex plugin add dialogue-bridge@dialogue-bridge
```

For a local source checkout, use `codex plugin marketplace add .` from its root
before the same plugin-add command.

Then open a new local chat and select `@Dialogue Bridge`. First-use guidance can
prepare the pinned dependency in an explicit private environment. You can also
invoke `$dialogue-collaborate` for source links or `$dialogue-understand` for an
already connected space.

To prepare a checkout environment yourself:

```text
python plugins/dialogue-bridge/scripts/setup.py --environment ./local-data/bridge-env
```

Setup prints the environment's Python path. On Windows it is normally
`./local-data/bridge-env/Scripts/python.exe`; on Linux/macOS,
`./local-data/bridge-env/bin/python`. Keep the environment and understanding data
outside the installed plugin cache so updates do not replace them.

Existing alpha.7 backgrounds stay in their private directories. The earlier
`dialogue.py context-*`, history, and note commands remain available; see the
[legacy continuation guide](plugins/dialogue-bridge/skills/dialogue-collaborate/references/continuation.md).

## Open the private management page

From the checkout, use the prepared environment's Python. For example, on Windows:

```powershell
./local-data/bridge-env/Scripts/python.exe plugins/dialogue-bridge/scripts/bridge_service.py serve
```

Open the printed local URL in your browser. The page provides an overview,
understanding and activity views for sources, shared and chat documents,
proposals, processing settings, jobs and migration. The URL includes a private
access token; the server listens on loopback by default. Stop it with Ctrl+C.
Use `--no-worker` when you want the page without processing queued work.

The same runtime is exposed through `bridge_*` MCP tools and a file-based CLI.
Skills handle these calls during normal conversation; users do not need to learn
the internal action envelopes.

The bundled lifecycle hooks target manually installed Codex desktop plugins.
Codex asks you to review and trust their current definition before running them;
the Skill and MCP tools can still be used without trusted hooks. The current
hook-bearing package is for manual distribution. A future public-directory
submission needs packaging that meets that directory's hook policy.
[OpenAI packaging guidance](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks)

Export keeps versioned understanding, indexed original evidence and allowlisted
document views, including pending external edits. It excludes runtime settings,
host bindings, worker commands and credential configuration files. Original source
text stays intact in the private bundle. Import verifies its manifest, hashes,
sizes, paths and databases before installing into a new or empty directory.
Unavailable original chats leave frozen evidence readable; fresh collection still
requires access to those chats. Restoring an earlier interpretation creates a new
revision and preserves the intervening history.

## Try the fictional walkthrough

With the prepared environment, run:

```powershell
./local-data/bridge-env/Scripts/python.exe plugins/dialogue-bridge/scripts/understanding_demo.py
```

The walkthrough uses two fictional histories and a separate reader. It saves
shared and independent chat interpretations, collects a later correction, reviews
a proposal, marks dependent documents, updates one chat and exports/imports a
bundle before restoring an earlier interpretation. All data lives in an isolated
temporary directory that is removed afterward. It makes no model calls, reads no
real chats and sends no messages.

This demonstrates the storage and continuation workflow. It does not measure
understanding quality, fewer corrections, better writing or token savings.

## Development and evidence

Dialogue Bridge uses a [pinned Agent State Core](plugins/dialogue-bridge/requirements.txt)
for versioned state and records. The core stays independent of conversation policy;
the understanding package and Codex adapters live in this plugin.

After preparing the environment:

```text
python -B -m unittest discover -s tests -v
```

Tests and demos use fictional data. The prior
[information-matched response comparison](docs/COMPARISON.md) documents an earlier
saved-background workflow and its limits; the current runtime is checked
separately for storage and continuation behavior. Real connected use and matched comparisons are still needed to assess
interpretation quality and how much coordination work this saves.

Feedback can be simple: what you wanted, what happened, and which explanation or
correction you had to repeat. See [contributing](CONTRIBUTING.md),
[dependency and design references](UPSTREAM.md) and the [changelog](CHANGELOG.md).
MIT License.
