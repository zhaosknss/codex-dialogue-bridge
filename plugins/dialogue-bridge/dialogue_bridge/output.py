"""Opt-in lean CLI output; evidence and continuation controls stay intact."""
from __future__ import annotations


def compact_history(history):
    return {
        "project": history["project"],
        "threads": [{key: source[key] for key in
                     ("id", "scan_finished", "messages", "non_text_inputs") if key in source}
                    for source in history["threads"]],
        "text_only": True,
        "excludes": ["tool output", "reasoning", "attachment contents"],
    }


def compact_result(command, result):
    """Drop duplicated index metadata, never excerpts, warnings or save guards."""
    if not isinstance(result, dict):
        return result
    result = dict(result)
    coverage = result.get("coverage")
    if isinstance(coverage, dict):
        if "history" in coverage:
            result["coverage"] = {**coverage, "history": compact_history(coverage["history"])}
        elif "threads" in coverage:
            result["coverage"] = compact_history(coverage)
    if command == "search":
        # The original ref already contains thread/turn/item IDs. Keep the link.
        result["hits"] = [{key: value for key, value in hit.items()
                           if key not in {"thread_id", "turn_id", "item_id"}}
                          for hit in result["hits"]]
    return result
