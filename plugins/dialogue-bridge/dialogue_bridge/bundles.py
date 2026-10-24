"""Portable, frozen understanding bundles. No execution or host registration."""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
from uuid import UUID
import zipfile


FORMAT = "dialogue-bridge-bundle"
VERSION = 1
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_FILES = 4096
MANIFEST = "manifest.json"
DATABASES = {"archive.db", "understanding.db", "notes.db"}
REQUIRED = {"project.json", "archive.db", "understanding.db"}
FIXED = REQUIRED | {"notes.db", "understanding.md", "INDEX.md", "shared.md",
                    ".dialogue-documents/projections.json"}


def _uuid(value):
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("Bundle identities must be canonical UUIDs")
    try:
        canonical = str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Bundle identities must be canonical UUIDs") from exc
    if canonical != value:
        raise ValueError("Bundle identities must be canonical UUIDs")
    return canonical


def _allowed(name):
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in {".", ".."} or ":" in p for p in path.parts):
        return False
    if str(path) != name:
        return False
    if name in FIXED:
        return True
    parts = path.parts
    if len(parts) == 2 and parts[0] == "chats" and parts[1].endswith(".md"):
        try:
            _uuid(parts[1][:-3])
            return True
        except ValueError:
            return False
    return bool(re.fullmatch(r"evidence/[0-9a-f]{64}\.json", name) or
                re.fullmatch(r"\.dialogue-documents/pending/external-[0-9a-f]{32}\.json", name))


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON field in bundle")
        result[key] = value
    return result


def _load(data):
    def invalid_constant(value):
        raise ValueError("Non-finite JSON value in bundle")
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs,
                          parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Bundle contains invalid UTF-8 JSON") from exc


def _dump(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def _text(value, maximum):
    return isinstance(value, str) and 0 < len(value.strip()) <= maximum


def _config(value, *, sanitize=False):
    if not isinstance(value, dict) or not {"project", "threads", "context"} <= set(value):
        raise ValueError("Bundle requires a selected understanding project")
    if not sanitize and set(value) != {"project", "threads", "context"}:
        raise ValueError("Bundle project contains unsupported settings")
    context = value["context"]
    if not isinstance(context, dict) or not {"id", "name", "sources"} <= set(context):
        raise ValueError("Bundle requires context identity, name and sources")
    if not sanitize and set(context) != {"id", "name", "sources"}:
        raise ValueError("Bundle context contains unsupported settings")
    _uuid(context["id"])
    if not _text(value["project"], 120) or not _text(context["name"], 120):
        raise ValueError("Bundle project and context names must be nonempty")
    if value["project"] != context["name"]:
        raise ValueError("Bundle project and context names disagree")
    threads = value["threads"]
    sources = context["sources"]
    if not isinstance(threads, list) or not threads or not isinstance(sources, list) or not sources:
        raise ValueError("Bundle requires selected source chats")
    selected = [_uuid(ident) for ident in threads]
    normalized = []
    for source in sources:
        if not isinstance(source, dict) or set(source) - {"thread", "scope", "label"}:
            raise ValueError("Bundle source fields are invalid")
        if not {"thread", "scope"} <= set(source) or not _text(source["scope"], 120):
            raise ValueError("Bundle source requires identity and scope")
        label = source.get("label", source["scope"])
        if not _text(label, 160):
            raise ValueError("Bundle source label is invalid")
        normalized.append({"thread": _uuid(source["thread"]), "scope": source["scope"], "label": label})
    source_ids = [source["thread"] for source in normalized]
    if len(set(selected)) != len(selected) or len(set(source_ids)) != len(source_ids) or set(source_ids) != set(selected):
        raise ValueError("Bundle sources and selected chats disagree")
    return {"project": value["project"], "threads": selected,
            "context": {"id": context["id"], "name": context["name"], "sources": normalized}}


def _regular(path, root):
    relative = path.relative_to(root)
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError("Bundle sources cannot be symbolic links")
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError("Bundle source must be a regular file within its space")


def _digest_file(path):
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_MEMBER_BYTES:
                raise ValueError("Bundle member exceeds the size limit")
            digest.update(chunk)
    return size, digest.hexdigest()


def _database_check(path, *, archive=False):
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("Bundle database failed quick_check")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"threads", "messages", "archive_turns", "history_changes"} if archive else {"asc_meta", "commits", "state_versions"}
            if not required <= tables:
                raise ValueError("Bundle database does not have the expected schema")
    except sqlite3.Error as exc:
        raise ValueError("Bundle database failed validation") from exc


