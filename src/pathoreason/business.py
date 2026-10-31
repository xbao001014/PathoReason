"""Project-scoped business capabilities and read projections; no scientific approval."""
from __future__ import annotations
import asyncio,csv,hashlib,hmac,io,json,os,subprocess,time,re,tempfile
from pathlib import Path
from typing import Literal,Any
from pydantic import BaseModel,ConfigDict,Field
from . import contracts as c
from .persistence import Conflict,encoded
from .settings import ROOT

class WorkflowRef(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    schema_version:Literal['pathoreason.business/1']='pathoreason.business/1'
    adapter:Literal['pathoreason.synthetic_mil']='pathoreason.synthetic_mil'
    project_id:c.Identifier
    resource_id:c.Identifier
    revision:c.Digest
    revision_kind:Literal['manifest_sha256']='manifest_sha256'
    access:Literal['read_only']='read_only'

class BusinessArtifact(c.ArtifactIndex):
    schema_version:Literal['pathoreason/2']='pathoreason/2'
    storage_root:Literal['pathoreason_artifacts']='pathoreason_artifacts'
    source_ref:WorkflowRef
    run_ref:WorkflowRef|None

class BusinessRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    turn_id:c.Identifier
    grant:c.Digest
    operation:Literal['inspect','intake','plan','revise','execute','recover','stop']
    target:c.Identifier
    expected_revision:c.Digest|None=None
    idempotency_key:c.Identifier|None=None
    parameters:dict[str,Any]=Field(default_factory=dict)

class BusinessAction(BaseModel):
    id:str;operation:str;status:str;turn_id:str;expected_revision:str;plan_digest:str
    workflow_status:str|None=None
    tool_succeeded:bool|None=None

class BusinessEvent(BaseModel):
    seq:int;scope:Literal['domain']='domain';producer:str;kind:str;status:str
    turn_id:str;action_id:str;at:float

class PlanRevision(BaseModel):
    before:str|None;after:str;feedback:str|None;learning_rate:float;action_id:str;turn_id:str

class BusinessView(BaseModel):
    project_id:str;scope:Literal['synthetic']='synthetic';status:str;revision:str
    run_id:str|None=None;plan_digest:str|None=None;question:str|None=None
    completed_units:int=0;total_units:int=8;failed_units:int=0
    used_worker_seconds:float=0;reserved_worker_seconds:float=0
    usage_accounting:Literal['cumulative_worker_wall_seconds_not_cpu_process_time']='cumulative_worker_wall_seconds_not_cpu_process_time'
    scientific_status:Literal['not_assessed']='not_assessed'
    independent_confirmation_verified:Literal[False]=False
    submission_ready:Literal[False]=False
    goal_achieved_dev:bool=False
    actions:list[BusinessAction]=Field(default_factory=list)
    revisions:list[PlanRevision]=Field(default_factory=list)
    events:list[BusinessEvent]=Field(default_factory=list)
    artifact_ids:list[str]=Field(default_factory=list)
    available_operations:list[str]=Field(default_factory=list)
    error_type:str|None=None

class Business:
    def __init__(self,service):
        self.service=service;self.store=service.store;self.data=service.data
        self.worker=ROOT/'src/pathoreason/business_worker.py'
        self.python=Path(service.config.get('legacy_root','/home/bxn/projects/auto-research'))/'.venv/bin/python'
        self.token_path=self.data/'runtime/control/business-token'
        with self.store.connect(True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS business_turns(turn_id TEXT PRIMARY KEY REFERENCES turns(id),mode TEXT NOT NULL,context TEXT NOT NULL)')
    def token(self):
        if self.token_path.is_symlink() or self.token_path.stat().st_mode & 0o077:raise ValueError('business_token_permissions')
        return self.token_path.read_text().strip()
    def mode(self,tid):
        with self.store.connect() as db:r=db.execute('SELECT mode FROM business_turns WHERE turn_id=?',(tid,)).fetchone()
        return r[0] if r else 'discuss'
    def register(self,tid,mode,context):
        with self.store.connect(True) as db:db.execute('INSERT INTO business_turns VALUES(?,?,?)',(tid,mode,encoded(context)))
    def grant(self,tid):
        row=self.store.turn(tid)
        return hmac.new(self.token().encode(),(tid+':'+row['input_digest']+':'+self.mode(tid)).encode(),hashlib.sha256).hexdigest()
    def redact(self,text,cid):
        if not self.token_path.exists():return text
        for row in self.store.turns(cid):
            if self.mode(row['id'])=='synthetic':text=text.replace(self.grant(row['id']),'[本回合执行凭证已隐藏]')
        return re.sub(r'(?i)\bgrant\b[^\n]*','[本回合执行凭证已隐藏]',text)
    def invoke(self,request):
        proc=subprocess.run([str(self.python),str(self.worker),'request'],input=encoded(request),text=True,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,cwd=ROOT,
            env={'PATH':str(self.python.parent)+':/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1',
                'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
        try:response=json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError,IndexError):raise Conflict('business_adapter_unavailable') from None
        if proc.returncode or 'error' in response:raise Conflict(response.get('error','business_adapter_failed'))
        return response
    def inspect(self,pid):
        self.store.project(pid)
        raw=self.invoke({'method':'inspect','project_id':pid})
        return self.project(raw)
    def project(self,raw):
        state=raw['snapshot']['state'];pid=state['project_id'];result=state.get('result',{})
        counts=state.get('progress',{}).get('counts',{});budget=result.get('budget',{})
        aids=self.publish(state)
        actions=[]
        for a in raw.get('actions',[raw['action']] if 'action' in raw else []):
            detail=a['plan']['detail'];r=a.get('result') or {}
            actions.append(BusinessAction(id=a['id'],operation=a['plan']['capability'],status=a['status'],
                turn_id=detail['parameters']['turn_id'],expected_revision=a['plan']['expected_revision'],plan_digest=a['digest'],
                workflow_status=r.get('workflow_status'),tool_succeeded=r.get('tool_succeeded')))
        return BusinessView(project_id=pid,status=state['status'],revision=raw['snapshot']['revision'],
            run_id=state['run_id'],plan_digest=state['plan'],question=state.get('question'),
            completed_units=counts.get('completed',0),failed_units=counts.get('failed',0),
            used_worker_seconds=budget.get('used_worker_seconds',state.get('progress',{}).get('spent',0)),
            reserved_worker_seconds=budget.get('reserved_worker_seconds',state.get('progress',{}).get('reserved',0)),
            goal_achieved_dev=bool(result.get('goal_achieved_dev',False)),actions=actions,
            revisions=state.get('revisions',[]),events=state['history'],artifact_ids=aids,
            available_operations=[c['id'] for c in raw['capabilities'] if c['available']],error_type=state.get('error_type'))
    def call(self,body:BusinessRequest):
        row=self.store.turn(body.turn_id)
        if row['status'] not in ('running','queued'):raise Conflict('business_turn_inactive')
        if row['project_id']!=body.target:raise Conflict('business_project_mismatch')
        if self.mode(body.turn_id)!='synthetic':raise Conflict('business_execution_not_enabled')
        if not hmac.compare_digest(body.grant,self.grant(body.turn_id)):raise Conflict('business_grant_invalid')
        if self.store.project(body.target)['resources']:raise Conflict('legacy_projects_are_read_only')
        if body.operation=='inspect':return self.inspect(body.target)
        if not body.expected_revision or not body.idempotency_key:raise ValueError('expected_revision_and_idempotency_key_required')
        # Gate approval is a separate user turn after a plan is visible; model cannot approve its own new proposal.
        current=self.invoke({'method':'inspect','project_id':body.target})
        state=current['snapshot']['state']
        if body.operation=='execute' and state.get('revisions') and state['revisions'][-1]['turn_id']==body.turn_id:
            raise Conflict('plan_requires_next_user_turn')
        parameters=dict(body.parameters)
        if 'turn_id' in parameters:raise ValueError('turn_id_is_server_owned')
        raw=self.invoke({'method':'act','project_id':body.target,'turn_id':body.turn_id,'operation':body.operation,
            'expected_revision':body.expected_revision,'idempotency_key':body.idempotency_key,'parameters':parameters})
        return self.project(raw)
    def publish(self,state):
        pid=state['project_id'];run=state.get('run_id');result=state.get('result')
        if not run or not result:return []
        # Published evidence is bound to this result revision; recovery gets new artifacts, never replaces old bytes.
        digest=c.canonical_digest(result);short=digest[:12];prefix=f'{pid}/{run}/{short}'
        directory=self.data/'artifacts'/prefix;directory.mkdir(parents=True,exist_ok=True)
        ref=WorkflowRef(project_id=pid,resource_id=run,revision=digest)
        rows=[]
        for unit in result.get('unit_evidence',result.get('units',[])):
            verified=(unit.get('result') or {}).get('verified',{})
            request=(unit.get('payload') or {}).get('request',{})
            rows.append([unit.get('candidate',unit.get('candidate_id','')),request.get('fold',verified.get('fold','')),
                request.get('effective_seed',verified.get('effective_seed','')),unit['status'],verified.get('metrics',{}).get('val_rmse','')])
        buf=io.StringIO();writer=csv.writer(buf);writer.writerow(['candidate','fold','seed','status','val_rmse']);writer.writerows(rows)
        summary=('# 合成 MIL 验证\n\n'+f"执行状态：{state['status']}\n\n"+
            f"完整矩阵：{sum(r[3]=='completed' for r in rows)}/{len(rows)} 单元；2 候选 × 2 折 × 2 种子。\n\n"+
            f"开发目标达成：{'是' if result.get('goal_achieved_dev') else '否'}。独立验证：未通过。科学审核：未进行。投稿就绪：否。\n\n"+
            '数据为人工合成，仅验证执行链路，不能作为临床或真实研究证据。\n\n'+
            f"[执行账本](artifact:art_{run}_{short}_ledger) · [指标表](artifact:art_{run}_{short}_metrics) · [矩阵图](artifact:art_{run}_{short}_matrix)\n")
        svg=['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="260" viewBox="0 0 800 260"><rect width="800" height="260" fill="white"/><text x="24" y="32" font-size="20" fill="#171717">Synthetic MIL — complete matrix</text>']
        for i,r in enumerate(rows):
            x=24+i%4*190;y=58+i//4*90;color={'completed':'#166534','failed':'#b91c1c','running':'#1d4ed8'}.get(r[3],'#525252')
            svg.append(f'<rect x="{x}" y="{y}" width="176" height="76" rx="12" fill="#fafafa" stroke="{color}"/><text x="{x+10}" y="{y+24}" font-size="14" fill="#171717">Cell {i+1} · {r[3]}</text><text x="{x+10}" y="{y+53}" font-size="14" fill="{color}">RMSE {r[4] if r[4] != "" else "—"}</text>')
        svg.append('</svg>')
        files=[('ledger','执行账本','ledger.json','application/json','report',json.dumps(result,ensure_ascii=False,indent=2)),
            ('metrics','验证指标','metrics.csv','text/csv','table',buf.getvalue()),
            ('matrix','完整矩阵','matrix.svg','image/svg+xml','figure',''.join(svg)),
            ('summary','合成验证报告','summary.md','text/markdown','report',summary)]
        ids=[]
        for key,title,name,mime,kind,text in files:
            content=text.encode();path=directory/name
            if not path.exists():
                # Concurrent read projections publish the same immutable bytes.
                with tempfile.NamedTemporaryFile(dir=directory,delete=False) as f:
                    temporary=Path(f.name);f.write(content);f.flush();os.fsync(f.fileno())
                try:
                    try:os.link(temporary,path)
                    except FileExistsError:pass
                finally:temporary.unlink()
            if path.read_bytes()!=content:raise Conflict('business_artifact_collision')
            artifact=BusinessArtifact(id=f'art_{run}_{short}_{key}',project_id=pid,title=title,kind=kind,media_type=mime,
                relative_path=prefix+'/'+name,sha256=hashlib.sha256(content).hexdigest(),size_bytes=len(content),
                source_ref=ref,run_ref=ref,stage_ref='development',verification_scope='bytes_verified',evidence_role='synthetic')
            self.store.add_artifact(artifact);ids.append(artifact.id)
        return ids
