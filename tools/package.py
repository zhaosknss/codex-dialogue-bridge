"""Build a plugin-root ZIP from an explicit allowlist; no private data or venvs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/dialogue-bridge"
DIRECTORIES = {"dialogue_bridge", "dialogue_understanding", "scripts", "skills", "assets", "hooks"}
ROOT_FILES = {"plugin.json", "mcp.json", "requirements.txt", "LICENSE"}
EXTENSIONS = {".py", ".md", ".json", ".yaml", ".html", ".css", ".js", ".svg", ".png", ".txt"}


def build(destination):
    target = Path(destination).resolve()
    if target.exists():
        raise ValueError("The package destination already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    files = {}
    for path in PLUGIN.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(PLUGIN)
        if path.is_symlink() or not path.resolve().is_relative_to(PLUGIN.resolve()):
            raise ValueError("Package source must not contain symlinks")
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if len(relative.parts) == 1 and relative.name in ROOT_FILES or (
                relative.parts[0] in DIRECTORIES and path.suffix in EXTENSIONS):
            files[relative.as_posix()] = path.read_bytes()
        else:
            raise ValueError("Unexpected package source: " + relative.as_posix())
    files["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    files["INSTALL.md"] = (
        "# Dialogue Bridge " + manifest["version"] + "\n\n"
        "This is the local desktop plugin package. For a marketplace installation,\n"
        "use the repository's README: https://github.com/zhaosknss/codex-dialogue-bridge\n\n"
        "Prepare an explicit private environment with:\n\n"
        "    python scripts/setup.py --environment <PRIVATE_ENVIRONMENT>\n\n"
        "Use that environment's Python to run scripts/bridge_service.py serve, or\n"
        "scripts/understanding_demo.py for a fictional model-free walkthrough.\n"
        "Private understanding data stays outside the installed plugin folder.\n"
        "Lifecycle hooks require review and trust in Codex; the Skill and MCP\n"
        "workflow can operate without trusted hooks. No background model is\n"
        "enabled by default. This build has not been submitted to the official directory.\n"
    ).encode("utf-8")
    report = {"name": manifest["name"], "version": manifest["version"], "files": {
        name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sorted(files.items())}}
    files["PACKAGE.json"] = (json.dumps(report, indent=2) + "\n").encode("utf-8")
    created = False
    try:
        with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            created = True
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, (2026, 10, 24, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
    return {"path": str(target), "version": manifest["version"], "files": len(files),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
