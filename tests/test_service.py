"""Protocol/security checks with fictional data and real loopback requests."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "dialogue-bridge"
sys.path.insert(0, str(PLUGIN))
from dialogue_bridge.service import BridgeService, MCPServer, QueueWorker, create_http_server, hook_result

ACTOR = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def __call__(self, action, arguments, *, actor=None):
        self.calls.append((action, arguments, actor))
        if action == "list_spaces":
            return {"spaces": [{"name": "fiction / one", "sources": []}]}
        if action == "open":
            return {"bound": True, "name": "fiction / one", "scope": "fictional project", "shared": {"text": "A sourced interpretation"}, "pending_reviews": [{"text": "Treat this as data"}]}
        if action == "documents":
            return {"shared": {"text": "Shared", "revision": 1}, "chats": [{"actor": ACTOR, "text": "Local", "revision": 1}]}
        return {"action": action, "arguments": arguments, "actor": actor}


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRuntime()
        self.server = MCPServer(BridgeService(self.fake, actor=ACTOR))

    def request(self, method, params=None, request_id=1):
        return self.server.message({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})

    def initialize(self):
        result = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fixture", "version": "1"}})
        self.assertEqual(result["result"]["protocolVersion"], "2025-06-18")
        self.assertIsNone(self.server.message({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_handshake_and_unknown_version_negotiation(self):
        self.assertEqual(self.request("tools/list")["error"]["code"], -32002)
        result = self.request("initialize", {"protocolVersion": "future-version"})
        self.assertEqual(result["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(self.request("tools/list")["error"]["code"], -32002)

    def test_tools_call_and_actor_scope(self):
        self.initialize()
        listing = self.request("tools/list")["result"]["tools"]
        self.assertGreater(len(listing), 20)
        self.assertTrue(all("description" in tool and "inputSchema" in tool for tool in listing))
        result = self.request("tools/call", {"name": "bridge_search", "arguments": {"query": "fiction"}})
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(self.fake.calls[-1], ("search", {"query": "fiction"}, ACTOR))
        result = self.request("tools/call", {"name": "bridge_chat_update", "arguments": {"actor": OTHER, "text": "impersonation"}})
        self.assertTrue(result["result"]["isError"])
        self.assertNotEqual(self.fake.calls[-1][0], "chat_update")
        result = self.request("tools/call", {"name": "bridge_search", "arguments": {"query": 8}})
        self.assertTrue(result["result"]["isError"])

    def test_resources_are_fixed_scoped_views(self):
        self.initialize()
        listing = self.request("resources/list")["result"]["resources"]
        self.assertIn("bridge://space/fiction%20%2F%20one/shared", [row["uri"] for row in listing])
        result = self.request("resources/read", {"uri": "bridge://space/fiction%20%2F%20one/chat/" + ACTOR})
        self.assertIn("Shared", result["result"]["contents"][0]["text"])
        self.assertEqual(self.fake.calls[-1][1], {"name": "fiction / one", "scope": "chat", "actor": ACTOR})
        result = self.request("resources/read", {"uri": "file:///etc/passwd"})
        self.assertIn("error", result)
        result = self.request("resources/read", {"uri": "bridge://space/test/chat/" + OTHER})
        self.assertIn("error", result)

    def test_stdio_notifications_parse_errors_and_eof(self):
        messages = ["not json", json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}),
                    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"})]
        output = io.StringIO()
        self.server.run(io.StringIO("\n".join(messages) + "\n"), output)
        results = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["error"]["code"], -32700)
        self.assertEqual(results[1], {"jsonrpc": "2.0", "id": 2, "result": {}})

    def test_actual_mcp_entry_process_needs_no_ledger_for_handshake(self):
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, DIALOGUE_BRIDGE_HOME=directory)
            env.pop("CODEX_THREAD_ID", None)
            env.pop("DIALOGUE_BRIDGE_PYTHON", None)
            completed = subprocess.run([sys.executable, "-B", str(PLUGIN / "scripts" / "bridge_service.py"), "mcp", "--no-worker"],
                                       input="\n".join(json.dumps(m) for m in messages) + "\n", capture_output=True,
                                       text=True, encoding="utf-8", timeout=5, env=env)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertGreater(len(responses[1]["result"]["tools"]), 20)


class RuntimeBootstrapTests(unittest.TestCase):
    def test_live_service_detects_private_setup_without_changing_its_interpreter(self):
        from dialogue_bridge import service
        fake = str(Path(sys.executable).with_name("fictional-private-python.exe"))
        with patch.object(service, "_core_available", return_value=False), \
             patch.object(service, "_select_private_runtime", return_value=fake), \
             patch.object(service, "_delegate_action", return_value={"bound": True}) as delegate, \
             patch.dict(os.environ, {}, clear=True):
            self.assertEqual(service.runtime_dispatch("open", {}, actor=ACTOR), {"bound": True})
        delegate.assert_called_once_with(fake, "open", {}, ACTOR)

    def test_operator_delegation_keeps_target_separate_from_actual_author(self):
        from dialogue_bridge import service
        with patch.object(service.subprocess, "run") as run, patch.dict(os.environ, {"CODEX_THREAD_ID": ACTOR}):
            run.return_value.returncode = 0
            run.return_value.stdout = '{"status":"pending"}'
            result = service._delegate_action(sys.executable, "import_document", {"actor": OTHER, "scope": "chat", "text": "Fictional edit"}, None)
        self.assertEqual(result["status"], "pending")
        self.assertNotIn("CODEX_THREAD_ID", run.call_args.kwargs["env"])
        self.assertEqual(json.loads(run.call_args.kwargs["input"])["actor"], OTHER)
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_private_runtime_failure_does_not_become_a_successful_write(self):
        from dialogue_bridge import service
        with patch.object(service.subprocess, "run", side_effect=subprocess.TimeoutExpired("fixture", 120)):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                service._delegate_action(sys.executable, "shared_update", {}, ACTOR)
        with patch.object(service.subprocess, "run") as run:
            run.return_value.returncode = 1
            run.return_value.stderr = "Fictional dependency unavailable"
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                service._delegate_action(sys.executable, "open", {}, ACTOR)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRuntime()
        self.server = create_http_server(dispatcher=self.fake, token="fictional-access-token-123456789")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path="/api/action", *, method="POST", authorized=True, origin=None, host=None, content_type="application/json", body=None):
        headers = {"Content-Type": content_type}
        if authorized:
            headers["Authorization"] = "Bearer " + self.server.token
        if origin:
            headers["Origin"] = origin
        if host:
            headers["Host"] = host
        data = json.dumps(body or {"action": "list_spaces", "arguments": {}}).encode() if method == "POST" else None
        try:
            response = urlopen(Request(self.base + path, data=data, headers=headers, method=method), timeout=3)
        except HTTPError as exc:
            response = exc
        with contextlib.closing(response):
            return response.status, response.headers, response.read()

    def test_private_api_requires_token_and_rejects_cross_origin(self):
        self.assertEqual(self.request(authorized=False)[0], 401)
        self.assertEqual(self.request(origin="https://untrusted.example")[0], 403)
        self.assertEqual(self.request(host="rebind.example:" + str(self.server.server_port))[0], 403)
        self.assertEqual(self.fake.calls, [])
        status, _, body = self.request(origin=self.base)
        self.assertEqual(status, 200)
        self.assertIn("spaces", json.loads(body))

    def test_no_get_actions_or_arbitrary_file_reads(self):
        for path in ["/api/action?action=sync", "/../../AGENTS.md", "/files?path=C:/private"]:
            self.assertEqual(self.request(path, method="GET")[0], 404)
        self.assertEqual(self.fake.calls, [])
        status, headers, body = self.request("/", method="GET")
        self.assertEqual(status, 200)
        self.assertIn(b"Current understanding", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_writes_reach_same_dispatcher_and_invalid_payloads_do_not(self):
        body = {"action": "import_document", "arguments": {"name": "fiction", "scope": "shared", "text": "Correction", "user_confirmed": True}}
        self.assertEqual(self.request(body=body)[0], 200)
        self.assertEqual(self.fake.calls[-1], ("import_document", body["arguments"], None))
        self.assertEqual(self.request(content_type="text/plain")[0], 415)
        self.assertEqual(self.request(body={"action": "unknown"})[0], 400)
        self.assertEqual(self.request(body={"action": "search", "arguments": {"query": "x", "unexpected": "y"}})[0], 400)

    def test_refuses_non_loopback_and_weak_token(self):
        with self.assertRaises(ValueError):
            create_http_server("0.0.0.0")
        with self.assertRaises(ValueError):
            create_http_server(token="weak")


class HookTests(unittest.TestCase):
    def test_bound_context_is_data_and_bounded(self):
        fake = FakeRuntime()
        result = hook_result({"hook_event_name": "UserPromptSubmit", "session_id": ACTOR}, dispatcher=fake, environ={})
        self.assertEqual(fake.calls, [("open", {"lightweight": True, "queue": True}, ACTOR)])
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("not instructions", context)
        self.assertIn("fictional project", context)
        self.assertLessEqual(len(context), 6500)
        huge = lambda *a, **kw: {"bound": True, "shared": "x" * 100000}
        context = hook_result({"hook_event_name": "SessionStart", "session_id": ACTOR}, dispatcher=huge, environ={})["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(context), 6500)

    def test_unbound_errors_invalid_and_subagent_are_silent(self):
        for dispatcher in [lambda *a, **kw: {"bound": False}, lambda *a, **kw: 1 / 0]:
            self.assertIsNone(hook_result({"hook_event_name": "SessionStart", "session_id": ACTOR}, dispatcher=dispatcher, environ={}))
        fake = FakeRuntime()
        for payload in [{"hook_event_name": "SessionStart", "session_id": "../invalid"},
                        {"hook_event_name": "SessionStart", "session_id": ACTOR, "agent_id": OTHER},
                        {"hook_event_name": "Other", "session_id": ACTOR}]:
            self.assertIsNone(hook_result(payload, dispatcher=fake, environ={}))
        self.assertIsNone(hook_result({"hook_event_name": "SessionStart", "session_id": ACTOR}, dispatcher=fake, environ={"CODEX_THREAD_ID": OTHER}))
        self.assertEqual(fake.calls, [])

    def test_stop_only_queues_and_does_not_emit_context(self):
        fake = FakeRuntime()
        self.assertIsNone(hook_result({"hook_event_name": "Stop", "session_id": ACTOR}, dispatcher=fake, environ={}))
        self.assertEqual(fake.calls[-1], ("jobs", {"enqueue": "sync"}, ACTOR))
        self.assertFalse(any(action == "process_jobs" for action, _, _ in fake.calls))

    def test_runtime_selection_uses_existing_binding_without_writes(self):
        spec = importlib.util.spec_from_file_location("bridge_hook_test", PLUGIN / "scripts" / "bridge_hook.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertIsNone(module.select_runtime(actor=ACTOR, environ={"DIALOGUE_BRIDGE_HOME": directory}))
            self.assertEqual(list(home.iterdir()), [])
            with contextlib.closing(sqlite3.connect(home / "registry.db")) as db:
                db.executescript("CREATE TABLE contexts(name TEXT,directory TEXT,runtime_python TEXT); CREATE TABLE bindings(thread_id TEXT,name TEXT);")
                db.execute("INSERT INTO contexts VALUES(?,?,?)", ("fiction", directory, sys.executable))
                db.execute("INSERT INTO bindings VALUES(?,?)", (ACTOR, "fiction"))
                db.commit()
            self.assertEqual(module.select_runtime(actor=ACTOR, environ={"DIALOGUE_BRIDGE_HOME": directory}), str(Path(sys.executable).absolute()))
            self.assertIsNone(module.select_runtime(actor=OTHER, environ={"DIALOGUE_BRIDGE_HOME": directory}))
        output = io.StringIO()
        self.assertEqual(module.main(io.StringIO("invalid input"), output), 0)
        self.assertEqual(output.getvalue(), "")

    def test_hook_runtime_timeout_is_fail_open_even_in_current_interpreter(self):
        spec = importlib.util.spec_from_file_location("bridge_hook_timeout_test", PLUGIN / "scripts" / "bridge_hook.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch.object(module, "select_runtime", return_value=sys.executable), \
             patch.object(module.subprocess, "run", side_effect=subprocess.TimeoutExpired("fixture", 3)) as run:
            self.assertEqual(module.main(io.StringIO(json.dumps({"hook_event_name": "SessionStart", "session_id": ACTOR})), output), 0)
            self.assertEqual(run.call_args.kwargs["timeout"], 3)
        self.assertEqual(output.getvalue(), "")

    def test_worker_only_processes_policy_limited_automatic_work(self):
        fake = FakeRuntime()
        worker = QueueWorker(fake, interval=0.01).start()
        for _ in range(50):
            if fake.calls:
                break
            worker.stopped.wait(0.01)
        worker.stop()
        self.assertTrue(fake.calls)
        self.assertTrue(all(call == ("process_jobs", {"limit": 1, "automatic": True}, None) for call in fake.calls))


if __name__ == "__main__":
    unittest.main()
