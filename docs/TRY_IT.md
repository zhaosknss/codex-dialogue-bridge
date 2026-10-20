# Try Dialogue Bridge and tell us what carried over

Dialogue Bridge is an open-source Codex plugin for carrying useful understanding
between selected conversations. A direction may have changed, an example may
have been mistaken for a restriction, or an important correction may be buried
in another chat.

Start a new local chat, select `@Dialogue Bridge`, and paste the source chat links.
It first understands that background; you can then discuss the new task normally.
Saved understanding has source quotes and can be revised later. Separate branch
ideas stay separate until you choose what to bring back.

[Walk through an example](WALKTHROUGH.md) · [Inspect the comparison](COMPARISON.md)

```text
codex plugin marketplace add zhaosknss/codex-dialogue-bridge --ref v0.1.0-alpha.6
codex plugin add dialogue-bridge@dialogue-bridge
```

Needs local Codex, Python 3.11+ and Git. First setup uses the network.

We ran a small response comparison against a complete ordinary handoff. Both
conditions preserved the 12 selected boundaries. It did not demonstrate a
quality advantage. We would like to learn whether the source, refresh and
revision workflow is useful in real work, and where a simpler handoff is enough.

Useful feedback can be brief:

- What were you trying to carry into the next chat?
- What carried over, and what did you have to explain again?
- Did setup or refreshing the background feel awkward?

[Share a rough impression or a problem](https://github.com/zhaosknss/codex-dialogue-bridge/issues/new/choose).
Please leave private transcripts, credentials and personal information out of
public reports. A redacted example is enough when you want to include one.
