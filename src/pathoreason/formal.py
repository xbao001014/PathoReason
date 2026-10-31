"""P5 real-study entry. Native execution remains explicit, project-bound and reviewable."""
from __future__ import annotations
import hashlib,json,shutil
from pathlib import Path
from datetime import datetime
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from . import contracts as c
from .settings import ROOT
from .persistence import Conflict,Missing,now,uid,encoded
from .schema_v2 import RuntimeConfiguration,InvocationPolicy
from .permission_settings import PermissionSettings,ConversationPermissions

class StudyBudget(BaseModel):
    model_config=ConfigDict(extra='forbid')
    max_turns:int=Field(ge=1,le=1000)
    max_wall_seconds:int=Field(ge=60,le=86400)
class StudyCreate(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    request_key:c.Identifier
    title:str=Field(min_length=1,max_length=120)
    objective:str=Field(min_length=1,max_length=4000)
    budget:StudyBudget
class FormalPolicy(InvocationPolicy):
    execution_mode:Literal['research']='research'
class FormalConfiguration(RuntimeConfiguration):
    schema_version:Literal['pathoreason.runtime-config/2']='pathoreason.runtime-config/2'
    execution_mode:Literal['research']='research'
    agent:Literal['pathoreason-formal']='pathoreason-formal'
    invocation_policy:FormalPolicy
    study_revision:c.Digest
    permission_settings:PermissionSettings|None=None
    permission_revision:int|None=None
class StudyView(BaseModel):
    schema_version:Literal['pathoreason.study/1']='pathoreason.study/1'
    project_id:str
    workspace:str
    budget:StudyBudget
    used_turns:int
    used_wall_seconds:float
    phase:str='prepared'
    scientific_approval:Literal[False]=False
    revision:str
class NativePermission(BaseModel):
    id:str
    permission:str
    patterns:list[str]
    command:str|None=None
    always:list[str]=Field(default_factory=list)
class PermissionReply(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reply:Literal['once','always','reject']
class EntryStatus(BaseModel):
    environment:str
    available:bool
    data_endpoint:str|None
    data_live_verified:bool=False
    seedream_model:str|None
    seedream_credential_present:bool
    seedream_live_verified:bool=False
    migrated_skills:int
    release:str='0.6.3-p5-data-skill'
    formal_acceptance:Literal['pending_new_window']='pending_new_window'

TITLES={'academic-research-suite':'研究规划与流程','citation-management':'引文管理','histolab':'病理切片预处理','manuscript-to-latex':'LaTeX 排版与交付','method-results-to-manuscript':'研究成果转稿件','paper-lookup':'文献检索','pathology-figures':'病理图件路由','pathology-mil-paper-figures':'病理 MIL 图件','peer-review':'稿件评审','scientific-schematics':'方法图与原理图','scientific-visualization':'科学结果可视化','scientific-writing':'科学写作','statistical-analysis':'统计分析'}

def private_image_config(config):
    path=Path(config.get('image_config_file','/home/bxn/.config/pathoreason/image-generation.json'))
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:return {}
    return json.loads(path.read_text())

def migrated_skills(server):
    result=[];manifest=json.loads((ROOT/'config/p5/skill-migration.json').read_text())
    for item in manifest['skills']:
        name=item['name'];path=ROOT/item['destination']/'SKILL.md'
        if not path.is_file():continue
        raw={'schema_version':'pathoreason/1','id':name,'version':'0.6.0','title':TITLES[name],'description':'已迁移原 Skill 与配套资源；正式研究中按阶段加载，完整真实流程待验收。','input_schema_ref':'urn:pathoreason:study:1','output_schema_ref':'urn:pathoreason:artifact:3','instruction_refs':[item['destination']+'/SKILL.md#sha256='+hashlib.sha256(path.read_bytes()).hexdigest()],'capability_refs':['pathoreason:formal_study'],'workflow_template_refs':[],'runtime_support':['opencode'],'required_inputs':['研究问题、实际证据与阶段对应输入'],'required_tools':['native_skill','reviewed_workspace_execution'],'implementation_status':'implemented','evidence_scope':'contract_only','runtime_readiness':'ready' if server else 'unavailable','unavailable_reason':None if server else '正式试验在 bxn-server 进行'}
        result.append(c.SkillDefinition(**raw,digest=c.canonical_digest(raw)).model_dump(mode='json'))
    return result


def project_skills(server):
    """Project-owned native skills, separate from immutable upstream migration evidence."""
    base=ROOT/'skills/pathology-data-api'
    refs=[str(p.relative_to(ROOT))+'#sha256='+hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(base.rglob('*')) if p.is_file() and p.suffix in {'.md','.py'}]
    raw={'schema_version':'pathoreason/1','id':'pathology-data-api','version':'0.1.0',
         'title':'病理接口数据接入',
         'description':'按病种读取分页接口，核对患者/标本/切片关联、来源回执与中断续跑；工程检查通过，真实基模行为待验证。',
         'input_schema_ref':'urn:pathoreason:study:1','output_schema_ref':'urn:pathoreason:artifact:3',
         'instruction_refs':refs,'capability_refs':['pathoreason:formal_study'],
         'workflow_template_refs':[],'runtime_support':['opencode'],
         'required_inputs':['病种、接口协议及已授权数据范围'],
         'required_tools':['native_skill','reviewed_workspace_execution'],
         'implementation_status':'implemented','evidence_scope':'contract_only',
         'runtime_readiness':'ready' if server else 'unavailable',
         'unavailable_reason':None if server else '正式试验数据接入在 bxn-server 进行'}
    return [c.SkillDefinition(**raw,digest=c.canonical_digest(raw)).model_dump(mode='json')]

class Formal:
    def __init__(self,s):
        self.s=s
        with s.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS formal_studies(project_id TEXT PRIMARY KEY REFERENCES projects(id),request_key TEXT UNIQUE NOT NULL,input_digest TEXT NOT NULL,document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS formal_permissions(request_id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,turn_id TEXT NOT NULL,document TEXT NOT NULL);''')
        self.permissions=ConversationPermissions(self)
    def enabled(self):return self.s.runtime_name=='opencode' and self.s.config.get('execution_environment')=='bxn-server'
    def status(self):
        config=private_image_config(self.s.config) if self.enabled() else {}
        source=json.loads((ROOT/'config/p5/data-source.json').read_text())
        return EntryStatus(environment=self.s.config.get('execution_environment','local'),available=self.enabled(),data_endpoint=source['endpoint'] if self.enabled() else None,seedream_model=config.get('model'),seedream_credential_present=bool(config.get('api_key')),migrated_skills=len(TITLES))
    def record(self,pid):
        with self.s.store.connect() as db:row=db.execute('SELECT document FROM formal_studies WHERE project_id=?',(pid,)).fetchone()
        return json.loads(row[0]) if row else None
    def view(self,pid):
        self.s.store.project(pid);record=self.record(pid)
        if not record:return None
        with self.s.store.connect() as db:rows=db.execute('SELECT created_at,document FROM turns WHERE project_id=?',(pid,)).fetchall()
        used=sum(max(0,(datetime.fromisoformat(json.loads(r['document']).get('finished_at') or now())-datetime.fromisoformat(r['created_at'])).total_seconds()) for r in rows)
        return StudyView(project_id=pid,workspace=record['workspace'],budget=record['budget'],used_turns=len(rows),used_wall_seconds=used,revision=record['revision'])
    def create(self,body):
        if not self.enabled():raise Conflict('formal_server_only')
        digest=c.canonical_digest(body.model_dump(mode='json'))
        with self.s.store.connect() as db:old=db.execute('SELECT project_id,input_digest FROM formal_studies WHERE request_key=?',(body.request_key,)).fetchone()
        if old:
            if old['input_digest']!=digest:raise Conflict('idempotency_key_conflict')
            return self.view(old['project_id'])
        s=self.s;pid=uid('prj');workspace=s.data/'projects'/pid;artifact_dir=s.data/'artifacts'/pid
        p=c.ResearchProject(id=pid,title=body.title,objective=body.objective,revision=1,status='active',resources=[],created_at=now())
        conv=c.Conversation(id=uid('conv'),project_id=pid,title='正式研究对话',status='open',active_runtime_binding_id=uid('bind'),created_at=now())
        record={'schema_version':'pathoreason.study/1','project_id':pid,'workspace':str(workspace),'budget':body.budget.model_dump(),'created_at':now(),'training_authorized':False,'image_authorized':False}
        record['revision']=c.canonical_digest(record)
        try:
            workspace.mkdir();artifact_dir.mkdir()
            for name in ['inputs','plans','runs','manuscript','figures','outputs']:(workspace/name).mkdir()
            (workspace/'study.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
            (workspace/'AGENTS.md').write_text(self.instructions(pid,record))
            legacy=Path(s.config.get('legacy_root','/home/bxn/projects/auto-research'))/'config/compute.local.json'
            if legacy.exists():
                compute=json.loads(legacy.read_text());study_root=s.data/'studies'/pid;study_root.mkdir(parents=True)
                compute['storage_policy']['data_root']=str(study_root)
                compute['storage']={k:str(study_root/k) for k in compute['storage']}
                for target in compute['storage'].values():Path(target).mkdir()
                compute['real_training_authorized']=False
                (workspace/'compute.json').write_text(json.dumps(compute,indent=2)+'\n')
            with s.store.connect(True) as db:
                db.execute('INSERT INTO projects VALUES(?,?)',(pid,encoded(p)))
                db.execute('INSERT INTO conversations VALUES(?,?,?,?,?)',(conv.id,pid,encoded(conv),None,str(workspace)))
                db.execute('INSERT INTO formal_studies VALUES(?,?,?,?)',(pid,body.request_key,digest,encoded(record)))
        except BaseException:
            shutil.rmtree(workspace,ignore_errors=True);shutil.rmtree(artifact_dir,ignore_errors=True);shutil.rmtree(s.data/'studies'/pid,ignore_errors=True);raise
        return self.view(pid)
    def instructions(self,pid,record):
        return f'''# PathoReason real study workspace

Project: {pid}. Workspace: {record['workspace']}.
Read {ROOT}/docs/p5/OPERATOR.md and load relevant migrated skills from {ROOT}/.agents/skills. Use OpenCode + DeepSeek; use the configured Seedream helper for conceptual raster figures. Do not invoke Codex/Gemini/OpenRouter or delegate to unconfigured agents.

Existing researcher workflows, complete matrices, source hashes, budgets, patient grouping, held-out data boundaries and author gates remain in effect. Do not reduce an agreed design merely to finish. Do not modify or restart historical experiments. Reusable source: {self.s.config.get('legacy_root','/home/bxn/projects/auto-research')} (read-only).

All new inputs, plans, scripts and outputs belong to this workspace or its isolated /data/bxn/PathoReason/studies/{pid} storage. For legacy engine commands set PYTHONDONTWRITEBYTECODE=1 and AUTORESEARCH_COMPUTE_CONFIG to this workspace's compute.json. It does not authorize training. Check the frozen plan, resource budget and operator approval before any real compute, data fetch or paid image request. Preserve the original engine gates; native command approval does not replace scientific/author review.

The model conversation budget is {record['budget']['max_turns']} turns / {record['budget']['max_wall_seconds']} wall seconds, including waiting for command review. This is distinct from training/GPU/image budgets. Prepare a concrete plan within the user's authorized scope. Reuse existing authorization for that same scope across turns; request approval only for missing scope or budget, not for routine continuation. Native tools follow the permission settings selected for this conversation; explicit deny rules still apply. Permission settings do not change research budgets or scientific/author gates. Use ordinary chat for questions (native question tool is disabled).

For pathology API data acquisition, load the native pathology-data-api skill and its protocol reference before choosing a helper. The old study_io.py data command is only for the legacy Limit-based endpoint; use the skill helper for the authenticated PageIndex/PageSize protocol. Use {ROOT}/scripts/study_io.py image for one versioned Seedream candidate and publish to register actual outputs in the workbench. Do not put credential values or patient details in public chat. Source API records and feature tensors are different: resolve the returned remote paths and verify input completeness before training. Status and scientific approval derive from source evidence, not prose.
'''
    def prompt(self,row):
        record=self.record(row['project_id'])
        policy=self.permissions.view(row['conversation_id'])
        return self.instructions(row['project_id'],record)+'\nConversation permission settings: '+encoded(policy.settings)+'\nCurrent user request:\n'+row['user_text']
    def mode(self,cid):
        conv=self.s.store.conversation(cid)
        if not self.record(conv['project_id']):raise Conflict('formal_study_required')
        return conv
    async def pending(self,cid):
        conv=self.mode(cid)
        if not conv['native_session']:return []
        rows=await self.s.runtime.call('GET','/permission',conv['directory'])
        return [NativePermission(id=r['id'],permission=r['permission'],patterns=r.get('patterns',[]),command=r.get('metadata',{}).get('command'),always=r.get('always',[])) for r in rows if r.get('sessionID')==conv['native_session']]
    async def reply(self,cid,rid,reply):
        conv=self.mode(cid);active=[r for r in self.s.store.active() if r['conversation_id']==cid]
        if len(active)!=1:raise Conflict('no_unique_active_turn')
        requests=await self.pending(cid);request=next((r for r in requests if r.id==rid),None)
        if not request:raise Missing('permission_not_found')
        if reply=='always' and not request.always:raise Conflict('permission_session_patterns_unavailable')
        # Persist intent before contacting runtime; a lost acknowledgement never auto-replays approval.
        record={'request':request.model_dump(),'reply':reply,'at':now(),'state':'dispatching'}
        with self.s.store.connect(True) as db:
            if db.execute('SELECT 1 FROM formal_permissions WHERE request_id=?',(rid,)).fetchone():raise Conflict('permission_outcome_requires_native_reconciliation')
            db.execute('INSERT INTO formal_permissions VALUES(?,?,?,?)',(rid,cid,active[0]['id'],encoded(record)))
        await self.s.runtime.call('POST','/permission/'+rid+'/reply',conv['directory'],{'reply':reply})
        record['state']='acknowledged'
        with self.s.store.connect(True) as db:db.execute('UPDATE formal_permissions SET document=? WHERE request_id=?',(encoded(record),rid))
        return {'status':'acknowledged'}
