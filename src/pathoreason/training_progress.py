"""Bounded, read-only projections of executor receipts and task-emitted telemetry.

Never calls Training.view/reconcile, writes ledgers, or controls a worker. Files
are opened beneath the receipt's run/unit using no-follow directory descriptors.
"""
from contextlib import contextmanager
import json,math,os,re,sqlite3,stat,time
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,Field
from .persistence import Missing,now
from .training_account import boot_id,identity

class TrainingProgressView(BaseModel):
    schema_version:Literal['pathoreason.training-progress/1']='pathoreason.training-progress/1'
    project_id:str
    observed_at:str
    experiments:list[dict]
    execution_authority:Literal[False]=False

class TrainingTelemetryView(BaseModel):
    schema_version:Literal['pathoreason.training-telemetry/1']='pathoreason.training-telemetry/1'
    project_id:str
    experiment_id:str
    attempt_id:str
    observed_at:str
    last_epoch:float|None=None
    points:list[dict]=Field(default_factory=list)
    sources:list[str]=Field(default_factory=list)
    notices:list[str]=Field(default_factory=list)
    log:str=''
    log_bytes:int=0
    log_truncated:bool=False
    scientific_approval:Literal[False]=False

@contextmanager
def read_db(service):
    db=sqlite3.connect(Path(service.store.path).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)
    try:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN');yield db
    finally:db.close()

def records(service,pid,eid=None):
    service.store.project(pid)
    with read_db(service) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='training_experiments'").fetchone():
            if eid:raise Missing('training_experiment_not_found')
            return []
        rows=db.execute('SELECT document FROM training_experiments WHERE project_id=?'+(' AND id=?' if eid else '')+' ORDER BY rowid DESC',(pid,eid) if eid else (pid,)).fetchall()
        if eid and not rows:raise Missing('training_experiment_not_found')
        result=[]
        for row in rows:
            d=json.loads(row[0]);attempts=[json.loads(r[0]) for r in db.execute('SELECT document FROM training_attempts WHERE experiment_id=? ORDER BY rowid',(d['id'],))]
            events=[json.loads(r[0]) for r in db.execute('SELECT document FROM training_events WHERE experiment_id=? ORDER BY id DESC LIMIT 30',(d['id'],))]
            result.append((d,attempts,events))
        return result

def elapsed(a):
    if a.get('charged_seconds') is not None:return max(0,a['charged_seconds'])
    if a.get('boot_id')==boot_id():return max(0,a.get('observed_seconds',0),time.monotonic()-a['started_monotonic'])
    return max(0,a.get('allowance',0))

ATTEMPT_FIELDS=('id','unit_id','phase','run_id','status','error','started_at','finished_at','plan_digest','scope_digest')
def attempt_view(a,scope):
    return {**{k:a.get(k) for k in ATTEMPT_FIELDS},'elapsed_seconds':elapsed(a),'charged':a.get('charged_seconds') is not None,'current_scope':a.get('scope_digest')==scope}

def project_progress(service,pid):
    experiments=[]
    for d,attempts,events in records(service,pid):
        plan=d['plan'];scope=d['scope_digest'];units=[]
        for u in plan['units']:
            history=[a for a in attempts if a['unit_id']==u['id']]
            eligible=[a for a in history if a.get('scope_digest')==scope]
            completed=next((a for a in reversed(eligible) if a['status']=='completed'),None)
            latest=completed or (eligible[-1] if eligible else None)
            units.append({k:u.get(k) for k in ('id','label','phase','parameters','depends_on')}|{'status':latest['status'] if latest else 'pending','attempt_id':latest['id'] if latest else None,'attempt_count':len(history),'retry_count':max(0,len(history)-1)})
        counts={phase:{'total':sum(u['phase']==phase for u in units),'completed':sum(u['phase']==phase and u['status']=='completed' for u in units)} for phase in ('fit','evaluate')}
        controller=d.get('controller');alive=bool(controller and controller.get('boot_id')==boot_id() and identity(controller['pid'])==controller['identity'])
        running=next((a for a in reversed(attempts) if a['status']=='running' and a['run_id']==d.get('run_id')),None)
        current=None
        if running:
            tele=telemetry(service,pid,d['id'],running['id'],record=(d,attempts,events),include_log=False)
            current={'attempt_id':running['id'],'unit_id':running['unit_id'],'phase':running['phase'],'last_epoch':tele.last_epoch,'metrics':tele.points[-1]['metrics'] if tele.points else {}}
        experiments.append({k:d.get(k) for k in ('id','conversation_id','revision','status','authorized','run_id','error','plan_digest','scope_digest','budget')}|{
            'plan':{k:plan.get(k) for k in ('title','task_id','snapshot_id','environment_id','protocol','evaluation','gpu_uuid','memory_gib')},
            'units':units,'counts':counts,'current':current,'controller_alive':alive,
            'used_wall_seconds':sum(elapsed(a) for a in attempts),'used_gpu_seconds':sum(elapsed(a) for a in attempts if a.get('gpu')),
            'attempts':[attempt_view(a,scope) for a in attempts],
            'events':[{k:e[k] for k in ('at','kind','run_id','attempt_id','status','error','reason','budget') if k in e} for e in events],
            'scientific_approval':False})
    return TrainingProgressView(project_id=pid,observed_at=now(),experiments=experiments)

