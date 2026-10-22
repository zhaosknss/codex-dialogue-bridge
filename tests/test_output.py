import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_bridge import A, B, History, PLUGIN, turn, user
from dialogue_bridge.archive import Archive
from dialogue_bridge.output import compact_result


class OutputTests(unittest.TestCase):
    def test_search_keeps_evidence_and_incomplete_coverage_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Archive.create(Path(directory) / "background", "Fictional", [A, B])
            try:
                archive.sync(History([[turn("a", user("one", "Repeated corrections matter."))]]), A)
                full = archive.search("corrections", char_budget=7)
                lean = compact_result("search", full)
                self.assertEqual(lean["match_count"], full["match_count"])
                self.assertEqual(lean["more_matches"], full["more_matches"])
                self.assertEqual(lean["excerpt_characters"], 7)
                for key in ("ref", "role", "sha256", "excerpt", "excerpt_offset", "text_length", "link"):
                    self.assertEqual(lean["hits"][0][key], full["hits"][0][key])
                self.assertEqual(lean["coverage"]["threads"][1], {"id": B, "scan_finished": None})
                self.assertTrue(lean["coverage"]["text_only"])
                self.assertIn("attachment contents", lean["coverage"]["excludes"])
                self.assertLess(len(json.dumps(lean)), len(json.dumps(full)))
                self.assertIn("thread_id", full["hits"][0])  # Opt-in output never mutates full results.
            finally:
                archive.close()

    def test_compact_flag_works_for_list_results_and_exact_reads(self):
        self.assertEqual(compact_result("sync", [{"thread_id": A}]), [{"thread_id": A}])
        with tempfile.TemporaryDirectory() as directory:
            archive = Archive.create(Path(directory) / "background", "Fictional", [A])
            try:
                archive.sync(History([[turn("a", user("one", "A complete original message."))]]), A)
                result = archive.read(f"{A}/a/one", char_budget=3)
                self.assertEqual(compact_result("read", result), result)
                cli = str(PLUGIN / "scripts/dialogue.py")
                args = [sys.executable, "-B", cli, "--workspace", str(archive.root)]
                full = subprocess.run([*args, "search", "--query", "original"],
                                      capture_output=True, encoding="utf-8", env=os.environ)
                lean = subprocess.run([*args, "--compact", "search", "--query", "original"],
                                      capture_output=True, encoding="utf-8", env=os.environ)
                self.assertEqual(full.returncode, 0, full.stderr)
                self.assertEqual(lean.returncode, 0, lean.stderr)
                self.assertEqual(json.loads(lean.stdout)["hits"][0]["excerpt"],
                                 json.loads(full.stdout)["hits"][0]["excerpt"])
                self.assertLess(len(lean.stdout), len(full.stdout))
            finally:
                archive.close()
