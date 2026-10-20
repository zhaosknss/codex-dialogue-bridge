"""CLI used by the bundled skill. Payloads go through files, not shell interpolation."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dialogue_bridge.archive import Archive
from dialogue_bridge.rpc import ReadOnlyCodex


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", help="Private data directory; saved-context commands can use --name or this chat's binding")
    parser.add_argument("--name", help="Reusable private background name (context commands)")
    parser.add_argument("--core-path", help="Optional agent-state-core source checkout, instead of an installed package")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--project", required=True)
    init.add_argument("--thread", action="append", required=True)
    start = commands.add_parser("start", help="Initialize or reopen a selection and show history coverage plus the current chat's inbox")
    start.add_argument("--project", help="Required only for a new collaboration")
    start.add_argument("--thread", action="append", help="User-selected UUID or codex://threads/ link; current chat is included automatically")
    start.add_argument("--cursor", help="Last processed inbox position; not saved or advanced automatically")
    start.add_argument("--limit", type=int, default=8)
    commands.add_parser("status")
    sync = commands.add_parser("sync")
    sync.add_argument("--thread", action="append")
    search = commands.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--role", choices=["user", "assistant"])
    search.add_argument("--limit", type=int, default=8)
    search.add_argument("--chars", type=int, default=6000)
    read = commands.add_parser("read")
    read.add_argument("--ref", required=True)
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--chars", type=int, default=10000)
    read.add_argument("--before", type=int, default=0)
    read.add_argument("--after", type=int, default=0)
    record = commands.add_parser("record")
    record.add_argument("--input", required=True, help="UTF-8 JSON file; do not put private text into shell code")
    inbox = commands.add_parser("inbox")
    inbox.add_argument("--participant")
    inbox.add_argument("--cursor")
    inbox.add_argument("--limit", type=int, default=8)
    note = commands.add_parser("note")
    note.add_argument("--id", required=True)
    note.add_argument("--participant")
    listing = commands.add_parser("context-list", help="List saved backgrounds, optionally matching an exact set of source links")
    listing.add_argument("--thread", action="append", help="Match this exact source set; repeat for each supplied chat link")
    for name in ("context-init", "context-save", "context-source"):
        command = commands.add_parser(name)
        command.add_argument("--input", required=True, help="UTF-8 JSON prepared by the skill")
    commands.add_parser("context-register", help="Register a portable context folder on this machine")
    commands.add_parser("context-overview", help="See source scopes, index coverage and history samples")
    refresh = commands.add_parser("context-sync", help="Index selected histories, then refresh new turns and the saved boundary")
    refresh.add_argument("--full", action="store_true", help="Audit the complete history, including older edits")
    changes = commands.add_parser("context-changes")
    changes.add_argument("--after-change", type=int)
    changes.add_argument("--limit", type=int, default=20)
    changes.add_argument("--chars", type=int, default=6000)
    for name in ("context-open", "context-show"):
        command = commands.add_parser(name)
        command.add_argument("--scope", action="append", help="Selected project scopes; shared entries are also included")
        command.add_argument("--query", help="Optional literal terms over curated understanding")
        command.add_argument("--key", help="Read a particular understanding entry")
        command.add_argument("--chars", type=int, default=12000)
    args = parser.parse_args(argv)
    if args.core_path:
        sys.path.insert(0, str(Path(args.core_path).resolve()))
    archive = None
    try:
        if args.command.startswith("context-"):
            from dialogue_bridge.context import run_context
            result = run_context(args)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if not args.workspace:
            raise ValueError("This collaboration command requires --workspace")
        if args.command in ("start", "record", "inbox", "note"):
            from dialogue_bridge.notes import Notes, require_core
            require_core()  # Fail before creating or opening a collaboration directory.
        if args.command == "start":
            from dialogue_bridge.session import start_workspace
            archive, created = start_workspace(args.workspace, project=args.project, threads=args.thread)
        else:
            archive = (Archive.create(args.workspace, args.project, args.thread)
                       if args.command == "init" else Archive(args.workspace))
        if args.command in ("init", "status"):
            result = archive.status()
        elif args.command == "sync":
            selected = [archive.selected(x) for x in (args.thread or archive.threads)]
            with ReadOnlyCodex() as client:
                # Each thread is committed separately. Failures preserve its previous index.
                # The command exits nonzero; status still exposes each successful scan time.
                result = [archive.sync(client, x) for x in selected]
        elif args.command == "search":
            result = archive.search(args.query, role=args.role, limit=args.limit, char_budget=args.chars)
        elif args.command == "read":
            result = archive.read(args.ref, offset=args.offset, char_budget=args.chars, before=args.before, after=args.after)
        else:
            notes = Notes(archive)
            try:
                if args.command == "start":
                    result = {"workspace": str(archive.root.resolve()), "created": created,
                              "history": archive.status(),
                              "inbox": notes.inbox(cursor=args.cursor, limit=args.limit),
                              "next": "Sync unsaved/stale history when needed, then search and read relevant evidence; start does not scan chats or send messages"}
                elif args.command == "record":
                    result = notes.record(json.loads(Path(args.input).read_text(encoding="utf-8-sig")))
                elif args.command == "inbox":
                    result = notes.inbox(participant=args.participant, cursor=args.cursor, limit=args.limit)
                else:
                    result = notes.fetch(args.id, participant=args.participant)
            finally:
                notes.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TimeoutError, sqlite3.Error) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if archive:
            archive.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
