"""Persistent, coalesced local work. A queued job is not a model result."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


DEFAULT_SETTINGS = {"auto_sync": True, "auto_understand": False,
                    "model_command": None, "model_timeout": 180, "model_chars": 48000}


class Jobs:
    def __init__(self, home):
        self.path = Path(home) / "runtime.db"

    @contextmanager
    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings(directory TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS progress(directory TEXT PRIMARY KEY, change_id INTEGER NOT NULL,
                    text_offset INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS model_results(job_id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(
                    id TEXT PRIMARY KEY, directory TEXT NOT NULL, name TEXT NOT NULL,
                    kind TEXT NOT NULL, actor TEXT, status TEXT NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL, available REAL NOT NULL,
                    lease REAL NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
                    result TEXT, error TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS pending_job ON jobs(directory,kind)
                    WHERE status IN ('pending','running');
            """)
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    def settings(self, directory, changes=None):
        directory = str(Path(directory).resolve())
        with self.db() as db:
            row = db.execute("SELECT data FROM settings WHERE directory=?", (directory,)).fetchone()
            value = {**DEFAULT_SETTINGS, **(json.loads(row[0]) if row else {})}
            if changes:
                if set(changes) - set(DEFAULT_SETTINGS):
                    raise ValueError("Unknown runtime setting")
                for key in ("auto_sync", "auto_understand"):
                    if key in changes and type(changes[key]) is not bool:
                        raise ValueError(f"{key} must be a boolean")
                command = changes.get("model_command", value["model_command"])
                if command is not None and (not isinstance(command, list) or not command or
                        any(not isinstance(x, str) or not x or "\x00" in x for x in command)):
                    raise ValueError("model_command is an executable argument array, never a shell string")
                for key, low, high in (("model_timeout", 10, 1800), ("model_chars", 4000, 200000)):
                    if key in changes and (type(changes[key]) is not int or not low <= changes[key] <= high):
                        raise ValueError(f"{key} must be {low}..{high}")
                value.update(changes)
                db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (directory, json.dumps(value)))
        return value

    def enqueue(self, directory, name, kind="sync", actor=None):
        if kind not in {"sync", "understand"}:
            raise ValueError("Job kind must be sync or understand")
        directory = str(Path(directory).resolve())
        stamp = time.time()
        with self.db() as db:
            old = db.execute("SELECT * FROM jobs WHERE directory=? AND kind=? AND status IN ('pending','running')",
                             (directory, kind)).fetchone()
            if old:
                # Mark an in-flight scan dirty so a new turn arriving during it isn't lost.
                db.execute("UPDATE jobs SET updated=? WHERE id=?", (stamp, old["id"]))
                return {"id": old["id"], "kind": kind, "status": old["status"], "coalesced": True}
            ident = uuid4().hex
            db.execute("INSERT INTO jobs(id,directory,name,kind,actor,status,created,updated,available) "
                       "VALUES (?,?,?,?,?,'pending',?,?,?)", (ident, directory, name, kind, actor, stamp, stamp, stamp))
        return {"id": ident, "kind": kind, "status": "pending", "coalesced": False}

    def claim(self, *, directory=None, allow_models=False):
        stamp = time.time()
        with self.db() as db:
            # Model output may already have been billed. Never silently repeat after a crash.
            db.execute("UPDATE jobs SET status='failed',error='Model worker interrupted; explicitly retry after review' "
                       "WHERE status='running' AND lease<? AND kind='understand'", (stamp,))
            db.execute("UPDATE jobs SET status=CASE WHEN attempts<3 THEN 'pending' ELSE 'failed' END, "
                       "error='History worker interrupted' WHERE status='running' AND lease<? AND kind='sync'", (stamp,))
            sql = "SELECT * FROM jobs WHERE status='pending' AND available<=?"
            params = [stamp]
            if directory:
                sql += " AND directory=?"
                params.append(str(Path(directory).resolve()))
            if not allow_models:
                sql += " AND kind='sync'"
            sql += " ORDER BY created LIMIT 1"
            row = db.execute(sql, params).fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status='running',lease=?,attempts=attempts+1 WHERE id=?",
                       (stamp + 1900, row["id"]))
            return {**dict(row), "attempts": row["attempts"] + 1, "claimed_at": stamp}

    def finish(self, job, *, result=None, error=None):
        stamp = time.time()
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
            if not row or row["status"] != "running":
                raise ValueError("Job is no longer running")
            dirty = row["updated"] > job["claimed_at"]
            retry = error is not None and job["kind"] == "sync" and job["attempts"] < 3
            status = "pending" if retry or (dirty and error is None) else ("failed" if error else "complete")
            db.execute("UPDATE jobs SET status=?,lease=0,available=?,result=?,error=? WHERE id=?",
                       (status, stamp + (10 * job["attempts"] if retry else 0),
                        json.dumps(result, ensure_ascii=False) if result is not None else None,
                        str(error)[:2000] if error else None, job["id"]))
        return {"id": job["id"], "kind": job["kind"], "status": status,
                "result": result, "error": str(error)[:2000] if error else None}

    def list(self, directory=None, *, limit=50):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Job limit must be 1..100")
        with self.db() as db:
            rows = db.execute("SELECT * FROM jobs " + ("WHERE directory=? " if directory else "") +
                              "ORDER BY created DESC LIMIT ?",
                              ([str(Path(directory).resolve())] if directory else []) + [limit]).fetchall()
        return [{**dict(row), "result": json.loads(row["result"]) if row["result"] else None} for row in rows]

    def retry(self, ident, directory):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND directory=?",
                             (ident, str(Path(directory).resolve()))).fetchone()
            if not row or row["status"] != "failed":
                raise ValueError("Only a failed job in this space can be retried")
            if db.execute("SELECT 1 FROM jobs WHERE directory=? AND kind=? AND status IN ('pending','running')",
                          (row["directory"], row["kind"])).fetchone():
                raise ValueError("An equivalent job is already queued")
            db.execute("UPDATE jobs SET status='pending',attempts=0,available=?,updated=? WHERE id=?",
                       (time.time(), time.time(), ident))
        return {"id": ident, "status": "pending"}

    def cancel(self, ident, directory):
        with self.db() as db:
            row = db.execute("SELECT status FROM jobs WHERE id=? AND directory=?",
                             (ident, str(Path(directory).resolve()))).fetchone()
            if not row or row[0] != "pending":
                raise ValueError("Only pending jobs can be cancelled; running model work must finish or time out")
            db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (ident,))
        return {"id": ident, "status": "cancelled"}

    def progress(self, directory, position=None):
        directory = str(Path(directory).resolve())
        with self.db() as db:
            row = db.execute("SELECT change_id,text_offset FROM progress WHERE directory=?", (directory,)).fetchone()
            if position is not None:
                change, offset = position
                if type(change) is not int or type(offset) is not int or min(change, offset) < 0:
                    raise ValueError("Interpretation progress requires a nonnegative change and offset")
                # Offset zero completes a change; it follows every partial slice
                # of that change. Recovering an older job must not rewind progress.
                if row is None or (change, offset == 0, offset) > (row[0], row[1] == 0, row[1]):
                    db.execute("INSERT OR REPLACE INTO progress VALUES (?,?,?)", (directory, change, offset))
            row = db.execute("SELECT change_id,text_offset FROM progress WHERE directory=?", (directory,)).fetchone()
        return {"change": row[0] if row else 0, "offset": row[1] if row else 0,
                "meaning": "Background model input consumed; not proof that its interpretation is correct"}

    def model_result(self, ident, value=None):
        """Retain a completed response before applying its idempotent shared patch.

        This is private recovery data, not a provider command or a new model call.
        A stable operation ID and its exact original base survive explicit retries.
        """
        with self.db() as db:
            if value is not None:
                db.execute("INSERT INTO model_results VALUES (?,?)", (ident, json.dumps(value, ensure_ascii=False)))
            row = db.execute("SELECT data FROM model_results WHERE job_id=?", (ident,)).fetchone()
        return json.loads(row[0]) if row else None

    def clear_model_result(self, ident):
        with self.db() as db:
            db.execute("DELETE FROM model_results WHERE job_id=?", (ident,))