def _destination(value):
    raw = Path(value).expanduser().absolute()
    if raw.is_symlink() or not raw.parent.is_dir():
        raise ValueError("Use an explicit destination with an existing parent directory")
    return raw.parent.resolve() / raw.name


def _selected_paths(root):
    selected = {name for name in FIXED if (root / name).exists() or (root / name).is_symlink()}
    for directory, pattern in (("chats", "*.md"), ("evidence", "*.json"),
                               (".dialogue-documents/pending", "*.json")):
        parent = root / directory
        if parent.is_symlink():
            raise ValueError("Bundle source directories cannot be symbolic links")
        if parent.is_dir():
            selected.update(path.relative_to(root).as_posix() for path in parent.glob(pattern)
                            if _allowed(path.relative_to(root).as_posix()))
    if not REQUIRED <= selected:
        raise ValueError("Understanding space is missing required bundle files")
    if len(selected) > MAX_FILES:
        raise ValueError("Bundle has too many files")
    return sorted(selected)


def export_bundle(context, destination):
    """Snapshot a caller-stabilized open Context without registering or invoking it."""
    root = Path(context.archive.root).resolve()
    target = _destination(destination)
    if target.exists():
        raise ValueError("Export destination already exists")
    selected = _selected_paths(root)
    for name in selected:
        _regular(root / name, root)
        if (root / name).stat().st_size > MAX_MEMBER_BYTES:
            raise ValueError("Bundle member exceeds the size limit")
    config = _config(_load((root / "project.json").read_bytes()), sanitize=True)
    with tempfile.TemporaryDirectory(prefix=".bridge-export-", dir=target.parent) as temporary:
        staging = Path(temporary)
        files, total = [], 0
        for name in selected:
            source, snapshot = root / name, staging / "files" / name
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            if name == "project.json":
                snapshot.write_bytes(_dump(config))
            elif name in DATABASES:
                with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original, closing(sqlite3.connect(snapshot)) as copy:
                    original.backup(copy)
                _database_check(snapshot, archive=name == "archive.db")
            else:
                if source.stat().st_size > MAX_MEMBER_BYTES:
                    raise ValueError("Bundle member exceeds the size limit")
                shutil.copyfile(source, snapshot)
            size, sha256 = _digest_file(snapshot)
            total += size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Bundle exceeds the total size limit")
            files.append({"path": name, "size": size, "sha256": sha256})
        manifest = {"format": FORMAT, "version": VERSION, "name": config["context"]["name"],
                    "context_id": config["context"]["id"], "files": files}
        manifest_data = _dump(manifest)
        if len(manifest_data) > MAX_MEMBER_BYTES or total + len(manifest_data) > MAX_TOTAL_BYTES:
            raise ValueError("Bundle manifest exceeds the size limit")
        archive = staging / "bundle.zip"
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as stream:
            stream.writestr(MANIFEST, manifest_data)
            for item in files:
                stream.write(staging / "files" / item["path"], item["path"])
        with archive.open("r+b") as stream:
            os.fsync(stream.fileno())
        # Same-parent hard linking publishes a complete file atomically and refuses
        # to overwrite a destination created after the initial existence check.
        os.link(archive, target)
    return {"path": str(target), "name": manifest["name"], "context_id": manifest["context_id"],
            "files": len(files), "bytes": total, "frozen": True}


def _manifest(value):
    fields = {"format", "version", "name", "context_id", "files"}
    if not isinstance(value, dict) or set(value) != fields or value.get("format") != FORMAT or type(value.get("version")) is not int or value["version"] != VERSION:
        raise ValueError("Unsupported bundle manifest")
    _uuid(value["context_id"])
    if not _text(value["name"], 120) or not isinstance(value["files"], list) or len(value["files"]) > MAX_FILES:
        raise ValueError("Invalid bundle manifest")
    names, total = set(), 0
    for item in value["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"} or not _allowed(item.get("path")):
            raise ValueError("Bundle manifest has an unsupported member path")
        name = item["path"]
        if name.casefold() in names:
            raise ValueError("Duplicate bundle member")
        names.add(name.casefold())
        if type(item["size"]) is not int or not 0 <= item["size"] <= MAX_MEMBER_BYTES or not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("Invalid bundle member size or hash")
        total += item["size"]
    if total > MAX_TOTAL_BYTES or not REQUIRED <= {item["path"] for item in value["files"]}:
        raise ValueError("Bundle is too large or missing required files")
    return value


