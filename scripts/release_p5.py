"""Versioned source package and byte manifest; excludes private config and all runtime data."""
import hashlib,json,tarfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pathoreason.settings import ROOT,settings
cfg=settings();dest=Path(cfg['data_root'])/'releases/pathoreason-0.6.0-p5-entry';dest.mkdir(exist_ok=False)
files=[]
for name in ['src','scripts','tests','apps/web/src','apps/web/dist','config','contracts','docs','skills','.agents/skills']:
 for p in (ROOT/name).rglob('*'):
  if p.is_file() and not p.is_symlink() and not any(part in {'__pycache__','node_modules','.pytest_cache'} for part in p.parts) and not p.name.endswith(('.pyc','.local.json')) and '.env' not in p.name:files.append(p)
for name in ['AGENTS.md','EXECUTION_PLAN.md','README.md','design.md','requirements.lock','pyproject.toml','apps/web/package.json','apps/web/package-lock.json','apps/web/index.html','apps/web/tsconfig.json','apps/web/vite.config.ts']: 
 p=ROOT/name
 if p.is_file():files.append(p)
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}
with tarfile.open(dest/'source.tar.gz','w:gz') as archive:
 for p in sorted(set(files)):archive.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
record={'version':'0.6.0-p5-entry','scope':'entry_delivered; formal_end_to_end_pending','files':manifest,'archive_sha256':hashlib.sha256((dest/'source.tar.gz').read_bytes()).hexdigest(),'private_config_included':False,'runtime_data_included':False}
(dest/'manifest.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'release':str(dest),'files':len(files),'archive_sha256':record['archive_sha256']}))
