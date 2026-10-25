"""Independent chat documents, scoped proposals and recoverable Markdown views.

``shared`` is a caller-supplied snapshot with revision, name, sources and entries.
Sources identify thread/scope/label; citations retain their original ref/quote/hash.
The caller verifies quotations against its source archive: neither a reference nor
an exact quotation proves the interpretation true. Local files are host-owned
projections, not a substitute for actor-scoped access through ``view``.

Writes require operation_id and the *global Ledger* expected_revision. Exact
operation retries replay the original committed result before current-state checks.
Chat payloads: text, dependencies (entry keys), optional title/reason/sources/scope,
owner_thread and draft. A cross-owner draft must explicitly set draft=true; its
actual author is retained and it cannot overwrite the owner's own document.
Proposal payloads additionally allow entries/remove_keys/target_key/type.
Import payloads: relative path, document_sha256, optional text, plus write fields.
Imports retain full external bytes as an attributed pending proposal, never as
original-chat participation or an automatically adopted shared rule.

Ledger history is authoritative. Markdown and its private projection manifest can
be rebuilt; unexpected edits are queued before replacement and need explicit
import. File writes use atomic replacement with a last-moment comparison. An
uncooperative editor can still race that final filesystem operation; files and
SQLite do not form one transaction. A retry rebuilds current, never old, views.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from urllib.parse import quote
from uuid import UUID


STATE_KEY = "dialogue_documents"
_WRITE_FIELDS = {"operation_id", "expected_revision"}
_CHAT_FIELDS = {"text", "dependencies", "title", "reason", "sources", "scope",
                "owner_thread", "draft", "document_sha256"}
_PROPOSAL_FIELDS = {"text", "dependencies", "title", "reason", "sources", "scope",
                    "entries", "remove_keys", "target_key", "type"}
_DERIVED_ENTRY_FIELDS = {"source_warnings", "needs_review", "revision", "updated_at"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _bytes_digest(value):
    return hashlib.sha256(value).hexdigest()


def _text(value, field, *, optional=False):
    if optional and value is None:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    if len(value) > 200000:
        raise ValueError(f"{field} exceeds 200000 characters")
    return value


def _thread(value):
    if not isinstance(value, str):
        raise ValueError("actor/owner must be a chat UUID")
    try:
        canonical = str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError("actor/owner must be a chat UUID") from exc
    if canonical != value.lower() or len(value) != 36:
        raise ValueError("actor/owner must be a canonical chat UUID")
    return canonical


def _entry_digest(entry):
    return _digest({k: v for k, v in entry.items() if k not in _DERIVED_ENTRY_FIELDS})


def _empty():
    return {"schema_version": 1, "chats": {}, "proposals": {}, "external_edits": {}}


class DocumentStore:
    """Use a caller-owned agent_state_core Ledger without closing or replacing it.

    ``source_link`` may map a citation/source to a host URL. Otherwise explicit
    url/uri fields are honored and portable source URNs retain exact locators.
    actor=None is a trusted operator read; an actor gets shared + its source scopes.
    Host-issued actor_scopes grant additional scopes; actor_limits can narrow the
    resulting set to the current binding. Neither is accepted in a write payload.
    """

    def __init__(self, ledger, directory, *, source_link=None, actor_scopes=None, actor_limits=None):
        self.ledger = ledger
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.source_link = source_link
        if actor_scopes is not None and not isinstance(actor_scopes, dict):
            raise ValueError("actor_scopes must be a trusted actor-to-scopes mapping")
        self.actor_scopes = {}
        for actor, scopes in (actor_scopes or {}).items():
            actor = _thread(actor)
            if not isinstance(scopes, (list, tuple, set)) or any(not isinstance(s, str) for s in scopes):
                raise ValueError("Trusted actor scopes must be scope names")
            self.actor_scopes[actor] = set(scopes)
        self.actor_limits = {}
        if actor_limits is not None and not isinstance(actor_limits, dict):
            raise ValueError("actor_limits must be a trusted actor-to-scopes mapping")
        for actor, scopes in (actor_limits or {}).items():
            if not isinstance(scopes, (list, tuple, set)) or any(not isinstance(s, str) for s in scopes):
                raise ValueError("Trusted actor limits must be scope names")
            self.actor_limits[_thread(actor)] = set(scopes)

    def _snapshot(self):
        snapshot = self.ledger.snapshot()
        state = deepcopy(snapshot.state.get(STATE_KEY, _empty()))
        if state.get("schema_version") != 1:
            raise ValueError("Unsupported dialogue document schema")
        return snapshot.revision, state

    @staticmethod
    def _shared(shared):
        if not isinstance(shared, dict) or type(shared.get("revision")) is not int or shared["revision"] < 0:
            raise ValueError("shared requires a nonnegative revision")
        if not isinstance(shared.get("sources", []), list) or not isinstance(shared.get("entries", []), list):
            raise ValueError("shared sources and entries must be lists")
        result = deepcopy(shared)
        keys = set()
        source_scopes = {}
        for source in result.get("sources", []):
            source["thread"] = _thread(source.get("thread"))
            _text(source.get("scope"), "source scope")
            if source["thread"] in source_scopes and source_scopes[source["thread"]] != source["scope"]:
                raise ValueError("A selected source cannot have ambiguous scopes")
            source_scopes[source["thread"]] = source["scope"]
        for entry in result.get("entries", []):
            key = _text(entry.get("key"), "shared entry key")
            if key in keys:
                raise ValueError("Shared entry keys must be unique")
            keys.add(key)
            _text(entry.get("scope"), "shared entry scope")
            _text(entry.get("text"), "shared entry text")
        return result

    @staticmethod
    def _allowed(shared, actor=None, scopes=None):
        configured = {"shared", *(s["scope"] for s in shared.get("sources", []))}
        if actor is None:
            allowed = configured
        else:
            actor = _thread(actor)
            allowed = {"shared", *(s["scope"] for s in shared.get("sources", []) if s["thread"] == actor)}
        if scopes is not None:
            if not isinstance(scopes, (list, tuple, set)) or any(not isinstance(s, str) for s in scopes):
                raise ValueError("scopes must be a collection of scope names")
            requested = set(scopes)
            if not requested <= allowed:
                raise ValueError("Requested scope is not permitted for this actor")
            allowed = requested
        return allowed

    def _permissions(self, shared, actor=None, scopes=None):
        """Apply host-issued capabilities; never accept grants in write payloads."""
        allowed = self._allowed(shared, actor)
        if actor is not None:
            grants = self.actor_scopes.get(_thread(actor), set())
            configured = self._allowed(shared)
            if not grants <= configured:
                raise ValueError("Trusted actor grants contain unconfigured scopes")
            allowed |= grants
            limit = self.actor_limits.get(_thread(actor))
            if limit is not None:
                if not limit <= configured:
                    raise ValueError("Trusted actor limits contain unconfigured scopes")
                allowed &= limit
        if scopes is not None:
            if not isinstance(scopes, (list, tuple, set)) or any(not isinstance(s, str) for s in scopes):
                raise ValueError("scopes must be a collection of scope names")
            if not set(scopes) <= allowed:
                raise ValueError("Requested scope is not permitted for this actor")
            allowed &= set(scopes)
        return allowed

    def _scope(self, shared, actor, requested=None):
        allowed = self._permissions(shared, actor)
        own = sorted(allowed - {"shared"})
        scope = requested or (own[0] if own else "shared")
        if scope not in allowed:
            raise ValueError("Scope is not permitted for this actor")
        return scope

    def _sources(self, sources, shared, actor):
        if not isinstance(sources, list):
            raise ValueError("sources must be a list of original source references")
        configured = {s["thread"]: s["scope"] for s in shared.get("sources", [])}
        allowed = self._permissions(shared, actor)
        result = []
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("A source must be an object")
            reference = _text(source.get("ref"), "source ref")
            ident = _thread(source.get("thread", reference.split("/", 1)[0]))
            if reference.split("/", 1)[0] != ident:
                raise ValueError("Source ref and thread disagree")
            if ident not in configured or configured[ident] not in allowed:
                raise ValueError("Source scope is not permitted for this actor")
            if "source_scope" in source and source["source_scope"] != configured[ident]:
                raise ValueError("Source scope disagrees with selected original source")
            if "quote" in source:
                _text(source["quote"], "source quote")
            result.append({**deepcopy(source), "source_scope": configured[ident]})
        return result

    def _dependencies(self, keys, shared, actor):
        if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys) or len(keys) != len(set(keys)):
            raise ValueError("dependencies must be unique shared entry keys")
        entries = {e["key"]: e for e in shared.get("entries", [])}
        allowed = self._permissions(shared, actor)
        result = {}
        for key in keys:
            if key not in entries or entries[key]["scope"] not in allowed:
                raise ValueError("Dependency is missing or outside permitted scopes")
            result[key] = _entry_digest(entries[key])
        return result

    @staticmethod
    def _staleness(document, shared):
        entries = {e["key"]: e for e in shared.get("entries", [])}
        return [{"key": key, "status": "removed" if key not in entries else "changed"}
                for key, digest in document.get("dependency_digests", {}).items()
                if key not in entries or _entry_digest(entries[key]) != digest]

    def _envelope(self, actor, payload, fields):
        actor = _thread(actor)
        if not isinstance(payload, dict) or set(payload) - fields - _WRITE_FIELDS:
            raise ValueError("Unknown document fields")
        operation = _text(payload.get("operation_id"), "operation_id")
        if len(operation) > 150:
            raise ValueError("operation_id exceeds 150 characters")
        if type(payload.get("expected_revision")) is not int or payload["expected_revision"] < 0:
            raise ValueError("expected_revision must be a nonnegative integer")
        return actor, operation

    def _replay(self, actor, payload, kind):
        request = f"documents:{actor}:{payload['operation_id']}"
        previous = self.ledger.get_commit(request)
        if previous:
            body = previous.transition.records[0].body
            if body.get("input_digest") != _digest({"kind": kind, "payload": payload}):
                raise ValueError("operation_id was already committed with different content")
            return {**deepcopy(body["result"]), "replayed": True}
        return None

    def _base(self, payload, shared):
        revision, state = self._snapshot()
        if payload["expected_revision"] != revision:
            raise ValueError("Documents changed; read the current revision before saving")
        if shared["revision"] > revision:
            raise ValueError("Shared snapshot revision is newer than the Ledger")
        # A stale snapshot must not be used to label dependencies as current.
        self._check_shared_snapshot(shared, revision)
        state["shared_selection"] = deepcopy(shared)
        return revision, state

    def _check_shared_snapshot(self, shared, revision):
        understanding = self.ledger.snapshot(at_revision=revision).state.get("understanding")
        if understanding is not None:
            expected = {e["key"]: _entry_digest(e) for e in understanding.get("entries", [])}
            supplied = {e["key"]: _entry_digest(e) for e in shared.get("entries", [])}
            if expected != supplied:
                raise ValueError("Shared entries changed; refresh the shared snapshot")

    def _commit(self, actor, payload, kind, state, result, *, audience=()):
        from agent_state_core import Record, Transition
        record = Record("dialogue_documents_" + kind,
                        {"author_thread": actor, "input_digest": _digest({"kind": kind, "payload": payload}),
                         "result": result}, tuple(sorted({actor, *audience})),
                        {"meaning": "Sourced working interpretations and proposals, not user instructions"})
        self.ledger.commit(Transition(updates={STATE_KEY: state}, records=(record,)),
                           expected_revision=payload["expected_revision"],
                           request_id=f"documents:{actor}:{payload['operation_id']}")
        return {**deepcopy(result), "replayed": False}

    def save_chat(self, actor, payload, shared):
        actor, _ = self._envelope(actor, payload, _CHAT_FIELDS)
        replay = self._replay(actor, payload, "chat")
        if replay is not None:
            return replay
        shared = self._shared(shared)
        revision, state = self._base(payload, shared)
        owner = _thread(payload.get("owner_thread", actor))
        if "draft" in payload and type(payload["draft"]) is not bool:
            raise ValueError("draft must be a boolean")
        scope = self._scope(shared, actor, payload.get("scope"))
        if owner != actor:
            owner_scopes = {s["scope"] for s in shared.get("sources", []) if s["thread"] == owner}
            if not payload.get("draft") or not owner_scopes or not owner_scopes <= self._permissions(shared, actor):
                raise ValueError("A cross-owner draft needs explicit draft=true and permitted owner scopes")
            if owner in state["chats"] and state["chats"][owner]["author_thread"] == owner:
                raise ValueError("A derived draft cannot replace the owner's own document")
        path = f"chats/{owner}.md"
        acknowledged = None
        has_acknowledged_edit = self._dirty(path)
        if has_acknowledged_edit:
            acknowledged = self._file_hash(path)
            imported = any(e["path"] == path and e["sha256"] == acknowledged
                           for e in state["external_edits"].values())
            if "document_sha256" not in payload or payload["document_sha256"] != acknowledged or not imported:
                raise ValueError("The chat document was edited externally; import it and acknowledge document_sha256 before saving")
        dependencies = self._dependencies(payload.get("dependencies", []), shared, actor)
        entry_scopes = {e["key"]: e["scope"] for e in shared.get("entries", [])}
        old = state["chats"].get(owner)
        document = {"owner_thread": owner, "actor": owner, "author_thread": actor,
                    "authorship": "original_chat" if owner == actor else "derived_draft",
                    "scope": scope, "title": _text(payload.get("title", "Chat understanding"), "title"),
                    "text": _text(payload.get("text"), "text"),
                    "dependencies": list(dependencies), "dependency_digests": dependencies,
                    "dependency_scopes": {key: entry_scopes[key] for key in dependencies},
                    "shared_revision": shared["revision"], "sources": self._sources(payload.get("sources", []), shared, actor),
                    "reason": _text(payload.get("reason"), "reason", optional=True),
                    "revision": revision + 1, "previous_revision": old["revision"] if old else None}
        if owner != actor:
            document["derived_by"] = actor
        if has_acknowledged_edit:
            document["superseded_external_sha256"] = acknowledged
        state["chats"][owner] = document
        result = self._commit(actor, payload, "chat", state,
                              {"revision": revision + 1, "owner_thread": owner, "author_thread": actor,
                               "document": path, "authorship": document["authorship"]}, audience=(owner,))
        self.materialize(shared)
        return result

    def _proposal(self, actor, payload, shared, revision):
        scope = self._scope(shared, actor, payload.get("scope", "shared"))
        dependencies = self._dependencies(payload.get("dependencies", []), shared, actor)
        entries = payload.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("entries must be a list")
        checked, keys = [], set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Proposed entry must be an object")
            key = _text(entry.get("key"), "entry key")
            if key in keys:
                raise ValueError("Proposed entry keys must be unique")
            keys.add(key)
            _text(entry.get("scope"), "entry scope")
            self._scope(shared, actor, entry["scope"])
            _text(entry.get("text"), "entry text")
            evidence = self._sources(entry.get("sources", []), shared, actor)
            if not evidence:
                raise ValueError("A structured shared entry requires original sources")
            checked.append({**deepcopy(entry), "sources": evidence})
        remove = payload.get("remove_keys", [])
        self._dependencies(remove, shared, actor)
        if set(remove) & keys:
            raise ValueError("Cannot replace and remove the same shared entry")
        text = payload.get("text", "Proposed changes to shared entries" if entries or remove else None)
        sources = self._sources(payload.get("sources", []), shared, actor)
        entries_by_key = {e["key"]: e for e in shared.get("entries", [])}
        for key in [*remove, *(key for key in keys if key in entries_by_key)]:
            self._dependencies([key], shared, actor)
            dependencies[key] = _entry_digest(entries_by_key[key])
        proposal_id = "proposal-" + _digest([actor, payload["operation_id"]])[:24]
        proposal = {"id": proposal_id, "author_thread": actor, "scope": scope,
                    "text": _text(text, "text"), "sources": sources,
                    "dependencies": list(dependencies), "dependency_digests": dependencies,
                    "dependency_scopes": {key: entries_by_key[key]["scope"] for key in dependencies},
                    "shared_revision": shared["revision"], "revision": revision + 1,
                    "status": "pending", "reason": _text(payload.get("reason"), "reason", optional=True),
                    "title": _text(payload.get("title", "Proposed understanding update"), "title"),
                    "type": payload.get("type", "interpretation"),
                    "evidence_status": "references_supplied" if sources or checked or dependencies else "unsourced_proposal",
                    "meaning": "Author's proposal; not a user decision, global policy, or proof of adoption"}
        for field in ("entries", "remove_keys", "target_key"):
            if field in payload:
                proposal[field] = checked if field == "entries" else deepcopy(payload[field])
        return proposal

    def propose(self, actor, payload, shared):
        actor, _ = self._envelope(actor, payload, _PROPOSAL_FIELDS)
        replay = self._replay(actor, payload, "proposal")
        if replay is not None:
            return replay
        shared = self._shared(shared)
        revision, state = self._base(payload, shared)
        proposal = self._proposal(actor, payload, shared, revision)
        state["proposals"][proposal["id"]] = proposal
        result = self._commit(actor, payload, "proposal", state,
                              {"revision": revision + 1, "proposal_id": proposal["id"], "status": "pending"})
        self.materialize(shared)
        return result

    def proposals(self, actor=None, scopes=None):
        """Read proposals with scope filtering derived from persisted space metadata."""
        revision, state = self._snapshot()
        shared = self._persisted_shared(state, revision)
        allowed = self._permissions(shared, actor, scopes)
        rows = [deepcopy(p) for p in state["proposals"].values()
                if p["scope"] in allowed and self._evidence_visible(p, allowed, shared)]
        for row in rows:
            row["dependency_changes"] = self._staleness(row, shared)
            row["needs_review"] = bool(row["dependency_changes"])
        return {"revision": revision, "proposals": rows}

    def _persisted_shared(self, state, revision):
        shared = deepcopy(state.get("shared_selection", {"sources": [], "entries": []}))
        understanding = self.ledger.snapshot(at_revision=revision).state.get("understanding")
        if understanding is not None:
            shared["entries"] = deepcopy(understanding.get("entries", []))
        shared["revision"] = revision
        return shared

    def resolve(self, actor, proposal_id, status, reason, *, operation_id=None, expected_revision=None):
        """Record review disposition only. Applying shared changes is the caller's job.

        The optional CAS/operation parameters support explicit remote retries; the
        default ID is deterministic for this exact proposal/status/reason/actor.
        """
        actor = _thread(actor)
        proposal_id = _text(proposal_id, "proposal_id")
        reason = _text(reason, "reason")
        if status not in {"accepted", "rejected", "withdrawn", "deferred"}:
            raise ValueError("Invalid proposal resolution status")
        operation = operation_id or "resolve-" + _digest([proposal_id, status, reason])[:32]
        # The original base is restored for generated-ID retries.
        previous = self.ledger.get_commit(f"documents:{actor}:{operation}")
        if expected_revision is None and previous:
            expected_revision = previous.revision - 1
        revision, state = self._snapshot()
        payload = {"operation_id": operation, "expected_revision": revision if expected_revision is None else expected_revision,
                   "proposal_id": proposal_id, "status": status, "reason": reason}
        self._envelope(actor, payload, {"proposal_id", "status", "reason"})
        replay = self._replay(actor, payload, "resolve")
        if replay is not None:
            return replay
        if payload["expected_revision"] != revision:
            raise ValueError("Documents changed; read the current revision before resolving")
        proposal = state["proposals"].get(proposal_id)
        if proposal is None:
            raise ValueError("Unknown proposal")
        selection = self._persisted_shared(state, revision)
        allowed = self._permissions(selection, actor)
        if proposal["scope"] not in allowed or not self._evidence_visible(proposal, allowed, selection):
            raise ValueError("Proposal scope is not permitted for this actor")
        if status == "withdrawn" and proposal["author_thread"] != actor:
            raise ValueError("Only the author can withdraw a proposal")
        if proposal["status"] in {"accepted", "rejected", "withdrawn"}:
            raise ValueError("Proposal has already been resolved")
        proposal.setdefault("resolutions", []).append({"actor": actor, "status": status, "reason": reason,
                                                       "revision": revision + 1})
        proposal.update(status=status, resolved_by=actor, resolution_reason=reason,
                        resolution_revision=revision + 1)
        if proposal.get("external_edit_id") and status in {"accepted", "rejected", "withdrawn"}:
            state["external_edits"][proposal["external_edit_id"]]["projection_disposition"] = status
        result = self._commit(actor, payload, "resolve", state,
                              {"revision": revision + 1, "proposal_id": proposal_id, "status": status,
                               "meaning": "Review disposition only; shared adoption requires a separate sourced revision"})
        self.materialize(selection)
        return result

    @staticmethod
    def _citation_scope(source, shared):
        configured = {s["thread"]: s["scope"] for s in shared.get("sources", [])}
        return source.get("source_scope", configured.get(source.get("thread", source.get("ref", "").split("/", 1)[0])))

    def _evidence_visible(self, item, allowed, shared):
        if not set(item.get("dependency_scopes", {}).values()) <= allowed:
            return False
        evidence = list(item.get("sources", []))
        for entry in item.get("entries", []):
            evidence.extend(entry.get("sources", []))
            if entry.get("scope") not in allowed:
                return False
        return all(self._citation_scope(s, shared) in allowed for s in evidence)

    def view(self, shared, *, actor=None, scopes=None):
        shared = self._shared(shared)
        revision, state = self._snapshot()
        self._check_shared_snapshot(shared, revision)
        allowed = self._permissions(shared, actor, scopes)
        visible = deepcopy(shared)
        visible["sources"] = [s for s in shared.get("sources", []) if s["scope"] in allowed]
        visible["entries"] = []
        for entry in shared.get("entries", []):
            if entry["scope"] not in allowed:
                continue
            clean = deepcopy(entry)
            evidence = clean.get("sources", [])
            clean["sources"] = [s for s in evidence if self._citation_scope(s, shared) in allowed]
            if len(clean["sources"]) != len(evidence):
                clean["omitted_sources"] = len(evidence) - len(clean["sources"])
            visible["entries"].append(clean)
        if actor is not None and "coverage" in visible:
            visible["coverage"] = {k: v for k, v in visible["coverage"].items()
                                   if k in {"token", "all_sources_indexed", "meaning", "change"}}
        visible["text"] = self._render_shared(visible)
        chats = []
        for document in state["chats"].values():
            if document["scope"] not in allowed or not self._evidence_visible(document, allowed, shared):
                continue
            # A dependency can itself be project restricted even if the chat's
            # declared scope is shared; do not expose its interpretation across it.
            entries = {e["key"]: e for e in shared.get("entries", [])}
            if any(k in entries and entries[k]["scope"] not in allowed for k in document["dependencies"]):
                continue
            clean = deepcopy(document)
            clean["dependency_changes"] = self._staleness(document, shared)
            clean["needs_review"] = bool(clean["dependency_changes"])
            chats.append(clean)
        proposals = [deepcopy(p) for p in state["proposals"].values()
                     if p["scope"] in allowed and self._evidence_visible(p, allowed, shared)]
        for proposal in proposals:
            proposal["dependency_changes"] = self._staleness(proposal, shared)
            proposal["needs_review"] = bool(proposal["dependency_changes"])
        external = [deepcopy(e) for e in state["external_edits"].values()
                    if e["scope"] in allowed and (actor is None or e["author_thread"] == actor)]
        paths = {"INDEX.md", "shared.md", *(f"chats/{d['owner_thread']}.md" for d in chats)}
        dirty = [{"path": p, "sha256": self._file_hash(p)} for p in sorted(paths) if self._dirty(p)]
        return {"revision": revision, "shared": visible, "chats": chats, "proposals": proposals,
                "external_edits": external, "dirty_documents": dirty,
                "meaning": "Working interpretations; source identity and scope are checked, semantic truth is not inferred"}

    def _path(self, relative):
        if not isinstance(relative, str) or "\\" in relative or PurePosixPath(relative).is_absolute():
            raise ValueError("Use an allowlisted relative document path")
        parts = PurePosixPath(relative).parts
        valid = relative in {"INDEX.md", "shared.md"}
        if len(parts) == 2 and parts[0] == "chats" and parts[1].endswith(".md"):
            _thread(parts[1][:-3])
            valid = True
        if not valid or str(PurePosixPath(relative)) != relative:
            raise ValueError("Document path must be INDEX.md, shared.md or chats/<UUID>.md")
        target = self.directory / relative
        if not target.resolve().is_relative_to(self.directory):
            raise ValueError("Document path escapes the understanding directory")
        return target

    def _private(self, relative):
        target = self.directory / ".dialogue-documents" / relative
        if not target.resolve().is_relative_to(self.directory):
            raise ValueError("Private projection path escapes the understanding directory")
        return target

    def _manifest(self):
        path = self._private("projections.json")
        if not path.exists():
            return {"version": 1, "files": {}}
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("files"), dict):
            raise ValueError("Invalid projection manifest; preserve it before rebuilding")
        return data

    def _file_hash(self, relative):
        path = self._path(relative)
        return _bytes_digest(path.read_bytes()) if path.exists() else None

    def _dirty(self, relative):
        previous = self._manifest()["files"].get(relative)
        path = self._path(relative)
        if previous is None:
            return path.exists()
        return self._file_hash(relative) != previous["sha256"]

    @staticmethod
    def _atomic(path, data, *, previous=None, compare=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".dialogue-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if compare and (path.read_bytes() if path.exists() else None) != previous:
                return False
            os.replace(temporary, path)
            return True
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _queue(self, relative, current, revision):
        edit_id = "external-" + _digest([relative, _bytes_digest(current) if current is not None else None])[:32]
        path = self._private(f"pending/{edit_id}.json")
        if not path.exists():
            try:
                text = current.decode("utf-8-sig") if current is not None else None
                encoding = "utf-8"
            except UnicodeDecodeError:
                text, encoding = None, "base64"
            data = {"id": edit_id, "path": relative, "sha256": _bytes_digest(current) if current is not None else None,
                    "text": text, "encoding": encoding,
                    "detected_at_revision": revision, "origin": "external_edit", "editor": "unknown"}
            if encoding == "base64":
                data["bytes_base64"] = base64.b64encode(current).decode("ascii")
            self._atomic(path, (_json(data) + "\n").encode("utf-8"))
        return {"id": edit_id, "path": relative, "sha256": _bytes_digest(current) if current is not None else None,
                "status": "pending_import", "editor": "unknown"}

    def _link(self, source):
        if self.source_link:
            return str(self.source_link(source))
        return source.get("url", source.get("uri", "urn:dialogue-source:" + quote(source.get("ref", source.get("thread", "")), safe="")))

    def _evidence(self, sources):
        lines = []
        for source in sources:
            reference = source.get("ref", source.get("thread", "source"))
            lines.append(f"- [{reference}]({self._link(source)})")
            if source.get("quote"):
                lines.extend("> " + line for line in source["quote"].splitlines())
        return "\n".join(lines)

    def _render_shared(self, shared):
        lines = ["# " + shared.get("name", "Shared understanding"), "",
                 f"Shared snapshot revision: {shared['revision']}", "",
                 "Sourced working interpretations; not permanent user instructions.", ""]
        for entry in shared.get("entries", []):
            lines += [f"## {entry['key']}", "", f"Scope: {entry['scope']}", "", entry["text"], "",
                      self._evidence(entry.get("sources", [])), ""]
        return "\n".join(lines).rstrip() + "\n"

    def _render_chat(self, document, shared):
        changes = self._staleness(document, shared)
        lines = ["# " + document["title"], "", f"Owner: {document['owner_thread']}",
                 f"Author: {document['author_thread']} ({document['authorship']})",
                 f"Scope: {document['scope']}; document revision: {document['revision']}", ""]
        if changes:
            lines += ["Needs review: " + ", ".join(x["key"] + " (" + x["status"] + ")" for x in changes), ""]
        if document["dependencies"]:
            lines += ["Shared dependencies: " + ", ".join(
                f"[{key}](../shared.md#{quote(key.lower().replace(' ', '-'))})" for key in document["dependencies"]), ""]
        lines += ["<!-- dialogue-body:start -->", document["text"], "<!-- dialogue-body:end -->", "",
                  self._evidence(document.get("sources", [])), ""]
        return "\n".join(lines).rstrip() + "\n"

    def _render_index(self, state, shared):
        lines = ["# Understanding index", "", "[Shared understanding](shared.md)", "",
                 "Read relevant entries and original evidence; chat documents retain independent views.", "",
                 "## Shared entries", ""]
        for entry in shared.get("entries", []):
            lines.append(f"- [{entry['key']}](shared.md#{quote(entry['key'].lower().replace(' ', '-'))}) — {entry['scope']}")
        lines += ["", "## Chat documents", ""]
        for owner, document in sorted(state["chats"].items()):
            review = " — needs review" if self._staleness(document, shared) else ""
            lines.append(f"- [{document['title']}](chats/{owner}.md) — {document['scope']}; author {document['author_thread']}{review}")
        lines += ["", "## Proposals", ""]
        for proposal in state["proposals"].values():
            lines.append(f"- {proposal['id']}: {proposal['title']} ({proposal['status']}, {proposal['scope']})")
        return "\n".join(lines).rstrip() + "\n"

    def materialize(self, shared):
        """Render current views; preserve and queue unexpected edits/deletions.

        Recovering a partial prior render is safe: a file already equal to the
        current desired projection is accepted even if its manifest update failed.
        This method does not commit a new Ledger revision.
        """
        shared = self._shared(shared)
        revision, state = self._snapshot()
        self._check_shared_snapshot(shared, revision)
        desired = {"shared.md": self._render_shared(shared), "INDEX.md": self._render_index(state, shared)}
        desired.update({f"chats/{owner}.md": self._render_chat(doc, shared) for owner, doc in state["chats"].items()})
        manifest = self._manifest()
        written, conflicts = [], []
        for relative, text in desired.items():
            path = self._path(relative)
            data = text.encode("utf-8")
            previous = path.read_bytes() if path.exists() else None
            actual_hash = _bytes_digest(previous) if previous is not None else None
            baseline = manifest["files"].get(relative)
            accepted = any(e["path"] == relative and e["sha256"] == actual_hash
                           and e.get("projection_disposition") in {"accepted", "rejected", "withdrawn"}
                           for e in state["external_edits"].values())
            if relative.startswith("chats/"):
                document = state["chats"].get(relative[6:-3], {})
                accepted = accepted or ("superseded_external_sha256" in document and
                    document.get("superseded_external_sha256") == actual_hash)
            clean = previous == data or (baseline is None and previous is None) or (
                baseline is not None and actual_hash == baseline["sha256"]) or accepted
            if not clean:
                conflicts.append(self._queue(relative, previous, revision))
                continue
            if previous != data:
                if self.ledger.revision != revision:
                    return {"revision": revision, "written": written, "conflicts": conflicts,
                            "interrupted": "Ledger changed during materialization; render the current snapshot again"}
                if not self._atomic(path, data, previous=previous, compare=True):
                    latest = path.read_bytes() if path.exists() else None
                    conflicts.append(self._queue(relative, latest, revision))
                    continue
                written.append(relative)
            manifest["files"][relative] = {"sha256": _bytes_digest(data), "revision": revision}
        self._atomic(self._private("projections.json"), (_json(manifest) + "\n").encode("utf-8"))
        return {"revision": revision, "written": written, "conflicts": conflicts,
                "meaning": "Generated local views; external edits remain pending until explicit import"}

    def ingest_document(self, actor, payload, shared):
        actor, _ = self._envelope(actor, payload, {"path", "text", "document_sha256", "scope", "reason"})
        replay = self._replay(actor, payload, "import")
        if replay is not None:
            return replay
        shared = self._shared(shared)
        revision, state = self._base(payload, shared)
        relative = payload.get("path", f"chats/{actor}.md")
        path = self._path(relative)
        if relative.startswith("chats/") and relative != f"chats/{actor}.md":
            raise ValueError("An actor may import only its own chat document")
        supplied = payload.get("text")
        if supplied is not None and not isinstance(supplied, str):
            raise ValueError("Imported text must be a string")
        if supplied is None and relative in {"INDEX.md", "shared.md"}:
            # The generated host-wide files can contain multiple project scopes.
            # A narrower actor can still submit explicitly supplied correction
            # text, but cannot obtain unrelated contents by importing from disk.
            required = {e["scope"] for e in shared.get("entries", [])}
            for entry in shared.get("entries", []):
                required.update(self._citation_scope(s, shared) for s in entry.get("sources", []))
            if relative == "INDEX.md":
                required.update(d["scope"] for d in state["chats"].values())
                required.update(p["scope"] for p in state["proposals"].values())
            if not required <= self._permissions(shared, actor):
                raise ValueError("The host-wide document contains other scopes; submit explicit scoped text instead")
        raw = supplied.encode("utf-8") if supplied is not None else (path.read_bytes() if path.exists() else None)
        actual = _bytes_digest(raw) if raw is not None else None
        if "document_sha256" not in payload or payload["document_sha256"] != actual:
            raise ValueError("External document hash changed; read the exact edit before importing")
        queued = self._queue(relative, raw, revision)
        scope = self._scope(shared, actor, payload.get("scope", "shared" if relative in {"INDEX.md", "shared.md"} else None))
        edit = {**queued, "text": raw.decode("utf-8-sig") if raw is not None else None,
                "scope": scope, "author_thread": actor, "editor": "unknown", "origin": "external_edit",
                "revision": revision + 1, "reason": _text(payload.get("reason"), "reason", optional=True),
                "meaning": "Explicitly imported external edit; importer identity does not establish editor identity or user approval"}
        existing = state["external_edits"].get(edit["id"])
        if existing is not None:
            raise ValueError("This external edit was already imported; use its original operation_id to retry")
        proposal_id = "proposal-" + _digest([actor, payload["operation_id"]])[:24]
        proposal = {"id": proposal_id, "author_thread": actor, "scope": scope,
                    "text": edit["text"] if edit["text"] is not None else f"External deletion of {relative}",
                    "title": f"External edit: {relative}", "type": "external_edit", "status": "pending",
                    "sources": [], "dependencies": [], "dependency_digests": {}, "external_edit_id": edit["id"],
                    "shared_revision": shared["revision"], "revision": revision + 1,
                    "evidence_status": "external_edit_unverified", "editor": "unknown",
                    "meaning": "Pending external revision; requires sourced review before adoption"}
        state["external_edits"][edit["id"]] = edit
        state["proposals"][proposal_id] = proposal
        state["shared_selection"] = deepcopy(shared)
        return self._commit(actor, payload, "import", state,
                            {"revision": revision + 1, "external_edit_id": edit["id"],
                             "proposal_id": proposal_id, "status": "pending", "editor": "unknown"})
