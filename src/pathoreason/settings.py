from __future__ import annotations
import json, os
from pathlib import Path
from .storage import data_root

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/pathoreason.local.json"

def settings():
    value=json.loads(CONFIG.read_text())
    value["data_root"]=str(data_root(CONFIG))
    return value

def credential():
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"]
    file=Path(settings().get("credential_file","/home/bxn/.config/pathoreason/credentials.env"))
    if not file.exists():return ""
    if file.is_symlink() or file.stat().st_mode & 0o077:
        return ""
    for line in file.read_text().splitlines():
        name,sep,value=line.removeprefix("export ").partition("=")
        if sep and name.strip()=="DEEPSEEK_API_KEY":return value.strip().strip("\"'")
    return ""
