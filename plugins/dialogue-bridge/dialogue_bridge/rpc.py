"""A deliberately read-only client for the installed Codex App Server."""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time


class RpcError(RuntimeError):
    pass


class ReadOnlyCodex:
    ALLOWED = {"initialize", "thread/read", "thread/turns/list"}

    def __init__(self, command=None, *, timeout=30):
        self.command = command or ["codex", "app-server", "--stdio"]
        self.timeout = timeout
        self.proc = None
        self.messages = queue.Queue()
        self.ident = 0

    def __enter__(self):
        self.proc = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.request("initialize", {
                "clientInfo": {"name": "dialogue_bridge_reader", "version": "0.1.0-alpha.2"},
            })
            self._send({"method": "initialized", "params": {}})
        except BaseException:
            self.close()
            raise
        return self

    def _read(self):
        try:
            for line in self.proc.stdout:
                try:
                    self.messages.put(json.loads(line))
                except json.JSONDecodeError:
                    self.messages.put(RpcError("App Server emitted invalid JSON"))
        finally:
            self.messages.put(RpcError("App Server transport closed"))

    def _send(self, payload):
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params):
        if method not in self.ALLOWED:
            raise ValueError(f"This client cannot invoke {method!r}; only stored-history reads are supported")
        self.ident += 1
        ident = self.ident
        self._send({"method": method, "id": ident, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"App Server timed out: {method}")
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError(f"App Server timed out: {method}") from exc
            if isinstance(message, Exception):
                raise message
            if "method" in message:
                if "id" in message:
                    self._send({"id": message["id"], "error": {"code": -32601, "message": "Read-only history client does not execute host requests"}})
                continue
            if message.get("id") == ident:
                if "error" in message:
                    raise RpcError(f"{method}: {message['error']}")
                return message["result"]

    def metadata(self, thread_id):
        return self.request("thread/read", {"threadId": thread_id})["thread"]

    def pages(self, thread_id):
        cursor = None
        seen = set()
        while True:
            params = {"threadId": thread_id, "limit": 25, "sortDirection": "asc", "itemsView": "full"}
            if cursor is not None:
                params["cursor"] = cursor
            page = self.request("thread/turns/list", params)
            yield page["data"]
            cursor = page.get("nextCursor")
            if cursor is None:
                break
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise RpcError("Invalid or repeated history cursor; coverage is incomplete")
            seen.add(cursor)

    def close(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)
        self.reader.join(timeout=3)
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.proc = None

    def __exit__(self, *_):
        self.close()
