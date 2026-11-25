"""Review and apply a sourced, single-file change in a selected local project."""
from __future__ import annotations

import difflib
import hashlib
import os
from pathlib import Path
import stat

from .context import digest, nonempty

MAX_FILE_BYTES = 256 * 1024


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _project(project_root):
    root = Path(nonempty(project_root, "project_root", 2000))
    if not root.is_absolute():
        raise ValueError("Select an absolute project root")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Select an existing project directory")
    return root, digest(os.path.normcase(str(root)))


def _target(project_root, path, context, home):
    root, project_id = _project(project_root)
    relative = nonempty(path, "path", 1000)
    parts = relative.split("/")
    if (any(not part or part != part.rstrip(" .") or part.lower() == ".git" for part in parts)
            or any(ord(char) < 32 for char in relative)
            or "\\" in relative or ":" in relative or Path(relative).suffix.lower() != ".md"):
        raise ValueError("Select an existing project Markdown file by its root-relative path")
    target = root.joinpath(*parts)
    if (target.resolve(strict=True) != target or not target.is_file()
            or any(target.is_relative_to(p.resolve()) for p in (context.archive.root, home))):
        raise ValueError("The target must be a regular project file outside Bridge's private data")
    return target, project_id


def project_proposals(proposals, arguments):
    _, project_id = _project(arguments.get("project_root"))
    path, ident = arguments.get("path"), arguments.get("id")
    if path is not None:
        path = os.path.normcase(nonempty(path, "path", 1000))
    if ident is not None:
        nonempty(ident, "id", 200)
    limit = arguments.get("limit", 8)
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("Use a project proposal limit of 1..30")

    matches = []
    for proposal in proposals:
        edit = proposal.get("project_edit") or {}
        if edit.get("project_id") != project_id or (path is not None and os.path.normcase(edit["path"]) != path):
            continue
        if ident is not None and ident != proposal["id"]:
            continue
        matches.append(proposal)
    matches.sort(key=lambda proposal: proposal["revision"], reverse=True)
    results = matches[:limit] if ident is not None else [
        {**{field: proposal[field] for field in ("id", "status", "revision")},
         "path": proposal["project_edit"]["path"], "source_count": len(proposal["sources"]),
         "reason_preview": proposal["reason"][:240]}
        for proposal in matches[:limit]]
    return {"proposals": results, "total": len(matches), "more": len(matches) > limit}


def _read(path):
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES or b"\0" in data:
        raise ValueError("Project edits require a UTF-8 Markdown file up to 256 KiB")
    data.decode("utf-8")
    return data


def _replace(data, before, after):
    crlf = b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
    if crlf:
        before = before.replace("\r\n", "\n").replace("\n", "\r\n")
        after = after.replace("\r\n", "\n").replace("\n", "\r\n")
    old, new = before.encode("utf-8"), after.encode("utf-8")
    start = data.find(old)
    if start < 0 or data.find(old, start + 1) >= 0:
        raise ValueError("The original excerpt must occur exactly once in the project file")
    if old == new:
        raise ValueError("The replacement must change the project file")
    replacement = data[:start] + new + data[start + len(old):]
    if len(replacement) > MAX_FILE_BYTES or b"\0" in new:
        raise ValueError("The result must be UTF-8 Markdown up to 256 KiB")
    return replacement


def _diff(before, after, path):
    changes = difflib.unified_diff(before.decode("utf-8").splitlines(keepends=True),
                                   after.decode("utf-8").splitlines(keepends=True),
                                   fromfile="a/" + path, tofile="b/" + path)
    return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                   for line in changes)


