"""Fictional, model-free checks for scoped understanding and editable projections."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "dialogue-bridge"
sys.path.insert(0, str(PLUGIN))
if os.environ.get("AGENT_STATE_CORE_PATH"):
    sys.path.insert(0, os.environ["AGENT_STATE_CORE_PATH"])

from agent_state_core import Ledger, Transition, StaleRevision
from dialogue_understanding import DocumentStore

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
C = "00000000-0000-4000-8000-000000000003"
D = "00000000-0000-4000-8000-000000000004"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = Ledger(self.root / "state.db")
        self.shared = {"revision": 0, "name": "Fictional writing space", "sources": [
            {"thread": A, "scope": "story", "label": "Story author"},
            {"thread": B, "scope": "research", "label": "Research author"},
            {"thread": C, "scope": "story", "label": "Second story author"},
        ], "entries": [
            {"key": "explore", "scope": "shared", "text": "Discussion may remain exploratory.",
             "sources": [{"ref": A + "/turn-1/message-1", "quote": "Let us discuss first.", "sha256": "fictional-1"}]},
            {"key": "story-context", "scope": "story", "text": "A particular fictional draft needs a slow opening.",
             "sources": [{"ref": A + "/turn-2/message-2", "quote": "This opening should be slower."}]},
            {"key": "research-context", "scope": "research", "text": "A fictional observation needs its denominator.",
             "sources": [{"ref": B + "/turn-1/message-1", "quote": "Keep the denominator."}]},
        ], "coverage": {"token": "fictional-coverage", "all_sources_indexed": True,
                         "history": {"secret": "not for other scopes"}}}
        self.change_shared()
        self.store = DocumentStore(self.ledger, self.root / "documents")

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def change_shared(self):
        self.ledger.commit(Transition(updates={"understanding": {
            "entries": copy.deepcopy(self.shared["entries"]), "purpose": "Fictional background"}}),
            expected_revision=self.ledger.revision)
        self.shared["revision"] = self.ledger.revision

    def payload(self, operation="save", **changes):
        result = {"operation_id": operation, "expected_revision": self.ledger.revision,
                  "text": "My own interpretation for this task.", "dependencies": ["explore"]}
        result.update(changes)
        return result

    def own_path(self, actor=A):
        return self.store.directory / "chats" / (actor + ".md")

    def test_chat_is_sourced_authored_and_shared_state_is_preserved(self):
        understanding = copy.deepcopy(self.ledger.snapshot().state["understanding"])
        result = self.store.save_chat(A, self.payload(sources=[self.shared["entries"][0]["sources"][0]]), self.shared)
        self.assertEqual(result["revision"], 2)
        self.assertEqual(self.ledger.snapshot().state["understanding"], understanding)
        doc = self.store.view(self.shared, actor=A)["chats"][0]
        self.assertEqual(doc["author_thread"], A)
        self.assertEqual(doc["authorship"], "original_chat")
        self.assertEqual(doc["sources"][0]["quote"], "Let us discuss first.")
        self.assertFalse(doc["needs_review"])
        for filename in ("INDEX.md", "shared.md", "chats/" + A + ".md"):
            self.assertTrue((self.store.directory / filename).is_file())
        self.assertIn("urn:dialogue-source:", self.own_path().read_text(encoding="utf-8"))
        self.assertIn("author " + A, (self.store.directory / "INDEX.md").read_text(encoding="utf-8"))

    def test_exact_retry_uses_original_result_without_rolling_back_later_document(self):
        original = self.payload("original")
        result = self.store.save_chat(A, original, self.shared)
        self.store.save_chat(A, self.payload("new", text="A later interpretation."), self.shared)
        before = self.own_path().read_bytes()
        self.shared["entries"][0]["text"] = "Changed shared interpretation."
        self.change_shared()
        replay = self.store.save_chat(A, original, self.shared)
        self.assertEqual({**result, "replayed": True}, replay)
        self.assertEqual(self.own_path().read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "different content"):
            self.store.save_chat(A, {**original, "text": "Not the same retry."}, self.shared)
        with self.assertRaisesRegex(ValueError, "different content"):
            self.store.propose(A, original, self.shared)

    def test_scope_checks_precede_documents_and_cannot_be_spoofed_by_source_label(self):
        for changes in (
            {"scope": "research"}, {"dependencies": ["research-context"]},
            {"sources": [self.shared["entries"][2]["sources"][0]]},
            {"sources": [{**self.shared["entries"][0]["sources"][0], "source_scope": "research"}]},
            {"sources": [{"ref": A + "/t/m", "thread": B, "quote": "Invented identity"}]},
        ):
            with self.assertRaises(ValueError):
                self.store.save_chat(A, self.payload(**changes), self.shared)
        self.assertEqual(self.ledger.revision, 1)
        self.assertFalse(self.own_path().exists())
        with self.assertRaisesRegex(ValueError, "scope"):
            self.store.view(self.shared, actor=A, scopes=["research"])

    def test_views_filter_scope_and_do_not_leak_restricted_sources_or_dependencies(self):
        self.store.save_chat(A, self.payload("story", scope="shared", dependencies=["story-context"]), self.shared)
        self.store.save_chat(B, self.payload("research", dependencies=["research-context"]), self.shared)
        view = self.store.view(self.shared, actor=B)
        self.assertEqual([d["owner_thread"] for d in view["chats"]], [B])
        self.assertEqual({e["key"] for e in view["shared"]["entries"]}, {"explore", "research-context"})
        shared_entry = view["shared"]["entries"][0]
        self.assertEqual(shared_entry["sources"], [])
        self.assertEqual(shared_entry["omitted_sources"], 1)
        self.assertNotIn("history", view["shared"]["coverage"])
        self.assertEqual(len(self.store.view(self.shared)["chats"]), 2)
        self.assertEqual(self.store.view(self.shared, actor=D)["chats"], [])
        self.shared["entries"] = [e for e in self.shared["entries"] if e["key"] != "story-context"]
        self.change_shared()
        self.assertEqual([d["owner_thread"] for d in self.store.view(self.shared, actor=B)["chats"]], [B])

    def test_only_dependencies_of_changed_or_removed_entries_need_review(self):
        self.store.save_chat(A, self.payload("a"), self.shared)
        self.store.save_chat(B, self.payload("b", dependencies=["research-context"]), self.shared)
        self.shared["entries"][2]["text"] = "Keep denominator and sample context."
        self.change_shared()
        docs = {d["actor"]: d for d in self.store.view(self.shared)["chats"]}
        self.assertFalse(docs[A]["needs_review"])
        self.assertTrue(docs[B]["needs_review"])
        self.store.save_chat(B, self.payload("b-reviewed", dependencies=["research-context"]), self.shared)
        self.shared["entries"] = self.shared["entries"][1:]
        self.change_shared()
        docs = {d["actor"]: d for d in self.store.view(self.shared)["chats"]}
        self.assertEqual(docs[A]["dependency_changes"], [{"key": "explore", "status": "removed"}])
        self.assertFalse(docs[B]["needs_review"])
        self.store.materialize(self.shared)
        self.assertIn("Needs review: explore (removed)", self.own_path().read_text(encoding="utf-8"))

    def test_source_hash_change_counts_but_coverage_and_unrelated_ledger_changes_do_not(self):
        self.store.save_chat(A, self.payload(), self.shared)
        self.ledger.commit(Transition(updates={"unrelated": "a worker checkpoint"}), expected_revision=self.ledger.revision)
        self.shared["revision"] = self.ledger.revision
        self.shared["coverage"]["token"] = "a-new-history-token"
        self.assertFalse(self.store.view(self.shared)["chats"][0]["needs_review"])
        self.shared["entries"][0]["sources"][0]["sha256"] = "new-original-source-version"
        self.change_shared()
        self.assertTrue(self.store.view(self.shared)["chats"][0]["needs_review"])

    def test_structured_proposals_retain_attribution_and_never_adopt_themselves(self):
        entry = copy.deepcopy(self.shared["entries"][0])
        entry["text"] = "The author proposes a narrower interpretation."
        payload = self.payload("proposal", entries=[entry], remove_keys=["story-context"], scope="story")
        understanding = copy.deepcopy(self.ledger.snapshot().state["understanding"])
        result = self.store.propose(A, payload, self.shared)
        proposal = self.store.proposals(actor=A)["proposals"][0]
        self.assertEqual(proposal["author_thread"], A)
        self.assertEqual(proposal["entries"][0]["sources"][0]["quote"], "Let us discuss first.")
        self.assertEqual(self.store.proposals(actor=B)["proposals"], [])
        resolved = self.store.resolve(A, result["proposal_id"], "accepted", "Review finished; adoption is separate.")
        self.assertEqual(self.ledger.snapshot().state["understanding"], understanding)
        self.assertEqual(self.store.resolve(A, result["proposal_id"], "accepted", "Review finished; adoption is separate."),
                         {**resolved, "replayed": True})
        self.assertEqual(self.store.propose(A, payload, self.shared), {**result, "replayed": True})
        with self.assertRaisesRegex(ValueError, "already been resolved"):
            self.store.resolve(A, result["proposal_id"], "rejected", "A different resolution.")

    def test_proposal_review_cannot_cross_its_evidence_scope(self):
        payload = self.payload("proposal", sources=[self.shared["entries"][0]["sources"][0]], scope="shared")
        result = self.store.propose(A, payload, self.shared)
        self.assertEqual(self.store.proposals(actor=B)["proposals"], [])
        with self.assertRaisesRegex(ValueError, "scope"):
            self.store.resolve(B, result["proposal_id"], "accepted", "Cannot read this evidence.")
        with self.assertRaisesRegex(ValueError, "author"):
            self.store.resolve(C, result["proposal_id"], "withdrawn", "Not my proposal.")
        self.store.propose(A, self.payload("dependent", dependencies=["story-context"], scope="shared"), self.shared)
        self.assertEqual(self.store.proposals(actor=B)["proposals"], [])

    def test_drafts_retain_real_author_and_do_not_impersonate_or_replace_original_chat(self):
        payload = self.payload("draft", owner_thread=A, draft=True)
        result = self.store.save_chat(C, payload, self.shared)
        self.assertEqual(result["authorship"], "derived_draft")
        doc = self.store.view(self.shared)["chats"][0]
        self.assertEqual(doc["derived_by"], C)
        self.assertEqual(doc["owner_thread"], A)
        self.store.save_chat(A, self.payload("original-chat"), self.shared)
        with self.assertRaisesRegex(ValueError, "owner's own"):
            self.store.save_chat(C, self.payload("replace", owner_thread=A, draft=True), self.shared)
        with self.assertRaisesRegex(ValueError, "permitted owner scopes"):
            self.store.save_chat(B, self.payload("cross", owner_thread=C, draft=True), self.shared)
        with self.assertRaisesRegex(ValueError, "UUID"):
            self.store.save_chat(A, self.payload("bad-owner", owner_thread="../../bad"), self.shared)

    def test_external_chat_edit_is_preserved_queued_imported_and_explicitly_acknowledged(self):
        first = self.store.save_chat(A, self.payload("first"), self.shared)
        manual = "# My external correction\nThe temporary idea was not a decision.\n"
        self.own_path().write_bytes(manual.encode("utf-8"))
        materialized = self.store.materialize(self.shared)
        self.assertEqual(len(materialized["conflicts"]), 1)
        again = self.store.materialize(self.shared)
        self.assertEqual(again["conflicts"][0]["id"], materialized["conflicts"][0]["id"])
        self.assertEqual(self.own_path().read_text(encoding="utf-8"), manual)
        self.assertEqual(len(self.store.view(self.shared, actor=A)["dirty_documents"]), 1)
        with self.assertRaisesRegex(ValueError, "edited externally"):
            self.store.save_chat(A, self.payload("unsafe"), self.shared)
        imported = self.store.ingest_document(A, {
            "operation_id": "import", "expected_revision": self.ledger.revision,
            "path": "chats/" + A + ".md", "document_sha256": sha(manual)}, self.shared)
        edit = self.store.view(self.shared, actor=A)["external_edits"][0]
        self.assertEqual(edit["text"], manual)
        self.assertEqual(edit["editor"], "unknown")
        self.assertEqual(edit["author_thread"], A)
        self.assertEqual(imported["status"], "pending")
        self.store.save_chat(A, self.payload("reviewed", text="The idea was exploratory.", document_sha256=sha(manual)), self.shared)
        self.assertIn("The idea was exploratory.", self.own_path().read_text(encoding="utf-8"))
        history = self.ledger.snapshot(at_revision=first["revision"]).state["dialogue_documents"]
        self.assertEqual(history["chats"][A]["text"], "My own interpretation for this task.")
        self.assertEqual(self.ledger.snapshot().state["dialogue_documents"]["external_edits"][edit["id"]]["text"], manual)

    def test_import_hash_and_path_are_bounded_and_exact_retry_does_not_duplicate(self):
        self.store.save_chat(A, self.payload(), self.shared)
        for path in ("../state.db", str(self.root / "private.md"), "chats/../shared.md", "chats/" + B + ".md", "shared.md/."):
            with self.assertRaises(ValueError):
                self.store.ingest_document(A, {"operation_id": "bad", "expected_revision": self.ledger.revision,
                    "path": path, "text": "A scoped correction.", "document_sha256": sha("A scoped correction.")}, self.shared)
        payload = {"operation_id": "import", "expected_revision": self.ledger.revision,
                   "path": "shared.md", "text": "A scoped correction.", "document_sha256": sha("A scoped correction.")}
        with self.assertRaisesRegex(ValueError, "hash"):
            self.store.ingest_document(A, {**payload, "document_sha256": "wrong"}, self.shared)
        result = self.store.ingest_document(A, payload, self.shared)
        self.store.save_chat(A, self.payload("later"), self.shared)
        replay = self.store.ingest_document(A, payload, self.shared)
        self.assertEqual(replay, {**result, "replayed": True})
        self.assertEqual(len(self.store.view(self.shared)["external_edits"]), 1)

    def test_shared_external_edit_stays_pending_until_explicit_resolution(self):
        self.store.materialize(self.shared)
        path = self.store.directory / "shared.md"
        path.write_text("External tentative revision.", encoding="utf-8")
        payload = {"operation_id": "external", "expected_revision": self.ledger.revision,
                   "path": "shared.md", "document_sha256": sha("External tentative revision.")}
        with self.assertRaisesRegex(ValueError, "other scopes"):
            self.store.ingest_document(A, payload, self.shared)
        payload["text"] = "External tentative revision."
        result = self.store.ingest_document(A, payload, self.shared)
        self.store.materialize(self.shared)
        self.assertEqual(path.read_text(encoding="utf-8"), "External tentative revision.")
        # Applying the underlying sourced update is explicitly outside this layer.
        self.shared["entries"][0]["text"] = "A reviewed and sourced interpretation."
        self.change_shared()
        self.store.resolve(A, result["proposal_id"], "accepted", "Underlying shared revision was separately applied.")
        self.store.materialize(self.shared)
        self.assertIn("A reviewed and sourced interpretation.", path.read_text(encoding="utf-8"))
        self.assertIn("External tentative revision.", self.store.view(self.shared)["external_edits"][0]["text"])

    def test_stale_shared_snapshot_and_stale_revision_do_not_change_files(self):
        stale = copy.deepcopy(self.shared)
        payload = self.payload()
        self.ledger.commit(Transition(updates={"another_writer": True}), expected_revision=self.ledger.revision)
        with self.assertRaisesRegex(ValueError, "current revision"):
            self.store.save_chat(A, payload, self.shared)
        self.shared["entries"][0]["text"] = "A changed interpretation."
        self.change_shared()
        with self.assertRaisesRegex(ValueError, "Shared entries changed"):
            self.store.save_chat(A, self.payload("stale-shared"), stale)
        with self.assertRaisesRegex(ValueError, "Shared entries changed"):
            self.store.materialize(stale)
        self.assertFalse(self.own_path().exists())
        with self.assertRaises(ValueError):
            self.store.save_chat(A, self.payload("bool", expected_revision=True), self.shared)

    def test_edit_during_commit_is_not_overwritten(self):
        self.store.save_chat(A, self.payload("first"), self.shared)
        commit = self.ledger.commit
        def edit_after_commit(*args, **kwargs):
            result = commit(*args, **kwargs)
            self.own_path().write_text("A simultaneous external correction.", encoding="utf-8")
            return result
        with patch.object(self.ledger, "commit", side_effect=edit_after_commit):
            self.store.save_chat(A, self.payload("second"), self.shared)
        self.assertEqual(self.own_path().read_text(encoding="utf-8"), "A simultaneous external correction.")
        self.assertTrue(self.store.view(self.shared)["dirty_documents"])

    def test_ledger_cas_race_cannot_publish_uncommitted_document(self):
        other = Ledger(self.root / "state.db")
        commit = self.ledger.commit
        def race(*args, **kwargs):
            other.commit(Transition(updates={"concurrent": True}), expected_revision=other.revision)
            return commit(*args, **kwargs)
        try:
            with patch.object(self.ledger, "commit", side_effect=race):
                with self.assertRaises(StaleRevision):
                    self.store.save_chat(A, self.payload(), self.shared)
            self.assertNotIn("dialogue_documents", self.ledger.snapshot().state)
            self.assertFalse(self.own_path().exists())
        finally:
            other.close()

    def test_partial_projection_failure_is_recoverable_without_repeating_commit(self):
        original = self.store._atomic
        payload = self.payload()
        def fail_manifest(path, data, **kwargs):
            if path.name == "projections.json":
                raise OSError("Fictional interrupted manifest write")
            return original(path, data, **kwargs)
        with patch.object(self.store, "_atomic", side_effect=fail_manifest):
            with self.assertRaises(OSError):
                self.store.save_chat(A, payload, self.shared)
        self.assertEqual(self.ledger.revision, 2)
        replay = self.store.save_chat(A, payload, self.shared)
        self.assertEqual(replay["revision"], 2)
        self.assertTrue(replay["replayed"])
        recovered = self.store.materialize(self.shared)
        self.assertEqual(recovered["conflicts"], [])
        self.assertFalse(self.store.view(self.shared)["dirty_documents"])

    def test_deleted_or_non_utf8_external_file_is_queued_without_loss(self):
        self.store.save_chat(A, self.payload(), self.shared)
        self.own_path().unlink()
        result = self.store.materialize(self.shared)
        conflict = next(x for x in result["conflicts"] if x["path"].startswith("chats/"))
        self.assertIsNone(conflict["sha256"])
        self.assertFalse(self.own_path().exists())
        path = self.store.directory / "INDEX.md"
        path.write_bytes(b"\xff\x00a binary accidental edit")
        result = self.store.materialize(self.shared)
        conflict = next(x for x in result["conflicts"] if x["path"] == "INDEX.md")
        queued = json.loads((self.store.directory / ".dialogue-documents" / "pending" / (conflict["id"] + ".json")).read_text(encoding="utf-8"))
        self.assertEqual(queued["encoding"], "base64")
        self.assertEqual(path.read_bytes(), b"\xff\x00a binary accidental edit")
        self.store.ingest_document(A, {"operation_id": "deleted-import", "expected_revision": self.ledger.revision,
            "path": "chats/" + A + ".md", "document_sha256": None}, self.shared)
        self.store.save_chat(A, self.payload("restore-deletion", document_sha256=None), self.shared)
        self.assertTrue(self.own_path().exists())

    def test_copying_private_directory_and_ledger_preserves_provenance(self):
        self.store.save_chat(A, self.payload(sources=[self.shared["entries"][0]["sources"][0]]), self.shared)
        self.ledger.close()
        shutil.copytree(self.root / "documents", self.root / "moved")
        shutil.copyfile(self.root / "state.db", self.root / "moved-state.db")
        self.ledger = Ledger(self.root / "moved-state.db")
        moved = DocumentStore(self.ledger, self.root / "moved")
        self.assertEqual(moved.materialize(self.shared)["conflicts"], [])
        self.assertEqual(moved.view(self.shared)["chats"][0]["sources"][0]["quote"], "Let us discuss first.")

    def test_trusted_host_capability_keeps_operator_identity_and_is_not_a_payload_grant(self):
        result = self.store.propose(A, self.payload("scoped-proposal", scope="story",
            sources=[self.shared["entries"][0]["sources"][0]]), self.shared)
        with self.assertRaisesRegex(ValueError, "scope"):
            self.store.resolve(D, result["proposal_id"], "rejected", "No capability.")
        manager = DocumentStore(self.ledger, self.store.directory, actor_scopes={D: ["story", "research"]})
        resolved = manager.resolve(D, result["proposal_id"], "rejected", "Host-authorized operator review.")
        self.assertEqual(resolved["status"], "rejected")
        proposal = manager.proposals(actor=D)["proposals"][0]
        self.assertEqual(proposal["resolved_by"], D)
        self.assertEqual(proposal["author_thread"], A)
        self.assertNotIn(D, [s["thread"] for s in self.shared["sources"]])
        with self.assertRaisesRegex(ValueError, "Unknown document fields"):
            self.store.save_chat(D, self.payload("inject-grant", actor_scopes={D: ["story"]}), self.shared)
        with self.assertRaisesRegex(ValueError, "unconfigured"):
            DocumentStore(self.ledger, self.store.directory, actor_scopes={D: ["other-project"]}).view(self.shared, actor=D)


if __name__ == "__main__":
    unittest.main()
