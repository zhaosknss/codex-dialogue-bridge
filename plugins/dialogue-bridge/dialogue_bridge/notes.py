"""Scoped collaboration records on agent-state-core; no model calls or dispatch."""
from __future__ import annotations

import base64
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path


def require_core():
    root = Path(__file__).resolve().parents[1]
    guidance = f"Prepare a private environment with {root / 'scripts/setup.py'} --environment <private-directory>; see {root / 'skills/dialogue-collaborate/references/setup.md'}"
    try:
        from agent_state_core import Ledger
    except ModuleNotFoundError as exc:
        if exc.name != "agent_state_core":
            raise
        raise ValueError(f"Notes require agent-state-core. {guidance}") from exc
    if not hasattr(Ledger, "view_page"):
        raise ValueError(f"The installed core lacks view_page; old alpha-2 archives are incompatible. {guidance}")
    return Ledger


class Notes:
    KINDS = {"request", "response", "understanding", "correction", "adoption", "withdrawal"}
    FIELDS = {"operation_id", "kind", "key", "text", "scope", "recipients", "sources",
              "supersedes", "relates_to", "metadata"}

    def __init__(self, archive, actor=None):
        Ledger = require_core()
        self.archive = archive
        self.actor = actor or os.environ.get("CODEX_THREAD_ID")
        self.ledger = Ledger(archive.root / "notes.db")
        self.scope = hashlib.sha256(json.dumps({
            "directory": str(archive.root.resolve()), "project": archive.project,
            "threads": sorted(archive.threads),
        }, sort_keys=True).encode()).hexdigest()

    def close(self):
        self.ledger.close()

    def _participant(self, ident=None):
        if not (ident or self.actor):
            raise ValueError("A selected thread ID is required; runtime identity is CODEX_THREAD_ID")
        return self.archive.selected(ident or self.actor)

    def inbox(self, *, participant=None, cursor=None, limit=8):
        from agent_state_core import RecordCursor
        participant = self._participant(participant)
        position, upper = None, None
        if cursor is not None:
            data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if data["scope"] != self.scope or data["participant"] != participant:
                raise ValueError("Cursor belongs to a different workspace or participant")
            position = RecordCursor(**data["position"])
            upper = data["upper"]
        if not 1 <= limit <= 30:
            raise ValueError("limit must be 1..30")
        page = self.ledger.view_page(participant, after=position, at_revision=upper,
                                     kinds=("dialogue_note",), limit=limit)
        token = base64.urlsafe_b64encode(json.dumps({
            "scope": self.scope, "participant": participant,
            "position": asdict(page.next_cursor), "upper": page.revision if page.has_more else None,
        }, sort_keys=True).encode()).decode()
        return {"project": self.archive.project, "participant": participant,
                "notes": [{"id": r.id, "revision": r.revision, **{
                    k: r.body[k] for k in ("kind", "key", "author_thread", "recipients", "supersedes", "relates_to")},
                    "preview": r.body["text"][:240]} for r in page.records],
                "through_revision": page.revision, "next_cursor": token, "has_more": page.has_more,
                "meaning": "visible records only; fetching or saving a cursor does not mean agreement or adoption"}

    def fetch(self, note_id, *, participant=None):
        from agent_state_core import RecordCursor
        participant = self._participant(participant)
        cursor, upper = None, None
        while True:
            page = self.ledger.view_page(participant, after=cursor, at_revision=upper,
                                         kinds=("dialogue_note",), limit=100)
            upper = page.revision
            for record in page.records:
                if record.id == note_id:
                    return {"id": record.id, "revision": record.revision,
                            "body": record.body, "source": record.source}
            if not page.has_more:
                raise ValueError("Note not found in this participant's visible history")
            cursor = page.next_cursor

    def record(self, payload):
        from agent_state_core import Record, Transition
        if not isinstance(payload, dict):
            raise ValueError("Record input must be a JSON object")
        unknown = set(payload) - self.FIELDS
        if unknown:
            names = ", ".join(sorted(map(str, unknown)))
            raise ValueError(f"Unknown record field(s): {names}. Put custom JSON in metadata; no record was written")
        actor = self._participant()
        for key, maximum in [("operation_id", 150), ("key", 150), ("text", 5000), ("scope", 1000)]:
            if not isinstance(payload.get(key), str) or not 1 <= len(payload[key].strip()) <= maximum:
                raise ValueError(f"{key} must contain 1..{maximum} characters")
        kind = payload.get("kind")
        if not isinstance(kind, str) or kind not in self.KINDS:
            raise ValueError("Unknown collaboration note kind")
        if not isinstance(payload.get("recipients"), list) or not payload["recipients"]:
            raise ValueError("Select at least one recipient explicitly")
        recipients = list(dict.fromkeys(self.archive.selected(x) for x in payload["recipients"]))
        sources = payload.get("sources", [])
        if not isinstance(sources, list) or (kind != "request" and not sources):
            raise ValueError("Non-request notes require original-message sources")
        checked = []
        checked_notes = []
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("Each source must contain a message ref and verbatim quote")
            quote = source.get("quote")
            if not isinstance(quote, str) or not quote.strip():
                raise ValueError("Source quote must be nonempty text")
            source_kind = source.get("kind", "message")
            if source_kind == "message":
                message = self.archive.message(source["ref"])
                if quote not in message["text"]:
                    raise ValueError("Source quote does not occur verbatim in the indexed original message")
                # Keep legacy message serialization for idempotent retries after upgrade.
                checked.append({"ref": message["ref"], "quote": quote, "role": message["role"], "sha256": message["sha256"]})
            elif source_kind == "note":
                cited = self.fetch(source["ref"], participant=actor)
                if quote not in cited["body"]["text"]:
                    raise ValueError("Source quote does not occur verbatim in the visible collaboration note")
                digest = hashlib.sha256(json.dumps(cited["body"], ensure_ascii=False, sort_keys=True,
                                                   separators=(",", ":")).encode("utf-8")).hexdigest()
                checked_notes.append({"kind": "note", "ref": cited["id"], "revision": cited["revision"],
                                      "quote": quote, "author_thread": cited["body"]["author_thread"],
                                      "record_kind": cited["body"]["kind"], "record_status": cited["body"]["status"],
                                      "sha256": digest})
            else:
                raise ValueError("Source kind must be message or note")
        if sum(len(x["quote"]) for x in [*checked, *checked_notes]) > 12000:
            raise ValueError("Source quotes exceed 12000 characters; reference focused excerpts instead of copying transcripts")
        supersedes, relates_to = payload.get("supersedes"), payload.get("relates_to")
        for previous_id in filter(None, (supersedes, relates_to)):
            previous = self.fetch(previous_id, participant=actor)
            if previous_id == supersedes and (previous["body"]["author_thread"] != actor or previous["body"]["key"] != payload["key"]):
                raise ValueError("Revise your own interpretation with the same key; use a response to challenge another author")
        if kind == "withdrawal" and not supersedes:
            raise ValueError("Withdrawal must identify the author's previous note")
        body = {"project": self.archive.project, "kind": kind, "key": payload["key"],
                "text": payload["text"], "scope": payload["scope"], "author_thread": actor,
                "recipients": recipients, "supersedes": supersedes, "relates_to": relates_to,
                "status": "withdrawn" if kind == "withdrawal" else "candidate"}
        if "metadata" in payload:
            body["metadata"] = payload["metadata"]
        provenance = {"messages": checked, "authorship": "local runtime thread label; not cryptographic attestation"}
        if checked_notes:
            provenance["notes"] = checked_notes
        # Audience is a set in the core's persisted representation. Canonicalize
        # before replay comparison so an author after its recipients sorts identically.
        record = Record("dialogue_note", body, tuple(sorted({actor, *recipients})), provenance)
        request_id = f"dialogue:{actor}:{payload['operation_id']}"
        previous = self.ledger.get_commit(request_id)
        if previous:
            if previous.transition.records != (record,):
                raise ValueError("operation_id was already committed with different content")
            revision = previous.revision
        else:
            revision = self.ledger.commit(Transition(records=(record,)),
                                          expected_revision=self.ledger.revision, request_id=request_id).revision
        # Obtain the public record ID through the core API rather than inventing it.
        from agent_state_core import RecordCursor
        page = self.ledger.view_page(actor, after=RecordCursor(revision - 1), at_revision=revision, limit=1)
        return {"id": page.records[0].id, "revision": revision, "kind": kind,
                "recipients": recipients, "delivery": "stored for recipient check-in; no chat was resumed or sent a prompt"}
