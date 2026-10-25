"""Portable, sourced working understanding. Models interpret; code checks storage."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

from .archive import Archive, thread_id
from .notes import require_core


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def atomic_text(path, text):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def nonempty(value, name, maximum=4000):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(f"{name} must contain 1..{maximum} characters")
    return value


class Registry:
    """Private names and explicit per-chat bindings, separate from native memory."""
    def __init__(self, home=None):
        self.home = Path(home or os.environ.get("DIALOGUE_BRIDGE_HOME") or
                         Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "dialogue-bridge")

    @contextmanager
    def database(self):
        self.home.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.home / "registry.db", timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS contexts(name TEXT PRIMARY KEY, directory TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS bindings(thread_id TEXT PRIMARY KEY, name TEXT NOT NULL, scopes TEXT);
            """)
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                columns = {row[1] for row in connection.execute("PRAGMA table_info(contexts)")}
                if "runtime_python" not in columns:
                    connection.execute("ALTER TABLE contexts ADD COLUMN runtime_python TEXT")
                yield connection
        finally:
            connection.close()

    def register(self, name, directory):
        name = nonempty(name, "name", 120)
        with self.database() as db:
            previous = db.execute("SELECT directory FROM contexts WHERE name=?", (name,)).fetchone()
            if previous and previous[0] != str(Path(directory).resolve()):
                raise ValueError("That background name already points elsewhere; choose another name")
            db.execute("INSERT INTO contexts(name,directory,runtime_python) VALUES (?,?,?) "
                       "ON CONFLICT(name) DO UPDATE SET runtime_python=excluded.runtime_python",
                       (name, str(Path(directory).resolve()), str(Path(sys.executable).absolute())))

    def list(self, threads=None):
        selected = {thread_id(value) for value in threads} if threads else None
        with self.database() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM contexts ORDER BY name")]
        result = []
        for row in rows:
            try:
                config = json.loads((Path(row["directory"]) / "project.json").read_text(encoding="utf-8"))
                sources = [Context.source(value) for value in config["context"]["sources"]]
                if not sources or {s["thread"] for s in sources} != {thread_id(x) for x in config["threads"]}:
                    raise ValueError("Background sources and archive selection disagree")
                row.update(available=True, sources=sources)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                row.update(available=False, sources=[], error=str(exc))
            if selected is None or (row["available"] and {s["thread"] for s in row["sources"]} == selected):
                result.append(row)
        return result

    def resolve(self, *, name=None, directory=None, actor=None):
        if directory:
            config = json.loads((Path(directory) / "project.json").read_text(encoding="utf-8"))
            if name and config.get("context", {}).get("name") != name:
                raise ValueError("The explicit directory does not match the selected background name")
            return Path(directory), None
        with self.database() as db:
            bound = db.execute("SELECT name, scopes FROM bindings WHERE thread_id=?", (actor,)).fetchone() if actor else None
            selected = name or (bound["name"] if bound else None)
            row = db.execute("SELECT directory FROM contexts WHERE name=?", (selected,)).fetchone()
            if not row:
                raise ValueError("Select a saved background by --name (context-list shows available names)")
            scopes = json.loads(bound["scopes"]) if bound and selected == bound["name"] else None
            return Path(row[0]), scopes

    def bind(self, name, actor, scopes=None):
        actor = thread_id(actor)
        with self.database() as db:
            if not db.execute("SELECT 1 FROM contexts WHERE name=?", (name,)).fetchone():
                raise ValueError("Register this background before binding a new chat")
            db.execute("INSERT OR REPLACE INTO bindings VALUES (?,?,?)", (actor, name, json.dumps(scopes)))


