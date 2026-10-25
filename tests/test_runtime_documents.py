"""Real runtime/document integration using fictional original chat evidence."""
import copy
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "dialogue-bridge"
sys.path.insert(0, str(PLUGIN))
if os.environ.get("AGENT_STATE_CORE_PATH"):
    sys.path.insert(0, os.environ["AGENT_STATE_CORE_PATH"])

from dialogue_bridge.context import Context, Registry
from dialogue_bridge import runtime
from dialogue_understanding import DocumentStore

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
C = "00000000-0000-4000-8000-000000000003"


class FictionalHistory:
    def __init__(self, text="Discuss first; the temporary idea is not approved."):
        self.text = text

    def pages(self, ident):
        yield [{"id": "turn-1", "items": [{"id": "message-1", "type": "userMessage",
            "content": [{"type": "text", "text": self.text}]}]}]

    def metadata(self, ident):
        return {"id": ident, "name": "Fictional independent chat", "status": {"type": "notLoaded"}}


class RuntimeDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "private-registry"
        self.directory = self.root / "space"
        self.environment = patch.dict(os.environ, {"DIALOGUE_BRIDGE_HOME": str(self.home)})
        self.environment.start()
        context = Context.create(self.directory, "Fictional space", [
            {"thread": A, "scope": "story", "label": "Fictional story"},
            {"thread": B, "scope": "research", "label": "Fictional research"}])
        try:
            context.archive.sync(FictionalHistory(), A)
            context.archive.sync(FictionalHistory("Retain the denominator for this observation."), B)
            context.save({"operation_id": "seed", "expected_revision": 0,
                "coverage_token": context.coverage()["token"], "purpose": "Fictional task context",
                "reason": "Initial sourced interpretation", "entries": [
                    {"key": "exploration", "scope": "shared", "text": "Distinguish exploration from approval.",
                     "sources": [self.citation(A)]},
                    {"key": "story", "scope": "story", "text": "The temporary story idea is tentative.",
                     "sources": [self.citation(A)]},
                    {"key": "research", "scope": "research", "text": "Retain the denominator.",
                     "sources": [self.citation(B)]}]}, actor=C)
            runtime._store(context).materialize(runtime._shared(context))
        finally:
            context.close()
        Registry().register("Fictional space", self.directory)

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    @staticmethod
    def citation(actor):
        return {"ref": actor + "/turn-1/message-1", "quote": "Discuss first" if actor == A else "Retain the denominator"}

    def call(self, action, arguments=None, *, actor=A):
        return runtime.dispatch(action, {"name": "Fictional space", **(arguments or {})}, actor=actor)

    def revision(self):
        context = Context(self.directory)
        try:
            return context.ledger.revision
        finally:
            context.close()

    def current(self):
        context = Context(self.directory)
        try:
            return copy.deepcopy(context.ledger.snapshot())
        finally:
            context.close()

    def own(self, operation="own", **updates):
        return {"operation_id": operation, "expected_revision": self.revision(),
                "text": "My independent interpretation.", "dependencies": ["exploration"], **updates}

    def proposal(self, operation="proposal", **updates):
        return {"operation_id": operation, "expected_revision": self.revision(),
                "text": "A narrower tentative interpretation.", "scope": "story", "sources": [self.citation(A)],
                "entries": [{"key": "story", "scope": "story", "text": "This temporary idea remains exploratory.",
                             "sources": [self.citation(A)]}], **updates}

    def change_source(self):
        context = Context(self.directory)
        try:
            context.archive.sync(FictionalHistory("This original message was later replaced."), A)
        finally:
            context.close()

    def test_partial_revision_preserves_unreviewed_source_hashes_and_warnings(self):
        before = next(e for e in self.current().state["understanding"]["entries"] if e["key"] == "story")
        context = Context(self.directory)
        try:
            context.archive.sync(FictionalHistory("Discuss first; the story idea is now approved."), A)
        finally:
            context.close()
        self.call("shared_update", {"operation_id": "research-only", "expected_revision": self.revision(),
            "coverage_token": self.call("documents", actor=B)["shared"]["coverage"]["token"],
            "reason": "Reconsider research only", "entries": [{"key": "research", "scope": "research",
            "text": "Keep sample counts with the denominator.", "sources": [self.citation(B)]}]}, actor=B)
        after = next(e for e in self.current().state["understanding"]["entries"] if e["key"] == "story")
        self.assertEqual(after, before)
        opened = self.call("open", {"queue": False})
        self.assertTrue(opened["shared_needs_review"])
        self.assertEqual(next(e for e in opened["entries"] if e["key"] == "story")["source_warnings"][0]["status"], "source_changed")

    def test_partial_revision_is_not_blocked_by_another_projects_removed_quote(self):
        context = Context(self.directory)
        try:
            context.archive.sync(FictionalHistory("The research quotation has been replaced."), B)
        finally:
            context.close()
        result = self.call("shared_update", {"operation_id": "story-only", "expected_revision": self.revision(),
            "coverage_token": self.call("documents")["shared"]["coverage"]["token"],
            "reason": "Reconsider story only", "entries": [{"key": "story", "scope": "story",
            "text": "Keep this story idea exploratory.", "sources": [self.citation(A)]}]})
        self.assertEqual(result["revision"], self.revision())
        research = next(e for e in self.call("documents", actor=B)["shared"]["entries"] if e["key"] == "research")
        self.assertTrue(research["source_warnings"])

    def test_reader_can_save_own_citations_and_dependencies_without_source_enrollment(self):
        Registry().bind("Fictional space", C, ["story"])
        saved = self.call("chat_update", self.own("reader-own", dependencies=["story"], sources=[self.citation(A)]), actor=C)
        self.assertEqual(saved["author_thread"], C)
        docs = self.call("documents", actor=C)
        own = next(d for d in docs["chats"] if d["owner_thread"] == C)
        self.assertEqual(own["dependencies"], ["story"])
        self.assertEqual(own["sources"][0]["quote"], "Discuss first")
        self.assertNotIn(C, [s["thread"] for s in docs["shared"]["sources"]])
        for payload in (self.own("hidden-dependency", dependencies=["research"]),
                        self.own("hidden-quote", sources=[self.citation(B)]),
                        self.own("hidden-scope", scope="research")):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.call("chat_update", payload, actor=C)

    def test_narrowed_source_binding_limits_document_dependencies_and_default_scope(self):
        Registry().bind("Fictional space", A, ["shared"])
        with self.assertRaisesRegex(ValueError, "permitted scopes"):
            self.call("chat_update", self.own("hidden-native-dependency", dependencies=["story"]))
        self.call("chat_update", self.own("shared-only"))
        self.assertEqual(self.call("documents")["chats"][0]["scope"], "shared")

    def test_regular_runtime_chat_update_and_per_entry_review_after_shared_change(self):
        saved = self.call("chat_update", self.own())
        self.assertEqual(saved["author_thread"], A)
        self.call("shared_update", {"operation_id": "unrelated", "expected_revision": self.revision(),
            "coverage_token": self.call("documents")["shared"]["coverage"]["token"],
            "reason": "Adjust the unrelated research entry", "entries": [{"key": "research", "scope": "research",
            "text": "Retain the denominator and sample context.", "sources": [self.citation(B)]}]}, actor=None)
        self.assertFalse(self.call("documents")["chats"][0]["needs_review"])
        self.assertEqual(self.call("chat_update", self.own("reviewed"))["revision"], self.revision())

    def test_ui_text_only_import_is_normalized_and_remains_pending(self):
        result = self.call("import_document", {"text": "A tentative UI correction.",
            "expected_revision": self.revision(), "scope": "shared", "user_confirmed": True}, actor=None)
        self.assertEqual(result["status"], "pending")
        view = self.call("documents", actor=None)
        proposal = next(p for p in view["proposals"] if p["id"] == result["proposal_id"])
        self.assertEqual(proposal["editor"], "unknown")
        self.assertNotIn("A tentative UI correction.", view["shared"]["entries"][0]["text"])

    def test_explicit_import_uses_utf8_digest_and_keeps_crlf_text_exact(self):
        text = "A correction.\r\nPreserve its exact supplied bytes.\r\n"
        result = self.call("import_document", {"operation_id": "crlf", "expected_revision": self.revision(),
            "text": text, "document_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}, actor=None)
        edit = next(e for e in self.call("documents", actor=None)["external_edits"]
                    if e["id"] == result["external_edit_id"])
        self.assertEqual(edit["text"], text)

    def test_bound_scope_cannot_review_or_ack_a_hidden_proposal(self):
        result = self.call("propose", self.proposal())
        Registry().bind("Fictional space", A, ["shared"])
        self.assertEqual(self.call("proposals")["proposals"], [])
        with self.assertRaises((ValueError, PermissionError)):
            self.call("review_proposal", {"id": result["proposal_id"], "decision": "reject", "reason": "Hidden scope"})
        with self.assertRaises((ValueError, PermissionError)):
            self.call("ack", {"id": result["proposal_id"], "stage": "read"})

    def test_search_shared_entries_redacts_other_project_original_quotes(self):
        result = self.call("search", {"query": "exploration"}, actor=B)
        entry = result["entries"][0]
        self.assertEqual(entry["key"], "exploration")
        self.assertFalse(entry.get("sources"), "Shared text is visible, story-project quotations are outside B's scope")

    def test_exact_runtime_chat_retry_survives_later_original_source_edit(self):
        payload = self.own(sources=[self.citation(A)])
        original = self.call("chat_update", payload)
        self.change_source()
        replay = self.call("chat_update", payload)
        self.assertEqual(replay, {**original, "replayed": True})

    def test_exact_runtime_proposal_retry_survives_later_original_source_edit(self):
        payload = self.proposal()
        original = self.call("propose", payload)
        self.change_source()
        replay = self.call("propose", payload)
        self.assertEqual(replay, {**original, "replayed": True})

    def test_review_two_step_crash_completes_without_reapplying_shared_patch(self):
        proposal = self.call("propose", self.proposal())
        arguments = {"id": proposal["proposal_id"], "decision": "accept", "reason": "Reviewed original context.",
                     "operation_id": "review-once", "expected_revision": self.revision()}
        with patch.object(DocumentStore, "resolve", side_effect=OSError("Fictional interruption after patch")):
            with self.assertRaises(OSError):
                self.call("review_proposal", arguments)
        applied_revision = self.revision()
        result = self.call("review_proposal", arguments)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["shared_update"]["revision"], applied_revision)
        self.assertEqual(self.revision(), applied_revision + 1)

    def test_review_two_step_crash_rejects_changed_retry_content(self):
        proposal = self.call("propose", self.proposal())
        arguments = {"id": proposal["proposal_id"], "decision": "accept", "reason": "Reviewed original context.",
                     "operation_id": "review-once", "expected_revision": self.revision()}
        with patch.object(DocumentStore, "resolve", side_effect=OSError("Fictional interruption after patch")):
            with self.assertRaises(OSError):
                self.call("review_proposal", arguments)
        before = self.revision()
        changed = {**arguments, "reason": "A different rationale.", "entries": [{"key": "story", "scope": "story",
                   "text": "A different unapplied interpretation.", "sources": [self.citation(A)]}]}
        with self.assertRaisesRegex(ValueError, "different content|conflict|retry"):
            self.call("review_proposal", changed)
        self.assertEqual(self.revision(), before)
        self.assertEqual(self.call("proposals")["proposals"][0]["status"], "pending")

    def test_resolved_review_rejects_changed_same_operation_instead_of_false_replay(self):
        proposal = self.call("propose", self.proposal())
        arguments = {"id": proposal["proposal_id"], "decision": "reject", "reason": "Original rationale.",
                     "operation_id": "reject-once"}
        self.call("review_proposal", arguments)
        with self.assertRaisesRegex(ValueError, "different content|conflict|retry"):
            self.call("review_proposal", {**arguments, "reason": "A different rationale."})

    def test_local_operator_does_not_partially_apply_an_unresolvable_scoped_review(self):
        proposal = self.call("propose", self.proposal())
        before = self.revision()
        try:
            result = self.call("review_proposal", {"id": proposal["proposal_id"], "decision": "accept",
                "reason": "Operator reviewed the sourced proposal.", "operation_id": "operator-review"}, actor=None)
        except (ValueError, PermissionError):
            self.assertEqual(self.revision(), before, "Authorization refusal must happen before applying shared changes")
        else:
            self.assertEqual(result["status"], "accepted")
            self.assertEqual(self.call("proposals", actor=None)["proposals"][0]["resolved_by"], runtime._UI_ACTOR)

    def test_runtime_dirty_chat_guard_survives_new_revisions(self):
        self.call("chat_update", self.own())
        own_path = self.directory / "chats" / (A + ".md")
        own_path.write_bytes(b"An external correction that must remain.\n")
        self.call("propose", self.proposal())
        with self.assertRaisesRegex(ValueError, "edited externally"):
            self.call("chat_update", self.own("overwrite-dirty"))
        self.assertEqual(own_path.read_bytes(), b"An external correction that must remain.\n")

    def test_ui_chat_edit_does_not_claim_original_chat_authorship(self):
        # An unbound local UI can author a proposal/draft under its operator
        # identity, or refuse this operation. It must not fabricate participation.
        arguments = {**self.own(), "actor": A}
        try:
            self.call("chat_update", arguments, actor=None)
        except (ValueError, PermissionError):
            return
        document = self.call("documents", actor=None)["chats"][0]
        self.assertNotEqual(document["authorship"], "original_chat")
        self.assertNotEqual(document["author_thread"], A)

    def test_shared_remove_retry_replays_after_target_disappeared_and_new_commits(self):
        arguments = {"operation_id": "remove-story", "expected_revision": self.revision(),
                     "coverage_token": self.call("documents")["shared"]["coverage"]["token"],
                     "reason": "The tentative project entry is withdrawn.", "remove_keys": ["story"]}
        original = self.call("shared_update", arguments)
        self.call("chat_update", self.own("after-removal"))
        before = self.revision()
        replay = self.call("shared_update", arguments)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["revision"], original["revision"])
        self.assertEqual(self.revision(), before)
        self.assertNotIn("story", [e["key"] for e in self.current().state["understanding"]["entries"]])

    def test_shared_update_exact_retry_survives_changed_original_quote(self):
        arguments = {"operation_id": "revise-story", "expected_revision": self.revision(),
                     "coverage_token": self.call("documents")["shared"]["coverage"]["token"],
                     "reason": "Keep the tentative status clear.", "entries": [{"key": "story", "scope": "story",
                     "text": "The story idea remains tentative.", "sources": [self.citation(A)]}]}
        original = self.call("shared_update", arguments)
        self.change_source()
        replay = self.call("shared_update", arguments)
        self.assertEqual(replay["revision"], original["revision"])
        self.assertTrue(replay["replayed"])

    def test_restore_after_chat_and_proposal_revisions_preserves_dependency_meaning(self):
        original_revision = self.revision()
        self.call("chat_update", self.own("own-before-restore"))
        self.call("shared_update", {"operation_id": "changed-exploration", "expected_revision": self.revision(),
            "coverage_token": self.call("documents")["shared"]["coverage"]["token"],
            "reason": "A changed interpretation to restore later.", "entries": [{"key": "exploration", "scope": "shared",
            "text": "A different tentative explanation.", "sources": [self.citation(A)]}]})
        self.assertTrue(self.call("documents")["chats"][0]["needs_review"])
        self.call("propose", self.proposal("before-restore"))
        restored = self.call("restore", {"revision": original_revision, "operation_id": "restore-original"}, actor=None)
        self.assertEqual(restored["revision"], self.revision())
        self.assertEqual(self.call("documents")["shared"]["entries"][0]["text"], "Distinguish exploration from approval.")
        self.assertFalse(self.call("documents")["chats"][0]["needs_review"])

    def test_stale_review_caller_revision_is_refused_before_intent(self):
        proposal = self.call("propose", self.proposal())
        stale = self.revision()
        self.call("chat_update", self.own("another-commit"))
        before = self.revision()
        with self.assertRaisesRegex(ValueError, "current revision"):
            self.call("review_proposal", {"id": proposal["proposal_id"], "decision": "accept",
                "operation_id": "stale-review", "expected_revision": stale})
        self.assertEqual(self.revision(), before)
        self.assertNotIn("bridge_review_intents", self.current().state)

    def test_plain_import_cannot_be_accepted_as_a_rule_without_cited_patch(self):
        imported = self.call("import_document", {"text": "An unreviewed external assertion."}, actor=None)
        before = self.revision()
        reviewed = self.call("review_proposal", {"id": imported["proposal_id"], "decision": "accept"}, actor=None)
        self.assertTrue(reviewed["needs_source_review"])
        self.assertEqual(reviewed["status"], "pending")
        self.assertEqual(self.revision(), before)

    def test_ack_retry_does_not_roll_reported_stage_back(self):
        proposal = self.call("propose", self.proposal())
        original = self.call("ack", {"id": proposal["proposal_id"], "stage": "read", "operation_id": "read-once"})
        self.call("ack", {"id": proposal["proposal_id"], "stage": "adopted", "evidence": {"artifact": "fictional-result.md"}})
        replay = self.call("ack", {"id": proposal["proposal_id"], "stage": "read", "operation_id": "read-once"})
        self.assertEqual(replay, {**original, "replayed": True})
        receipt = self.current().state["bridge_receipts"][A][proposal["proposal_id"]]
        self.assertEqual(receipt["stage"], "adopted")
        with self.assertRaisesRegex(ValueError, "different content"):
            self.call("ack", {"id": proposal["proposal_id"], "stage": "received", "operation_id": "read-once"})

    def test_operator_chat_correction_is_accepted_only_after_owners_own_new_document(self):
        self.call("chat_update", self.own("original-own"))
        imported = self.call("import_document", {"actor": A, "scope": "chat", "text": "A local correction to reconsider."}, actor=None)
        before = self.revision()
        pending = self.call("review_proposal", {"id": imported["proposal_id"], "decision": "accept"}, actor=None)
        self.assertTrue(pending["needs_source_review"])
        self.assertEqual(self.revision(), before)
        self.call("chat_update", self.own("owners-reconsidered", text="The owner reconsiders the local correction in its context."))
        approved = self.call("review_proposal", {"id": imported["proposal_id"], "decision": "accept", "operation_id": "owner-reviewed"})
        self.assertEqual(approved["status"], "accepted")
        self.assertEqual(approved["chat_adoption"]["owner_thread"], A)
        self.assertIsNone(approved["shared_update"])
        self.assertEqual(self.current().state["understanding"]["entries"][0]["text"], "Distinguish exploration from approval.")

    def test_restore_exact_retry_does_not_overwrite_later_work(self):
        revision = self.revision()
        original = self.call("restore", {"revision": revision, "operation_id": "restore-exact"})
        self.call("chat_update", self.own("later-document"))
        replay = self.call("restore", {"revision": revision, "operation_id": "restore-exact"})
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["revision"], original["revision"])

    def test_changed_original_source_marks_dependent_chat_for_review_before_resummary(self):
        self.call("chat_update", self.own())
        self.change_source()
        view = self.call("documents")
        self.assertTrue(view["chats"][0]["needs_review"])
        self.assertEqual(view["chats"][0]["source_dependency_changes"], ["exploration"])


if __name__ == "__main__":
    unittest.main()
