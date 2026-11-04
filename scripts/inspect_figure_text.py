"""Extract figure text with a locked, project-local OCR runtime."""
import argparse,hashlib,json,os,re,sqlite3,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def project_workspace(project_id):
    if not re.fullmatch(r'prj_[A-Za-z0-9_-]+',project_id):raise ValueError('invalid_project_id')
    config=json.loads((ROOT/'config/pathoreason.local.json').read_text());data=Path(config['data_root'])
    if not data.is_absolute() or not data.is_relative_to('/data/bxn') or data.is_symlink():raise ValueError('invalid_data_root')
    with sqlite3.connect(data/'state/pathoreason.sqlite3') as db:row=db.execute('SELECT document FROM formal_studies WHERE project_id=?',(project_id,)).fetchone()
    if not row:raise ValueError('formal_study_required')
    root=Path(json.loads(row[0])['workspace']);expected=data/'projects'/project_id
    if root!=expected or any(path.is_symlink() for path in (root,*root.parents)):raise ValueError('invalid_study_workspace')
    return root

def checked_figure(root,relative):
    value=Path(relative)
    if value.is_absolute() or not value.parts or value.parts[0] not in {'figures','manuscript'} or any(part in {'','.', '..'} for part in value.parts):raise ValueError('invalid_figure_path')
    path=root/value
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root) or path.stat().st_size>32*1024*1024:raise ValueError('invalid_figure_path')
    if path.suffix.lower() not in {'.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp'}:raise ValueError('unsupported_figure_media')
    return path

def checked_output(root,relative):
    value=Path(relative)
    if value.is_absolute() or len(value.parts)<2 or value.parts[0]!='manuscript' or any(part in {'','.', '..'} for part in value.parts) or value.suffix!='.json':raise ValueError('invalid_audit_output_path')
    target=root/value
    if target.parent.is_symlink() or not target.parent.is_dir() or target.is_symlink() or not target.resolve().is_relative_to(root):raise ValueError('invalid_audit_output_path')
    return target

def sha256(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project-id',required=True);parser.add_argument('--relative-path',action='append',required=True);parser.add_argument('--output');args=parser.parse_args()
    root=project_workspace(args.project_id);runtime=ROOT/'.tools/image-ocr/root';binary=runtime/'usr/bin/tesseract'
    if not binary.is_file():raise SystemExit('image_ocr_runtime_missing; run scripts/setup_image_ocr.py')
    env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL'}};env['LD_LIBRARY_PATH']=str(runtime/'usr/lib/x86_64-linux-gnu');env['TESSDATA_PREFIX']=str(runtime/'usr/share/tesseract-ocr/4.00/tessdata')
    version=subprocess.run([str(binary),'--version'],env=env,capture_output=True,text=True,check=True).stdout.splitlines()[0];figures=[]
    for relative in args.relative_path:
        path=checked_figure(root,relative);result=subprocess.run([str(binary),str(path),'stdout','-l','eng'],env=env,capture_output=True,text=True,timeout=120,check=True)
        figures.append({'relative_path':relative,'sha256':sha256(path),'size_bytes':path.stat().st_size,'text':result.stdout.strip()})
    report={'schema_version':'pathoreason.figure-text-audit/1','project_id':args.project_id,'engine':version,'figures':figures,'scope':'OCR supports cross-material review; it is not scientific or author approval.'};rendered=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:checked_output(root,args.output).write_text(rendered)
    print(rendered,end='');return 0

if __name__=='__main__':raise SystemExit(main())