@contextmanager
def output_dir(service,a):
    parts=('runs',a['run_id'],a['unit_id'],'output')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+',p) for p in parts):raise ValueError('invalid_receipt_path')
    root=(service.data/'training').resolve()
    if Path(a.get('output',''))!=root.joinpath(*parts):raise ValueError('output_identity_mismatch')
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in parts:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
        yield fd
    finally:os.close(fd)

def read_file(directory,name,limit,tail=False):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    try:
        meta=os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):raise ValueError('not_regular_file')
        if meta.st_size>limit and not tail:raise ValueError('file_exceeds_read_limit')
        if tail:os.lseek(fd,max(0,meta.st_size-limit),os.SEEK_SET)
        chunks=[];remaining=limit
        while remaining:
            chunk=os.read(fd,min(remaining,65536))
            if not chunk:break
            chunks.append(chunk);remaining-=len(chunk)
        return b''.join(chunks),meta.st_size
    finally:os.close(fd)

def number(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def point(row):
    if not isinstance(row,dict) or not number(row.get('epoch')) or row['epoch']<0:return None
    metrics={}
    for key in ('train_loss','loss','val_loss','validation_loss','accuracy','acc','auc','macro_auc','qwk','val_accuracy','val_auc'):
        if number(row.get(key)):metrics[key]=row[key]
    for group in ('train','val','validation'):
        if isinstance(row.get(group),dict):
            for key,value in row[group].items():
                if key in ('loss','accuracy','acc','auc','macro_auc','qwk','f1','macro_f1','precision','recall','mse','mae','c_index') and number(value):metrics[group+'.'+key]=value
    return {'epoch':row['epoch'],'metrics':metrics} if metrics else None

def telemetry(service,pid,eid,aid,record=None,include_log=True):
    d,attempts,_=record or records(service,pid,eid)[0]
    a=next((x for x in attempts if x['id']==aid),None)
    if not a:raise Missing('training_attempt_not_found')
    out=TrainingTelemetryView(project_id=pid,experiment_id=eid,attempt_id=aid,observed_at=now())
    try:
        with output_dir(service,a) as directory:
            # Directory scan, file count, byte volume and log tail are all bounded.
            names=[]
            with os.scandir(directory) as entries:
                for i,entry in enumerate(entries):
                    if i>=10000:out.notices.append('目录超过 10000 项，仅展示已扫描指标。');break
                    if re.fullmatch(r'epoch-\d+\.json',entry.name):names.append(entry.name)
            names.sort(key=lambda n:int(n[6:-5]))
            if len(names)>512:out.notices.append('逐 epoch 文件仅展示最近 512 个。')
            by_epoch={}
            def consume(row):
                p=point(row)
                if p:by_epoch[p['epoch']]=p
            for name in ['metrics.json','progress.json','metrics.jsonl',*names[-512:]]:
                try:
                    raw,_=read_file(directory,name,1024*1024 if name in ('metrics.json','metrics.jsonl') else 16384)
                    if name.endswith('.jsonl'):
                        for line in raw.splitlines():
                            try:consume(json.loads(line))
                            except (ValueError,RecursionError):out.notices.append('部分指标行尚未写完整或格式无效。')
                    else:
                        doc=json.loads(raw)
                        if isinstance(doc,dict):
                            consume(doc)
                            for row in doc.get('rows',doc.get('history',[]))[:5000] if isinstance(doc.get('rows',doc.get('history',[])),list) else []:consume(row)
                    out.sources.append(name)
                except FileNotFoundError:pass
                except (OSError,ValueError,TypeError,RecursionError):out.notices.append(name+'：未读取，可能正在写入或格式不受支持。')
            points=[by_epoch[k] for k in sorted(by_epoch)]
            if len(points)>512:out.notices.append('曲线仅展示最近 512 个已上报 epoch。')
            out.points=points[-512:];out.last_epoch=out.points[-1]['epoch'] if out.points else None
            if include_log:
                try:
                    raw,size=read_file(directory,'worker.log',65536,tail=True)
                    out.log=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',raw.decode('utf-8',errors='replace')).replace('\x00','')
                    out.log_bytes=size;out.log_truncated=size>65536
                except FileNotFoundError:out.notices.append('尚无 worker.log。')
                except (OSError,ValueError):out.notices.append('日志不可读取。')
    except (OSError,ValueError,KeyError):out.notices.append('本次尝试的输出目录暂不可读取。')
    out.notices=list(dict.fromkeys(out.notices))[:12]
    return out