def propose_project_edit(context, store, actor, arguments, allowed, home):
    from .runtime import _check_sources, _shared, _source_input

    operation = nonempty(arguments.get("operation_id"), "operation_id", 130)
    request = {key: value for key, value in arguments.items() if key not in {"actor", "directory", "name"}}
    fingerprint = digest(request)
    previous = context.ledger.get_commit(f"documents:{actor}:{operation}")
    shared = _shared(context)
    if previous:
        proposal_id = previous.transition.records[0].body.get("result", {}).get("proposal_id")
        proposal = next((p for p in store.view(shared, actor=actor)["proposals"] if p["id"] == proposal_id), None)
        if not proposal or proposal.get("project_edit", {}).get("request_digest") != fingerprint:
            raise ValueError("operation_id was already committed with different content or scope")
        return {"proposal_id": proposal_id, "status": proposal["status"], "revision": shared["revision"],
                "diff": proposal["project_edit"]["diff"], "sources": proposal["sources"], "replayed": True}

    path = arguments.get("path")
    target, project_id = _target(arguments.get("project_root"), path, context, home)
    before = nonempty(arguments.get("before"), "before", 16000)
    after = arguments.get("after")
    if not isinstance(after, str) or len(after) > 16000:
        raise ValueError("after must be text of at most 16000 characters")
    reason = nonempty(arguments.get("reason"), "reason", 4000)
    sources = _check_sources(context, _source_input(arguments.get("sources")), allowed)
    if not sources or any("quote" not in source for source in sources):
        raise ValueError("A project edit requires exact quotations from selected original messages")
    for source in sources:
        source["sha256"] = context.archive.message(source["ref"])["sha256"]
    original = _read(target)
    replacement = _replace(original, before, after)
    edit = {"project_id": project_id, "path": path, "before": before, "after": after,
            "base_sha256": _sha(original), "result_sha256": _sha(replacement),
            "diff": _diff(original, replacement, path), "request_digest": fingerprint}
    result = store.propose(actor, {"operation_id": operation, "expected_revision": arguments.get("expected_revision"),
        "scope": arguments.get("scope", "shared"), "title": f"Update {path}", "text": reason,
        "reason": reason, "type": "project_file_edit", "sources": sources, "project_edit": edit}, shared)
    return {**result, "diff": edit["diff"], "sources": sources}


def apply_project_edit(context, store, actor, arguments, allowed, home):
    from .runtime import _check_sources, _shared, space_lock

    if arguments.get("user_confirmed") is not True:
        raise ValueError("Show the saved diff and get explicit approval before applying it")
    proposal = next((p for p in store.view(_shared(context), actor=actor)["proposals"]
                     if p["id"] == arguments.get("id") and p.get("project_edit")), None)
    if not proposal or proposal["status"] not in {"pending", "accepted"}:
        raise ValueError("Select a visible pending or previously accepted project edit")
    edit = proposal["project_edit"]
    project_root = arguments.get("project_root")
    target, project_id = _target(project_root, edit["path"], context, home)
    if project_id != edit["project_id"]:
        raise ValueError("Use the same project checkout that the user reviewed")
    with space_lock(home / "project-edits" / digest(os.path.normcase(str(target)))):
        target, current_project = _target(project_root, edit["path"], context, home)
        if current_project != project_id:
            raise ValueError("The project checkout changed; prepare a fresh proposal")
        original = _read(target)
        current_sha = _sha(original)
        result = {"proposal_id": proposal["id"], "path": edit["path"], "sha256": edit["result_sha256"]}
        if current_sha == edit["result_sha256"] and proposal["status"] == "accepted":
            return {**result, "status": "already_current"}
        if current_sha != edit["base_sha256"]:
            raise ValueError("The target file changed after preview; prepare a fresh proposal")
        _check_sources(context, proposal["sources"], allowed)
        if any(context.archive.message(source["ref"])["sha256"] != source.get("sha256")
               for source in proposal["sources"]):
            raise ValueError("Original evidence changed after preview; prepare a fresh proposal")
        replacement = _replace(original, edit["before"], edit["after"])
        if _sha(replacement) != edit["result_sha256"]:
            raise ValueError("The saved replacement does not match the reviewed result")
        if proposal["status"] == "pending":
            # Save approval first. If replacement fails or is interrupted, a
            # retry can apply the same approved bytes to the original base.
            store.resolve(actor, proposal["id"], "accepted", "User approved the displayed project diff.")
        if not store._atomic(target, replacement, previous=original, compare=True,
                             mode=stat.S_IMODE(target.stat().st_mode)):
            raise ValueError("The target file changed during apply; prepare a fresh proposal")
        return {**result, "status": "applied"}
