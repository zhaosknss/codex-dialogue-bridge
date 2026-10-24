import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from test_bridge import A, C, History, turn, user
from dialogue_bridge.bundles import export_bundle, import_bundle, inspect_bundle, MANIFEST
from dialogue_bridge.context import Context
from dialogue_bridge.notes import Notes


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.context = Context.create(self.root / "source", "Fictional planning background", [
            {"thread": A, "scope": "planning", "label": "Planning"}])
        self.context.archive.sync(History([[turn("first", user("message", "Discuss the alternatives before choosing."))]]), A)
        self.context.save({
            "operation_id": "first", "expected_revision": 0,
            "coverage_token": self.context.coverage()["token"],
            "purpose": "Fictional portable background", "reason": "Preserve a scoped example",
            "entries": [{"key": "alternatives", "scope": "planning", "status": "working",
                         "text": "Keep alternatives open while discussing this design.",
                         "sources": [{"ref": f"{A}/first/message", "quote": "Discuss the alternatives before choosing."}]}]}, actor=C)

    def tearDown(self):
        self.context.close()
        self.temporary.cleanup()

    def bundle(self, name="portable.zip"):
        target = self.root / name
        export_bundle(self.context, target)
        return target

    def rewrite(self, source, output, transform):
        with zipfile.ZipFile(source) as original:
            rows = [(info, original.read(info)) for info in original.infolist()]
        rows = transform(rows)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for info, data in rows:
                    archive.writestr(info, data)
        return output

    def test_roundtrip_keeps_frozen_evidence_revisions_dirty_views_and_excludes_runtime(self):
        source = self.context.archive.root
        (source / "shared.md").write_text("An explicit unadopted local edit.\n", encoding="utf-8")
        (source / "INDEX.md").write_text("# Private index\n", encoding="utf-8")
        (source / "chats").mkdir()
        (source / "chats" / f"{A}.md").write_text("Independent interpretation.\n", encoding="utf-8")
        private = source / ".dialogue-documents"
        (private / "pending").mkdir(parents=True)
        (private / "projections.json").write_text('{"version":1,"files":{}}', encoding="utf-8")
        pending = private / "pending" / ("external-" + "a" * 32 + ".json")
        pending.write_text('{"origin":"external_edit","editor":"unknown"}', encoding="utf-8")
        (source / "evidence").mkdir()
        evidence = source / "evidence" / ("b" * 64 + ".json")
        evidence.write_text('{"kind":"fictional preserved quote"}', encoding="utf-8")
        for name in ("settings.json", "credentials.json", ".bridge.lock", "jobs.db", "worker.py"):
            (source / name).write_text("FICTIONAL_RUNTIME_MARKER", encoding="utf-8")
        # Future operational settings in project metadata must not leave the host.
        config = json.loads((source / "project.json").read_text(encoding="utf-8"))
        config["runtime"] = {"model_command": ["fictional-worker"], "credential": "FICTIONAL_MARKER"}
        config["context"]["auto_understand"] = True
        (source / "project.json").write_text(json.dumps(config), encoding="utf-8")
        output = self.bundle()
        with zipfile.ZipFile(output) as bundle:
            self.assertFalse({"settings.json", "credentials.json", ".bridge.lock", "jobs.db", "worker.py"} & set(bundle.namelist()))
            exported_config = json.loads(bundle.read("project.json"))
            self.assertEqual(set(exported_config), {"project", "context", "threads"})
            self.assertEqual(set(exported_config["context"]), {"id", "name", "sources"})
            manifest = json.loads(bundle.read(MANIFEST))
            for item in manifest["files"]:
                self.assertEqual(item["sha256"], hashlib.sha256(bundle.read(item["path"])).hexdigest())
        result = import_bundle(output, self.root / "restored")
        restored = Path(result["directory"])
        self.assertTrue(result["frozen"])
        self.assertEqual((restored / "shared.md").read_text(encoding="utf-8"), "An explicit unadopted local edit.\n")
        self.assertEqual((restored / pending.relative_to(source)).read_bytes(), pending.read_bytes())
        self.assertEqual((restored / evidence.relative_to(source)).read_bytes(), evidence.read_bytes())
        self.assertFalse((restored / "settings.json").exists())
        reopened = Context(restored)
        try:
            self.assertEqual(reopened.ledger.revision, 1)
            self.assertEqual(reopened.archive.message(f"{A}/first/message")["text"], "Discuss the alternatives before choosing.")
            self.assertEqual(reopened.snapshot()[1]["entries"][0]["key"], "alternatives")
        finally:
            reopened.close()

    def test_sqlite_backup_includes_committed_wal_without_sidecars(self):
        db = self.context.archive.db
        db.execute("PRAGMA journal_mode=WAL")
        self.context.archive.sync(History([[turn("second", user("wal", "A committed later example."))]]), A)
        output = self.bundle()
        restored = self.root / "wal-restored"
        import_bundle(output, restored)
        with zipfile.ZipFile(output) as bundle:
            self.assertFalse(any(name.endswith(("-wal", "-shm")) for name in bundle.namelist()))
        check = sqlite3.connect(restored / "archive.db")
        try:
            self.assertEqual(check.execute("SELECT text FROM messages WHERE item_id='wal'").fetchone()[0], "A committed later example.")
        finally:
            check.close()

    def test_existing_export_and_populated_import_are_never_replaced(self):
        output = self.bundle()
        original = output.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            export_bundle(self.context, output)
        self.assertEqual(output.read_bytes(), original)
        target = self.root / "occupied"
        target.mkdir()
        (target / "keep.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "new or empty"):
            import_bundle(output, target)
        self.assertEqual((target / "keep.txt").read_text(), "keep")

    def test_empty_target_is_supported_without_registry_or_binding_changes(self):
        target = self.root / "empty"
        target.mkdir()
        registry = self.root / "host-registry"
        with patch.dict(os.environ, {"DIALOGUE_BRIDGE_HOME": str(registry)}):
            import_bundle(self.bundle(), target)
        self.assertTrue((target / "project.json").exists())
        self.assertFalse(registry.exists())

    def test_corruption_is_rejected_before_target_install(self):
        output = self.bundle()
        corrupted = self.rewrite(output, self.root / "corrupt.zip", lambda rows: [
            (info, data + b"tampered" if info.filename == "understanding.md" else data) for info, data in rows])
        target = self.root / "corrupt-target"
        with self.assertRaisesRegex(ValueError, "size|hash"):
            import_bundle(corrupted, target)
        self.assertFalse(target.exists())
        self.assertFalse(list(self.root.glob(".bridge-import-*")))

    def test_duplicate_traversal_absolute_backslash_and_symlink_members_are_rejected(self):
        output = self.bundle()
        extras = ["../escape.md", "/absolute.md", "chats\\escape.md", "understanding.md"]
        for index, name in enumerate(extras):
            with self.subTest(name=name):
                bad = self.rewrite(output, self.root / f"unsafe-{index}.zip", lambda rows, n=name: [*rows, (n, b"unsafe")])
                with self.assertRaisesRegex(ValueError, "Unsafe|duplicate"):
                    import_bundle(bad, self.root / f"unsafe-{index}")
        def symlink(rows):
            result = []
            for info, data in rows:
                if info.filename == "understanding.md":
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                result.append((info, data))
            return result
        bad = self.rewrite(output, self.root / "link.zip", symlink)
        with self.assertRaisesRegex(ValueError, "regular files"):
            import_bundle(bad, self.root / "linked")

    def test_manifest_identity_and_sqlite_contents_are_checked_even_with_valid_hashes(self):
        output = self.bundle()
        for kind in ("identity", "database"):
            def invalid(rows):
                changed = []
                manifest = None
                for info, data in rows:
                    if info.filename == MANIFEST:
                        manifest = json.loads(data)
                        continue
                    if kind == "database" and info.filename == "archive.db":
                        data = b"not a SQLite database"
                    changed.append((info, data))
                if kind == "identity":
                    manifest["context_id"] = A
                for item in manifest["files"]:
                    data = next(data for info, data in changed if info.filename == item["path"])
                    item.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
                return [(MANIFEST, json.dumps(manifest).encode()), *changed]
            bad = self.rewrite(output, self.root / f"invalid-{kind}.zip", invalid)
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "identity|database"):
                import_bundle(bad, self.root / f"invalid-{kind}")

    def test_size_limits_and_unlisted_members_fail_without_partial_output(self):
        output = self.bundle()
        with patch("dialogue_bridge.bundles.MAX_MEMBER_BYTES", 32):
            with self.assertRaisesRegex(ValueError, "size limit"):
                import_bundle(output, self.root / "too-large")
            with self.assertRaisesRegex(ValueError, "size limit"):
                export_bundle(self.context, self.root / "too-large.zip")
        self.assertFalse((self.root / "too-large").exists())
        self.assertFalse((self.root / "too-large.zip").exists())
        bad = self.rewrite(output, self.root / "unlisted.zip", lambda rows: [*rows, ("shared.md", b"unlisted")])
        with self.assertRaisesRegex(ValueError, "disagree"):
            import_bundle(bad, self.root / "unlisted")

    def test_export_publication_race_does_not_overwrite_new_destination(self):
        output = self.root / "race.zip"
        original_link = os.link
        def raced(source, target):
            Path(target).write_bytes(b"a concurrent export")
            return original_link(source, target)
        with patch("dialogue_bridge.bundles.os.link", side_effect=raced):
            with self.assertRaises(FileExistsError):
                export_bundle(self.context, output)
        self.assertEqual(output.read_bytes(), b"a concurrent export")
        self.assertFalse(list(self.root.glob(".bridge-export-*")))

    def test_optional_notes_database_is_backed_up_with_its_records(self):
        notes = Notes(self.context.archive, actor=A)
        try:
            notes.record({"operation_id": "note", "kind": "understanding", "key": "planning",
                          "text": "A fictional attributed contribution.", "scope": "Planning only",
                          "recipients": [A], "sources": [{"ref": f"{A}/first/message",
                          "quote": "Discuss the alternatives before choosing."}]})
        finally:
            notes.close()
        restored = self.root / "notes-restored"
        import_bundle(self.bundle(), restored)
        reopened = Context(restored)
        notes = Notes(reopened.archive, actor=A)
        try:
            self.assertEqual(len(notes.inbox()["notes"]), 1)
            note = notes.fetch(notes.inbox()["notes"][0]["id"])
            self.assertEqual(note["body"]["text"], "A fictional attributed contribution.")
        finally:
            notes.close()
            reopened.close()

    def test_install_failure_keeps_original_empty_target_and_removes_staging(self):
        output = self.bundle()
        target = self.root / "empty-on-failure"
        target.mkdir()
        with patch("dialogue_bridge.bundles.Path.rename", side_effect=OSError("fictional install failure")):
            with self.assertRaisesRegex(OSError, "install failure"):
                import_bundle(output, target)
        self.assertTrue(target.is_dir())
        self.assertEqual(list(target.iterdir()), [])
        self.assertFalse(list(self.root.glob(".bridge-import-*")))

    def test_inspection_returns_checked_identity_without_installing_or_claiming_payload_validation(self):
        output = self.bundle()
        before = set(self.root.iterdir())
        result = inspect_bundle(output)
        self.assertEqual(result["name"], self.context.config["name"])
        self.assertEqual(result["context_id"], self.context.config["id"])
        self.assertFalse(result["payload_verified"])
        self.assertEqual(set(self.root.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
