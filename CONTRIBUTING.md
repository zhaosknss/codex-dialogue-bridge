# Trying and improving Dialogue Bridge

Feedback from actual use is especially useful at this early stage. Open an issue
with what you wanted, what happened, and what felt off. A short impression is
enough; a redacted example is helpful if a particular piece of context was missed.

Areas to explore include first-run setup, chat selection, source retrieval,
revising an interpretation, returning discoveries to the original work, and
combining the plugin with other tools.

For code changes, read [AGENTS.md](AGENTS.md) and [UPSTREAM.md](UPSTREAM.md).
Prepare a private environment with the bundled setup script, then run the unit
tests using that environment's Python:

```text
python -B -m unittest discover -s tests -v
```

Use fictional conversations in tests and examples. Keep real archives, records
and credentials outside the repository. Describe what you tested and which host
or Python version you used. Protocol tests and actual model behavior are different
evidence, so say which the change addresses.

General state/record features belong in
[Agent State Core](https://github.com/zhaosknss/agent-state-core); Codex integration
and conversation behavior belong here. New integrations can be proposed without
requiring a particular agent role or discussion sequence.