def _read_envelope(stream):
    infos, names, total = stream.infolist(), set(), 0
    if len(infos) > MAX_FILES + 1:
        raise ValueError("Bundle has too many members")
    for info in infos:
        name = info.filename
        if name != info.orig_filename or (name != MANIFEST and not _allowed(name)) or name.casefold() in names:
            raise ValueError("Unsafe or duplicate bundle member")
        names.add(name.casefold())
        mode = info.external_attr >> 16
        if info.is_dir() or stat.S_IFMT(mode) not in {0, stat.S_IFREG} or info.flag_bits & 1:
            raise ValueError("Bundle members must be unencrypted regular files")
        if not 0 <= info.file_size <= MAX_MEMBER_BYTES:
            raise ValueError("Bundle member exceeds the size limit")
        total += info.file_size
    if total > MAX_TOTAL_BYTES or MANIFEST not in names:
        raise ValueError("Bundle exceeds the size limit or has no manifest")
    manifest = _manifest(_load(stream.read(MANIFEST)))
    expected = {item["path"]: item for item in manifest["files"]}
    if set(expected) | {MANIFEST} != {info.filename for info in infos}:
        raise ValueError("Bundle manifest and archive members disagree")
    if any(stream.getinfo(name).file_size != item["size"] for name, item in expected.items()):
        raise ValueError("Bundle member size does not match its manifest")
    return manifest, expected


def inspect_bundle(bundle):
    """Check the envelope without installation; import still validates all payloads."""
    try:
        with zipfile.ZipFile(Path(bundle).expanduser().resolve()) as stream:
            manifest, expected = _read_envelope(stream)
            project = stream.read("project.json")
            if hashlib.sha256(project).hexdigest() != expected["project.json"]["sha256"]:
                raise ValueError("Bundle project hash verification failed")
            config = _config(_load(project))
            if config["context"]["id"] != manifest["context_id"] or config["context"]["name"] != manifest["name"]:
                raise ValueError("Bundle project identity disagrees with manifest")
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise ValueError("Bundle archive is corrupt or unsupported") from exc
    return {"name": manifest["name"], "context_id": manifest["context_id"],
            "files": len(expected), "bytes": sum(item["size"] for item in expected.values()),
            "frozen": True, "payload_verified": False}


def import_bundle(bundle, directory):
    """Verify and atomically install a new frozen space; never change bindings."""
    source, target = Path(bundle).expanduser().resolve(), _destination(directory)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError("Import requires a new or empty destination directory")
    try:
        with zipfile.ZipFile(source) as stream:
            manifest, expected = _read_envelope(stream)
            with tempfile.TemporaryDirectory(prefix=".bridge-import-", dir=target.parent) as temporary:
                staging = Path(temporary) / "space"
                staging.mkdir()
                for name, item in expected.items():
                    info = stream.getinfo(name)
                    if info.file_size != item["size"]:
                        raise ValueError("Bundle member size does not match its manifest")
                    output, digest, size = staging / name, hashlib.sha256(), 0
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with stream.open(info) as member, output.open("xb") as destination:
                        while chunk := member.read(1024 * 1024):
                            size += len(chunk)
                            if size > item["size"]:
                                raise ValueError("Bundle member exceeds its declared size")
                            destination.write(chunk)
                            digest.update(chunk)
                    if size != item["size"] or digest.hexdigest() != item["sha256"]:
                        raise ValueError("Bundle member hash or size verification failed")
                config = _config(_load((staging / "project.json").read_bytes()))
                if config["context"]["id"] != manifest["context_id"] or config["context"]["name"] != manifest["name"]:
                    raise ValueError("Bundle project identity disagrees with manifest")
                for name in DATABASES & set(expected):
                    _database_check(staging / name, archive=name == "archive.db")
                # No original-chat access, model process, registry or binding write
                # occurs while validating or installing this frozen directory.
                existed_empty = target.exists()
                if existed_empty:
                    target.rmdir()  # Fails if another writer populated it meanwhile.
                try:
                    staging.rename(target)
                except BaseException:
                    if existed_empty and not target.exists():
                        target.mkdir()
                    raise
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise ValueError("Bundle archive is corrupt or unsupported") from exc
    return {"directory": str(target), "path": str(target), "name": manifest["name"],
            "context_id": manifest["context_id"], "files": len(expected),
            "bytes": sum(item["size"] for item in expected.values()), "frozen": True}
