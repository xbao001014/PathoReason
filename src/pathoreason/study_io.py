"""Project-bound dataset fetch, configured Seedream invocation and immutable publication."""
from __future__ import annotations
import base64,hashlib,json,os,re,subprocess,urllib.request,urllib.error
from pathlib import Path
from .settings import ROOT,settings
from .persistence import Store,Conflict,encoded
from .legacy import _checked_path,read_verified_file
from .formal import private_image_config

def workspace(project_id,cfg,store=None):
    if not re.fullmatch(r'prj_[A-Za-z0-9_-]+',project_id):raise ValueError('invalid_project_id')
    store=store or Store(Path(cfg['data_root'])/'state/pathoreason.sqlite3')
    with store.connect() as db:row=db.execute('SELECT document FROM formal_studies WHERE project_id=?',(project_id,)).fetchone()
    if not row:raise ValueError('formal_study_required')
    record=json.loads(row[0]);root=Path(record['workspace'])
    if root!=Path(cfg['data_root'])/'projects'/project_id or any(p.is_symlink() for p in [root,*root.parents]):raise ValueError('invalid_study_workspace')
    return root

def output_dir(root,name):
    parts=Path(name).parts
    if not parts or Path(name).is_absolute() or any(x in {'.','..'} for x in name.split('/')) or '\\' in name:raise ValueError('invalid_output_path')
    path=root
    for part in parts:
        path=path/part
        if path.is_symlink():raise ValueError('symlink_output_path')
    path.mkdir(parents=True,exist_ok=False)
    return path

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def fetch_data(project_id,disease,limit,relative,cfg=None,opener=None,store=None):
    from urllib.parse import urlencode,urlsplit
    cfg=cfg or settings();root=workspace(project_id,cfg,store)
    if not disease.strip() or len(disease)>200 or not 1<=limit<=10000:raise ValueError('invalid_data_query')
    source=json.loads((ROOT/'config/p5/data-source.json').read_text());endpoint=source['endpoint'];parts=urlsplit(endpoint)
    if parts.hostname!='ai.gzfxyl.cn' or parts.path!='/api/v1/pathology/diseases/slides':raise ValueError('unconfigured_data_endpoint')
    url=endpoint+'?'+urlencode({'DiseaseName':disease,'Limit':limit});out=output_dir(root,relative)
    receipt={'schema_version':'pathoreason.data-fetch/1','project_id':project_id,'endpoint':endpoint,'query':{'DiseaseName':disease,'Limit':limit},'status':'requested','scope':'source_metadata_not_verified_training_dataset'}
    try:
        with (opener or urllib.request.build_opener(NoRedirect)).open(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=source['timeout_seconds']) as response:
            raw=response.read(source['max_response_bytes']+1)
        if len(raw)>source['max_response_bytes']:raise ValueError('data_response_limit')
        parsed=json.loads(raw)
        if not isinstance(parsed,(dict,list)):raise ValueError('data_response_structure')
        (out/'response.json').write_bytes(raw)
        receipt.update(status='downloaded',sha256=hashlib.sha256(raw).hexdigest(),size_bytes=len(raw),data_file='response.json')
    except Exception as exc:
        receipt.update(status='failed',error_type=type(exc).__name__)
        (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
        raise RuntimeError('data_fetch_failed; inspect receipt; no automatic retry') from None
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');return out/'receipt.json'

def generate_image(project_id,request,relative,cfg=None):
    cfg=cfg or settings();root=workspace(project_id,cfg);request_path=_checked_path(root,request)
    body=json.loads(request_path.read_text());private=private_image_config(cfg)
    if not private.get('model') or not private.get('api_key'):raise ValueError('seedream_configuration_missing')
    if not body.get('sources'):raise ValueError('method_sources_required')
    # Do not permit a request to override the configured provider or inject credentials.
    if set(body)-{'prompt','sources','reference_images'}:raise ValueError('image_request_fields_invalid')
    for key in ['sources','reference_images']:
        body[key]=[str(_checked_path(root,p)) for p in body.get(key,[])]
    body['config']={k:private[k] for k in ['provider','model','api_key_env','size']}
    out=output_dir(root,relative);bound=out/'request.json';bound.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n')
    script=ROOT/'.agents/skills/manuscript-to-latex/scripts/generate_method_figure.py'
    python=Path(cfg.get('legacy_root','/home/bxn/projects/auto-research'))/'.venv/bin/python'
    env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','SSL_CERT_FILE','SSL_CERT_DIR']}
    env.update(PYTHONDONTWRITEBYTECODE='1',ARK_API_KEY=private['api_key'])
    if private['api_key_env']!='ARK_API_KEY':raise ValueError('unsupported_image_credential_ref')
    result=subprocess.run([str(python),str(script),'--request',str(bound),'--output-dir',str(out/'candidate')],env=env,capture_output=True,timeout=210)
    if result.returncode:raise RuntimeError('seedream_request_failed; inspect candidate/candidate.json; no automatic retry')
    return out/'candidate/candidate.json'

def publish_artifact(service,project_id,relative,title):
    from .formal_contracts import FormalArtifact,FormalRef
    from .contracts import canonical_digest
    service.store.project(project_id,writable=True)
    cfg=service.config;root=workspace(project_id,cfg,service.store)
    # Only explicit result areas may be published. Dataset records and credentials are not public artifacts.
    if relative.split('/')[0] not in {'outputs','figures','manuscript'}:raise ValueError('publish_result_area_required')
    path=_checked_path(root,relative);size=path.stat().st_size
    if size>32*1024*1024:raise ValueError('publish_size_limit')
    sha=hashlib.sha256(path.read_bytes()).hexdigest();blob=read_verified_file(root,relative,sha)
    import mimetypes
    media=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    if path.suffix=='.md':media='text/markdown'
    if media not in {'application/pdf','application/json','text/markdown','text/plain','text/csv','image/png','image/jpeg','image/svg+xml'}:raise ValueError('unsupported_artifact_media')
    aid='art_'+canonical_digest([project_id,relative,sha])[:32];target=service.data/'artifacts'/project_id/(aid+path.suffix)
    target.parent.mkdir(exist_ok=True)
    if target.is_symlink() or target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=sha:raise Conflict('artifact_collision')
    if not target.exists():
        with target.open('xb') as output:output.write(blob)
    artifact=FormalArtifact(id=aid,project_id=project_id,title=title,kind='figure' if media.startswith('image/') else 'report',media_type=media,storage_root='pathoreason_artifacts',relative_path=str(target.relative_to(service.data/'artifacts')),sha256=sha,size_bytes=len(blob),source_ref=FormalRef(project_id=project_id,resource_id=relative,revision=sha),run_ref=None,stage_ref=None,verification_scope='bytes_verified',evidence_role='not_assessed')
    service.store.add_artifact(artifact);return artifact
