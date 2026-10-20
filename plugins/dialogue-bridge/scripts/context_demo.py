"""Fictional end-to-end saved-background example; no Codex or model calls."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dialogue_bridge.context import Context, Registry

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
C = "00000000-0000-4000-8000-000000000003"


def turn(ident, text):
    return {"id": ident, "items": [{"id": "user", "type": "userMessage", "content": [{"type": "text", "text": text}]}]}


class FictionalHistory:
    def __init__(self, turns):
        self.turns = turns

    def metadata(self, ident):
        return {"name": "Fictional background source", "status": {"type": "notLoaded"}}

    def pages(self, ident):
        yield self.turns

    def recent_pages(self, ident):
        for item in reversed(self.turns):
            yield [item]


def run(directory):
    root = Path(directory)
    if root.exists():
        raise ValueError("Use a new private demo directory; existing material is not replaced")
    context = Context.create(root / "background", "Fictional background", [
        {"thread": A, "scope": "writing"}, {"thread": B, "scope": "research"}])
    try:
        context.archive.refresh(FictionalHistory([turn("a1", "Discuss first; a later explicit request may authorize the work.")]), A)
        context.archive.refresh(FictionalHistory([turn("b1", "This report is provisional.")]), B)
        payload = {"operation_id": "first", "expected_revision": 0,
                   "coverage_token": context.coverage()["token"], "purpose": "New discussion with prior examples",
                   "reason": "The original correction is local, not a permanent approval requirement",
                   "entries": [{"key": "discussion", "scope": "shared", "text": "Respect exploration in context.",
                                "sources": [{"ref": f"{A}/a1/user", "quote": "Discuss first"}]}]}
        context.save(payload, actor=C)
        registry = Registry(root / "private-registry")
        registry.register("Fictional background", context.archive.root)
        registry.bind("Fictional background", C)
        revised = {**payload, "operation_id": "reconsider", "expected_revision": 1,
                   "entries": [{**payload["entries"][0], "text": "Follow the later explicit request when it authorizes work."}]}
        context.save(revised, actor=C)
        replay = context.save(payload, actor=C)
        update = context.archive.refresh(FictionalHistory([
            turn("a1", "Discuss first; a later explicit request may authorize the work."),
            turn("a2", "Now carry out the requested work.")]), A)
        checks = {
            "new_reader_does_not_become_source": C not in context.archive.threads,
            "saved_name_resolves_for_reader": registry.resolve(actor=C)[0] == context.archive.root,
            "original_evidence_retained": context.get()["entries"][0]["sources"][0]["quote"] == "Discuss first",
            "revision_history_preserved": context.ledger.snapshot(at_revision=1).state["understanding"]["entries"][0]["text"] == "Respect exploration in context.",
            "old_retry_does_not_undo_revision": replay["replayed"] and context.ledger.revision == 2,
            "incremental_update_requests_review": update["mode"] == "incremental" and context.get()["needs_review"],
        }
        result = {"checks": checks, "fictional": True, "model_calls": 0,
                  "directory": str(root.resolve()), "meaning": "Protocol demonstration, not a test of understanding quality"}
        (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.directory), ensure_ascii=True, indent=2))
