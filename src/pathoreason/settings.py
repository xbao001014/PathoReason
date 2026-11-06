from __future__ import annotations
import json, os
from pathlib import Path
from .storage import data_root

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/pathoreason.local.json"

def settings():
    value=json.loads(CONFIG.read_text())
    value["data_root"]=str(data_root(CONFIG))
    from .provider_config import effective_settings
    return effective_settings(value)

def credential():
    cfg=settings()
    if cfg.get('provider_profiles_enabled'):
        from .provider_config import key_for
        return key_for(cfg,cfg['provider']['id'])
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"]
    file=Path(cfg.get("credential_file","/home/bxn/.config/pathoreason/credentials.env"))
    if not file.exists():return ""
    if file.is_symlink() or file.stat().st_mode & 0o077:
        return ""
    for line in file.read_text().splitlines():
        name,sep,value=line.removeprefix("export ").partition("=")
        if sep and name.strip()=="DEEPSEEK_API_KEY":return value.strip().strip("\"'")
    return ""
