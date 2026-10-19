import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / "plugins/dialogue-bridge"
sys.path[:0] = [str(PLUGIN), str(PLUGIN / "scripts")]
if os.environ.get("AGENT_STATE_CORE_PATH"):
    sys.path.insert(0, os.environ["AGENT_STATE_CORE_PATH"])

from dialogue_bridge.archive import Archive
from dialogue_bridge.environment import dependency_pin, environment_python, matches_pin, prepare_environment
from dialogue_bridge.notes import Notes
from demo import run_demo, B


class SetupTests(unittest.TestCase):
    def test_missing_dependency_fails_before_creating_collaboration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "not-created"
            result = subprocess.run([sys.executable, "-I", "-S", str(PLUGIN / "scripts/dialogue.py"),
                                     "--workspace", str(target), "start", "--project", "fictional"],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 1)
            self.assertIn("scripts", result.stderr)
            self.assertIn("setup.py", result.stderr)
            self.assertIn("references", result.stderr)
            self.assertFalse(target.exists())

    def test_setup_preserves_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "existing.txt"
            sentinel.write_text("Keep this exact text", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "existing files were not changed"):
                prepare_environment(directory)
            self.assertEqual(list(Path(directory).iterdir()), [sentinel])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "Keep this exact text")

    def test_setup_reuses_verified_venv_without_installing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "pyvenv.cfg").touch()
            python = environment_python(root)
            python.parent.mkdir(exist_ok=True)
            python.touch()
            pin = dependency_pin()
            report = {"prefix": str(root), "isolated_venv": True, "paging": True,
                      "module_path": str(root / "lib/agent_state_core/__init__.py"),
                      "origin": {"url": pin["url"], "vcs_info": {"commit_id": pin["commit"]}}}
            with patch("dialogue_bridge.environment.inspect_environment", return_value=report), \
                 patch("dialogue_bridge.environment.subprocess.run") as execute, \
                 patch("dialogue_bridge.environment.shutil.which", return_value=None):
                self.assertTrue(prepare_environment(root)["reused"])
                execute.assert_not_called()
            for changes in [{"isolated_venv": False}, {"prefix": str(root.parent)},
                            {"origin": {"url": pin["url"], "vcs_info": {"commit_id": "0" * 40}}}]:
                changed = copy.deepcopy(report)
                changed.update(changes)
                self.assertFalse(matches_pin(changed, pin, root))

    def test_fictional_demo_retains_provenance_and_does_not_replace_data(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo"
            result = run_demo(target)
            self.assertTrue(all(result["checks"].values()))
            self.assertEqual(result["model_calls"], 0)
            self.assertEqual(result["real_chats_read"], 0)
            archive = Archive(target)
            notes = Notes(archive, actor=B)
            try:
                old = notes.fetch(result["records"]["initial"])
                revised = notes.fetch(result["records"]["revision"])
                self.assertEqual(revised["body"]["supersedes"], old["id"])
                self.assertEqual(revised["source"]["notes"][0]["ref"], result["records"]["peer_response"])
                self.assertEqual(notes.ledger.revision, 4)
            finally:
                notes.close()
                archive.close()
            before = (target / "result.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "existing data was not changed"):
                run_demo(target)
            self.assertEqual((target / "result.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
