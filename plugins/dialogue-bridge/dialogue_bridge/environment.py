"""Prepare an explicitly selected private venv using the bundled dependency pin."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

PLUGIN = Path(__file__).resolve().parents[1]


def dependency_pin():
    lines = [x.strip() for x in (PLUGIN / "requirements.txt").read_text(encoding="utf-8").splitlines()
             if x.strip() and not x.lstrip().startswith("#")]
    match = re.fullmatch(r"agent-state-core @ git\+(https://[^@\s]+)@([0-9a-f]{40})", lines[0]) if len(lines) == 1 else None
    if not match:
        raise ValueError("Bundled requirements must pin agent-state-core to an HTTPS Git repository and full commit")
    return {"url": match[1], "commit": match[2]}


def environment_python(root):
    return root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def inspect_environment(python):
    probe = '''import importlib.metadata, json, sys
result = {"prefix": sys.prefix, "isolated_venv": sys.prefix != sys.base_prefix}
try:
    import agent_state_core
    dist = importlib.metadata.distribution("agent-state-core")
    result.update(module_path=agent_state_core.__file__, paging=hasattr(agent_state_core.Ledger, "view_page"),
                  origin=json.loads(dist.read_text("direct_url.json") or "{}"))
except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
    result["unavailable"] = str(exc)
print(json.dumps(result))
'''
    result = subprocess.run([str(python), "-I", "-c", probe], capture_output=True, text=True, encoding="utf-8", timeout=30)
    if result.returncode:
        raise RuntimeError(f"Could not inspect the selected environment: {result.stderr.strip()}")
    return json.loads(result.stdout)


def matches_pin(report, pin, root):
    origin = report.get("origin", {})
    return (report.get("isolated_venv") is True and Path(report["prefix"]).resolve() == root
            and report.get("paging") is True
            and Path(report.get("module_path", "")).resolve().is_relative_to(root)
            and origin.get("url") == pin["url"]
            and origin.get("vcs_info", {}).get("commit_id") == pin["commit"])


def prepare_environment(directory):
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11+ is required")
    pin = dependency_pin()
    root = Path(directory).resolve()
    config = root / "pyvenv.cfg"
    if root.exists() and (not root.is_dir() or (not config.is_file() and any(root.iterdir()))):
        raise ValueError("Choose a new/empty directory or an existing dedicated virtual environment; existing files were not changed")
    python = environment_python(root)
    report = inspect_environment(python) if config.is_file() and python.is_file() else {}
    reused = matches_pin(report, pin, root)
    if not reused:
        if not shutil.which("git"):
            raise ValueError("Git is required to install the pinned source dependency; the environment was not changed")
        if not config.is_file():
            subprocess.run([sys.executable, "-m", "venv", str(root)], check=True, stdout=sys.stderr, timeout=120)
        if not python.is_file():
            raise ValueError("The selected venv is incomplete; choose another dedicated directory")
        # Explicit interpreter/prefix and pip isolation keep this out of global Python.
        subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "--require-virtualenv",
                        "--disable-pip-version-check", "install", "--no-user", "--no-deps",
                        "--force-reinstall", "--prefix", str(root), "-r", str(PLUGIN / "requirements.txt")],
                       check=True, stdout=sys.stderr, timeout=300)
        report = inspect_environment(python)
        if not matches_pin(report, pin, root):
            raise ValueError("Dependency installation did not match the pinned commit and private environment; see setup output")
    return {"environment": str(root), "python": str(python), "reused": reused,
            "dependency": pin, "verified": report,
            "demo_command": [str(python), str(PLUGIN / "scripts/demo.py"), "--directory", "<new-private-demo-directory>"],
            "entry_command": [str(python), str(PLUGIN / "scripts/dialogue.py"), "--workspace", "<private-shared-directory>", "start"]}
