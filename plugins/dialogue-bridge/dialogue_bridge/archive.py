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
            CREATE TABLE IF NOT EXISTS archive_turns (
                thread_id TEXT NOT NULL, turn_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                digest TEXT NOT NULL, non_text_inputs INTEGER NOT NULL,
                PRIMARY KEY(thread_id, turn_id)
            );
            CREATE TABLE IF NOT EXISTS history_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT NOT NULL,
                ref TEXT NOT NULL, kind TEXT NOT NULL, sha256 TEXT
            );
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
            before = self._hashes(ident)
            self.db.execute("DELETE FROM messages WHERE thread_id=?", (ident,))
            self.db.execute("DELETE FROM archive_turns WHERE thread_id=?", (ident,))
            seen_turns = set()
            for page in client.pages(ident):
                for turn in page:
                    if turn["id"] in seen_turns:
                        raise ValueError("Repeated turn during paging; cannot claim a complete scan")
                    seen_turns.add(turn["id"])
                    counts["turns"] += 1
                    added, non_text = self._store_turn(ident, turn, counts["turns"], counts["messages"])
                    counts["messages"] += added
                    counts["non_text_inputs"] += non_text
            self.db.execute("INSERT OR REPLACE INTO threads VALUES (?,?,?,?,?,?,?,?,?)", (
                ident, meta.get("name"), meta.get("cwd"), json.dumps(meta.get("status")),
                started, now(), counts["turns"], counts["messages"], counts["non_text_inputs"],
            ))
            self._log_changes(ident, before)
        return {"thread_id": ident, **counts, "coverage": "persisted user/assistant text; excludes tool output, reasoning and attachment contents; not an atomic snapshot of a running chat"}

    def _hashes(self, ident):
        return dict(self.db.execute("SELECT ref, sha256 FROM messages WHERE thread_id=?", (ident,)))

    def _log_changes(self, ident, before):
        after = self._hashes(ident)
        for ref in sorted(before.keys() | after.keys()):
            if before.get(ref) != after.get(ref):
                kind = "removed" if ref not in after else "updated" if ref in before else "added"
                self.db.execute("INSERT INTO history_changes(thread_id, ref, kind, sha256) VALUES (?,?,?,?)",
                                (ident, ref, kind, after.get(ref)))

    @staticmethod
    def _text_items(turn):
        if turn.get("itemsView") not in (None, "full") or not isinstance(turn.get("items"), list):
            raise ValueError("Server did not return full turn items")
        rows, non_text = [], 0
        for item in turn["items"]:
            if item["type"] == "userMessage":
                parts = item.get("content", [])
                text = "\n".join(x["text"] for x in parts if x.get("type") == "text")
                non_text += sum(x.get("type") != "text" for x in parts)
                role = "user"
            elif item["type"] == "agentMessage":
                text, role = item.get("text", ""), "assistant"
            else:
                continue
            if text:
                rows.append((item["id"], role, item.get("phase"), text))
        return rows, non_text

    def _store_turn(self, ident, turn, ordinal, seq):
        rows, non_text = self._text_items(turn)
        for offset, (item_id, role, phase, text) in enumerate(rows):
            self.db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?)", (
                f"{ident}/{turn['id']}/{item_id}", ident, turn["id"], item_id, seq + offset,
                role, phase, text, text.casefold(), hashlib.sha256(text.encode("utf-8")).hexdigest()))
        digest = hashlib.sha256(json.dumps([rows, non_text], ensure_ascii=False).encode()).hexdigest()
        self.db.execute("INSERT INTO archive_turns VALUES (?,?,?,?,?)",
                        (ident, turn["id"], ordinal, digest, non_text))
        return len(rows), non_text

    def refresh(self, client, ident, *, full=False):
        """Read new turns and re-read the last saved turn, including appended items.

        A disappeared boundary (e.g. reverted history) forces a complete rescan.
        Edits before that boundary require an explicit full refresh.
        """
        ident = self.selected(ident)
        anchor = self.db.execute("SELECT * FROM archive_turns WHERE thread_id=? ORDER BY ordinal DESC LIMIT 1",
                                 (ident,)).fetchone()
        if full or anchor is None or not hasattr(client, "recent_pages"):
            return {**self.sync(client, ident), "mode": "full"}
        started, meta, pending, seen, found = now(), client.metadata(ident), [], set(), False
        received_turns = 0
        for page in client.recent_pages(ident):
            received_turns += len(page)
            for turn in page:
                if turn["id"] in seen:
                    raise ValueError("Repeated turn during paging; coverage is incomplete")
                seen.add(turn["id"])
                self._text_items(turn)
                pending.append(turn)
                if turn["id"] == anchor["turn_id"]:
                    found = True
                    break
            if found:
                break
        if not found:
            return {**self.sync(client, ident), "mode": "full_boundary_missing"}
        with self.db:
            # A second writer must not move our boundary while the read was in flight.
            self.db.execute("BEGIN IMMEDIATE")
            latest = self.db.execute("SELECT turn_id, digest FROM archive_turns WHERE thread_id=? ORDER BY ordinal DESC LIMIT 1",
                                     (ident,)).fetchone()
            if latest is None or tuple(latest) != (anchor["turn_id"], anchor["digest"]):
                raise ValueError("History index changed during refresh; retry")
            before = self._hashes(ident)
            self.db.execute("DELETE FROM messages WHERE thread_id=? AND turn_id=?", (ident, anchor["turn_id"]))
            self.db.execute("DELETE FROM archive_turns WHERE thread_id=? AND turn_id=?", (ident, anchor["turn_id"]))
            seq = self.db.execute("SELECT COALESCE(MAX(seq)+1,0) FROM messages WHERE thread_id=?", (ident,)).fetchone()[0]
            for offset, turn in enumerate(reversed(pending)):
                added, _ = self._store_turn(ident, turn, anchor["ordinal"] + offset, seq)
                seq += added
            count, non_text = self.db.execute("SELECT COUNT(*), COALESCE(SUM(non_text_inputs),0) FROM archive_turns WHERE thread_id=?", (ident,)).fetchone()
            self.db.execute("INSERT OR REPLACE INTO threads VALUES (?,?,?,?,?,?,?,?,?)",
                            (ident, meta.get("name"), meta.get("cwd"), json.dumps(meta.get("status")),
                             started, now(), count, seq, non_text))
            self._log_changes(ident, before)
        return {"thread_id": ident, "mode": "incremental", "fetched_turns": received_turns,
                "checked_turns": len(pending),
                "turns": count, "messages": seq,
                "coverage": "new turns plus the last saved turn; earlier edits require full refresh; not an atomic desktop snapshot"}

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
