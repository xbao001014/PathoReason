"""Version-bound author decisions inside the manuscript stage, never model approvals."""
import hashlib,hmac,json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .contracts import Identifier,canonical_digest
from .persistence import Conflict,Missing,encoded,now
from .legacy import read_verified_file
from .presentation_revision import PresentationChange,validate_presentation,instructions as presentation_instructions

Gate=Literal['blueprint','draft','review','scientific','delivery']
GATES=[
 ('blueprint','事实与写作方案',['facts','plan','claims','figure_plan'],'整理事实、测试使用记录、冲突、论文主线、论点边界和图表计划，复用已确认事实，仅询问未决取舍。'),
 ('draft','初稿与图件',['manuscript','references','citations','literature','argument','skill_usage','author_inputs','integrity','figure_manifest'],'核验文献、论点支持和跨材料一致性，生成初稿与实际图件；提交检索与证据矩阵、研究论证/段落覆盖及实际 Skill 使用记录。'),
 ('review','审稿意见裁定',['integrity','review_report'],'先核验初稿完整性并修复事实性阻塞，再提出有位置与依据的审稿意见，等作者逐条裁定；模型评议不是独立外部同行评审。'),
 ('scientific','修订稿与科学内容冻结',['manuscript','references','revision_matrix','integrity','figure_manifest'],'只按作者裁定修订；保留旧稿，完成逐条回应与针对确切修订稿的最终完整性核验。作者确认后才能冻结科学内容。'),
 ('delivery','最终交付',['pdf','source','pdf_qa','checklist'],'使用已批准科学内容排版，保存源包、PDF、真实页面检查与待办清单；内容变化须退回科学内容审核。交付确认不授权投稿。'),
]
class Contract(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class ReviewMaterial(Contract):
    role:str=Field(min_length=1,max_length=60)
    label:str=Field(min_length=1,max_length=120)
    artifact_id:Identifier
class ReviewIssue(Contract):
    id:Identifier
    finding:str=Field(min_length=1,max_length=1200)
    location:str=Field(default='',max_length=300)
    blocking:bool=False
    resolved:bool=False
class ReviewRequest(Contract):
    gate:Gate
    expected_revision:int=Field(ge=0)
    summary:str=Field(min_length=1,max_length=1800)
    materials:list[ReviewMaterial]=Field(min_length=1,max_length=24)
    issues:list[ReviewIssue]=Field(default_factory=list,max_length=40)
    author_questions:list[str]=Field(default_factory=list,max_length=12)
    changes:list[str]=Field(default_factory=list,max_length=8)
    key_findings:list[str]=Field(default_factory=list,max_length=8)
    key_limitations:list[str]=Field(default_factory=list,max_length=8)
    # A report's claim, bound to actual bytes; not a scientific certification.
    audit_status:Literal['not_applicable','passed','blocked']='not_applicable'
    audited_manuscript_sha256:str|None=Field(default=None,pattern='^[0-9a-f]{64}$')
    presentation_only:bool=False
    presentation_changes:list[PresentationChange]=Field(default_factory=list,max_length=24)
    scientific_basis_digest:str|None=Field(default=None,pattern='^[0-9a-f]{64}$')
    @model_validator(mode='after')
    def unique(self):
        if len({i.id for i in self.issues})!=len(self.issues):raise ValueError('manuscript_duplicate_issue')
        if any(not q or len(q)>600 for q in self.author_questions):raise ValueError('manuscript_question_invalid')
        if any(not item or len(item)>600 for items in (self.changes,self.key_findings,self.key_limitations) for item in items):raise ValueError('manuscript_review_overview_invalid')
        return self
class IssueDecision(Contract):
    issue_id:Identifier
    decision:Literal['accept','modify','reject','defer']
    rationale:str=Field(min_length=1,max_length=1200)
class ReviewDecision(Contract):
    request_key:Identifier
    expected_revision:int=Field(ge=0)
    action:Literal['approve','revise','clarify','reopen']
    comment:str=Field(default='',max_length=8000)
    issues:list[IssueDecision]=Field(default_factory=list,max_length=40)
    target_gate:Gate|None=None
    confirm_answers:bool=Field(default=False,description='Explicit user confirmation that the comment answers the pending blueprint questions and approves that plan with these answers. Does not waive integrity checks or approve later manuscript content.')

class RevisionRoute(Contract):
    turn_id:Identifier
    grant:str=Field(min_length=1,max_length=128)
    expected_goal_revision:int=Field(ge=1)
    expected_revision:int=Field(ge=0)
    target_gate:Literal['scientific','delivery']='scientific'
    revision_kind:Literal['content','presentation']='content'
    source:Literal['author_feedback','user_message']
    source_id:str=Field(min_length=1,max_length=128)
    instruction_excerpt:str=Field(min_length=1,max_length=8000)
    reason:str=Field(min_length=1,max_length=600)

    @model_validator(mode='after')
    def matching_scope(self):
        if (self.target_gate=='delivery')!=(self.revision_kind=='presentation'):raise ValueError('manuscript_revision_scope_mismatch')
        return self

class Manuscripts:
    def __init__(self,s):
        self.s=s;self.root=Path(s.store.path).parent.parent/'manuscript_reviews'
        with s.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS manuscript_workflows(project_id TEXT PRIMARY KEY,document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS manuscript_review_events(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS manuscript_review_commands(project_id TEXT NOT NULL,request_key TEXT NOT NULL,digest TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(project_id,request_key));''')
    def get(self,db,pid):
        row=db.execute('SELECT document FROM manuscript_workflows WHERE project_id=?',(pid,)).fetchone()
        return json.loads(row[0]) if row else {'project_id':pid,'revision':0,'index':0,'status':'preparing','pending':None,'approved':[],'history':[]}
    def save(self,db,w,event):
        w['revision']+=1
        db.execute('INSERT OR REPLACE INTO manuscript_workflows VALUES(?,?)',(w['project_id'],encoded(w)))
        db.execute('INSERT INTO manuscript_review_events(project_id,document) VALUES(?,?)',(w['project_id'],encoded({'at':now(),'event':event,'workflow':w})))
    def owner(self,db,cid):
        conv=self.s.store.conversation(cid);stage=self.s.stages.get(db,conv['project_id'])
        if not stage or stage['stage_id']!='manuscript' or stage['conversation_id']!=cid:raise Conflict('manuscript_stage_required')
        return conv,stage
    def view(self,cid):
        with self.s.store.connect() as db:
            conv,stage=self.owner(db,cid);w=self.get(db,conv['project_id']);goal=self.s.goals._latest(db,cid)
        current=GATES[min(w['index'],4)]
        required=[*current[2]]
        if current[0]=='delivery' and (w.get('revision_context') or {}).get('kind')=='presentation':required.append('presentation_audit')
        return {**w,'goal_state':goal['state'] if goal else None,'gate':current[0],'label':current[1],'required_roles':required,'next_work':current[3],
            'gates':[{'id':g[0],'label':g[1],'status':'approved' if i<w['index'] else w['status'] if i==w['index'] else 'not_started'} for i,g in enumerate(GATES)],
            'author_content_approved':w['index']>=4,'delivery_approved':w['index']==5,'submission_authorized':False,'independent_scientific_approval':False}
    def material_bytes(self,pid,item):
        art=self.s.store.artifact(item['artifact_id'],pid);data=self.s.artifact_bytes(art)
        if len(data)>32*1024*1024:raise ValueError('manuscript_material_too_large')
        ref=art.get('source_ref') or {}
        if ref.get('project_id')!=pid or ref.get('revision')!=art['sha256']:raise ValueError('manuscript_project_source_required')
        from .study_io import workspace
        read_verified_file(workspace(pid,self.s.config,self.s.store),ref['resource_id'],art['sha256'])
        return art,data
    def checked(self,pid,request):
        out=[];total=0
        for m in request['materials']:
            art,data=self.material_bytes(pid,m);total+=len(data)
            if total>64*1024*1024:raise ValueError('manuscript_packet_too_large')
            if not data:raise ValueError('manuscript_material_empty')
            if m['role']=='pdf' and not data.startswith(b'%PDF-'):raise ValueError('manuscript_pdf_invalid')
            out.append({**m,'sha256':hashlib.sha256(data).hexdigest(),'media_type':art['media_type'],'size':len(data)})
        return out
    def verify(self,pid,packet):
        if canonical_digest({k:v for k,v in packet.items() if k!='digest'})!=packet['digest']:raise Conflict('manuscript_review_changed')
        try:current=self.checked(pid,packet['request'])
        except (ValueError,OSError,Missing) as exc:raise Conflict('manuscript_evidence_changed') from exc
        if current!=packet['materials']:raise Conflict('manuscript_evidence_changed')
        for m in packet['materials']:
            try:archived=(self.root/pid/packet['id']/m['artifact_id']).read_bytes()
            except OSError as exc:raise Conflict('manuscript_snapshot_changed') from exc
            if hashlib.sha256(archived).hexdigest()!=m['sha256']:raise Conflict('manuscript_snapshot_changed')
    def chain(self,pid,w):
        for packet in w['approved']:self.verify(pid,packet)
    def validate(self,db,row,body):
        req=body.manuscript_review
        if not req:return
        conv,stage=self.owner(db,row['conversation_id']);w=self.get(db,row['project_id'])
        if body.outcome!='needs_input' or body.answer_only or body.stage_handoff:raise ValueError('manuscript_review_needs_input')
        if w['index']>=5 or req.gate!=GATES[w['index']][0] or req.expected_revision!=w['revision']:raise Conflict('manuscript_review_changed')
        self.chain(row['project_id'],w)
        roles={m.role for m in req.materials}
        required={'integrity'} if req.gate=='review' and req.audit_status=='blocked' else set(GATES[w['index']][2])
        if required-roles:raise ValueError('manuscript_material_roles_missing')
        if req.gate!='blueprint' and (not req.changes or not req.key_findings or not req.key_limitations):raise ValueError('manuscript_review_overview_required')
        if {m.artifact_id for m in req.materials}-set(body.evidence.artifact_ids):raise ValueError('manuscript_material_not_in_checkpoint')
        materials=self.checked(row['project_id'],req.model_dump(mode='json'))
        if req.gate in ('draft','scientific'):
            manifests=[m for m in materials if m['role']=='figure_manifest']
            if len(manifests)!=1:raise ValueError('manuscript_figure_manifest_required')
            try:figures=json.loads(self.material_bytes(row['project_id'],manifests[0])[1])
            except (ValueError,UnicodeError) as exc:raise ValueError('manuscript_figure_manifest_invalid') from exc
            if not isinstance(figures,dict) or not isinstance(figures.get('artifact_ids'),list):raise ValueError('manuscript_figure_manifest_invalid')
            listed=figures['artifact_ids']
            if any(not isinstance(x,str) for x in listed) or len(set(listed))!=len(listed):raise ValueError('manuscript_figure_manifest_invalid')
            if set(listed)!={m['artifact_id'] for m in materials if m['role']=='figure'}:raise ValueError('manuscript_figure_materials_mismatch')
            if not listed and not str(figures.get('no_figures_reason','')).strip():raise ValueError('manuscript_no_figures_reason_required')
            if listed and 'figure_audit' not in roles:raise ValueError('manuscript_figure_audit_required')
            entries=figures.get('figures')
            if listed:
                if not isinstance(entries,list) or len(entries)!=len(listed):raise ValueError('manuscript_figure_manifest_invalid')
                ids=[entry.get('artifact_id') for entry in entries if isinstance(entry,dict)]
                numbers=[entry.get('figure_number') for entry in entries if isinstance(entry,dict)]
                if len(ids)!=len(entries) or any(not isinstance(item,str) for item in ids) or any(not isinstance(item,(int,str)) for item in numbers):raise ValueError('manuscript_figure_manifest_invalid')
                if set(ids)!=set(listed) or len(set(numbers))!=len(numbers):raise ValueError('manuscript_figure_manifest_invalid')
                if any(not str(entry.get('caption','')).strip() or not str(entry.get('file','')).strip() for entry in entries):raise ValueError('manuscript_figure_manifest_invalid')
        if req.gate in ('draft','review','scientific','delivery') and req.audit_status=='not_applicable':raise ValueError('manuscript_integrity_report_required')
        if req.gate=='review':
            hashes={m['sha256'] for m in w['approved'][1]['materials'] if m['role']=='manuscript'}
            if hashes!={req.audited_manuscript_sha256}:raise Conflict('manuscript_audit_version_mismatch')
        if req.gate in ('draft','scientific'):
            hashes={m['sha256'] for m in materials if m['role']=='manuscript'}
            if hashes!={req.audited_manuscript_sha256}:raise Conflict('manuscript_audit_version_mismatch')
        if req.gate=='delivery' and req.scientific_basis_digest!=w['approved'][3]['digest']:raise Conflict('manuscript_scientific_basis_changed')
        validate_presentation(self,row['project_id'],w,req,materials)
    def settled(self,db,row,goal,checkpoint):
        req=checkpoint.get('manuscript_review')
        if not req:return
        w=self.get(db,row['project_id'])
        if w['revision']!=req['expected_revision']:goal.update(state='blocked',reason='manuscript_review_changed');return
        try:
            self.chain(row['project_id'],w)
            materials=self.checked(row['project_id'],req)
            packet={'id':'mrv_'+row['id'],'project_id':row['project_id'],'goal_id':goal['id'],'source_conversation':row['conversation_id'],'source_turn':row['id'],'request':req,'materials':materials,'created_at':now()}
            packet['digest']=canonical_digest(packet)
            directory=self.root/row['project_id']/packet['id'];directory.mkdir(parents=True,exist_ok=True,mode=0o700)
            for m in materials:
                _,data=self.material_bytes(row['project_id'],m)
                if hashlib.sha256(data).hexdigest()!=m['sha256']:raise Conflict('manuscript_evidence_changed')
                dest=directory/m['artifact_id']
                if dest.exists():
                    if dest.read_bytes()!=data:raise Conflict('manuscript_snapshot_changed')
                else:
                    with dest.open('xb') as f:f.write(data)
                    dest.chmod(0o600)
        except (ValueError,OSError,Conflict,Missing):
            goal.update(state='blocked',reason='manuscript_evidence_changed');return
        if w['pending']:w['history'].append({'event':'superseded_review','packet':w['pending'],'at':now()})
        w.update(status='awaiting_review',pending=packet);self.save(db,w,'review_requested')
        goal.update(state='waiting_input',completion_scope='not_complete',reason='manuscript_review_pending',wait_for=None,next_action='请在输入框上方的“稿件审核”栏审阅当前版本；可确认进入下一节点，或直接提交修改意见。')
    def hold(self,db,row,goal):
        w=self.get(db,row['project_id'])
        if w['pending'] and w['pending']['goal_id']==goal['id'] and goal['state'] not in ('paused','cancelled','blocked','budget_exhausted'):
            goal.update(state='waiting_input',completion_scope='not_complete',reason='manuscript_review_pending')
    def assert_complete(self,db,pid):
        w=self.get(db,pid)
        if w['index']!=5:raise Conflict('manuscript_author_review_required')
        self.chain(pid,w)
    async def decide(self,cid,body):
        async with self.s.lock:
            self.s.store.conversation(cid,writable=True)
            await self.s.context.ensure_other_operations_idle()
            with self.s.store.connect() as db:
                conv,stage=self.owner(db,cid);w=self.get(db,conv['project_id']);goal=self.s.goals._latest(db,cid)
                prior=db.execute('SELECT digest FROM manuscript_review_commands WHERE project_id=? AND request_key=?',(conv['project_id'],body.request_key)).fetchone()
            command=body.model_dump(mode='json')
            if not body.confirm_answers:command.pop('confirm_answers',None)  # Preserve pre-extension idempotency digests.
            digest=canonical_digest(command)
            if prior:
                if prior[0]!=digest:raise Conflict('manuscript_duplicate_request_changed')
                return self.view(cid)
            if body.expected_revision!=w['revision']:raise Conflict('manuscript_review_changed')
            if self.s.store.active():raise Conflict('manuscript_active_turn')
            if conv['native_session']:
                if (await self.s.runtime.status(conv['directory'])).get(conv['native_session'],{}).get('type','idle')!='idle':raise Conflict('runtime_busy')
                if await self.s.formal.pending(cid):raise Conflict('permission_settings_turn_active')
            packet=w['pending'];target=w['index']
            if body.action=='reopen':
                if not body.target_gate or not body.comment:raise ValueError('manuscript_reopen_reason_required')
                target=[g[0] for g in GATES].index(body.target_gate)
                if target>min(w['index'],4):raise Conflict('manuscript_reopen_future_gate')
            else:
                if not packet or w['status']!='awaiting_review':raise Conflict('manuscript_no_pending_review')
                if not goal or goal['id']!=packet['goal_id']:raise Conflict('manuscript_goal_changed')
                if body.target_gate:raise ValueError('manuscript_target_only_for_reopen')
            if body.confirm_answers and (body.action!='approve' or not packet or packet['request']['gate']!='blueprint' or not packet['request']['author_questions']):raise ValueError('manuscript_answer_confirmation_wrong_gate')
            if body.action=='approve':
                self.chain(conv['project_id'],w);self.verify(conv['project_id'],packet)
                req=packet['request']
                if any(i['blocking'] and not i['resolved'] for i in req['issues']) or req['audit_status']=='blocked':raise Conflict('manuscript_unresolved_blockers')
                if req['author_questions'] and not (req['gate']=='blueprint' and body.confirm_answers and body.comment.strip()):raise Conflict('manuscript_author_facts_required')
                if req['gate'] in ('scientific','delivery') and not body.comment:raise ValueError('manuscript_written_confirmation_required')
                if req['gate']=='review':
                    ids={i['id'] for i in req['issues']};decisions=[i.issue_id for i in body.issues]
                    if len(decisions)!=len(ids) or set(decisions)!=ids:raise ValueError('manuscript_each_issue_requires_decision')
                elif body.issues:raise ValueError('manuscript_issue_decisions_wrong_gate')
            elif not body.comment:raise ValueError('manuscript_feedback_required')
            if body.action=='revise' and packet['request']['gate']=='review' and (packet['request']['audit_status']=='blocked' or any(i['blocking'] and not i['resolved'] for i in packet['request']['issues'])):target=1
            receipt={'event':'author_decision','source':'user_review_ui','at':now(),'action':body.action,'comment':body.comment,'issues':[i.model_dump() for i in body.issues],'target_gate':GATES[min(target,4)][0],'packet':packet,'invalidated':w['approved'][target:] if target<w['index'] else []}
            if body.confirm_answers:receipt['question_response']={'questions':packet['request']['author_questions'],'answer':body.comment,'confirmed_with_plan':True}
            w['history'].append(receipt)
            if body.action=='approve':w['approved'].append(packet);w['index']+=1
            if body.action=='reopen' or target<w['index'] and body.action!='approve':w['approved']=w['approved'][:target];w['index']=target
            if w['index']<4:w.pop('revision_context',None)
            w.update(status='approved' if w['index']==5 else 'preparing',pending=None)
            with self.s.store.connect(True) as db:
                if self.get(db,conv['project_id'])['revision']!=body.expected_revision:raise Conflict('manuscript_review_changed')
                self.save(db,w,'author_'+body.action)
                db.execute('INSERT INTO manuscript_review_commands VALUES(?,?,?,?)',(conv['project_id'],body.request_key,digest,encoded(receipt)))
                if stage['status']=='completed' and body.action=='reopen':
                    stage['history'].append({'kind':'revision_requested','stage_id':'manuscript','conversation_id':cid,'handoff':stage['handoff'],'at':now()})
                    stage.update(status='active',handoff=None);self.s.stages.save(db,stage,'manuscript_reopened')
                if goal and goal['state'] not in ('completed','cancelled'):
                    # Same transaction as the author receipt. Retries return above;
                    # agent checkpoints and ordinary chat never reset this window.
                    goal['turn_window']={'kind':'manuscript_review','gate':GATES[w['index']][0] if w['index']<5 else 'handoff',
                        'review_revision':w['revision'],'action':body.action,'start_turns':goal['turns_used']}
                    goal['limit_revision']=goal.get('limit_revision',0)+1
                    goal['user_instructions']=[*goal.get('user_instructions',[]),{'source':'manuscript_author_review','text':encoded({k:v for k,v in receipt.items() if k not in ('packet','invalidated')}),'review_digest':packet['digest'] if packet else None}][-12:]
                    if goal['state']!='paused':
                        goal.update(state='active',completion_scope='not_complete',reason='manuscript_author_decision',blocker=None,wait_for=None,stagnant_turns=0,
                            next_action=GATES[w['index']][3] if w['index']<5 else '作者已确认交付文件；登记成果并提交稿件阶段交接，不投稿。')
                    self.s.goals._save(db,goal,'manuscript_author_decision')
        self.s.goals.start();return self.view(cid)
    def archived_material(self,cid,review_id,artifact_id):
        with self.s.store.connect() as db:
            conv,stage=self.owner(db,cid);w=self.get(db,conv['project_id'])
        packets=[w['pending'],*w['approved'],*[h.get('packet') for h in w['history']]]
        packet=next((p for p in packets if p and p['id']==review_id),None)
        if not packet:raise Missing('manuscript_review_not_found')
        m=next((m for m in packet['materials'] if m['artifact_id']==artifact_id),None)
        if not m:raise Missing('manuscript_material_not_found')
        data=(self.root/conv['project_id']/packet['id']/m['artifact_id']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=m['sha256']:raise Conflict('manuscript_snapshot_changed')
        return data,m['media_type']
    def route_revision(self,body):
        """Interpret an existing user instruction; never approve a model's revision."""
        from .goals import GoalCheckpoint
        row=self.s.store.turn(body.turn_id)
        if not hmac.compare_digest(body.grant,self.s.guidance.grant(body.turn_id)):raise Conflict('goal_grant_invalid')
        payload=body.model_dump(mode='json',exclude={'grant'})
        check=GoalCheckpoint(turn_id=body.turn_id,grant=body.grant,expected_revision=body.expected_goal_revision,
            outcome='continue',summary='Route the existing author revision request.',next_action='Prepare a new version for scientific review.')
        with self.s.store.connect(True) as db:
            link=self.s.goals._check_checkpoint(db,row,check)
            if link['checkpoint']:raise Conflict('manuscript_route_after_checkpoint')
            if self.s.goals.frozen_config(db,body.turn_id).get('execution_scope','standard')!='standard':raise Conflict('goal_outside_turn_scope')
            conv=self.s.store.conversation(row['conversation_id'],writable=True)
            stage=self.s.stages.get(db,conv['project_id'])
            if not stage or stage['stage_id']!='manuscript':raise Conflict('manuscript_stage_required')
            route_key='revision_route_'+body.turn_id
            prior=db.execute('SELECT document FROM manuscript_review_commands WHERE project_id=? AND request_key=?',(conv['project_id'],route_key)).fetchone()
            if prior:
                if json.loads(prior[0]).get('request')!=payload:raise Conflict('manuscript_route_replay_changed')
                return self.view(row['conversation_id'])
            w=self.get(db,conv['project_id'])
            if w['revision']!=body.expected_revision:raise Conflict('manuscript_review_changed')
            if w['index'] not in (4,5):raise Conflict('manuscript_route_requires_delivery')
            moving=stage['conversation_id']!=row['conversation_id']
            if moving:
                old_goal=self.s.goals._latest(db,stage['conversation_id'])
                if w['index']!=5 or w.get('pending') or (old_goal and old_goal['state'] not in ('completed','cancelled')):raise Conflict('manuscript_revision_owner_busy')
                self.s.store.conversation(stage['conversation_id'])
            elif stage['status'] not in ('active','completed'):raise Conflict('manuscript_stage_required')
            if body.source=='author_feedback':
                author=next((h for h in reversed(w['history']) if h['event']=='author_decision'),None)
                if link['origin']!='goal' or not author or author['at']!=body.source_id or author['action']!='revise':raise Conflict('manuscript_revision_instruction_required')
                if db.execute("SELECT 1 FROM turns t JOIN goal_turns g ON g.turn_id=t.id WHERE t.conversation_id=? AND g.origin='user' AND t.created_at>? LIMIT 1",(row['conversation_id'],author['at'])).fetchone():raise Conflict('manuscript_revision_instruction_superseded')
                instruction=author['comment']
            else:
                if link['origin']!='user' or body.source_id!=body.turn_id:raise Conflict('manuscript_revision_instruction_required')
                instruction=row['user_text']
                context=db.execute('SELECT document FROM turn_guidance_context WHERE turn_id=?',(body.turn_id,)).fetchone()
                if context and json.loads(context[0]).get('unresolved_acceptance'):raise Conflict('manuscript_revision_intent_unresolved')
            if body.instruction_excerpt not in instruction:raise Conflict('manuscript_revision_excerpt_mismatch')
            self.chain(conv['project_id'],w)
            target=4 if body.revision_kind=='presentation' else 3
            receipt={'event':'revision_routed','source':'agent_interpretation','at':now(),'source_turn':body.turn_id,
                'instruction_source':body.source,'instruction_source_id':body.source_id,'comment':instruction,
                'instruction_excerpt':body.instruction_excerpt,'reason':body.reason,'target_gate':body.target_gate,'revision_kind':body.revision_kind,
                'packet':w['pending'],'invalidated':w['approved'][target:]}
            w['history'].append(receipt)
            if moving or stage['status']=='completed':
                stage['history'].append({'kind':'revision_requested','stage_id':'manuscript','conversation_id':stage['conversation_id'],
                    'destination':row['conversation_id'],'handoff':stage.get('handoff'),'source_turn':row['id'],'at':now()})
                stage.update(conversation_id=row['conversation_id'],status='active',handoff=None)
                self.s.stages.save(db,stage,'manuscript_revision_attached')
            w.update(index=target,approved=w['approved'][:target],pending=None,status='preparing',
                revision_context={'kind':body.revision_kind,'source_turn':row['id'],'scientific_basis_digest':w['approved'][3]['digest']})
            self.save(db,w,'revision_routed')
            db.execute('INSERT INTO manuscript_review_commands VALUES(?,?,?,?)',(conv['project_id'],route_key,canonical_digest(payload),encoded({'request':payload,'receipt':receipt})))
        return self.view(row['conversation_id'])

    def revision_entry_prompt(self,cid):
        conv=self.s.store.conversation(cid)
        with self.s.store.connect() as db:
            stage=self.s.stages.get(db,conv['project_id']);w=self.get(db,conv['project_id'])
            if not stage or stage['stage_id']!='manuscript' or w['index']!=5:return ''
            old=self.s.goals._latest(db,stage['conversation_id'])
            available=not old or old['state'] in ('completed','cancelled')
        return '\nPROJECT MANUSCRIPT REVISION ENTRY (read-only discovery, not ownership or permission): '+encoded({
            'project_id':conv['project_id'],'current_owner':stage['conversation_id'],'revision':w['revision'],
            'revision_entry_available':available,'approved_packets':[{k:p[k] for k in ('id','digest','materials')} for p in w['approved'][3:]],
            'rule':'For a clear request to revise this existing manuscript, route the exact current user instruction before editing. Ordinary discussion does not reopen anything. If unavailable, return to the current stage conversation.'})+'\n'+presentation_instructions(str(Path(__file__).resolve().parents[2]/'scripts/manuscript_revision.py'))

    def prompt(self,cid):
        v=self.view(cid)
        if v['gate']=='delivery':
            v['next_work']+=presentation_instructions(str(Path(__file__).resolve().parents[2]/'scripts/manuscript_revision.py'))
        if v['gate'] in ('draft','scientific'):
            v['next_work']+=' 显式调用 anti-defensive-writing Skill 并完整读取其 authorial-voice 配套规范。起草时使用；作者裁定后的科学修订在请求冻结前完成全文语义检查，输出与确切稿件 SHA 绑定的 reader_facing_style_review.json 和 reader_facing_voice_report.json，作为 style_review/voice_report 材料登记并纳入 checkpoint evidence。科学冻结前须同时 status=passed、style_status=passed；只读过规范、关键词扫描、一般完整性报告均不等于通过。保留阴性结果、不确定性与实质限制，不把反复自我否定当审慎。'
        elif v['gate'] in ('review','delivery'):
            v['next_work']+=' 显式调用 anti-defensive-writing Skill 核对对应稿件的语义及 voice 报告、SHA 和双 passed 状态；缺失/过期/失败须列明为未解决问题，不能用完整性或 PDF QA 通过替代。交付时保护已批准正文；用户已授权文字修改时先按上述接口转入 scientific 并生成新版本；没有修改授权时只读检查并提出具体修改范围，不自行覆盖冻结稿或伪造通过记录。'
        if v['gate']=='draft':
            v['next_work']+=' 实际加载 method-results-to-manuscript 并完整读取 references/stage-execution.md，按其任务依赖加载子 Skill 和配套文件；目录清单不是已读证据。背景/引用/研究动机补强必须重走 paper-lookup、citation-management、文献综合及 scientific-writing，不能只审计旧稿。读取 authorial-voice.md；病理概念图读取 methodology-figures.md 和 raster-generation.md，获授权后用配置的 Seedream 链路生成真实候选，不以实验框图代替。文学证据和 argument 覆盖临床/病理背景、已有工作、具体缺口、研究问题与设计理由；不以引用数量代替语义支持。'
        # Keep original author statements across phases and context recovery; never replace them with a model paraphrase.
        statements=[{k:h.get(k) for k in ('at','action','comment','issues','target_gate','question_response')} for h in v['history'] if h['event']=='author_decision']
        if v['gate'] in ('draft','scientific'):
            v['next_work']+=' 有图时逐一运行 scripts/inspect_figure_text.py，核对图内标签、图注、manifest 与稿件；登记绑定图件哈希的 figure_audit 材料。OCR 仅是辅助证据，无法核验关键标签时必须阻塞完整性审计，不能转嫁给作者。对确定性生成的图表还必须在渲染后验证文字边界完全位于所属面板内、面板互不重叠，并把图件 SHA、尺寸和几何结果纳入 figure_audit；每次返工另存新版本，禁止覆盖已登记源文件。'
        return '\nMANUSCRIPT AUTHOR WORKFLOW: '+encoded({k:v[k] for k in ('revision','gate','label','status','required_roles','next_work','author_content_approved','delivery_approved')})+'\nAUTHOR STATEMENTS (retain scope, resolve conflicts explicitly): '+encoded(statements)+'\nUse method-results-to-manuscript, peer-review and manuscript-to-latex skills for the applicable work. This is five author review nodes inside stage 5, not five new conversations. You may prepare routine drafts/checks within authority, but cannot advance or approve an author gate. When current materials are ready, register actual artifacts and checkpoint outcome=needs_input with manuscript_review={gate,expected_revision,summary,changes:[plain-language version changes],key_findings:[claims the author should verify],key_limitations:[material limitations that remain],materials:[{role,label,artifact_id}],issues:[{id,finding,location,blocking,resolved}],author_questions,audit_status,audited_manuscript_sha256,scientific_basis_digest}. Include every material artifact ID in checkpoint evidence. For every node after blueprint, provide non-empty changes, key_findings and key_limitations so the review bar can present the decision without forcing the author to reconstruct it from a file list. Preserve versions; never overwrite approved artifacts. Required roles are listed above. Draft review requires the actual bibliography and a fresh cross-material integrity report bound by audited_manuscript_sha256 to the exact manuscript bytes; compare manuscript, references, citation report, author checklist, figure manifest, figure labels/captions and declared block structure. Resolve routine inconsistencies before requesting approval, or declare concrete blocking issues. Draft and scientific figure_manifest is a registered JSON artifact {artifact_ids:[figure artifact IDs],no_figures_reason:optional}; include those actual images/PDFs as role=figure in the same review packet. An empty list needs an explicit honest reason, not a placeholder image. Changed scientific figures require renewed author review. Source snapshots and review decisions are platform-owned. Do not create author signatures, gate receipts or declarations yourself. For draft/review/scientific/delivery provide a fresh integrity or PDF QA report with audit_status passed/blocked. Draft and scientific audits bind the exact manuscript SHA-256; the review audit binds the SHA-256 of the approved draft. If pre-review integrity is blocked, submit the integrity material and blocking issues rather than a fabricated peer review; requesting changes reopens the draft and revokes its approval. Use the current author workflow below as the host authority; do not run legacy workflow stores or write approval receipts. Create pipeline files beneath manuscript/ so publish_artifact can register them. For delivery use the approved scientific packet digest from GET /api/v2/conversations/'+cid+'/manuscript-review. Check references, figures and PDF pages, not merely compilation. No external or independent peer-review claim for model reviews. Write every review request for a busy author: summary leads with what is ready, the recommended choice and what happens after approval, in plain language; put technical inventories and verification details in materials/issues. Ask only unresolved decisions that change the current scope or necessary facts, group closely related decisions, and reuse prior instructions. Optional future directions must not block this gate: retain them as non-blocking notes with no new commitment unless the user requests one. Blueprint approval may include a platform-recorded question_response: apply that original answer while preparing the draft, do not request the same confirmation again, and preserve the unchanged scope and budgets. If an answer conflicts with evidence or requires materially changing approved scope, explain that concrete conflict instead of inventing a resolution. Later content approval still binds exact reviewed bytes; feedback requiring content changes creates a new version. Missing author facts go in author_questions only if necessary to decide THIS gate; submission-only missing facts remain in a clearly marked checklist and do not block earlier drafting. Citation verification, factual integrity and declared blocking issues cannot be waived by approval. Before asking for facts check all author statements; null fields and generic approval do not erase earlier facts. User comments can clarify or request changes but ordinary continue, tool auto-approval and a model report cannot approve these gates. Respect per-issue accept/modify/reject/defer decisions and preserve deferred limitations. Rework invalidates affected approvals and requires fresh review. After all gates approved, submit the existing manuscript stage_handoff; stage completion does not authorize submission.\n'
