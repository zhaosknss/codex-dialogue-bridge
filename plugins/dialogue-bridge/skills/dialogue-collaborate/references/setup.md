# Private dependency setup and a minimal example

Use Python 3.11+ and Git. First-time setup needs Internet access to the pinned
public dependency and its Python build requirements. History-only commands use
stdlib; `start`, records, inboxes and the demo also need Agent State Core.

The plugin bundles `requirements.txt`, `scripts/setup.py` and `scripts/demo.py`.
Resolve these from the installed plugin root, three directories above this file's
containing directory. Do not depend on the author's development checkout.

Prepare a dedicated environment outside the installed cache, in an ignored
project-local data directory. When dependency setup is authorized, run:

```text
python <PLUGIN_ROOT>/scripts/setup.py --environment <PRIVATE_PROJECT_DATA>/bridge-env
```

The JSON result gives the exact environment Python path. Use that interpreter
for subsequent commands; no activation or `--core-path` is needed. Setup verifies
both the pinned Git commit recorded in package metadata and the paging API.
Repeating setup reuses a matching environment; failures are reported without
falling back to global Python. Leave unrelated existing directories alone.

Run the deterministic example in a new private directory:

```text
<ENV_PYTHON> <PLUGIN_ROOT>/scripts/demo.py --directory <PRIVATE_PROJECT_DATA>/bridge-demo
```

It creates fictional planner/reviewer text, finds the user's original statement,
stores a response and a revision, retains the old interpretation, retries the same
contribution and reads only the delta from a saved position. All six checks should
be true; `result.json` and the databases remain available for inspection. It never
reads a real chat or calls a model. The dialogue and its correction are scripted,
so this does not test AI judgment or a host's original-chat messaging ability.

For actual use, use a different private directory and the same interpreter:

```text
<ENV_PYTHON> <PLUGIN_ROOT>/scripts/dialogue.py --workspace <PRIVATE_SHARED_DATA> start --project <PROJECT_NAME> --thread codex://threads/<SELECTED_PEER_UUID>
```

Run real-chat `start` from Codex so `CODEX_THREAD_ID` names the current author.
Later invocations reuse that selected workspace. All original participants need
the same shared-data path and a compatible runtime, each keeping their own cursor.
Read-only history access never authorizes sending a message to another chat.
