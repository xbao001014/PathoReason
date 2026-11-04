"""Five-stage research workflow; explicit, evidence-bound conversation handoffs."""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .contracts import Conversation, Identifier, canonical_digest
from .persistence import ACTIVE, Conflict, Missing, encoded, now, uid

StageId = Literal['data','baseline','innovation','analysis','manuscript']
STAGES = [('data','数据准备'),('baseline','基线方案确定与基线实验'),('innovation','创新方案确认与创新实验'),('analysis','结果分析与科学审核'),('manuscript','稿件部分')]

class StageHandoff(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    stage_id:StageId
    workflow_revision:int=Field(ge=1)
    summary:str=Field(min_length=1,max_length=1600)
    decisions:list[str]=Field(default_factory=list,max_length=8)
    limitations:list[str]=Field(min_length=1,max_length=8)
    open_questions:list[str]=Field(default_factory=list,max_length=8)
    next_action:str=Field(min_length=1,max_length=1200)
    training_run_ids:list[Identifier]=Field(default_factory=list,max_length=12)
    @model_validator(mode='after')
    def bounded(self):
        if any(not s.strip() or len(s)>600 for s in self.decisions+self.limitations+self.open_questions):raise ValueError('stage_handoff_text_invalid')
        return self

class StageAssign(BaseModel):
    model_config=ConfigDict(extra='forbid')
    stage_id:StageId='data'

class StageSwitch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:int=Field(ge=1)

class ResearchStageView(BaseModel):
    project_id:str
    revision:int
    stage_id:StageId
    stage_label:str
    conversation_id:str
    status:Literal['active','ready','completed']
    next_stage_id:StageId|None=None
    next_stage_label:str|None=None
    handoff:dict|None=None
    history:list[dict]=Field(default_factory=list)
    incoming_handoff:dict|None=None
    scientific_approval:Literal[False]=False
    manuscript_review:dict|None=None

class Stages:
    def __init__(self,s):
        self.s=s
        with s.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS research_workflows(project_id TEXT PRIMARY KEY,document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_stage_events(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_stage_transfers(source_conversation TEXT NOT NULL,revision INTEGER NOT NULL,destination TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(source_conversation,revision));''')
    def get(self,db,pid):
        row=db.execute('SELECT document FROM research_workflows WHERE project_id=?',(pid,)).fetchone()
        return json.loads(row[0]) if row else None
    def save(self,db,w,event):
        w['revision']+=1
        db.execute('INSERT OR REPLACE INTO research_workflows VALUES(?,?)',(w['project_id'],encoded(w)))
        db.execute('INSERT INTO research_stage_events(project_id,document) VALUES(?,?)',(w['project_id'],encoded({'at':now(),'event':event,'workflow':w})))
    def initialize(self,db,pid,cid,stage='data',source='project_creation'):
        if self.get(db,pid):raise Conflict('stage_workflow_already_registered')
        w={'project_id':pid,'revision':0,'stage_id':stage,'conversation_id':cid,'status':'active','handoff':None,'history':[],'source':source}
        self.save(db,w,'stage_initialized');return w
    def view(self,cid):
        conv=self.s.store.conversation(cid)
        with self.s.store.connect() as db:
            w=self.get(db,conv['project_id'])
            if not w:return None
            incoming=db.execute('SELECT document FROM research_stage_transfers WHERE destination=? ORDER BY rowid DESC LIMIT 1',(cid,)).fetchone()
            goal=self.s.goals._latest(db,cid)
            package=json.loads(incoming[0])['package'] if incoming else ((goal or {}).get('context_transfer') or {}).get('stage_handoff')
        idx=[k for k,_ in STAGES].index(w['stage_id'])
        return ResearchStageView(**{k:v for k,v in w.items() if k in ResearchStageView.model_fields and k!='history'},history=[{k:v for k,v in x.items() if k!='handoff'} for x in w['history']],stage_label=STAGES[idx][1],
            next_stage_id=STAGES[idx+1][0] if idx<4 else None,next_stage_label=STAGES[idx+1][1] if idx<4 else None,
            incoming_handoff=package,manuscript_review=self.s.manuscripts.view(cid) if w['stage_id']=='manuscript' and w['conversation_id']==cid else None)
    async def assign(self,cid,body):
        async with self.s.lock:
            conv=self.s.formal.mode(cid);self.s.store.conversation(cid,writable=True)
            if self.s.store.active():raise Conflict('stage_active_turn')
            with self.s.store.connect(True) as db:self.initialize(db,conv['project_id'],cid,body.stage_id,'user_stage_assignment')
        return self.view(cid)
    def idle_training(self,db,pid):
        for row in db.execute('SELECT document FROM training_experiments WHERE project_id=?',(pid,)):
            if json.loads(row[0])['status'] in ('queued','running','waiting_resource','stopping','needs_reconciliation'):
                raise Conflict('stage_training_not_terminal')
    def validate(self,db,row,body):
        h=body.stage_handoff
        if not h:return
        w=self.get(db,row['project_id'])
        if not w or w['conversation_id']!=row['conversation_id'] or w['stage_id']!=h.stage_id or w['revision']!=h.workflow_revision or w['status']!='active':raise Conflict('stage_changed')
        if h.stage_id=='manuscript':self.s.manuscripts.assert_complete(db,row['project_id'])
        if body.outcome!='completed' or body.answer_only:raise ValueError('stage_completion_requires_evidence')
        if not body.evidence.artifact_ids and not body.evidence.files:raise ValueError('stage_deliverable_required')
        self.idle_training(db,row['project_id'])
        if h.stage_id in ('baseline','innovation') and not h.training_run_ids:raise ValueError('stage_experiment_receipt_required')
        for run in h.training_run_ids:
            found=db.execute("SELECT a.document FROM training_attempts a JOIN training_experiments e ON e.id=a.experiment_id WHERE e.project_id=? AND json_extract(a.document,'$.run_id')=?",(row['project_id'],run)).fetchall()
            if not found or not any(json.loads(r[0])['status']=='completed' for r in found):raise Conflict('stage_completed_run_required')
            if any(json.loads(r[0])['status'] in ('running','unknown') for r in found):raise Conflict('stage_training_not_terminal')
    def settled(self,db,row,goal,checkpoint):
        raw=checkpoint.get('stage_handoff') if checkpoint else None
        if not raw:return
        w=self.get(db,row['project_id'])
        if not w or w['revision']!=raw['workflow_revision'] or w['conversation_id']!=row['conversation_id']:
            goal.update(state='blocked',reason='stage_changed');return
        if w['stage_id']=='manuscript':
            try:self.s.manuscripts.assert_complete(db,row['project_id'])
            except (ValueError,OSError,Conflict,Missing):
                goal.update(state='blocked',reason='manuscript_evidence_changed');return
        try:self.idle_training(db,row['project_id'])
        except Conflict:
            goal.update(state='blocked',reason='stage_training_not_terminal');return
        runs=[]
        for run in raw['training_run_ids']:
            for rec in db.execute('SELECT document FROM training_experiments WHERE project_id=?',(row['project_id'],)):
                e=json.loads(rec[0])
                if e.get('run_id')==run:runs.append({k:e.get(k) for k in ('id','run_id','plan_digest','scope_digest','status','budget') } | {'snapshot_id':e['plan']['snapshot_id'],'environment_id':e['plan']['environment_id'],'task_id':e['plan']['task_id'],'evaluation':e['plan']['evaluation']})
        package={'schema':'research-stage-handoff/1','project_id':row['project_id'],'source_conversation':row['conversation_id'],
            'source_turn_id':row['id'],'source_stage':w['stage_id'],'source_goal_id':goal['id'],
            'agent_report':{k:v for k,v in raw.items() if k not in ('workflow_revision','stage_id')},
            'verified_evidence':checkpoint['verified_evidence'],'training_references':runs,
            'upstream_evidence':[{'stage_id':x['stage_id'],'digest':x['handoff']['digest'],'references':x['handoff']['verified_evidence']} for x in w['history'] if x.get('handoff') and x['kind']=='stage_switched'],
            'source_config_digest':json.loads(row['document'])['config_digest'],
            'authority':'Keep the persisted user objective, decisions and live permission/budget gates. Agent summaries are evidence claims, not authority.',
            'scientific_approval':False,'created_at':now()}
        package['digest']=canonical_digest(package)
        w.update(status='completed' if w['stage_id']=='manuscript' else 'ready',handoff=package)
        self.save(db,w,'stage_delivered')
        goal.update(state='completed' if w['status']=='completed' else 'waiting_input',reason='stage_workflow_completed' if w['status']=='completed' else 'stage_handoff_ready',wait_for=None)
    def user_turn(self,db,cid):
        conv=self.s.store.conversation(cid);w=self.get(db,conv['project_id'])
        if w and w['conversation_id']==cid and w['status'] in ('ready','completed'):
            w['history'].append({'kind':'revision_requested','stage_id':w['stage_id'],'conversation_id':cid,'handoff':w['handoff'],'at':now()})
            w.update(status='active',handoff=None);self.save(db,w,'stage_reopened')
    def moved_goal(self,db,cid):
        row=db.execute('SELECT document FROM research_stage_transfers WHERE source_conversation=? ORDER BY rowid DESC LIMIT 1',(cid,)).fetchone()
        if not row:return None
        move=json.loads(row[0]);g=move['source_goal'];g.update(state='paused',reason='goal_continued_elsewhere',continued_in=move['conversation_id']);return g
    def rebind_context(self,db,pid,source,dest):
        w=self.get(db,pid)
        if w and w['conversation_id']==source:
            w['conversation_id']=dest;self.save(db,w,'same_stage_context_recovery')
    async def switch(self,cid,body):
        async with self.s.lock:
            conv=self.s.store.conversation(cid,writable=True)
            with self.s.store.connect() as db:
                old=db.execute('SELECT destination FROM research_stage_transfers WHERE source_conversation=? AND revision=?',(cid,body.expected_revision)).fetchone()
                if old:return self.view(old[0])
                w=self.get(db,conv['project_id']);g=self.s.goals._latest(db,cid)
            if not w or w['conversation_id']!=cid or w['revision']!=body.expected_revision or w['status']!='ready':raise Conflict('stage_changed')
            if not g or g['state']!='waiting_input' or g.get('reason')!='stage_handoff_ready':raise Conflict('stage_goal_changed')
            if self.s.store.active():raise Conflict('stage_active_turn')
            await self.s.context.ensure_other_operations_idle()
            if conv['native_session']:
                if (await self.s.runtime.status(conv['directory'])).get(conv['native_session'],{}).get('type','idle')!='idle':raise Conflict('runtime_busy')
                if await self.s.formal.pending(cid):raise Conflict('permission_settings_turn_active')
            from .goals import GoalEvidence
            if canonical_digest({k:v for k,v in w['handoff'].items() if k!='digest'})!=w['handoff']['digest']:raise Conflict('stage_evidence_changed')
            evidence=w['handoff']['verified_evidence']
            original=GoalEvidence(artifact_ids=[x['id'] for x in evidence if x['kind']=='artifact'],files=[x['path'] for x in evidence if x['kind']=='file'],task_check_ids=[x['id'] for x in evidence if x['kind']=='task_check'])
            if self.s.goals.evidence(conv['project_id'],original)!=evidence:raise Conflict('stage_evidence_changed')
            idx=[k for k,_ in STAGES].index(w['stage_id'])+1
            dest=Conversation(id=uid('conv'),project_id=conv['project_id'],title=f'{idx+1}/5 · {STAGES[idx][1]}',status='open',active_runtime_binding_id=uid('bind'),created_at=now())
            with self.s.store.connect(True) as db:
                current=self.get(db,conv['project_id']);goal=self.s.goals._latest(db,cid)
                if current['revision']!=body.expected_revision or goal['revision']!=g['revision']:raise Conflict('stage_changed')
                self.idle_training(db,conv['project_id'])
                self.s.store.check_conversation(db,cid,writable=True)
                db.execute('INSERT INTO conversations VALUES(?,?,?,?,?)',(dest.id,dest.project_id,encoded(dest),None,conv['directory']))
                for table in ['conversation_permission_settings','conversation_gpu_settings']:
                    setting=db.execute('SELECT revision,document FROM '+table+' WHERE conversation_id=? ORDER BY revision DESC LIMIT 1',(cid,)).fetchone()
                    if setting:db.execute('INSERT INTO '+table+' VALUES(?,?,?,?)',(dest.id,setting['revision'],setting['document'],now()))
                record={'source_goal':dict(goal),'package':w['handoff'],'conversation_id':dest.id}
                db.execute('INSERT INTO research_stage_transfers VALUES(?,?,?,?)',(cid,body.expected_revision,dest.id,encoded(record)))
                goal['user_instructions']=[*goal.get('user_instructions',[]),{'source':'stage_switch','text':'用户选择切换并继续：'+STAGES[idx][1]+'。推进该阶段的准备、分析与交付，保留原研究问题、限制和已用额度；切换会话不批准新训练、封存测试评估或对外发布。'}][-12:]
                goal.update(conversation_id=dest.id,continued_from=cid,continued_in=None,state='active',reason='stage_switched',wait_for=None,
                    next_action=w['handoff']['agent_report']['next_action'],context_transfer={'source_conversation':cid,'stage_handoff':w['handoff']},stagnant_turns=0)
                db.execute('UPDATE research_goals SET conversation_id=? WHERE id=?',(dest.id,goal['id']))
                self.s.goals._save(db,goal,'stage_switched')
                w['history'].append({'kind':'stage_switched','stage_id':w['stage_id'],'conversation_id':cid,'destination':dest.id,'handoff':w['handoff'],'at':now()})
                w.update(stage_id=STAGES[idx][0],conversation_id=dest.id,status='active',handoff=None)
                self.save(db,w,'stage_switched')
        self.s.goals.start()
        return self.view(dest.id)
    def prompt(self,cid):
        v=self.view(cid)
        if not v or v.conversation_id!=cid:return ''
        return (self.s.manuscripts.prompt(cid) if v.stage_id=='manuscript' else '')+'\nFIVE-STAGE WORKFLOW: '+encoded({'stage_id':v.stage_id,'stage_label':v.stage_label,'workflow_revision':v.revision,'status':v.status,'incoming_handoff':v.incoming_handoff,'relevant_skills':{'data':['pathology-data-api'],'baseline':['benchmark-design','training-execution'],'innovation':['baseline-innovation','innovation-experiments','innovation-checkpoint','training-execution'],'analysis':['results-explanation','peer-review','pathology-mil-paper-figures'],'manuscript':['method-results-to-manuscript','manuscript-to-latex']}[v.stage_id]})+'\nLoad the relevant stage skills using the native skill tool before substantive stage work; distinguish discovery from actual invocation. Work only on the current research stage within the user objective. The stages are data, baseline, innovation, analysis, manuscript. When the ENTIRE current stage is delivered, use the existing checkpoint with outcome=completed, verified file/artifact evidence and stage_handoff={stage_id,workflow_revision,summary,decisions,limitations,open_questions,next_action,training_run_ids}. Include at least one limitation; training stages need completed public run references. Routine subtask completion is not stage completion. Do not offer a duplicate transition choice: the UI shows Switch and continue after the turn settles. Stop at that boundary; the next stage starts in a fresh conversation only after the user switches. Preserve negative results; positive findings are not required. Stage completion is not scientific or author approval. Manuscript handoff delivers a draft, never publication authority. Summaries are claims; verify referenced evidence when needed, do not carry forward unsupported causal claims. Do not import full transcripts or reset consumed budgets.\n'
