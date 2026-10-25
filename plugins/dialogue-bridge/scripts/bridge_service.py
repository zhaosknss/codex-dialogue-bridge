"""Dialogue Bridge MCP, loopback management page, and file-based action entry."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dialogue_bridge.service import BridgeService, MAX_MESSAGE, MCPServer, QueueWorker, create_http_server, environment_actor
from bridge_hook import select_runtime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    mcp = commands.add_parser("mcp", help="Serve newline-delimited MCP on stdin/stdout")
    mcp.add_argument("--no-worker", action="store_true")
    serve = commands.add_parser("serve", help="Open the printed private loopback management URL")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--no-worker", action="store_true")
    action = commands.add_parser("action", help="Run one runtime action from a UTF-8 JSON argument file")
    action.add_argument("action")
    action.add_argument("--input", required=True)
    action_stdin = commands.add_parser("action-stdin", help="Internal bounded JSON-stdin action adapter for an already-running service")
    action_stdin.add_argument("action")
    args = parser.parse_args(argv)
    parameters = {}
    if args.command in {"action", "action-stdin"}:
        if args.command == "action":
            raw = Path(args.input).read_text(encoding="utf-8-sig")
        else:
            raw = sys.stdin.read(MAX_MESSAGE + 1)
            if len(raw) > MAX_MESSAGE:
                raise ValueError("Action input exceeds the size limit")
        parameters = json.loads(raw)
        if not isinstance(parameters, dict):
            raise ValueError("Action input must be an object")
    actor = environment_actor()
    runtime = select_runtime(actor=actor, name=parameters.get("name"), directory=parameters.get("directory")) or select_runtime()
    if runtime and Path(runtime).absolute() != Path(sys.executable).absolute() and not os.environ.get("DIALOGUE_BRIDGE_SERVICE_RELAUNCHED"):
        env = dict(os.environ, DIALOGUE_BRIDGE_SERVICE_RELAUNCHED="1")
        command = [runtime, "-B", str(Path(__file__).resolve()), *(argv if argv is not None else sys.argv[1:])]
        if args.command == "action-stdin":
            return subprocess.run(command, input=raw, text=True, encoding="utf-8", env=env).returncode
        return subprocess.call(command, env=env)
    if args.command in {"action", "action-stdin"}:
        print(json.dumps(BridgeService(actor=actor).call(args.action, parameters), ensure_ascii=False))
        return 0
    worker = None if args.no_worker else QueueWorker().start()
    try:
        if args.command == "mcp":
            MCPServer(BridgeService(actor=actor)).run()
        else:
            server = create_http_server(args.host, args.port)
            print(server.management_url, flush=True)
            try:
                server.serve_forever(poll_interval=0.25)
            finally:
                server.server_close()
    finally:
        if worker:
            worker.stop()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
