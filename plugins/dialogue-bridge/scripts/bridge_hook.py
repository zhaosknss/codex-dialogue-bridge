"""Fail-open Codex hooks, using the registered private runtime when available.

Bundled hooks require the user's manual trust in Codex desktop. Plugins carrying
hooks are not eligible for the public plugin directory; use manual/local setup.
"""
from __future__ import annotations

import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

PLUGIN = Path(__file__).resolve().parents[1]


def select_runtime(*, actor=None, name=None, directory=None, environ=None):
    """Read configuration only; never create a registry or scan chat archives."""
    env = os.environ if environ is None else environ
    explicit = env.get("DIALOGUE_BRIDGE_PYTHON")
    if explicit:
        candidate = Path(explicit).expanduser()
        return str(candidate.absolute()) if candidate.is_file() else None
    home = Path(env.get("DIALOGUE_BRIDGE_HOME") or Path(env.get("CODEX_HOME", Path.home() / ".codex")) / "dialogue-bridge")
    registry = home / "registry.db"
    if not registry.is_file():
        return None
    try:
        with closing(sqlite3.connect(registry.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.3)) as db:
            if actor:
                rows = db.execute("SELECT c.runtime_python FROM contexts c JOIN bindings b ON b.name=c.name WHERE b.thread_id=?", (actor,)).fetchall()
            elif name:
                rows = db.execute("SELECT runtime_python FROM contexts WHERE name=?", (name,)).fetchall()
            elif directory:
                rows = db.execute("SELECT runtime_python FROM contexts WHERE directory=?", (str(Path(directory).resolve()),)).fetchall()
            else:
                rows = db.execute("SELECT runtime_python FROM contexts ORDER BY name").fetchall()
        for row in rows:
            if row[0] and Path(row[0]).is_file():
                return str(Path(row[0]).absolute())
    except (OSError, sqlite3.Error, ValueError):
        pass
    return None


def main(input_stream=None, output_stream=None):
    if str(PLUGIN) not in sys.path:
        sys.path.insert(0, str(PLUGIN))
    source, sink = input_stream or sys.stdin, output_stream or sys.stdout
    try:
        raw = source.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            return 0
        payload = json.loads(raw)
        from dialogue_bridge.service import actor_id, hook_result
        if not isinstance(payload, dict):
            return 0
        actor = actor_id(payload.get("session_id") or os.environ.get("CODEX_THREAD_ID"))
        if os.environ.get("CODEX_THREAD_ID") and actor_id(os.environ["CODEX_THREAD_ID"]) != actor:
            return 0
        runtime = select_runtime(actor=actor) or sys.executable
        # Bound all runtime work, including database lock contention, even when
        # this interpreter already is the configured private environment.
        if not os.environ.get("DIALOGUE_BRIDGE_HOOK_RELAUNCHED"):
            env = dict(os.environ, DIALOGUE_BRIDGE_HOOK_RELAUNCHED="1")
            result = subprocess.run([runtime, "-B", str(Path(__file__).resolve())], input=raw, text=True,
                                    encoding="utf-8", capture_output=True, timeout=3, env=env)
            if result.returncode == 0 and result.stdout:
                # Only the expected bounded JSON contract is forwarded to Codex.
                output = json.loads(result.stdout)
                if isinstance(output, dict) and "hookSpecificOutput" in output and len(result.stdout) <= 12000:
                    sink.write(json.dumps(output, ensure_ascii=False) + "\n")
            return 0
        result = hook_result(payload)
        if result:
            sink.write(json.dumps(result, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
