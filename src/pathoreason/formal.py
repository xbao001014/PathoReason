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
from .gpu_settings import GpuBinding

class StudyBudget(BaseModel):
    model_config=ConfigDict(extra='forbid')
    max_turns:int=Field(ge=1,le=1000)
    max_wall_seconds:int=Field(ge=60,le=86400)
    max_turn_wall_seconds:int=Field(default=86400,ge=60,le=604800)
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
    execution_scope:Literal['standard','dialogue','inspection']='standard'
    gpu_binding:GpuBinding|None=None
    time_accounting:Literal['legacy_wall','tool_excluded_v1']='legacy_wall'
    max_turn_wall_seconds:int=Field(default=86400,ge=60,le=604800)
class StudyView(BaseModel):
    schema_version:Literal['pathoreason.study/1']='pathoreason.study/1'
    project_id:str
    workspace:str
    budget:StudyBudget
    used_turns:int
    used_wall_seconds:float
    used_budget_seconds:float=0
    excluded_tool_seconds:float=0
    legacy_wall_seconds:float=0
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
    release:str='0.6.11-p5-process-budget'
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
    definitions=[
        ('pathology-data-api','病理接口数据接入','按病种读取分页接口，核对患者/标本/切片关联、来源回执与中断续跑。','病种、接口协议及已授权数据范围'),
        ('benchmark-design','Benchmark 选型与比较方案','结合现有方法库和近期联网论文，形成有来源的模型候选、公平协议、实验矩阵及实现缺口。','研究问题、候选队列、现有方案及资源条件'),
    ]
    result=[]
    for name,title,description,required in definitions:
        base=ROOT/'skills'/name
        refs=[str(p.relative_to(ROOT))+'#sha256='+hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(base.rglob('*')) if p.is_file() and p.suffix in {'.md','.py'}]
        raw={'schema_version':'pathoreason/1','id':name,'version':'0.4.0' if name=='benchmark-design' else '0.1.0',
             'title':title,'description':description,
             'input_schema_ref':'urn:pathoreason:study:1','output_schema_ref':'urn:pathoreason:artifact:3',
             'instruction_refs':refs,'capability_refs':['pathoreason:formal_study'],
             'workflow_template_refs':[],'runtime_support':['opencode'],
             'required_inputs':[required],'required_tools':['native_skill','reviewed_workspace_execution'],
             'implementation_status':'implemented','evidence_scope':'contract_only',
             'runtime_readiness':'ready' if server else 'unavailable',
             'unavailable_reason':None if server else '正式研究在 bxn-server 进行'}
        result.append(c.SkillDefinition(**raw,digest=c.canonical_digest(raw)).model_dump(mode='json'))
    return result

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
        from .timing import totals
        with self.s.store.connect() as db:rows=self.s.store.budget_rows(db,pid)
        used=totals(rows)
        return StudyView(project_id=pid,workspace=record['workspace'],budget=record['budget'],used_turns=len(rows),used_wall_seconds=used['wall_seconds'],used_budget_seconds=used['budget_seconds'],excluded_tool_seconds=used['tool_seconds'],legacy_wall_seconds=used['legacy_seconds'],revision=record['revision'])
    def create(self,body):
        if not self.enabled():raise Conflict('formal_server_only')
        payload=body.model_dump(mode='json')
        if 'max_turn_wall_seconds' not in body.budget.model_fields_set:payload['budget'].pop('max_turn_wall_seconds',None)
        digest=c.canonical_digest(payload)
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
For substantive work, read {ROOT}/docs/p5/OPERATOR.md and load relevant migrated skills from {ROOT}/.agents/skills. Use OpenCode + DeepSeek; use the configured Seedream helper for conceptual raster figures. Do not invoke Codex/Gemini/OpenRouter or delegate to unconfigured agents.

Existing researcher workflows, complete matrices, source hashes, budgets, patient grouping, held-out data boundaries and author gates remain in effect. Do not reduce an agreed design merely to finish. Do not modify or restart historical experiments. Reusable source: {self.s.config.get('legacy_root','/home/bxn/projects/auto-research')} (read-only).

All new inputs, plans, scripts and outputs belong to this workspace or its isolated /data/bxn/PathoReason/studies/{pid} storage. For legacy engine commands set PYTHONDONTWRITEBYTECODE=1 and AUTORESEARCH_COMPUTE_CONFIG to this workspace's compute.json. It does not authorize training. Check the frozen plan, resource budget and operator approval before any real compute, data fetch or paid image request. Preserve the original engine gates; native command approval does not replace scientific/author review.

