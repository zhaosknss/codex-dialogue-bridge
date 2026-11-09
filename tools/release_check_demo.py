"""Replay a fictional release check with Bridge and a tiny Python zipapp."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "dialogue-bridge" / "scripts"))
from understanding_demo import BridgeService, FictionalHistory, READER, RESEARCH, WRITING, turn


SPACE = "Fictional release checklist"
BEFORE = "Run the smoke check from the source checkout."
AFTER = "Run the smoke check from the source checkout. Then run the packaged app from a clean directory."
FINDING = "The source check passed, but the release archive failed with ModuleNotFoundError: No module named 'release_helper'."
APP = 'from release_helper import status\nprint(status)\n'
HELPER = 'status = "Release smoke check passed."\n'


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def smoke(target, cwd):
    return subprocess.run([sys.executable, "-I", str(target)], cwd=cwd,
                          capture_output=True, text=True, timeout=15)


def pack(archive, include_helper):
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("__main__.py", APP)
        if include_helper:
            bundle.writestr("release_helper.py", HELPER)


def run(root):
    source = root / "source"
    clean = root / "clean"
    source.mkdir()
    clean.mkdir()
    project_files = {
        root / "project" / "docs" / "release-checks.md": "# Release checks\n\n",
        root / "project" / ".agents" / "skills" / "release-check" / "SKILL.md":
            "---\nname: release-check\ndescription: Check a packaged release before publishing.\n---\n\n",
    }
    for path, heading in project_files.items():
        path.parent.mkdir(parents=True)
        path.write_text(f"{heading}{BEFORE}\n", encoding="utf-8")
    (source / "release_helper.py").write_text(HELPER, encoding="utf-8")
    # The source smoke check has access to the checkout, unlike the zipapp check.
    source_run = subprocess.run([sys.executable, "-I", "-c",
                                 "import sys; sys.path.insert(0, sys.argv[1]); " + APP,
                                 str(source)], cwd=source, capture_output=True, text=True, timeout=15)
    check(source_run.returncode == 0, source_run.stderr)
    broken = root / "before.pyz"
    pack(broken, include_helper=False)
    broken_run = smoke(broken, clean)
    check(broken_run.returncode == 1 and "No module named 'release_helper'" in broken_run.stderr,
          broken_run.stderr)

    history = FictionalHistory()
    history.data = {WRITING: [turn("w1", BEFORE)], RESEARCH: [turn("r1", "Review the packaged release.")]}
    with patch.dict(os.environ, {"DIALOGUE_BRIDGE_HOME": str(root / "registry")}), \
            patch("dialogue_bridge.rpc.ReadOnlyCodex") as transport, \
            patch("dialogue_bridge.models.derive", side_effect=RuntimeError("Model calls are disabled")):
        transport.return_value.__enter__.return_value = history
        planning = BridgeService(actor=WRITING)
        packaging = BridgeService(actor=RESEARCH)
        reader = BridgeService(actor=READER)
        sequence = 0

        def current(actor=planning):
            return actor.call("open", {"name": SPACE, "queue": False})

        def change():
            nonlocal sequence
            sequence += 1
            return {"name": SPACE, "operation_id": f"release-example-{sequence}",
                    "expected_revision": current()["revision"]}

        reader.call("connect", {"name": SPACE, "directory": str(root / "space"), "participate": False,
                    "sources": [{"thread": WRITING, "scope": "shared", "label": "Planning"},
                                {"thread": RESEARCH, "scope": "shared", "label": "Packaging"}]})
        reader.call("sync", {"name": SPACE})
        entry = {"key": "release-check", "scope": "shared", "status": "working", "text": BEFORE,
                 "sources": [{"ref": f"{WRITING}/w1/user", "quote": BEFORE}]}
        reader.call("shared_update", {**change(), "coverage_token": current()["coverage"]["token"],
                    "reason": "Record the fictional starting rule.", "entries": [entry]})
        planning.call("chat_update", {**change(), "scope": "shared", "text": BEFORE,
                      "dependencies": [entry["key"]]})
        packaging.call("chat_update", {**change(), "scope": "shared", "text": "Review package contents.",
                        "dependencies": []})

        history.data[RESEARCH].append(turn("r2", FINDING))
        reader.call("sync", {"name": SPACE})
        sources = [*entry["sources"], {"ref": f"{RESEARCH}/r2/user", "quote": FINDING}]
        revised = {**entry, "text": AFTER, "sources": sources}
        proposal = packaging.call("propose", {**change(), "scope": "shared", "text": AFTER,
                                  "reason": "The packaged app fails its smoke check.", "entries": [revised],
                                  "dependencies": [entry["key"]], "sources": sources})
        check(current()["entries"][0]["text"] == BEFORE, "A pending proposal changed the shared rule")
        review = reader.call("review_proposal", {**change(), "id": proposal["proposal_id"],
                               "decision": "accept", "coverage_token": current()["coverage"]["token"],
                               "reason": "Scripted approval for this fictional project's release checklist."})
        check(review["status"] == "accepted", "The revision was not accepted")
        check(current()["chat"]["needs_review"], "The dependent chat was not marked for review")
        check(not current(packaging)["chat"]["needs_review"], "The unrelated chat document was invalidated")

        fresh_reader = BridgeService(actor="44444444-4444-4444-8444-444444444444")
        selected = current(fresh_reader)["entries"][0]
        check(selected["text"] == AFTER and selected["sources"][-1]["quote"] == FINDING,
              "The fresh reader did not receive the revised rule and source")

    # Simulate the developer applying the reviewed change to the project files.
    for path, heading in project_files.items():
        check(path.read_text(encoding="utf-8") == f"{heading}{BEFORE}\n",
              f"The project file changed before the developer applied the edit: {path.name}")
        path.write_text(f"{heading}{selected['text']}\n", encoding="utf-8")
    fixed = root / "after.pyz"
    pack(fixed, include_helper=True)
    fixed_run = smoke(fixed, clean)
    check(fixed_run.returncode == 0 and fixed_run.stdout.strip() == "Release smoke check passed.", fixed_run.stderr)
    print("Source check: exit 0. Original archive: exit 1 (missing release_helper).")
    print("Bridge: pending correction preserved the old rule. Accepted revision reached a fresh reader.")
    print("Bridge: dependent chat marked for review. Unrelated chat view retained.")
    print("Scripted project edits: docs/release-checks.md and .agents/skills/release-check/SKILL.md.")
    print("Fixed archive: exit 0. Release smoke check passed.")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="bridge-release-example-") as directory:
        run(Path(directory))
