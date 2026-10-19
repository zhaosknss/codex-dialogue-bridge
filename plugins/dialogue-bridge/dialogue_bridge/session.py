"""Open a selected collaboration without silently changing its scope."""
from __future__ import annotations

import os
from pathlib import Path

from .archive import Archive, thread_id


def start_workspace(directory, *, project=None, threads=None):
    actor = os.environ.get("CODEX_THREAD_ID")
    if not actor:
        raise ValueError("Start from a Codex conversation with CODEX_THREAD_ID; use init/status for offline reads")
    actor = thread_id(actor)
    selected = list(dict.fromkeys(thread_id(x) for x in (threads or []) + [actor]))
    exists = (Path(directory) / "project.json").exists()
    if not exists:
        if not project or not project.strip():
            raise ValueError("A new collaboration requires --project; add --thread links for the selected peers")
        return Archive.create(directory, project, selected), True
    archive = Archive(directory)
    try:
        archive.selected(actor)
        if project is not None and project != archive.project:
            raise ValueError("Project differs from the saved collaboration; use its existing project or a separate workspace")
        if threads is not None and set(selected) != set(archive.threads):
            raise ValueError("Selected chats differ from the saved collaboration; use a separate workspace, not a silent scope change")
        return archive, False
    except Exception:
        archive.close()
        raise
