# Dependency and design references

Checked 2026-10-24. This local plugin does not vendor third-party source code.

## Actual dependency

- **Agent State Core**, commit `538a3be386ec778e1682168d4fd418c2d0b51869`,
  [MIT license](https://github.com/zhaosknss/agent-state-core/blob/538a3be386ec778e1682168d4fd418c2d0b51869/LICENSE).
  Uses public `Ledger`, `Record`, `Transition`, and `RecordCursor` APIs from
  `agent_state_core`. This checkout includes Unreleased paging; the old alpha-2
  release archives do not. The base core has no third-party runtime dependencies.
  `--core-path` is a development source override; check the revision separately.
  The single pin is shipped in `plugins/dialogue-bridge/requirements.txt`;
  root requirements only includes it. Bundled setup uses Python venv/pip and Git
  to install it in an explicitly selected private environment. It verifies the
  installed package's Git origin/commit and paging API before reporting success.
  The core source is not vendored into the plugin. Its build requirements come
  from that pinned project's `pyproject.toml`.
- Installed Codex CLI, tested with `0.163.0-alpha.10.2` on Windows. JSONL App Server
  requests: initialization, `thread/read`, `thread/turns/list`. Uses the existing
  application's history access. No Codex source or login credentials are copied.
- CI uses `actions/checkout` at `3d3c42e5aac5ba805825da76410c181273ba90b1`
  and `actions/setup-python` at `5fda3b95a4ea91299a34e894583c3862153e4b97`.
  Their corresponding MIT license files were checked. These run only in CI;
  neither action's implementation is bundled in the plugin.

## References, not integrated dependencies

- [Honcho architecture](https://github.com/plastic-labs/honcho/blob/ce56c3e8e07f33ffcade58809282de102b36ce56/docs/v3/documentation/core-concepts/architecture.mdx),
  commit `ce56c3e8e07f33ffcade58809282de102b36ce56`, root AGPL-3.0 license checked.
  Reference for cross-session understanding, attributed messages and targeted
  retrieval. No Honcho code, service, SDK or prompts are bundled.
- [Hindsight mental models](https://github.com/vectorize-io/hindsight/blob/87a305e646d60d4ff7f57a7aab7a0cc7017c8de3/skills/hindsight-docs/references/developer/api/mental-models.md),
  commit `87a305e646d60d4ff7f57a7aab7a0cc7017c8de3`, root MIT license checked.
  Reference for evidence-backed current understanding, delta updates and full
  reconsideration. Our whole-snapshot revision storage and boundary-turn history
  refresh are newly authored, not a copy of Hindsight's block-operation engine.
- [ECC observer](https://github.com/affaan-m/ECC/blob/6f1881aeafa3c48f7b603cc4be4b2e4e70daad59/skills/continuous-learning-v2/agents/observer.md),
  commit `6f1881aeafa3c48f7b603cc4be4b2e4e70daad59`, root MIT license checked.
  Reference for using corrections/examples with project attribution. We do not
  copy its observer, background Claude invocation, hooks, confidence formula or
  automatic promotion of project patterns to global rules.
- [Maestro group chat](https://github.com/RunMaestro/Maestro/blob/995372b50c784bdf2893e4710c5e9288dae10c17/docs/group-chat.md),
  commit `995372b50c784bdf2893e4710c5e9288dae10c17`, root AGPL-3.0 license checked.
  Reference for persistent participants, routing relevant context, and handling
  busy agents. We do not embed Maestro, reproduce its interface or copy its code.
- [Epistemic Protocols intent record](https://github.com/jongwony/epistemic-protocols/blob/087602112103306a9ec34d247a71b817b0f75bd8/docs/intent-record.md),
  commit `087602112103306a9ec34d247a71b817b0f75bd8`, root MIT license checked.
  Reference for revisable interpretation with provenance and reopening original
  sources. The skill here is newly authored; no upstream workflow file is bundled.
- [October Bus Codex adapter](https://github.com/october-dev/october-bus/blob/21b959a2418a5aee92ff85a605fd134b9ce342a1/adapters/codex/README.md),
  commit `21b959a2418a5aee92ff85a605fd134b9ce342a1`, root Apache-2.0 license checked.
  Reference for pull-based delivery and separating delivery from model readiness.
  Current adapter is experimental. No daemon, SDK or MCP adapter is installed.

The user's iterative corrections motivated the workflow, including separating
exploration from decisions and letting another conversation challenge the
coordinator. Public code contains fictional test messages, not private transcripts.

## Official integration contracts

The understanding document engine, persistent queue, JSON worker adapter, MCP
stdio server, private HTTP page, hooks and portable bundles are newly authored.
They use the Python standard library and the same pinned core dependency above.
No Honcho/Hindsight service or code is integrated by this update.

- [App Server](https://learn.chatgpt.com/docs/app-server): stored-history paging
  differs from resuming a thread or starting a model turn.
- [Plugin packaging](https://developers.openai.com/plugins/build/plugins):
  portable root `plugin.json`, `skills/`, and a repo-local marketplace.
