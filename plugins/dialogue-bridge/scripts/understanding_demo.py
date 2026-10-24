"""Fictional, model-free runtime walkthrough in an automatically removed temp space."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if os.environ.get("AGENT_STATE_CORE_PATH"):
    sys.path.insert(0, os.environ["AGENT_STATE_CORE_PATH"])

from dialogue_bridge.service import BridgeService


WRITING = "11111111-1111-4111-8111-111111111111"
RESEARCH = "22222222-2222-4222-8222-222222222222"
READER = "33333333-3333-4333-8333-333333333333"
NAME = "Fictional shared background"


def turn(ident, text):
    return {"id": ident, "itemsView": "full", "items": [{"id": "user", "type": "userMessage",
            "content": [{"type": "text", "text": text}]}]}


class FictionalHistory:
    def __init__(self):
        self.data = {
            WRITING: [turn("w1", "Keep the alternative ending open while we discuss this draft.")],
            RESEARCH: [turn("r1", "Keep sample limits visible when interpreting this report.")],
        }

    def metadata(self, ident):
        return {"id": ident, "name": "Fictional source chat", "status": {"type": "notLoaded"}}

    def pages(self, ident):
        for item in copy.deepcopy(self.data[ident]):
            yield [item]

    def recent_pages(self, ident):
        for item in reversed(copy.deepcopy(self.data[ident])):
            yield [item]


def run():
    history = FictionalHistory()
    with tempfile.TemporaryDirectory(prefix="dialogue-bridge-fictional-") as temporary:
        root = Path(temporary)
        with patch.dict(os.environ, {"DIALOGUE_BRIDGE_HOME": str(root / "registry")}), \
                patch("dialogue_bridge.rpc.ReadOnlyCodex") as transport, \
                patch("dialogue_bridge.models.derive", side_effect=RuntimeError("This demo never invokes a model")):
            transport.return_value.__enter__.return_value = history
            reader, writing, research, manager = (BridgeService(actor=READER), BridgeService(actor=WRITING),
                                                 BridgeService(actor=RESEARCH), BridgeService())
            sequence = 0

            def current():
                return manager.call("open", {"name": NAME, "queue": False})

            def change():
                nonlocal sequence
                sequence += 1
                return {"operation_id": f"fictional-step-{sequence}", "expected_revision": current()["revision"]}

            def checkpoint(condition, description):
                if not condition:
                    raise RuntimeError("Walkthrough did not reach: " + description)
                print(description)

            connected = reader.call("connect", {"name": NAME, "directory": str(root / "space"),
                "sources": [{"thread": WRITING, "scope": "writing", "label": "Writing"},
                            {"thread": RESEARCH, "scope": "research", "label": "Research"}],
                "participate": False})
            reader.call("sync", {"name": NAME})
            checkpoint(not connected["participant"] and current()["coverage"]["all_sources_indexed"],
                       "1. Indexed two fictional histories; the new reader remains separate.")

            entry = {"key": "discussion", "scope": "shared", "status": "working",
                     "text": "Keep alternatives open during discussion, subject to the current task.",
                     "sources": [{"ref": f"{WRITING}/w1/user", "quote": history.data[WRITING][0]["items"][0]["content"][0]["text"]}]}
            initial = reader.call("shared_update", {"name": NAME, **change(),
                "coverage_token": current()["coverage"]["token"], "reason": "A scripted interpretation of the fictional example.",
                "entries": [entry]})
            for service, scope, text in (
                    (writing, "writing", "For this draft, preserve the alternative ending until the choice is made."),
                    (research, "research", "In research, weigh alternatives against the report's sample limits.")):
                service.call("chat_update", {"name": NAME, **change(), "scope": scope,
                    "text": text, "dependencies": ["discussion"]})
            checkpoint(len(manager.call("documents", {"name": NAME})["chats"]) == 2,
                       "2. Saved common context and two independent chat interpretations.")

            correction = "That was local to this draft. After I choose an ending, continue with that choice."
            history.data[WRITING].append(turn("w2", correction))
            reader.call("sync", {"name": NAME})
            revised = {**entry, "text": "Keep this draft's alternatives open while discussing; follow the user's explicit choice afterward.",
                       "sources": [*entry["sources"], {"ref": f"{WRITING}/w2/user", "quote": correction}]}
            proposal = writing.call("propose", {"name": NAME, **change(), "scope": "shared",
                "text": "The later correction narrows the original interpretation to the discussion stage.",
                "reason": "Preserve the original context and the explicit later choice.",
                "entries": [revised], "dependencies": ["discussion"], "sources": revised["sources"]})
            checkpoint(current()["entries"][0]["text"] == entry["text"],
                       "3. Collected a later correction and kept its proposal pending review.")

            reviewed = writing.call("review_proposal", {"name": NAME, **change(), "id": proposal["proposal_id"],
                "decision": "accept", "coverage_token": current()["coverage"]["token"],
                "reason": "The new example limits when this interpretation applies."})
            docs = manager.call("documents", {"name": NAME})
            checkpoint(reviewed["status"] == "accepted" and all(chat["needs_review"] for chat in docs["chats"]),
                       "4. Revised the shared entry; dependent chats now need reconsideration.")
            writing.call("chat_update", {"name": NAME, **change(), "scope": "writing",
                "text": "Once the ending is chosen, use it in the next draft. The research chat keeps its own judgment.",
                "dependencies": ["discussion"]})
            checkpoint(not writing.call("open", {"name": NAME, "queue": False})["chat"]["needs_review"],
                       "5. The writing chat refreshed its own view; this is a document update, not verified writing quality.")

            package = root / "fictional.zip"
            manager.call("export", {"name": NAME, "path": str(package)})
            with patch.dict(os.environ, {"DIALOGUE_BRIDGE_HOME": str(root / "imported-registry")}):
                imported = manager.call("import", {"path": str(package), "directory": str(root / "imported-space")})
                before = current()["revision"]
                manager.call("restore", {"name": NAME, "revision": initial["revision"], "operation_id": "fictional-restore"})
                restored = current()
                checkpoint(imported["frozen"] and restored["revision"] > before and restored["entries"][0]["text"] == entry["text"],
                           "6. Imported the private bundle and restored an earlier interpretation as a new revision.")
    print("Fictional walkthrough complete. No model calls, real chat reads or messages; temporary data removed.")
    print("This demonstrates storage and continuation behavior, not an understanding-quality comparison.")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