class Context:
    @staticmethod
    def source(value):
        if not isinstance(value, dict) or set(value) - {"thread", "scope", "label"}:
            raise ValueError("A source contains thread, scope and optional label")
        return {"thread": thread_id(value.get("thread")),
                "scope": nonempty(value.get("scope"), "source scope", 120),
                "label": nonempty(value.get("label", value.get("scope")), "source label", 160)}

    @classmethod
    def create(cls, directory, name, sources):
        require_core()  # Do not leave a half-created selection on missing dependencies.
        name = nonempty(name, "name", 120)
        if not isinstance(sources, list) or not sources:
            raise ValueError("Select at least one source conversation")
        sources = [cls.source(source) for source in sources]
        if len({s["thread"] for s in sources}) != len(sources):
            raise ValueError("Select each source conversation only once")
        archive = Archive.create(directory, name, [s["thread"] for s in sources])
        try:
            archive.config["context"] = {"id": str(uuid4()), "name": name, "sources": sources}
            atomic_text(archive.root / "project.json", json.dumps(archive.config, ensure_ascii=False, indent=2))
        finally:
            archive.close()
        return cls(directory)

    def __init__(self, directory):
        self.archive = Archive(directory)
        try:
            self.config = self.archive.config["context"]
            if {s["thread"] for s in self.config["sources"]} != set(self.archive.threads):
                raise ValueError("Background sources and archive selection disagree")
            self.ledger = require_core()(self.archive.root / "understanding.db")
        except Exception:
            self.archive.close()
            raise
        self.audience = "context:" + self.config["id"]

    def close(self):
        self.ledger.close()
        self.archive.close()

    def add_source(self, source):
        source = self.source(source)
        for previous in self.config["sources"]:
            if previous["thread"] == source["thread"]:
                if previous != source:
                    raise ValueError("Source already exists with different scope/label")
                return {"added": False, "source": previous}
        self.config["sources"].append(source)
        self.archive.threads.append(source["thread"])
        atomic_text(self.archive.root / "project.json", json.dumps(self.archive.config, ensure_ascii=False, indent=2))
        return {"added": True, "source": source, "next": "Refresh this explicitly added source before revising understanding"}

    def snapshot(self):
        saved = self.ledger.snapshot()
        return saved.revision, saved.state.get("understanding")

    def understanding_revision(self, current=None):
        """The shared projection changes only when understanding changes.

        Chat documents, proposals and receipts share this Ledger's concurrency
        revision, but must not make an unchanged projection look human-edited.
        Older alpha records have no embedded version, so locate their last
        understanding transition through the public history API.
        """
        if current is None:
            _, current = self.snapshot()
        if current is None:
            return 0
        if "shared_revision" in current:
            return current["shared_revision"]
        for commit in reversed(self.ledger.history()):
            if "understanding" in commit.transition.updates:
                return commit.revision
        return 0

    def coverage(self):
        latest = json.loads((self.archive.root / "project.json").read_text(encoding="utf-8"))
        if latest != self.archive.config:
            raise ValueError("Background selection changed; reopen before continuing")
        generation = self.archive.db.execute("SELECT COALESCE(MAX(id),0) FROM history_changes").fetchone()[0]
        status = self.archive.status()
        indexed = all(x.get("scan_finished") for x in status["threads"])
        return {"token": digest([self.config, generation, indexed]), "change": generation,
                "all_sources_indexed": indexed, "history": status,
                "meaning": "Indexed user/assistant text, not proof that the model read or understood every message"}

    def overview(self):
        result = []
        for source in self.config["sources"]:
            rows = self.archive.db.execute("SELECT ref, text FROM messages WHERE thread_id=? AND role='user' ORDER BY seq",
                                           (source["thread"],)).fetchall()
            positions = sorted({int(i * (len(rows)-1) / 7) for i in range(8)}) if rows else []
            result.append({**source, "user_messages": len(rows), "samples": [
                {"ref": rows[i]["ref"], "excerpt": rows[i]["text"][:220]} for i in positions]})
        revision, current = self.snapshot()
        return {"name": self.config["name"], "workspace": str(self.archive.root.resolve()),
                "revision": revision, "coverage": self.coverage(), "sources": result,
                "has_understanding": current is not None,
                "next": "Samples are orientation only: search full indexed history and read key corrections with neighbors"}

    def changes(self, *, after=None, limit=20, chars=6000):
        if not 1 <= limit <= 100 or not 1 <= chars <= 20000:
            raise ValueError("Use limit 1..100 and chars 1..20000")
        _, current = self.snapshot()
        after = after if after is not None else (current or {}).get("processed_change", 0)
        if type(after) is not int or after < 0:
            raise ValueError("after must be a nonnegative history-change position")
        upper = self.coverage()["change"]
        rows = self.archive.db.execute("SELECT * FROM history_changes WHERE id>? AND id<=? ORDER BY id LIMIT ?",
                                       (after, upper, limit)).fetchall()
        output, remaining, position = [], chars, after
        for row in rows:
            if remaining <= 0:
                break
            message = self.archive.db.execute("SELECT role,text FROM messages WHERE ref=?", (row["ref"],)).fetchone()
            excerpt = message["text"][:min(500, remaining)] if message else None
            remaining -= len(excerpt or "")
            output.append({**dict(row), "role": message["role"] if message else None, "excerpt": excerpt})
            position = row["id"]
        return {"changes": output, "next_after": position, "through_change": upper,
                "has_more": position < upper,
                "meaning": "Changes since the last saved understanding; current excerpts may reflect a later edit, so recheck coverage before save"}

    def save(self, payload, *, actor=None):
        return self._save(payload, actor=actor)

    def _save(self, payload, *, actor=None, retained=None):
        """Retained entries come only from the historical base of a partial revision."""
        from agent_state_core import Record, Transition
        allowed = {"operation_id", "expected_revision", "coverage_token", "purpose", "reason", "entries", "document_sha256"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ValueError("Unknown understanding fields; use the documented snapshot envelope")
        actor = thread_id(actor or os.environ.get("CODEX_THREAD_ID", ""))
        operation = nonempty(payload.get("operation_id"), "operation_id", 150)
        fingerprint = digest(payload)
        request = "context:" + actor + ":" + operation
        replay = self.ledger.get_commit(request)
        if replay:
            if replay.transition.records[0].body["input_digest"] != fingerprint:
                raise ValueError("operation_id was already committed with different content")
            # A replay must not roll the current document back to an old revision.
            return {"revision": replay.revision, "replayed": True, "current_revision": self.ledger.revision}
        revision, old = self.snapshot()
        if type(payload.get("expected_revision")) is not int or payload["expected_revision"] != revision:
            raise ValueError("Understanding changed; read the current revision before saving")
        coverage = self.coverage()
        if not coverage["all_sources_indexed"] or payload.get("coverage_token") != coverage["token"]:
            raise ValueError("History coverage changed or is incomplete; refresh and review before saving")
        purpose = nonempty(payload.get("purpose"), "purpose", 2000)
        reason = nonempty(payload.get("reason"), "reason", 2000)
        entries = payload.get("entries")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
            raise ValueError("Provide 1..100 working-understanding entries")
        scopes = {"shared", *[s["scope"] for s in self.config["sources"]]}
        source_scopes = {s["thread"]: s["scope"] for s in self.config["sources"]}
        checked, keys = [], set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) - {"key", "scope", "text", "sources", "status"}:
                raise ValueError("Entry fields are key, scope, text, sources and optional status")
            key = nonempty(entry.get("key"), "key", 120)
            if key in keys or not isinstance(entry.get("scope"), str) or entry["scope"] not in scopes:
                raise ValueError("Entry keys must be unique and scopes must be explicitly selected")
            keys.add(key)
            status = entry.get("status", "working")
            if status not in {"working", "tentative"}:
                raise ValueError("status must be working or tentative; neither is an authoritative user rule")
            text = nonempty(entry.get("text"), "entry text")
            citations = entry.get("sources")
            if not isinstance(citations, list) or not 1 <= len(citations) <= 8:
                raise ValueError("Each entry needs 1..8 original message quotations")
            if retained is not None and key in retained:
                # An unrelated patch is not a review of this entry's evidence.
                # Keep its original hashes, even when a source changed/disappeared.
                checked.append(deepcopy(retained[key]))
                continue
            evidence = []
            for citation in citations:
                if not isinstance(citation, dict) or set(citation) != {"ref", "quote"}:
                    raise ValueError("A citation contains ref and quote")
                message = self.archive.message(citation["ref"])
                quote = nonempty(citation.get("quote"), "quote", 2500)
                if quote not in message["text"]:
                    raise ValueError("Quote is not verbatim in its original source")
                evidence.append({"ref": message["ref"], "quote": quote, "sha256": message["sha256"],
                                 "role": message["role"], "source_scope": source_scopes[message["thread_id"]]})
            checked.append({"key": key, "scope": entry["scope"], "text": text, "status": status, "sources": evidence})
        if sum(len(e["text"]) + sum(len(s["quote"]) for s in e["sources"]) for e in checked) > 60000:
            raise ValueError("Understanding exceeds 60000 characters; keep source history in the index")
        document = self.archive.root / "understanding.md"
        original_document = document.read_bytes() if document.exists() else None
        if document.exists():
            actual = hashlib.sha256(original_document).hexdigest()
            expected = hashlib.sha256(self.render(old, self.understanding_revision(old)).encode()).hexdigest()
            if actual != expected and payload.get("document_sha256") != actual:
                raise ValueError("The understanding document was edited; read it and supply its document_sha256 before replacing it")
        current = {"purpose": purpose, "entries": checked, "reason": reason, "author_thread": actor,
                   "coverage_token": coverage["token"], "processed_change": coverage["change"],
                   "shared_revision": revision + 1}
        event = Record("working_understanding", {"reason": reason, "input_digest": fingerprint},
                       (self.audience,), {"scope": "this saved background only; interpretation, not permanent instructions"})
        result = self.ledger.commit(Transition(updates={"understanding": current}, records=(event,)),
                                    expected_revision=revision, request_id=request)
        if (document.read_bytes() if document.exists() else None) != original_document:
            return {"revision": result.revision, "replayed": False,
                    "document_warning": "Working document changed during save and was preserved; read it before updating the projection"}
        atomic_text(document, self.render(current, result.revision))
        return {"revision": result.revision, "replayed": False, "document": str(document.resolve()),
                "meaning": "Saved a sourced working interpretation; quote validation does not prove its semantic correctness"}

    def revise(self, payload, *, actor=None):
        """Replace selected keys without making the caller reconstruct other entries.

        Materialize against the requested historical revision, so an exact retry
        uses the same save envelope even after another revision has been saved.
        The existing save path still checks coverage, quotes and document edits.
        """
        allowed = {"operation_id", "expected_revision", "coverage_token", "purpose", "reason",
                   "entries", "remove_keys", "document_sha256"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ValueError("Unknown revision fields; use entries and optional remove_keys")
        revision = payload.get("expected_revision")
        if type(revision) is not int or not 1 <= revision <= self.ledger.revision:
            raise ValueError("Read an existing understanding revision before revising it")
        base = self.ledger.snapshot(at_revision=revision).state["understanding"]
        edits, removed = payload.get("entries", []), payload.get("remove_keys", [])
        if not isinstance(edits, list) or not isinstance(removed, list) or not (edits or removed):
            raise ValueError("Provide entries to replace/add or remove_keys to remove")
        keys = []
        for entry in edits:
            if not isinstance(entry, dict):
                raise ValueError("Each revised entry must be an object")
            keys.append(nonempty(entry.get("key"), "entry key", 120))
        for key in removed:
            nonempty(key, "removed key", 120)
        if len(set(keys)) != len(keys) or len(set(removed)) != len(removed) or set(keys) & set(removed):
            raise ValueError("Revision keys must be unique and cannot be both replaced and removed")
        if set(removed) - {entry["key"] for entry in base["entries"]}:
            raise ValueError("Cannot remove an unknown understanding key")
        # Stored evidence has checked metadata; callers submit only original refs/quotes.
        entries = {entry["key"]: {**entry, "sources": [
            {"ref": source["ref"], "quote": source["quote"]} for source in entry["sources"]]}
                   for entry in base["entries"] if entry["key"] not in removed}
        entries.update((entry["key"], entry) for entry in edits)
        envelope = {key: value for key, value in payload.items() if key != "remove_keys"}
        envelope.update(purpose=payload.get("purpose", base["purpose"]), entries=list(entries.values()))
        retained = {entry["key"]: entry for entry in base["entries"]
                    if entry["key"] not in set(keys) | set(removed)}
        return self._save(envelope, actor=actor, retained=retained)

    def render(self, current, revision):
        if current is None:
            return ""
        lines = [f"# {self.config['name']}", "", f"Revision: {revision}", "",
                 "Working interpretation; use the current request and check source context.", "", current["purpose"], ""]
        for entry in current["entries"]:
            lines += [f"## {entry['key']} [{entry['scope']}; {entry['status']}]", "", entry["text"], ""]
            for source in entry["sources"]:
                lines += [f"> {source['quote']}", f"Source: {source['ref']} ({source['role']}; {source['source_scope']})", ""]
        return "\n".join(lines)

    def get(self, *, scopes=None, query=None, key=None, chars=12000):
        if not 1 <= chars <= 60000:
            raise ValueError("chars must be 1..60000")
        revision, current = self.snapshot()
        coverage = self.coverage()
        if current is None:
            return {**self.overview(), "entries": [], "next": "Prepare an initial sourced understanding from selected history"}
        selected_scopes = set(scopes) | {"shared"} if scopes else None
        valid_scopes = {s["scope"] for s in self.config["sources"]} | {"shared"}
        if selected_scopes is not None and selected_scopes - valid_scopes:
            raise ValueError("Unknown scope; choose a saved source scope")
        terms = query.casefold().split() if query else []
        candidates = [e for e in current["entries"] if (not selected_scopes or e["scope"] in selected_scopes)
                      and (key is None or e["key"] == key)
                      and all(t in (e["key"] + " " + e["text"]).casefold() for t in terms)]
        entries, remaining = [], chars
        for entry in candidates:
            cost = len(json.dumps(entry, ensure_ascii=False))
            if cost > remaining:
                continue
            problems = []
            for evidence in entry["sources"]:
                try:
                    if self.archive.message(evidence["ref"])["sha256"] != evidence["sha256"]:
                        problems.append({"ref": evidence["ref"], "status": "source_changed"})
                except ValueError:
                    problems.append({"ref": evidence["ref"], "status": "source_missing"})
            entries.append({**entry, "source_warnings": problems})
            remaining -= cost
        document = self.archive.root / "understanding.md"
        data = document.read_bytes() if document.exists() else b""
        return {"name": self.config["name"], "workspace": str(self.archive.root.resolve()), "revision": revision,
                "purpose": current["purpose"], "entries": entries, "omitted_entries": len(candidates)-len(entries),
                "entry_index": [{"key": e["key"], "scope": e["scope"], "status": e["status"]} for e in current["entries"]],
                "coverage": coverage, "needs_review": current["coverage_token"] != coverage["token"]
                    or any(e["source_warnings"] for e in entries),
                "document": str(document.resolve()), "document_sha256": hashlib.sha256(data).hexdigest(),
                "document_edited": data != self.render(current, self.understanding_revision(current)).encode(),
                "retrieval": "literal matching over curated entries; the host chooses conceptual relevance and can search original history"}


def refresh_context(context, *, full=False):
    from .rpc import ReadOnlyCodex
    with ReadOnlyCodex() as client:
        return [context.archive.refresh(client, source["thread"], full=full)
                for source in context.config["sources"]]


def run_context(args):
    """CLI adapter. No model calls, chat messages or native-memory edits."""
    registry = Registry()
    actor = os.environ.get("CODEX_THREAD_ID")
    command = args.command
    if command == "context-list":
        return {"backgrounds": registry.list(args.thread),
                "selection": "exact_source_set" if args.thread else "saved_names",
                "automatic_selection": False}
    if command == "context-init":
        if not args.name:
            raise ValueError("Give this source group a reusable --name")
        if any(x["name"] == args.name for x in registry.list()):
            raise ValueError("Background name already exists; open it or choose a new name")
        payload = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict) or set(payload) != {"sources"}:
            raise ValueError("Selection input contains a sources list")
        directory = Path(args.workspace) if args.workspace else registry.home / "contexts" / uuid4().hex
        context = Context.create(directory, args.name, payload["sources"])
        try:
            registry.register(args.name, directory)
            return context.overview()
        finally:
            context.close()
    if command == "context-open":
        if not actor:
            raise ValueError("Open from a Codex chat with CODEX_THREAD_ID; context-show supports offline reading")
        thread_id(actor)  # Reject an invalid reader before refreshing history or changing a binding.
    directory, bound_scopes = registry.resolve(name=args.name, directory=args.workspace, actor=actor)
    context = Context(directory)
    try:
        if command == "context-register":
            registry.register(context.config["name"], directory)
            return {"registered": context.config["name"], "directory": str(directory.resolve())}
        if command == "context-sync":
            return {"updates": refresh_context(context, full=args.full), "coverage": context.coverage()}
        if command == "context-overview":
            return context.overview()
        if command == "context-changes":
            return context.changes(after=args.after_change, limit=args.limit, chars=args.chars)
        if command == "context-save":
            return context.save(json.loads(Path(args.input).read_text(encoding="utf-8-sig")))
        if command == "context-revise":
            return context.revise(json.loads(Path(args.input).read_text(encoding="utf-8-sig")))
        if command == "context-source":
            return context.add_source(json.loads(Path(args.input).read_text(encoding="utf-8-sig")))
        refreshed = refresh_context(context) if command == "context-open" and args.refresh else None
        scopes = args.scope if args.scope is not None else bound_scopes
        result = context.get(scopes=scopes, query=args.query, key=args.key, chars=args.chars)
        if command == "context-open":
            if refreshed is not None:
                result["refresh"] = refreshed
                if result.get("needs_review"):
                    result["changes"] = context.changes(limit=8, chars=2400)
            registry.register(context.config["name"], directory)
            registry.bind(context.config["name"], actor, scopes)
            result["bound_to"] = thread_id(actor)
            result["delivery"] = "Read in this chat; source chats were not resumed or messaged"
        return result
    finally:
        context.close()
