"""Install the locked OCR runtime beneath .tools without changing the host."""
import hashlib,json,shutil,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/'config/p5/image-ocr-lock.json'
TARGET=ROOT/'.tools/image-ocr'

def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()

def main():
    lock=json.loads(LOCK.read_text());lock_sha=digest(LOCK);manifest=TARGET/'manifest.json'
    if manifest.is_file() and json.loads(manifest.read_text()).get('lock_sha256')==lock_sha and (TARGET/'root/usr/bin/tesseract').is_file():
        print(json.dumps({'status':'ready','root':str(TARGET),'lock_sha256':lock_sha}));return 0
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='image-ocr.',dir=TARGET.parent))
    try:
        downloads=staging/'downloads';downloads.mkdir();extracted=staging/'root';extracted.mkdir();receipts=[]
        for package in lock['packages']:
            before=set(downloads.glob('*.deb'))
            subprocess.run(['apt','download',package['name']+'='+package['version']],cwd=downloads,check=True,stdout=subprocess.DEVNULL)
            created=list(set(downloads.glob('*.deb'))-before)
            if len(created)!=1 or digest(created[0])!=package['sha256']:raise RuntimeError('image_ocr_package_digest_mismatch:'+package['name'])
            subprocess.run(['dpkg-deb','-x',str(created[0]),str(extracted)],check=True)
            receipts.append({**package,'file':created[0].name})
        if not (extracted/'usr/bin/tesseract').is_file():raise RuntimeError('image_ocr_binary_missing')
        (staging/'manifest.json').write_text(json.dumps({'schema_version':'pathoreason.image-ocr-runtime/1','lock_sha256':lock_sha,'packages':receipts},indent=2)+'\n')
        if TARGET.exists():shutil.rmtree(TARGET)
        staging.rename(TARGET)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True);raise
    print(json.dumps({'status':'installed','root':str(TARGET),'lock_sha256':lock_sha}));return 0

if __name__=='__main__':raise SystemExit(main())
