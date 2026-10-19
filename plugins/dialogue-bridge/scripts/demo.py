"""Run a fictional, model-free collaboration in a new private directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dialogue_bridge.archive import Archive
from dialogue_bridge.notes import Notes, require_core

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"


class FictionalHistory:
    def metadata(self, ident):
        return {"id": ident, "name": "Fictional planner" if ident == A else "Fictional reviewer"}

    def pages(self, ident):
        if ident == A:
            items = [{"type": "userMessage", "id": "goal", "content": [{"type": "text", "text": "先讨论方案，暂时不要实现。"}]},
                     {"type": "agentMessage", "id": "guess", "text": "准备开始实现。"}]
        else:
            items = [{"type": "userMessage", "id": "scope", "content": [{"type": "text", "text": "复盘当前项目，不扩大工作范围。"}]}]
        yield [{"id": "fictional-turn", "itemsView": "full", "items": items}]


def run_demo(directory):
    require_core()
    root = Path(directory).resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("The demo needs a new or empty directory; existing data was not changed")
    archive = Archive.create(root, "fictional-dialogue-demo", [A, B])
    planner = reviewer = None
    try:
        for ident in [A, B]:
            archive.sync(FictionalHistory(), ident)
        user_ref = f"{A}/fictional-turn/goal"
        guess_ref = f"{A}/fictional-turn/guess"
        hit = archive.search("讨论", role="user")["hits"][0]
        original = archive.read(hit["ref"])["messages"][0]["text"]
        planner, reviewer = Notes(archive, actor=A), Notes(archive, actor=B)
        old = planner.record({"operation_id": "demo-initial", "kind": "understanding", "key": "goal",
                              "text": "候选理解：可以开始实现。", "scope": "Fictional example only",
                              "recipients": [B], "sources": [{"ref": guess_ref, "quote": "准备开始实现"}]})
        request = planner.record({"operation_id": "demo-request", "kind": "request", "key": "review",
                                  "text": "请核对这个理解有没有遗漏用户的限制。", "scope": "Fictional example only",
                                  "recipients": [B], "sources": [], "relates_to": old["id"]})
        correction_payload = {"operation_id": "demo-correction", "kind": "response", "key": "review",
                              "text": "讨论不是执行授权；原话要求先讨论。", "scope": "Fictional example only",
                              "recipients": [A], "sources": [{"ref": user_ref, "quote": "先讨论方案，暂时不要实现"}],
                              "relates_to": request["id"]}
        correction = reviewer.record(correction_payload)
        retry = reviewer.record(correction_payload)
        before = reviewer.inbox()
        revised = planner.record({"operation_id": "demo-revision", "kind": "correction", "key": "goal",
                                  "text": "修订理解：当前只比较方案，等待进一步授权。", "scope": "Fictional example only",
                                  "recipients": [B], "supersedes": old["id"], "relates_to": correction["id"],
                                  "sources": [{"kind": "note", "ref": correction["id"], "quote": "讨论不是执行授权"},
                                              {"ref": user_ref, "quote": "暂时不要实现"}]})
        delta = reviewer.inbox(cursor=before["next_cursor"])
        checks = {"original_user_text_found": original == "先讨论方案，暂时不要实现。",
                  "same_input_retry_keeps_record": retry["id"] == correction["id"],
                  "old_interpretation_retained": planner.fetch(old["id"])["body"]["text"] == "候选理解：可以开始实现。",
                  "revision_links_old_interpretation": planner.fetch(revised["id"])["body"]["supersedes"] == old["id"],
                  "saved_position_returns_only_new_record": [x["id"] for x in delta["notes"]] == [revised["id"]],
                  "no_authoritative_state_written": planner.ledger.snapshot().state == {}}
        if not all(checks.values()):
            raise RuntimeError(f"Demo check failed: {checks}")
        result = {"mode": "fictional deterministic protocol example; no AI discussion was run",
                  "directory": str(root), "real_chats_read": 0, "model_calls": 0,
                  "checks": checks, "records": {"initial": old["id"], "request": request["id"],
                                               "peer_response": correction["id"], "revision": revised["id"]},
                  "new_inbox_ids": [x["id"] for x in delta["notes"]],
                  "meaning": "Scripted inputs demonstrate storage and source checks; models still judge relevance and interpretations"}
        (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if reviewer:
            reviewer.close()
        if planner:
            planner.close()
        archive.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, help="New private example directory; no existing data is replaced")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run_demo(args.directory), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
