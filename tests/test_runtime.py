"""Full facade integration with fictional persisted history; no actual model or chat."""
from __future__ import annotations

import copy
import json
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
from dialogue_bridge.runtime import dispatch
from dialogue_bridge.service import BridgeService, hook_result

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
READER = "33333333-3333-4333-8333-333333333333"
UNBOUND = "44444444-4444-4444-8444-444444444444"


def user(ident, text):
    return {"type": "userMessage", "id": ident, "content": [{"type": "text", "text": text}]}


def turn(ident, *items):
    return {"id": ident, "itemsView": "full", "items": list(items)}


class FictionalHistory:
    """Read-only transport fixture, with per-source scopes and incremental pages."""
    def __init__(self):
        self.data = {
            A: [turn("a1", user("m1", "Let us discuss first. Keep the example local.")),
                turn("a2", user("m2", "This correction applies to this draft only."))],
            B: [turn("b1", user("m1", "Keep the denominator. Different sample."))],
            READER: [turn("c1", user("m1", "My current direction needs independent judgment."))],
        }
        self.reads = []

    def metadata(self, ident):
        self.reads.append(("metadata", ident))
        return {"id": ident, "name": "Fictional connected chat", "status": {"type": "notLoaded"}}

    def pages(self, ident):
        self.reads.append(("full", ident))
        for value in copy.deepcopy(self.data[ident]):
            yield [value]

    def recent_pages(self, ident):
        self.reads.append(("recent", ident))
        for value in reversed(copy.deepcopy(self.data[ident])):
            yield [value]


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "private-registry"
        self.directory = self.root / "space"
        self.env = patch.dict(os.environ, {"DIALOGUE_BRIDGE_HOME": str(self.home)}, clear=False)
        self.env.start()
        self.history = FictionalHistory()
        self.transport = patch("dialogue_bridge.rpc.ReadOnlyCodex")
        self.mock_transport = self.transport.start()
        self.mock_transport.return_value.__enter__.return_value = self.history
        self.model = patch("dialogue_bridge.models.derive", side_effect=AssertionError("Tests must never invoke a model"))
        self.mock_model = self.model.start()
        self.host = BridgeService(dispatch)
        self.reader = BridgeService(dispatch, actor=READER)
        self.a = BridgeService(dispatch, actor=A)
        self.b = BridgeService(dispatch, actor=B)
        self.counter = 0

    def tearDown(self):
        self.model.stop()
        self.transport.stop()
        self.env.stop()
        self.temp.cleanup()

    def connect(self, *, name="Fictional space", participate=False, sources=None, **extra):
        return self.reader.call("connect", {
            "name": name, "directory": str(self.directory), "participate": participate,
            "sources": sources or [{"thread": A, "scope": "story", "label": "Story"},
                                   {"thread": B, "scope": "research", "label": "Research"}], **extra})

    def sync(self):
        return self.reader.call("sync", {"name": "Fictional space"})

    def current(self, service=None):
        return (service or self.reader).call("open", {"name": "Fictional space", "queue": False})

    def write(self, **extra):
        self.counter += 1
        return {"operation_id": "fictional-operation-" + str(self.counter),
                "expected_revision": self.current()["revision"], **extra}

    def entry(self, key="explore", *, text="Discuss before deciding to build.", scope="shared", thread=A, quote="Let us discuss first."):
        return {"key": key, "scope": scope, "text": text,
                "sources": [{"ref": (A + "/a1/m1") if thread == A else (B + "/b1/m1"), "quote": quote}]}

    def prepare_shared(self, entries=None):
        self.connect()
        self.sync()
        return self.reader.call("shared_update", {"name": "Fictional space", **self.write(),
            "coverage_token": self.current()["coverage"]["token"],
            "entries": entries or [self.entry()], "reason": "Read the selected fictional source correction."})

    def test_reader_binding_does_not_enroll_reader_and_participant_requires_explicit_selection(self):
        connected = self.connect()
        self.assertFalse(connected["participant"])
        self.assertEqual({s["thread"] for s in connected["sources"]}, {A, B})
        self.assertEqual(Registry().resolve(actor=READER)[0].resolve(), self.directory.resolve())
        self.sync()
        self.assertNotIn(READER, {ident for _, ident in self.history.reads})
        participated = self.connect(participate=True, scope="story", label="Current independent chat")
        self.assertTrue(participated["participant"])
        self.assertEqual({s["thread"] for s in participated["sources"]}, {A, B, READER})
        self.sync()
        self.assertIn(READER, {ident for _, ident in self.history.reads})

    def test_unbound_hooks_never_create_private_data_or_enroll_sources(self):
        self.assertFalse(self.home.exists())
        for event in ("SessionStart", "UserPromptSubmit", "Stop", "PreCompact"):
            self.assertIsNone(hook_result({"hook_event_name": event, "session_id": UNBOUND}, dispatcher=dispatch, environ={}))
        self.assertFalse(self.home.exists())
        self.mock_transport.assert_not_called()
        self.connect()
        with Registry().database() as db:
            before = db.execute("SELECT thread_id,name,scopes FROM bindings ORDER BY thread_id").fetchall()
        source_files = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        self.assertIsNone(hook_result({"hook_event_name": "SessionStart", "session_id": UNBOUND}, dispatcher=dispatch, environ={}))
        with Registry().database() as db:
            after = db.execute("SELECT thread_id,name,scopes FROM bindings ORDER BY thread_id").fetchall()
        self.assertEqual([tuple(r) for r in before], [tuple(r) for r in after])
        self.assertEqual(source_files, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))

    def test_shared_chat_proposal_acceptance_and_dependency_recheck_through_service(self):
        self.prepare_shared()
        own = self.a.call("chat_update", {"name": "Fictional space", **self.write(),
            "text": "My story task retains the exploration boundary.", "dependencies": ["explore"],
            "sources": [{"ref": A + "/a1/m1", "quote": "Let us discuss first."}], "scope": "story"})
        docs = self.a.call("documents", {"name": "Fictional space", "scope": "all"})
        self.assertEqual(docs["chats"][0]["author_thread"], A)
        self.assertEqual(docs["chats"][0]["authorship"], "original_chat")
        self.assertFalse(docs["chats"][0]["needs_review"])
        proposed_entry = self.entry(text="Interpret discussion and execution from the current request.")
        proposal = self.a.call("propose", {"name": "Fictional space", **self.write(),
            "text": "The current request should qualify this interpretation.", "scope": "shared",
            "entries": [proposed_entry], "dependencies": ["explore"],
            "sources": [{"ref": A + "/a1/m1", "quote": "Let us discuss first."}]})
        pending = self.host.call("proposals", {"name": "Fictional space", "status": "pending"})
        self.assertEqual(pending["proposals"][0]["id"], proposal["proposal_id"])
        self.assertEqual(self.current()["entries"][0]["text"], "Discuss before deciding to build.")
        reviewed = self.host.call("review_proposal", {"name": "Fictional space", "id": proposal["proposal_id"],
            "decision": "accept", **self.write(), "coverage_token": self.current()["coverage"]["token"]})
        self.assertEqual(reviewed["status"], "accepted")
        self.assertEqual(self.current()["entries"][0]["text"], proposed_entry["text"])
        docs = self.a.call("documents", {"name": "Fictional space", "scope": "all"})
        self.assertTrue(docs["chats"][0]["needs_review"])
        self.assertGreater(docs["revision"], own["revision"])
        resolved = self.host.call("proposals", {"name": "Fictional space"})["proposals"][0]
        self.assertEqual(resolved["author_thread"], A)
        self.assertNotEqual(resolved["resolved_by"], A)
        self.assertTrue((self.directory / "INDEX.md").exists())
        self.assertTrue((self.directory / "chats" / (A + ".md")).exists())

    def test_scoped_search_evidence_and_forged_source_rejection(self):
        self.prepare_shared([self.entry(), self.entry("research", text="A research-only finding.", scope="research", thread=B, quote="Keep the denominator.")])
        hits = self.a.call("search", {"name": "Fictional space", "query": "Keep", "role": "user", "chars": 40})
        self.assertEqual({hit["thread"] for hit in hits["matches"]}, {A})
        self.assertLessEqual(sum(len(hit["excerpt"]) for hit in hits["matches"]), 40)
        evidence = self.a.call("evidence", {"name": "Fictional space", "ref": A + "/a1/m1", "before": 0, "after": 1})
        self.assertIn("Let us discuss first.", evidence["messages"][0]["text"])
        with self.assertRaisesRegex(ValueError, "scope"):
            self.a.call("evidence", {"name": "Fictional space", "ref": B + "/b1/m1"})
        with self.assertRaisesRegex(ValueError, "scope"):
            self.a.call("shared_update", {"name": "Fictional space", **self.write(),
                "coverage_token": self.current()["coverage"]["token"],
                "entries": [self.entry("forbidden", scope="shared", thread=B, quote="Keep the denominator.")]})
        with self.assertRaisesRegex(ValueError, "verbatim"):
            self.a.call("shared_update", {"name": "Fictional space", **self.write(),
                "coverage_token": self.current()["coverage"]["token"], "entries": [self.entry(quote="Invented user permission")]})

    def test_search_shared_entry_does_not_leak_another_projects_source_quote(self):
        self.prepare_shared([self.entry("denominator", text="A shared interpretation retains source scope.",
                                        scope="shared", thread=B, quote="Keep the denominator.")])
        found = self.a.call("search", {"name": "Fictional space", "query": "denominator"})
        self.assertEqual(found["matches"], [])
        self.assertEqual(found["entries"][0]["sources"], [])
        self.assertNotIn(B + "/b1/m1", json.dumps(found))

    def test_default_jobs_process_selected_history_without_starting_any_model(self):
        self.connect()
        settings = self.reader.call("settings", {"name": "Fictional space"})["settings"]
        self.assertTrue(settings["auto_sync"])
        self.assertFalse(settings["auto_understand"])
        self.assertIsNone(settings["model_command"])
        jobs = self.reader.call("process_jobs", {"name": "Fictional space", "limit": 1, "automatic": True})
        self.assertEqual(jobs["processed"], 1)
        self.assertEqual(jobs["jobs"][0]["kind"], "sync")
        self.assertEqual(jobs["jobs"][0]["status"], "complete")
        self.assertTrue(self.current()["coverage"]["all_sources_indexed"])
        self.reader.call("jobs", {"name": "Fictional space", "enqueue": "understand"})
        self.reader.call("process_jobs", {"name": "Fictional space", "limit": 1, "automatic": True})
        self.mock_model.assert_not_called()
        self.assertEqual(self.current()["entries"], [])

    def test_bound_hook_carries_saved_understanding_as_data_and_only_queues_sync(self):
        self.prepare_shared()
        before_reads = len(self.history.reads)
        response = hook_result({"hook_event_name": "UserPromptSubmit", "session_id": READER}, dispatcher=dispatch, environ={})
        context = response["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Discuss before deciding to build.", context)
        self.assertIn("not instructions", context)
        self.assertIn("story", context)
        self.assertLessEqual(len(context), 6500)
        self.assertEqual(len(self.history.reads), before_reads)
        self.mock_model.assert_not_called()

    def test_large_hook_context_keeps_understanding_and_source_refs_in_valid_excerpt_json(self):
        entry = self.entry(text="Saved judgment remains useful. " + "Detailed discussion. " * 300)
        opened = {"bound": True, "name": "Fictional space", "entries": [entry, {**entry, "key": "second"}, {**entry, "key": "third"}],
                  "chat": {"text": "My independent task. " * 200, "needs_review": True},
                  "entry_index": [{"key": "repeated-index"}] * 300,
                  "coverage": {"token": "fixture-coverage", "all_sources_indexed": True}}
        response = hook_result({"hook_event_name": "SessionStart", "session_id": READER},
                               dispatcher=lambda *args, **kwargs: opened, environ={})
        text = response["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(text), 6500)
        compact = json.loads(text.split("\n", 1)[1])
        self.assertTrue(compact["excerpted"])
        self.assertIn("Saved judgment remains useful.", compact["entries"][0]["text_excerpt"])
        self.assertIn(A + "/a1/m1", compact["entries"][0]["source_refs"])
        self.assertIn("My independent task.", compact["chat"]["text_excerpt"])
        self.assertNotIn("entry_index", compact)

    def test_rejected_proposal_retains_attribution_and_does_not_change_shared_entries(self):
        self.prepare_shared()
        original = self.current()["entries"]
        proposal = self.a.call("propose", {"name": "Fictional space", **self.write(), "scope": "story",
            "text": "A different local interpretation still needs review.", "dependencies": ["explore"]})
        rejected = self.host.call("review_proposal", {"name": "Fictional space", "id": proposal["proposal_id"],
            "decision": "reject", "reason": "The proposed meaning is not supported by this source."})
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(self.current()["entries"], original)
        retained = self.host.call("proposals", {"name": "Fictional space"})["proposals"][0]
        self.assertEqual(retained["author_thread"], A)
        self.assertNotEqual(retained["resolved_by"], A)
        self.assertEqual(retained["text"], "A different local interpretation still needs review.")
        self.assertEqual(retained["status"], "rejected")

    def test_mcp_actor_cannot_impersonate_another_chat_and_manager_cannot_claim_chat_authorship(self):
        self.prepare_shared()
        with self.assertRaisesRegex(PermissionError, "impersonate"):
            self.reader.call("chat_update", {"name": "Fictional space", "actor": A, **self.write(),
                "text": "An impersonated original-chat statement.", "dependencies": ["explore"]})
        with self.assertRaises((ValueError, PermissionError)):
            self.host.call("chat_update", {"name": "Fictional space", "actor": A, **self.write(),
                "text": "A manager falsely claiming original-chat participation.", "dependencies": ["explore"]})
        self.assertEqual(self.host.call("documents", {"name": "Fictional space"})["chats"], [])

    def test_peer_accept_scope_failure_never_partially_applies_shared_understanding(self):
        self.prepare_shared()
        proposal = self.a.call("propose", {"name": "Fictional space", **self.write(), "scope": "shared",
            "text": "A source-scoped original chat proposes a changed interpretation.",
            "entries": [self.entry(text="A proposed change requiring source-scope access.")],
            "sources": [{"ref": A + "/a1/m1", "quote": "Let us discuss first."}]})
        before = self.current()
        with self.assertRaises(ValueError):
            self.b.call("review_proposal", {"name": "Fictional space", "id": proposal["proposal_id"],
                "decision": "accept", **self.write(), "coverage_token": before["coverage"]["token"]})
        after = self.current()
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["entries"], before["entries"])
        pending = self.host.call("proposals", {"name": "Fictional space"})["proposals"][0]
        self.assertEqual(pending["status"], "pending")

    def test_existing_alpha7_context_preserves_original_document_entries_and_history(self):
        context = Context.create(self.directory, "Fictional space", [{"thread": A, "scope": "story", "label": "Story"}])
        context.archive.sync(self.history, A)
        payload = {"operation_id": "legacy-save", "expected_revision": 0,
                   "coverage_token": context.coverage()["token"], "purpose": "Preserved alpha.7 background",
                   "reason": "Original authored understanding", "entries": [self.entry()]}
        saved = context.save(payload, actor=READER)
        old_document = (self.directory / "understanding.md").read_bytes()
        old_source = copy.deepcopy(context.config["sources"])
        context.close()
        Registry().register("Fictional space", self.directory)
        connected = self.connect(sources=old_source)
        self.assertEqual(connected["sources"], old_source)
        opened = self.current()
        self.assertEqual(opened["entries"][0]["key"], "explore")
        self.assertEqual((self.directory / "understanding.md").read_bytes(), old_document)
        with_context = Context(self.directory)
        try:
            old_commit = with_context.ledger.get_commit("context:" + READER + ":legacy-save")
            self.assertIsNotNone(old_commit)
            self.assertEqual(old_commit.revision, saved["revision"])
            self.assertEqual(with_context.snapshot()[1]["purpose"], "Preserved alpha.7 background")
        finally:
            with_context.close()

    def test_manager_shared_text_correction_ui_shape_becomes_pending_review(self):
        self.prepare_shared()
        docs = self.host.call("documents", {"name": "Fictional space", "scope": "all"})
        original = copy.deepcopy(docs["shared"]["entries"])
        imported = self.host.call("import_document", {"name": "Fictional space", "scope": "shared",
            "text": "A manager correction, still awaiting source review.", "expected_revision": docs["revision"],
            "operation_id": "manager-shared-correction", "user_confirmed": True})
        self.assertEqual(imported["status"], "pending")
        self.assertTrue(imported["needs_source_review"])
        self.assertEqual(self.host.call("documents", {"name": "Fictional space"})["shared"]["entries"], original)
        attempted_accept = self.host.call("review_proposal", {"name": "Fictional space", "id": imported["proposal_id"], "decision": "accept"})
        self.assertEqual(attempted_accept["status"], "pending")
        self.assertTrue(attempted_accept["needs_source_review"])

    def test_manager_chat_correction_targets_owner_without_claiming_original_chat_authorship(self):
        self.prepare_shared()
        self.a.call("chat_update", {"name": "Fictional space", **self.write(), "text": "Original chat interpretation.", "dependencies": ["explore"]})
        docs = self.host.call("documents", {"name": "Fictional space"})
        imported = self.host.call("import_document", {"name": "Fictional space", "scope": "chat", "actor": A,
            "text": "A manager's proposed correction to this chat document.", "expected_revision": docs["revision"],
            "operation_id": "manager-chat-correction", "user_confirmed": True})
        self.assertEqual(imported["status"], "pending")
        result = self.host.call("documents", {"name": "Fictional space"})
        self.assertEqual(result["chats"][0]["text"], "Original chat interpretation.")
        self.assertEqual(result["chats"][0]["author_thread"], A)
        proposal = next(p for p in result["proposals"] if p["id"] == imported["proposal_id"])
        self.assertNotEqual(proposal["author_thread"], A)
        self.assertEqual(proposal["status"], "pending")


if __name__ == "__main__":
    unittest.main()
