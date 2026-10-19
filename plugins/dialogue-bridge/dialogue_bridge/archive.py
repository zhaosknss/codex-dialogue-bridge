"""Selected conversation text, with original locators; no automatic interpretation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from uuid import UUID


def thread_id(value):
    if not isinstance(value, str):
        raise ValueError("Thread ID must be a UUID or codex://threads/ link")
    value = value.removeprefix("codex://threads/").strip().rstrip("/")
    return str(UUID(value))


def now():
    return datetime.now(timezone.utc).isoformat()


class Archive:
    @classmethod
    def create(cls, directory, project, threads):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        config = root / "project.json"
        if config.exists():
            raise ValueError("Workspace already exists; use a separate directory for a different selection")
        selected = list(dict.fromkeys(thread_id(x) for x in threads))
        if not selected or not project.strip():
            raise ValueError("A project and at least one selected thread are required")
        # Creation must not silently replace another process's scope.
        with config.open("x", encoding="utf-8") as stream:
            json.dump({"project": project, "threads": selected}, stream, ensure_ascii=False, indent=2)
        return cls(root)

    def __init__(self, directory):
        self.root = Path(directory)
        self.config = json.loads((self.root / "project.json").read_text(encoding="utf-8"))
        self.project = self.config["project"]
        self.threads = self.config["threads"]
        self.db = sqlite3.connect(self.root / "archive.db", timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY, name TEXT, cwd TEXT, observed_status TEXT,
                scan_started TEXT, scan_finished TEXT, turns INTEGER,
                messages INTEGER, non_text_inputs INTEGER
            );
            CREATE TABLE IF NOT EXISTS messages (
                ref TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL,
                item_id TEXT NOT NULL, seq INTEGER NOT NULL, role TEXT NOT NULL,
                phase TEXT, text TEXT NOT NULL, search_text TEXT NOT NULL,
                sha256 TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS message_order ON messages(thread_id, seq);
        """)

    def close(self):
        self.db.close()

    def selected(self, ident):
        ident = thread_id(ident)
        if ident not in self.threads:
            raise ValueError("Thread is outside the explicitly selected workspace")
        return ident

    def sync(self, client, ident):
        ident = self.selected(ident)
        started = now()
        meta = client.metadata(ident)
        counts = {"turns": 0, "messages": 0, "non_text_inputs": 0}
        with self.db:
            self.db.execute("DELETE FROM messages WHERE thread_id=?", (ident,))
            seen_turns = set()
            for page in client.pages(ident):
                for turn in page:
                    if turn["id"] in seen_turns:
                        raise ValueError("Repeated turn during paging; cannot claim a complete scan")
                    seen_turns.add(turn["id"])
                    if turn.get("itemsView") not in (None, "full") or "items" not in turn:
                        raise ValueError("Server did not return full turn items")
                    counts["turns"] += 1
                    for item in turn["items"]:
                        kind = item["type"]
                        if kind == "userMessage":
                            parts = item.get("content", [])
                            text = "\n".join(x["text"] for x in parts if x.get("type") == "text")
                            counts["non_text_inputs"] += sum(x.get("type") != "text" for x in parts)
                            role = "user"
                        elif kind == "agentMessage":
                            text = item.get("text", "")
                            role = "assistant"
                        else:
                            continue
                        if not text:
                            continue
                        ref = f"{ident}/{turn['id']}/{item['id']}"
                        self.db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?)", (
                            ref, ident, turn["id"], item["id"], counts["messages"], role,
                            item.get("phase"), text, text.casefold(),
                            hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        ))
                        counts["messages"] += 1
            self.db.execute("INSERT OR REPLACE INTO threads VALUES (?,?,?,?,?,?,?,?,?)", (
                ident, meta.get("name"), meta.get("cwd"), json.dumps(meta.get("status")),
                started, now(), counts["turns"], counts["messages"], counts["non_text_inputs"],
            ))
        return {"thread_id": ident, **counts, "coverage": "persisted user/assistant text; excludes tool output, reasoning and attachment contents; not an atomic snapshot of a running chat"}

    def status(self):
        rows = {row["id"]: dict(row) for row in self.db.execute("SELECT * FROM threads")}
        return {"project": self.project, "threads": [rows.get(x, {"id": x, "scan_finished": None}) for x in self.threads],
                "runtime_status_scope": "independent reader process; not desktop availability",
                "automatic_dispatch": False}

    def message(self, ref):
        row = self.db.execute("SELECT * FROM messages WHERE ref=?", (ref,)).fetchone()
        if row is None or row["thread_id"] not in self.threads:
            raise ValueError("Message not found within selected, successfully indexed history")
        return dict(row)

    def search(self, query, *, role=None, limit=8, char_budget=6000):
        terms = list(dict.fromkeys(query.casefold().split()))
        if not terms or not 1 <= limit <= 30 or not 1 <= char_budget <= 20000:
            raise ValueError("Use nonempty search terms, limit 1..30 and character budget 1..20000")
        where = ["thread_id IN (" + ",".join("?" for _ in self.threads) + ")"]
        args = list(self.threads)
        for term in terms:
            where.append("instr(search_text, ?) > 0")
            args.append(term)
        if role is not None:
            if role not in ("user", "assistant"):
                raise ValueError("role must be user or assistant")
            where.append("role=?")
            args.append(role)
        clause = " AND ".join(where)
        total = self.db.execute(f"SELECT COUNT(*) FROM messages WHERE {clause}", args).fetchone()[0]
        # Give matching selected chats a turn before one long transcript fills the window.
        rows = self.db.execute(f"""SELECT * FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY thread_id ORDER BY seq DESC) AS hit_round
            FROM messages WHERE {clause}
        ) ORDER BY hit_round, thread_id LIMIT ?""", (*args, limit))
        hits = []
        remaining = char_budget
        for row in rows:
            if remaining <= 0:
                break
            row = dict(row)
            pos = row["search_text"].find(terms[0])
            # casefold may change character counts: it ranks/filter matches only.
            # Excerpts can start nearby; exact source text is always read by ref.
            start = max(0, min(pos, len(row["text"])) - 160)
            excerpt = row["text"][start:start + min(700, remaining)]
            remaining -= len(excerpt)
            hits.append({k: row[k] for k in ("ref", "thread_id", "turn_id", "item_id", "role", "phase", "sha256")} | {
                "excerpt": excerpt, "excerpt_offset": start,
                "text_length": len(row["text"]), "link": f"codex://threads/{row['thread_id']}",
            })
        return {"match_count": total, "hits": hits, "more_matches": len(hits) < total,
                "excerpt_characters": char_budget - remaining, "coverage": self.status(),
                "retrieval": "literal casefolded substring AND; not semantic search or evidence of understanding"}

    def read(self, ref, *, offset=0, char_budget=10000, before=0, after=0):
        if offset < 0 or not 1 <= char_budget <= 20000 or not 0 <= before <= 10 or not 0 <= after <= 10:
            raise ValueError("Invalid offset, character budget or neighboring-message count")
        focus = self.message(ref)
        if offset > len(focus["text"]):
            raise ValueError("Read offset is beyond the original message")
        rows = self.db.execute("SELECT * FROM messages WHERE thread_id=? AND seq BETWEEN ? AND ? ORDER BY seq", (
            focus["thread_id"], focus["seq"] - before, focus["seq"] + after,
        )).fetchall()
        output = []
        remaining = char_budget
        for source in rows:
            if remaining == 0:
                break
            source = dict(source)
            start = offset if source["ref"] == ref else 0
            text = source["text"][start:start + remaining]
            remaining -= len(text)
            output.append({k: source[k] for k in ("ref", "role", "phase", "sha256")} | {
                "text": text, "offset": start, "text_length": len(source["text"]),
                "next_offset": start + len(text) if start + len(text) < len(source["text"]) else None,
            })
        return {"focus": ref, "messages": output, "returned_characters": char_budget - remaining,
                "window_complete": len(output) == len(rows) and all(x["next_offset"] is None for x in output)}
