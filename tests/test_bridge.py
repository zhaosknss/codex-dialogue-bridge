import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "dialogue-bridge"
sys.path.insert(0, str(PLUGIN))
if os.environ.get("AGENT_STATE_CORE_PATH"):
    sys.path.insert(0, os.environ["AGENT_STATE_CORE_PATH"])

from dialogue_bridge.archive import Archive
from dialogue_bridge.notes import Notes
from dialogue_bridge.rpc import ReadOnlyCodex, RpcError
from dialogue_bridge.session import start_workspace

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
C = "00000000-0000-4000-8000-000000000003"


def turn(ident, *items):
    return {"id": ident, "itemsView": "full", "items": list(items)}


def user(ident, text):
    return {"type": "userMessage", "id": ident, "content": [{"type": "text", "text": text}]}


class History:
    def __init__(self, pages=None):
        self.data = pages if pages is not None else [
            [turn("t1", user("m1", "先讨论底层，插件只是候选。"),
                  {"type": "reasoning", "id": "private", "text": "DO_NOT_INDEX"},
                  {"type": "agentMessage", "id": "m2", "text": "准备开始制作。", "phase": "final_answer"})],
            [turn("t2", user("m3", "我没有说做，只是先让你整理。"))],
        ]

    def metadata(self, ident):
        return {"id": ident, "name": "Fictional independent chat", "status": {"type": "notLoaded"}}

    def pages(self, ident):
        yield from copy.deepcopy(self.data)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.archive = Archive.create(Path(self.temp.name) / "project", "fictional", [A, B])
        self.archive.sync(History(), A)
        self.archive.sync(History([[turn("b1", user("m1", "另一个方向可以借用接口经验。"))]]), B)
        self.notes = Notes(self.archive, actor=A)
        self.ref = f"{A}/t2/m3"

    def tearDown(self):
        self.notes.close()
        self.archive.close()
        self.temp.cleanup()

    def payload(self, ident="first", **changes):
        data = {"operation_id": ident, "kind": "understanding", "key": "goal",
                "text": "This is discussion, not permission to build.", "scope": "The current task only.",
                "recipients": [B], "sources": [{"ref": self.ref, "quote": "只是先让你整理"}]}
        data.update(changes)
        return data

    def test_full_paging_keeps_early_and_later_corrections(self):
        result = self.archive.search("底层", role="user")
        self.assertEqual(result["hits"][0]["ref"], f"{A}/t1/m1")
        result = self.archive.read(result["hits"][0]["ref"], after=2)
        self.assertIn("我没有说做", result["messages"][-1]["text"])
        self.assertEqual(self.archive.search("DO_NOT_INDEX")["match_count"], 0)

    def test_unicode_and_literal_sql_characters(self):
        self.assertEqual(self.archive.search("没有 整理")["match_count"], 1)
        self.assertEqual(self.archive.search("%' OR 1=1 --")["match_count"], 0)
        self.assertEqual(self.archive.search("底层", role="assistant")["match_count"], 0)

    def test_bounded_excerpts_and_continuation_read(self):
        self.assertLessEqual(self.archive.search("先", char_budget=3)["excerpt_characters"], 3)
        first = self.archive.read(self.ref, char_budget=5)
        rest = self.archive.read(self.ref, offset=first["messages"][0]["next_offset"])
        self.assertEqual(first["messages"][0]["text"] + rest["messages"][0]["text"], self.archive.message(self.ref)["text"])

    def test_search_does_not_let_one_long_chat_hide_other_matches(self):
        self.archive.sync(History([[turn("many", *(user(f"m{i}", "共同目标") for i in range(10)))]]), A)
        self.archive.sync(History([[turn("peer", user("one", "共同目标也要考虑另一种解释"))]]), B)
        result = self.archive.search("共同目标", limit=2)
        self.assertEqual({x["thread_id"] for x in result["hits"]}, {A, B})

    def test_non_text_coverage_and_unsynced_selection_are_visible(self):
        image_user = user("image", "Some text")
        image_user["content"].append({"type": "image", "url": "private-local-image"})
        self.archive.sync(History([[turn("image", image_user)]]), A)
        self.assertEqual(self.archive.status()["threads"][0]["non_text_inputs"], 1)
        other = Archive.create(Path(self.temp.name) / "unsynced", "empty", [A])
        try:
            result = other.search("anything")
            self.assertIsNone(result["coverage"]["threads"][0]["scan_finished"])
            self.assertEqual(result["match_count"], 0)
        finally:
            other.close()

    def test_failed_sync_preserves_previous_index(self):
        class Interrupted(History):
            def pages(self, ident):
                yield [turn("replacement", user("new", "Incomplete new history"))]
                raise RpcError("Connection failed before older history arrived")
        before = self.archive.status()
        with self.assertRaises(RpcError):
            self.archive.sync(Interrupted(), A)
        self.assertEqual(self.archive.status(), before)
        self.assertEqual(self.archive.message(self.ref)["text"], "我没有说做，只是先让你整理。")
        self.assertEqual(self.archive.search("Incomplete")["match_count"], 0)

    def test_duplicate_turn_is_not_claimed_as_complete(self):
        duplicate = History([[turn("same", user("x", "one"))], [turn("same", user("y", "two"))]])
        with self.assertRaisesRegex(ValueError, "Repeated turn"):
            self.archive.sync(duplicate, A)
        self.assertEqual(self.archive.search("底层")["match_count"], 1)

    def test_sources_must_be_real_and_verbatim(self):
        with self.assertRaisesRegex(ValueError, "verbatim"):
            self.notes.record(self.payload(sources=[{"ref": self.ref, "quote": "Start building now"}]))
        with self.assertRaises(ValueError):
            self.notes.record(self.payload(sources=[{"ref": f"{C}/t/m", "quote": "x"}]))
        self.assertEqual(self.notes.ledger.revision, 0)

    def test_unknown_record_fields_are_rejected_without_silent_loss(self):
        for extra in ({"artifacts": [{"sha256": "aaaa"}]}, {"relatesTo": "1:0"}):
            with self.assertRaisesRegex(ValueError, next(iter(extra))):
                self.notes.record(self.payload(**extra))
        self.assertEqual(self.notes.ledger.revision, 0)

    def test_custom_metadata_round_trips_and_changes_are_not_deduplicated(self):
        metadata = {"files": [{"path": "fictional.txt", "sha256": "aaaa", "checked": False}],
                    "application": {"labels": ["example", "not-verified"], "count": 2}}
        payload = self.payload(metadata=metadata)
        first = self.notes.record(payload)
        self.assertEqual(self.notes.fetch(first["id"])["body"]["metadata"], metadata)
        self.assertEqual(self.notes.record(payload)["id"], first["id"])
        changed = copy.deepcopy(payload)
        changed["metadata"]["files"][0]["sha256"] = "bbbb"
        with self.assertRaisesRegex(ValueError, "different content"):
            self.notes.record(changed)
        self.assertEqual(self.notes.ledger.revision, first["revision"])
        self.assertEqual(self.notes.fetch(first["id"])["body"]["status"], "candidate")
        self.assertEqual(self.notes.ledger.snapshot().state, {})

    def test_peer_can_cite_new_shared_contribution_without_resync(self):
        first = self.notes.record(self.payload())
        peer = Notes(self.archive, actor=B)
        try:
            contribution = self.payload("peer-note-source", kind="response", recipients=[A], relates_to=first["id"],
                                        sources=[{"kind": "note", "ref": first["id"], "quote": "discussion, not permission"}])
            result = peer.record(contribution)
            source = peer.fetch(result["id"])["source"]["notes"][0]
            self.assertEqual(source["author_thread"], A)
            self.assertEqual(source["ref"], first["id"])
            self.assertEqual(source["revision"], first["revision"])
            self.assertEqual(source["record_status"], "candidate")
            self.assertEqual(len(source["sha256"]), 64)
            self.assertEqual(peer.record(contribution)["id"], result["id"])
            self.assertEqual(self.archive.search("This is discussion")["match_count"], 0)
            self.assertEqual(self.notes.ledger.snapshot().state, {})
        finally:
            peer.close()

    def test_note_citation_rejects_hidden_sources_and_invented_quotes(self):
        hidden = self.notes.record(self.payload("private", recipients=[A]))
        visible = self.notes.record(self.payload("public"))
        peer = Notes(self.archive, actor=B)
        before = self.notes.ledger.revision
        try:
            with self.assertRaisesRegex(ValueError, "visible history"):
                peer.record(self.payload("hidden-citation", sources=[{"kind": "note", "ref": hidden["id"], "quote": "discussion"}]))
            with self.assertRaisesRegex(ValueError, "verbatim"):
                peer.record(self.payload("invented-citation", sources=[{"kind": "note", "ref": visible["id"], "quote": "Execute everything now"}]))
            self.assertEqual(self.notes.ledger.revision, before)
        finally:
            peer.close()

    def test_append_revision_keeps_original_and_no_authoritative_state(self):
        old = self.notes.record(self.payload())
        newer = self.notes.record(self.payload("new", kind="correction", text="Later evidence clarifies the scope.", supersedes=old["id"]))
        self.assertEqual(self.notes.fetch(old["id"])["body"]["text"], self.payload()["text"])
        self.assertEqual(self.notes.fetch(newer["id"])["body"]["supersedes"], old["id"])
        self.assertEqual(self.notes.ledger.snapshot().state, {})
        self.assertEqual(self.notes.fetch(newer["id"])["source"]["messages"][0]["role"], "user")

    def test_other_author_can_challenge_but_not_overwrite(self):
        old = self.notes.record(self.payload())
        peer = Notes(self.archive, actor=B)
        try:
            with self.assertRaisesRegex(ValueError, "own interpretation"):
                peer.record(self.payload("peer", supersedes=old["id"]))
            response = peer.record(self.payload("reply", kind="response", recipients=[A], relates_to=old["id"]))
            self.assertEqual(self.notes.fetch(response["id"])["body"]["author_thread"], B)
        finally:
            peer.close()

    def test_idempotent_retry_and_changed_operation_rejected(self):
        first = self.notes.record(self.payload())
        self.notes.record(self.payload("another", text="An independent contribution"))
        self.assertEqual(self.notes.record(self.payload())["id"], first["id"])
        with self.assertRaisesRegex(ValueError, "different content"):
            self.notes.record(self.payload(text="Changed on retry"))
        self.assertEqual(self.notes.ledger.revision, 2)

    def test_message_only_retry_with_author_after_recipient_keeps_original_commit(self):
        peer = Notes(self.archive, actor=B)
        try:
            original = self.payload("legacy-order", recipients=[A])
            first = peer.record(original)
            self.notes.record(self.payload("later-commit"))
            revision = self.notes.ledger.revision
            self.assertEqual(peer.record(original)["id"], first["id"])
            self.assertEqual(self.notes.ledger.revision, revision)
        finally:
            peer.close()

    def test_scoped_delivery_and_cursor_across_reopen(self):
        self.notes.record(self.payload("private", recipients=[A]))
        one = self.notes.record(self.payload("one"))
        two = self.notes.record(self.payload("two"))
        page = self.notes.inbox(participant=B, limit=1)
        self.assertEqual([x["id"] for x in page["notes"]], [one["id"]])
        self.assertTrue(page["has_more"])
        self.notes.close()
        self.notes = Notes(self.archive, actor=A)
        final = self.notes.inbox(participant=B, cursor=page["next_cursor"], limit=1)
        self.assertEqual([x["id"] for x in final["notes"]], [two["id"]])
        self.assertFalse(final["has_more"])
        empty = self.notes.inbox(participant=B, cursor=final["next_cursor"])
        self.assertEqual(empty["notes"], [])
        with self.assertRaises(ValueError):
            self.notes.fetch("1:0", participant=B)
        with self.assertRaisesRegex(ValueError, "different workspace or participant"):
            self.notes.inbox(participant=A, cursor=page["next_cursor"])

    def test_unselected_chat_and_other_project_are_excluded(self):
        with self.assertRaises(ValueError):
            self.archive.sync(History(), C)
        with self.assertRaises(ValueError):
            self.notes.record(self.payload(recipients=[C]))
        other = Archive.create(Path(self.temp.name) / "other", "another-project", [A, B])
        other_notes = Notes(other, actor=A)
        try:
            self.notes.record(self.payload())
            self.assertEqual(other_notes.inbox(participant=B)["notes"], [])
            with self.assertRaises(ValueError):
                other_notes.inbox(participant=B, cursor=self.notes.inbox(participant=B)["next_cursor"])
        finally:
            other_notes.close()
            other.close()

    def test_new_records_wait_until_pinned_inbox_history_is_drained(self):
        self.notes.record(self.payload("old-one"))
        second = self.notes.record(self.payload("old-two"))
        page = self.notes.inbox(participant=B, limit=1)
        new = self.notes.record(self.payload("during-drain"))
        finish = self.notes.inbox(participant=B, cursor=page["next_cursor"], limit=1)
        self.assertEqual([n["id"] for n in finish["notes"]], [second["id"]])
        self.assertFalse(finish["has_more"])
        updates = self.notes.inbox(participant=B, cursor=finish["next_cursor"])
        self.assertEqual([n["id"] for n in updates["notes"]], [new["id"]])

    def test_cli_uses_runtime_author_without_faking_peer_identity(self):
        path = Path(self.temp.name) / "note.json"
        path.write_text(json.dumps(self.payload()), encoding="utf-8")
        env = dict(os.environ, CODEX_THREAD_ID=C)
        command = [sys.executable, str(PLUGIN / "scripts/dialogue.py"), "--workspace", str(self.archive.root)]
        if os.environ.get("AGENT_STATE_CORE_PATH"):
            command += ["--core-path", os.environ["AGENT_STATE_CORE_PATH"]]
        run = subprocess.run([*command, "record", "--input", str(path)], env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("outside", run.stderr)
        self.assertEqual(self.notes.ledger.revision, 0)

    def test_reader_refuses_resume_and_model_turns(self):
        client = ReadOnlyCodex()
        for method in ["thread/resume", "thread/start", "turn/start", "turn/steer", "thread/name/set"]:
            with self.assertRaises(ValueError):
                client.request(method, {})

    def test_start_includes_current_chat_and_deduplicates_links(self):
        target = Path(self.temp.name) / "start"
        with patch.dict(os.environ, CODEX_THREAD_ID=A):
            archive, created = start_workspace(target, project="new", threads=[B, f"codex://threads/{B}"])
            try:
                self.assertTrue(created)
                self.assertEqual(archive.threads, [B, A])
                self.assertTrue(all(x["scan_finished"] is None for x in archive.status()["threads"]))
            finally:
                archive.close()
            archive, created = start_workspace(target, project="new", threads=[A, B])
            self.assertFalse(created)
            archive.close()

    def test_start_rejects_changed_scope_and_unselected_actor(self):
        config = (self.archive.root / "project.json").read_bytes()
        with patch.dict(os.environ, CODEX_THREAD_ID=A):
            with self.assertRaisesRegex(ValueError, "Selected chats differ"):
                start_workspace(self.archive.root, threads=[C])
            with self.assertRaisesRegex(ValueError, "Project differs"):
                start_workspace(self.archive.root, project="another")
        with patch.dict(os.environ, CODEX_THREAD_ID=C):
            with self.assertRaisesRegex(ValueError, "outside"):
                start_workspace(self.archive.root)
        self.assertEqual((self.archive.root / "project.json").read_bytes(), config)

    def test_start_without_runtime_does_not_create_workspace(self):
        target = Path(self.temp.name) / "not-created"
        with patch.dict(os.environ, CODEX_THREAD_ID=""):
            with self.assertRaisesRegex(ValueError, "CODEX_THREAD_ID"):
                start_workspace(target, project="new", threads=[B])
        self.assertFalse(target.exists())

    def test_cli_start_returns_scoped_inbox_without_marking_it_processed(self):
        hidden = self.notes.record(self.payload("hidden-start", recipients=[A]))
        shared = self.notes.record(self.payload("shared-start"))
        env = dict(os.environ, CODEX_THREAD_ID=B)
        command = [sys.executable, str(PLUGIN / "scripts/dialogue.py"), "--workspace", str(self.archive.root)]
        if os.environ.get("AGENT_STATE_CORE_PATH"):
            command += ["--core-path", os.environ["AGENT_STATE_CORE_PATH"]]
        def run(*extra):
            result = subprocess.run([*command, "start", *extra], env=env, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        first = run()
        self.assertFalse(first["created"])
        self.assertEqual([x["id"] for x in first["inbox"]["notes"]], [shared["id"]])
        self.assertNotIn(hidden["id"], [x["id"] for x in first["inbox"]["notes"]])
        self.assertEqual(run()["inbox"], first["inbox"])
        self.assertEqual(run("--cursor", first["inbox"]["next_cursor"])["inbox"]["notes"], [])
        self.assertEqual(self.notes.ledger.revision, 2)

    def test_rpc_pagination_requires_nonrepeating_cursor(self):
        client = ReadOnlyCodex()
        with patch.object(client, "request", side_effect=[{"data": [], "nextCursor": "same"}, {"data": [], "nextCursor": "same"}]):
            with self.assertRaises(RpcError):
                list(client.pages(A))


if __name__ == "__main__":
    unittest.main()
