import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_bridge import A, B, C, History, PLUGIN, turn, user
from dialogue_bridge.context import Context, Registry, run_context
from dialogue_bridge.rpc import RpcError


class RecentHistory(History):
    def recent_pages(self, ident):
        # Each turn is a page so boundary tests detect accidental full rereads.
        for item in reversed([t for page in copy.deepcopy(self.data) for t in page]):
            yield [item]


class SelectedHistory(RecentHistory):
    def pages(self, ident):
        if ident == B:
            yield [turn("b1", user("b", "Published is not an ideal example."))]
        else:
            yield from super().pages(ident)

    def recent_pages(self, ident):
        for item in reversed([t for page in self.pages(ident) for t in page]):
            yield [item]


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = Context.create(self.root / "saved", "Fictional writing background", [
            {"thread": A, "scope": "story", "label": "Story project"},
            {"thread": B, "scope": "analysis", "label": "Analysis project"},
        ])
        self.context.archive.sync(RecentHistory(), A)
        self.context.archive.sync(RecentHistory([[turn("b1", user("b", "Published is not an ideal example."))]]), B)
        self.ref = f"{A}/t2/m3"

    def tearDown(self):
        self.context.close()
        self.temp.cleanup()

    def payload(self, operation="first", **changes):
        result = {"operation_id": operation, "expected_revision": self.context.ledger.revision,
                  "coverage_token": self.context.coverage()["token"],
                  "purpose": "Start a new discussion with relevant background, not the old task",
                  "reason": "Reconsider the original correction in its context",
                  "entries": [{"key": "exploration", "scope": "shared", "text": "Distinguish discussion from execution in context.",
                               "sources": [{"ref": self.ref, "quote": "我没有说做，只是先让你整理。"}]}]}
        result.update(changes)
        return result

    def context_args(self, command="context-open", **changes):
        values = dict(command=command, name="Fictional writing background", workspace=None,
                      scope=None, query=None, key=None, chars=12000, refresh=True, full=False)
        values.update(changes)
        return SimpleNamespace(**values)

    def test_refresh_and_open_reuses_current_entries_without_an_overview_or_rebinding_sources(self):
        self.context.save(self.payload(), actor=C)
        home = self.root / "combined-home"
        Registry(home).register("Fictional writing background", self.context.archive.root)
        with patch.dict(os.environ, {"DIALOGUE_BRIDGE_HOME": str(home), "CODEX_THREAD_ID": C}), \
             patch("dialogue_bridge.rpc.ReadOnlyCodex") as transport, \
             patch.object(Context, "overview", side_effect=AssertionError("Do not reload samples for existing understanding")):
            transport.return_value.__enter__.return_value = SelectedHistory()
            result = run_context(self.context_args())
        self.assertEqual(result["entries"][0]["key"], "exploration")
        self.assertFalse(result["needs_review"])
        self.assertEqual(result["bound_to"], C)
        self.assertTrue(all(u["mode"] == "incremental" for u in result["refresh"]))
        self.assertNotIn("changes", result)
        self.assertNotIn(C, self.context.archive.threads)

    def test_refresh_and_open_exposes_new_evidence_with_the_saved_understanding(self):
        self.context.save(self.payload(), actor=C)
        home = self.root / "changed-home"
        Registry(home).register("Fictional writing background", self.context.archive.root)
        history = SelectedHistory([*History().data, [turn("t3", user("new", "The previous interpretation needs revision."))]])
        with patch.dict(os.environ, {"DIALOGUE_BRIDGE_HOME": str(home), "CODEX_THREAD_ID": C}), \
             patch("dialogue_bridge.rpc.ReadOnlyCodex") as transport:
            transport.return_value.__enter__.return_value = history
            result = run_context(self.context_args())
        self.assertTrue(result["needs_review"])
        self.assertEqual(result["entries"][0]["key"], "exploration")
        self.assertEqual(result["changes"]["changes"][0]["kind"], "added")

    def test_refresh_failure_does_not_bind_the_reader_or_replace_understanding(self):
        self.context.save(self.payload(), actor=C)
        home = self.root / "failed-home"
        registry = Registry(home)
        registry.register("Fictional writing background", self.context.archive.root)
        with patch.dict(os.environ, {"DIALOGUE_BRIDGE_HOME": str(home), "CODEX_THREAD_ID": C}), \
             patch("dialogue_bridge.rpc.ReadOnlyCodex") as transport:
            transport.return_value.__enter__.side_effect = RpcError("Unavailable source")
            with self.assertRaises(RpcError):
                run_context(self.context_args())
        with self.assertRaisesRegex(ValueError, "Select a saved background"):
            registry.resolve(actor=C)
        self.assertEqual(self.context.ledger.revision, 1)

    def test_invalid_reader_cannot_refresh_sources(self):
        for actor in ("", "not-a-chat"):
            with patch.dict(os.environ, {"CODEX_THREAD_ID": actor}), \
                 patch("dialogue_bridge.rpc.ReadOnlyCodex") as transport:
                with self.assertRaises(ValueError):
                    run_context(self.context_args(workspace=str(self.context.archive.root)))
                transport.assert_not_called()

    def test_empty_registry_can_initialize_read_interpret_and_reopen_without_prepared_background(self):
        home = self.root / "first-use-home"
        selection = self.root / "selection.json"
        selection.write_text(json.dumps({"sources": self.context.config["sources"]}), encoding="utf-8")
        with patch.dict(os.environ, {"DIALOGUE_BRIDGE_HOME": str(home), "CODEX_THREAD_ID": C}), \
             patch("dialogue_bridge.rpc.ReadOnlyCodex") as transport:
            transport.return_value.__enter__.return_value = SelectedHistory()
            self.assertEqual(Registry(home).list(), [])
            created = run_context(self.context_args("context-init", input=str(selection)))
            self.assertFalse(created["coverage"]["all_sources_indexed"])
            first = run_context(self.context_args())
            self.assertFalse(first["has_understanding"])
            self.assertTrue(first["coverage"]["all_sources_indexed"])
            self.assertEqual(len(first["sources"]), 2)
            payload = self.payload(coverage_token=first["coverage"]["token"])
            payload_file = self.root / "understanding.json"
            payload_file.write_text(json.dumps(payload), encoding="utf-8")
            run_context(self.context_args("context-save", input=str(payload_file)))
            reopened = run_context(self.context_args())
        self.assertEqual(reopened["revision"], 1)
        self.assertEqual(reopened["entries"][0]["key"], "exploration")
        self.assertEqual({source["thread"] for source in first["sources"]}, {A, B})
        self.assertFalse(reopened["needs_review"])

    def test_a_new_reader_binds_without_becoming_a_source_or_peer(self):
        self.context.save(self.payload(), actor=C)
        registry = Registry(self.root / "registry")
        registry.register("Fictional writing background", self.context.archive.root)
        registry.bind("Fictional writing background", C, ["story"])
        location, scopes = registry.resolve(actor=C)
        self.assertEqual(location, self.context.archive.root)
        self.assertEqual(scopes, ["story"])
        self.assertNotIn(C, self.context.archive.threads)
        self.assertEqual(self.context.get(scopes=scopes)["entries"][0]["key"], "exploration")

    def test_unindexed_or_changed_coverage_cannot_be_silently_saved(self):
        payload = self.payload()
        self.context.archive.sync(History([[turn("b2", user("b2", "Another correction"))]]), B)
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.context.save(payload, actor=C)
        self.assertEqual(self.context.ledger.revision, 0)

    def test_quotes_and_scope_are_checked_before_a_revision_is_committed(self):
        payload = self.payload()
        payload["entries"][0]["sources"][0]["quote"] = "Invented instruction"
        with self.assertRaisesRegex(ValueError, "verbatim"):
            self.context.save(payload, actor=C)
        payload = self.payload()
        payload["entries"][0]["scope"] = "unselected project"
        with self.assertRaisesRegex(ValueError, "scopes"):
            self.context.save(payload, actor=C)
        self.assertEqual(self.context.ledger.revision, 0)

    def test_scope_selection_keeps_other_project_understanding_out(self):
        payload = self.payload()
        second = copy.deepcopy(payload["entries"][0])
        second.update(key="analysis-only", scope="analysis", text="A published draft is not a universal model.")
        payload["entries"].append(second)
        self.context.save(payload, actor=C)
        self.assertEqual([x["key"] for x in self.context.get(scopes=["story"])["entries"]], ["exploration"])
        self.assertEqual(len(self.context.get(scopes=["analysis"])["entries"]), 2)
        with self.assertRaisesRegex(ValueError, "Unknown scope"):
            self.context.get(scopes=["unknown"])

    def test_later_understanding_can_reverse_an_earlier_interpretation(self):
        first = self.payload()
        self.context.save(first, actor=C)
        second = self.payload("reconsider")
        second["entries"][0]["text"] = "An explicit later request can authorize execution; the old correction was local."
        self.context.save(second, actor=C)
        self.assertIn("later request", self.context.get()["entries"][0]["text"])
        earlier = self.context.ledger.snapshot(at_revision=1).state["understanding"]
        self.assertEqual(earlier["entries"][0]["text"], first["entries"][0]["text"])
        replay = self.context.save(first, actor=C)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["current_revision"], 2)
        self.assertIn("later request", (self.context.archive.root / "understanding.md").read_text(encoding="utf-8"))

    def test_stale_revision_and_changed_idempotent_input_are_rejected(self):
        old = self.payload()
        self.context.save(old, actor=C)
        with self.assertRaisesRegex(ValueError, "current revision"):
            self.context.save({**old, "operation_id": "stale"}, actor=C)
        with self.assertRaisesRegex(ValueError, "different content"):
            self.context.save({**old, "reason": "Different request"}, actor=C)

    def test_user_edited_document_is_preserved_until_the_editor_reads_it(self):
        self.context.save(self.payload(), actor=C)
        document = self.context.archive.root / "understanding.md"
        document.write_text("User changed this interpretation", encoding="utf-8")
        payload = self.payload("incorporate")
        with self.assertRaisesRegex(ValueError, "document was edited"):
            self.context.save(payload, actor=C)
        self.assertEqual(document.read_text(encoding="utf-8"), "User changed this interpretation")
        self.assertTrue(self.context.get()["document_edited"])
        payload["document_sha256"] = self.context.get()["document_sha256"]
        self.context.save(payload, actor=C)
        self.assertFalse(self.context.get()["document_edited"])

    def test_incremental_refresh_rechecks_the_boundary_and_stops_before_old_history(self):
        class Appended(RecentHistory):
            def recent_pages(self, ident):
                yield [turn("t3", user("new", "Now start the requested trial."))]
                yield [turn("t2", user("m3", "我没有说做，只是先让你整理。"),
                            {"type": "agentMessage", "id": "new-answer", "text": "A later item in the same turn."})]
                raise AssertionError("Should stop before rereading older turns")
        self.context.save(self.payload(), actor=C)
        result = self.context.archive.refresh(Appended(), A)
        self.assertEqual(result["mode"], "incremental")
        self.assertEqual(result["fetched_turns"], 2)
        self.assertEqual(result["messages"], 5)
        self.assertEqual(self.context.archive.search("later item")["match_count"], 1)
        self.assertTrue(self.context.get()["needs_review"])
        delta = self.context.changes()
        self.assertEqual(len(delta["changes"]), 2)
        self.assertFalse(delta["has_more"])

    def test_unchanged_refresh_does_not_make_understanding_dirty(self):
        self.context.save(self.payload(), actor=C)
        before = self.context.coverage()["token"]
        self.context.archive.refresh(RecentHistory(), A)
        self.assertEqual(self.context.coverage()["token"], before)
        self.assertFalse(self.context.get()["needs_review"])

    def test_incremental_coverage_distinguishes_received_pages_from_checked_turns(self):
        class OneLargePage(RecentHistory):
            def recent_pages(self, ident):
                yield [turn("t2", user("m3", "我没有说做，只是先让你整理。")),
                       turn("t1", user("ignored", "Older page item, not revisited"))]
        result = self.context.archive.refresh(OneLargePage(), A)
        self.assertEqual(result["fetched_turns"], 2)
        self.assertEqual(result["checked_turns"], 1)
        self.assertEqual(self.context.archive.search("Older page item")["match_count"], 0)

    def test_a_concurrent_boundary_removal_preserves_the_other_writers_changes(self):
        archive = self.context.archive
        class ConcurrentRemoval(RecentHistory):
            def recent_pages(self, ident):
                with archive.db:
                    archive.db.execute("DELETE FROM archive_turns WHERE thread_id=?", (ident,))
                yield [turn("t2", user("m3", "Unexpected replacement"))]
        with self.assertRaisesRegex(ValueError, "changed during refresh"):
            archive.refresh(ConcurrentRemoval(), A)
        self.assertEqual(archive.message(self.ref)["text"], "我没有说做，只是先让你整理。")
        self.assertEqual(archive.db.execute("SELECT COUNT(*) FROM archive_turns WHERE thread_id=?", (A,)).fetchone()[0], 0)

    def test_missing_boundary_falls_back_and_marks_removed_evidence(self):
        self.context.save(self.payload(), actor=C)
        result = self.context.archive.refresh(RecentHistory([[turn("t1", user("old", "Reverted history"))]]), A)
        self.assertEqual(result["mode"], "full_boundary_missing")
        self.assertEqual(self.context.get()["entries"][0]["source_warnings"][0]["status"], "source_missing")

    def test_failed_incremental_read_preserves_index_and_saved_understanding(self):
        class Broken(RecentHistory):
            def recent_pages(self, ident):
                yield [turn("new", user("new", "Uncommitted text"))]
                raise RpcError("Interrupted before reaching boundary")
        self.context.save(self.payload(), actor=C)
        before = self.context.coverage()
        with self.assertRaises(RpcError):
            self.context.archive.refresh(Broken(), A)
        self.assertEqual(self.context.coverage(), before)
        self.assertEqual(self.context.archive.search("Uncommitted")["match_count"], 0)

    def test_explicit_full_refresh_can_find_an_edit_before_the_boundary(self):
        changed = RecentHistory([[turn("t1", user("m1", "An earlier corrected message"))],
                                 [turn("t2", user("m3", "我没有说做，只是先让你整理。"))]])
        self.context.archive.refresh(changed, A, full=True)
        self.assertEqual(self.context.archive.search("earlier corrected")["match_count"], 1)

    def test_adding_current_chat_as_a_source_is_explicit_and_invalidates_coverage(self):
        self.context.save(self.payload(), actor=C)
        result = self.context.add_source({"thread": C, "scope": "analysis", "label": "New feedback"})
        self.assertTrue(result["added"])
        self.assertFalse(self.context.coverage()["all_sources_indexed"])
        self.assertTrue(self.context.get()["needs_review"])
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.context.save(self.payload("not-yet-indexed"), actor=C)
        self.context.archive.refresh(RecentHistory([[turn("c1", user("c1", "New feedback"))]]), C)
        self.context.save(self.payload("indexed-feedback"), actor=C)
        self.assertFalse(self.context.get()["needs_review"])

    def test_budget_omissions_are_visible_and_the_whole_entry_can_be_requested(self):
        self.context.save(self.payload(), actor=C)
        tiny = self.context.get(chars=1)
        self.assertEqual(tiny["omitted_entries"], 1)
        self.assertEqual(tiny["entries"], [])
        self.assertEqual(len(self.context.get(key="exploration")["entries"]), 1)

    def test_copied_background_can_be_registered_without_the_original_directory(self):
        self.context.save(self.payload(), actor=C)
        self.context.close()
        shutil.copytree(self.root / "saved", self.root / "moved")
        self.context = Context(self.root / "moved")
        registry = Registry(self.root / "new-machine")
        registry.register("Fictional writing background", self.context.archive.root)
        self.assertEqual(registry.resolve(name="Fictional writing background")[0], self.root / "moved")
        self.assertEqual(self.context.get()["entries"][0]["sources"][0]["quote"], "我没有说做，只是先让你整理。")

    def test_cli_saved_name_and_new_chat_binding_work_without_a_source_membership(self):
        self.context.save(self.payload(), actor=C)
        home = self.root / "cli-home"
        Registry(home).register("Fictional writing background", self.context.archive.root)
        environment = {**os.environ, "DIALOGUE_BRIDGE_HOME": str(home), "CODEX_THREAD_ID": C}
        cli = str(PLUGIN / "scripts/dialogue.py")
        opened = subprocess.run([sys.executable, "-B", cli, "--name", "Fictional writing background", "context-open"],
                                env=environment, capture_output=True, encoding="utf-8")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.assertEqual(json.loads(opened.stdout)["bound_to"], C)
        shown = subprocess.run([sys.executable, "-B", cli, "context-show"], env=environment,
                               capture_output=True, encoding="utf-8")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(json.loads(shown.stdout)["entries"][0]["key"], "exploration")

    def test_bundled_context_example_runs_without_codex_or_model_calls(self):
        result = subprocess.run([sys.executable, "-B", str(PLUGIN / "scripts/context_demo.py"),
                                 "--directory", str(self.root / "demo")], capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(all(data["checks"].values()), data)
        self.assertEqual(data["model_calls"], 0)

    def test_background_name_does_not_silently_override_an_explicit_other_directory(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            Registry(self.root / "registry").resolve(name="Another background", directory=self.context.archive.root)

    def test_old_archive_without_checkpoints_is_fully_reindexed(self):
        with self.context.archive.db:
            self.context.archive.db.execute("DELETE FROM archive_turns WHERE thread_id=?", (A,))
        result = self.context.archive.refresh(RecentHistory(), A)
        self.assertEqual(result["mode"], "full")
        self.assertEqual(self.context.archive.search("我没有说做")["match_count"], 1)

    def test_registry_retains_a_reusable_private_interpreter(self):
        registry = Registry(self.root / "runtime-registry")
        registry.register("Saved", self.context.archive.root)
        self.assertEqual(registry.list()[0]["runtime_python"], str(Path(sys.executable).resolve()))

    def test_source_links_match_exactly_regardless_of_order_or_repetition(self):
        registry = Registry(self.root / "link-registry")
        registry.register("Saved", self.context.archive.root)
        matches = registry.list([f"codex://threads/{B}", A, A])
        self.assertEqual([row["name"] for row in matches], ["Saved"])
        self.assertEqual({s["thread"] for s in matches[0]["sources"]}, {A, B})
        self.assertEqual(registry.list([A]), [])
        self.assertEqual(registry.list([A, B, C]), [])

    def test_an_unavailable_saved_folder_does_not_hide_other_link_matches(self):
        registry = Registry(self.root / "missing-registry")
        registry.register("Missing", self.root / "not-here")
        registry.register("Saved", self.context.archive.root)
        self.assertFalse(registry.list()[0]["available"])
        self.assertEqual([r["name"] for r in registry.list([A, B])], ["Saved"])

    def test_cli_matches_supplied_links_without_requiring_a_saved_name(self):
        home = self.root / "links-cli-home"
        Registry(home).register("Saved", self.context.archive.root)
        result = subprocess.run([sys.executable, "-B", str(PLUGIN / "scripts/dialogue.py"), "context-list",
                                 "--thread", f"codex://threads/{B}", "--thread", A],
                                env={**os.environ, "DIALOGUE_BRIDGE_HOME": str(home)},
                                capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["selection"], "exact_source_set")
        self.assertEqual([r["name"] for r in data["backgrounds"]], ["Saved"])

    def test_a_document_edit_during_commit_is_not_overwritten(self):
        self.context.save(self.payload(), actor=C)
        document = self.context.archive.root / "understanding.md"
        commit = self.context.ledger.commit
        def edit_after_commit(*args, **kwargs):
            result = commit(*args, **kwargs)
            document.write_text("A simultaneous user correction", encoding="utf-8")
            return result
        with patch.object(self.context.ledger, "commit", side_effect=edit_after_commit):
            result = self.context.save(self.payload("concurrent-edit"), actor=C)
        self.assertIn("document_warning", result)
        self.assertEqual(document.read_text(encoding="utf-8"), "A simultaneous user correction")

    def test_a_malformed_incremental_turn_rolls_back_partial_writes(self):
        import sqlite3
        before = self.context.coverage()
        malformed = RecentHistory([[turn("t2", user("m3", "我没有说做，只是先让你整理。"))],
                                   [turn("t3", user("same", "one"), user("same", "two"))]])
        with self.assertRaises(sqlite3.IntegrityError):
            self.context.archive.refresh(malformed, A)
        self.assertEqual(self.context.coverage(), before)
        self.assertEqual(self.context.archive.message(self.ref)["text"], "我没有说做，只是先让你整理。")


if __name__ == "__main__":
    unittest.main()
