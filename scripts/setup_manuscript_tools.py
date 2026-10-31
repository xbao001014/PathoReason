"""Install pinned portable manuscript tools inside PathoReason; no system package changes."""
import hashlib,json,os,subprocess,tarfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
cfg=json.loads((ROOT/'config/pathoreason.local.json').read_text());cache=Path(cfg['data_root'])/'cache/tool-downloads';cache.mkdir(parents=True,exist_ok=True)
base=ROOT/'.tools/manuscript';base.mkdir(parents=True,exist_ok=True)
assets=[('rstudio/tinytex-releases','v2026.10','TinyTeX-linux-x86_64-v2026.10.tar.xz'),('jgm/pandoc','3.13','pandoc-3.13-linux-amd64.tar.gz')];receipt=[]
for repo,tag,name in assets:
 with urllib.request.urlopen(f'https://api.github.com/repos/{repo}/releases/tags/{tag}',timeout=30) as response:release=json.load(response)
 asset=next(a for a in release['assets'] if a['name']==name);target=cache/name
 if not target.exists():
  temporary=target.with_suffix(target.suffix+'.partial')
  with urllib.request.urlopen(asset['browser_download_url'],timeout=120) as response,temporary.open('wb') as output:
   while chunk:=response.read(1024*1024):output.write(chunk)
  temporary.replace(target)
 sha=hashlib.sha256(target.read_bytes()).hexdigest();expected=asset.get('digest')
 if expected and expected!='sha256:'+sha:raise ValueError('tool_archive_digest_mismatch')
 if target.stat().st_size!=asset['size']:raise ValueError('tool_archive_size_mismatch')
 with tarfile.open(target) as archive:
  prefix=archive.getmembers()[0].name.split('/')[0]
  if not (base/prefix).exists():archive.extractall(base,filter='data')
 receipt.append({'repository':repo,'tag':tag,'asset':name,'sha256':sha,'size_bytes':target.stat().st_size,'upstream_digest_verified':bool(expected)})
# Explicit PATH file, no edits to shell startup files or other projects.
paths=[p for p in base.glob('*/bin/*') if p.is_dir() and (p/'pdflatex').exists()]+[p for p in base.glob('*/bin') if (p/'pandoc').exists()]
(ROOT/'.tools/manuscript-path.json').write_text(json.dumps([str(p) for p in paths],indent=2)+'\n')
(ROOT/'config/p5/toolchain-lock.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'installed':receipt,'bin_paths':[str(p) for p in paths]},indent=2))
