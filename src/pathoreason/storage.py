"""PathoReason output allocation; legacy roots are never valid write targets."""
import json
import os
import re
from pathlib import Path

CATEGORIES = {"acceptance", "scratch", "state", "artifacts", "runtime", "projects", "releases", "cache"}


def data_root(config_path: Path) -> Path:
    config = json.loads(config_path.read_text())
    root = Path(config["data_root"])
    repo = Path(__file__).resolve().parents[2]
    if config.get("execution_environment")=="local":
        allowed=Path.home()/".local/share/PathoReason"
        if root!=allowed or root.is_relative_to(repo) or any(p.is_symlink() for p in (*root.parents,root)) or not root.is_dir():
            raise ValueError("invalid isolated local data root")
        return root
    if not root.is_absolute() or ".." in root.parts or not root.is_relative_to("/data/bxn"):
        raise ValueError("data root must be an absolute /data/bxn path")
    legacy_data = Path("/data/bxn/auto-research")
    if root == Path("/data/bxn") or root.is_relative_to(legacy_data) or legacy_data.is_relative_to(root):
        raise ValueError("PathoReason data must not overlap legacy storage")
    for p in (*root.parents, root):
        if p.is_symlink():
            raise ValueError("symlink in data root")
    if not os.path.ismount("/data") or os.stat("/data").st_dev == repo.stat().st_dev:
        raise ValueError("independent data mount unavailable")
    if not root.is_dir() or root.stat().st_dev != os.stat("/data").st_dev:
        raise ValueError("data root unavailable on configured mount")
    return root


def allocate(config_path: Path, category: str, name: str) -> Path:
    if category not in CATEGORIES or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("invalid storage category or allocation name")
    parent = data_root(config_path) / category
    if parent.is_symlink():
        raise ValueError("symlink storage category")
    parent.mkdir(exist_ok=True)
    path = parent / name
    path.mkdir(exist_ok=False)
    return path