The model conversation budget is {record['budget']['max_turns']} turns / {record['budget']['max_wall_seconds']} accounted seconds. New turns exclude only recorded native tool intervals (including approval waits within those intervals); historical wall-time charges are retained. This is a conservative Agent-time estimate, not provider billing or GPU time. Each new turn additionally has a {record['budget'].get('max_turn_wall_seconds',86400)} second wall cap. Do not keep the model polling a long training process: use the approved executor's persistent job/receipt workflow when available, return its real status, and resume analysis after completion; do not invent job support or detach untracked commands to bypass limits. This is distinct from training/GPU/image budgets. Prepare a concrete plan within the user's authorized scope. Reuse existing authorization for that same scope across turns; request approval only for missing scope or budget, not for routine continuation. Native tools follow the permission settings selected for this conversation; explicit deny rules still apply. Permission settings do not change research budgets or scientific/author gates. Use ordinary chat for questions (native question tool is disabled). Interpret brief everyday requests using relevant context and existing authorization. For clear reversible revisions, inherit unchanged parameters and produce the requested draft with stated assumptions. Ask only the missing consequential choice; do not demand a complete technical prompt or reconfirm a unique accepted proposal. Resolve simple ambiguity before loading unrelated protocols. Reply concisely in the user's language.

Resolve a missing user choice with the dialogue tool before exploration when context suffices. For actual baseline selection, experiment planning or comparison work, load the native benchmark-design skill. Establish the research comparison and data protocol, inventory the local library read-only, and search recent primary literature with websearch/webfetch. Separate scientifically justified model selection from executor availability; missing adapters become explicit implementation work, not silent benchmark exclusions. Preserve existing cohorts and plans; produce versioned candidate evidence, fair comparison protocol and a complete proposed matrix before training authorization. Network access settings govern both websearch and webfetch. For validation-protocol-only revisions, reuse existing candidate/source evidence and read benchmark-design validation-protocols.md. Use benchmark-plan/2 to distinguish fixed holdout from cross-validation, verify actual split status, and preserve old plans and any frozen patient membership.

For MIL execution preparation, smoke/pilot training or alignment diagnosis, read {ROOT}/skills/benchmark-design/references/execution-readiness.md and use the public mil_preflight.py / pathoreason.mil_execution components for supported adapters. Use explicit model and optimizer/scheduler parameters; verify finite gradients and non-bias weight updates before judging task difficulty. Keep unsupported adapters as explicit implementation gaps without shrinking the agreed matrix. Preflight uses CPU synthetic inputs only; real alignment uses train/validation data without test evaluation. Preserve prior failures and exposed-test provenance. New research scripts/configurations/results must be versioned by the research Agent, never silently repaired in place. These checks do not replace executor isolation, authorization, job budgets or scientific review.

For pathology API data acquisition, load the native pathology-data-api skill and its protocol reference before choosing a helper. The old study_io.py data command is only for the legacy Limit-based endpoint; use the skill helper for the authenticated PageIndex/PageSize protocol. Use {ROOT}/scripts/study_io.py image for one versioned Seedream candidate and publish to register actual outputs in the workbench. Do not put credential values or patient details in public chat. Source API records and feature tensors are different: resolve the returned remote paths and verify input completeness before training. Status and scientific approval derive from source evidence, not prose.
'''
    def prompt(self,row):
        record=self.record(row['project_id'])
        policy=self.permissions.view(row['conversation_id'])
        instructions=self.instructions(row['project_id'],record)
        with self.s.store.connect() as db:
            frozen=db.execute('SELECT document FROM runtime_configs WHERE digest=?',(json.loads(row['document'])['config_digest'],)).fetchone()
        binding=json.loads(frozen[0]).get('gpu_binding') if frozen else None
        if binding:
            import shlex
            command=shlex.join([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/compute_exec.py'),'--turn',row['id'],'--'])
            instructions=instructions.replace("AUTORESEARCH_COMPUTE_CONFIG to this workspace's compute.json",'AUTORESEARCH_COMPUTE_CONFIG to '+binding['compute_path'])
            instructions+='\nFrozen GPU binding for this turn: '+encoded(binding)+'\nFor every new GPU compute or legacy engine command, prefix the command with '+command+' . This launcher sets CUDA_VISIBLE_DEVICES to the selected UUID and AUTORESEARCH_COMPUTE_CONFIG to the frozen configuration, and checks the current UUID/index mapping. Do not override these variables or use a stale GPU index from previous chat or project files. Inside a single visible CUDA device use cuda:0. This is a future-task selection, not a reservation or permission to train. Existing jobs, frozen experiment plans, worker budgets and scientific/author gates remain unchanged. If an existing experiment is bound to another device, prepare and validate a new binding under its existing workflow; never edit its frozen config or silently migrate it. Recheck available memory before launching; if busy, report the resource blocker and allow another selection, without killing other processes.\n'
        return instructions+'\nConversation permission settings: '+encoded(policy.settings)+'\nCurrent user request:\n'+row['user_text']
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
