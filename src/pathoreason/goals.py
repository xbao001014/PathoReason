"""Durable, bounded goal continuation. Never interprets prose as a job receipt."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .contracts import Identifier, canonical_digest
from .persistence import ACTIVE, Conflict, Missing, Gone, encoded, now, uid
from .settings import ROOT
from .reasoning import ReasoningEffort

CONTEXT_BLOCKERS={'context_window_requires_compaction_or_handoff','context_operation_unresolved',
    'context_budget_exhausted','context_usage_unverified','context_recovery_failed','context_recovery_running'}


class GoalRecoveryInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    goal_id:Identifier
    expected_revision:int=Field(ge=1)
    action:Literal['compact','reconcile','new_conversation']


class GoalEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artifact_ids: list[Identifier] = Field(default_factory=list, max_length=10)
    files: list[str] = Field(default_factory=list, max_length=8)
    task_check_ids: list[Identifier] = Field(default_factory=list, max_length=8)


class GoalWait(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['synthetic_run','training_run']
    run_id: Identifier


class GoalBlocker(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['platform', 'permission', 'input', 'resource']
    capability: Literal['training_execution'] | None = None
    required_action: str = Field(min_length=1, max_length=600)

    @model_validator(mode='after')
    def category(self):
        if self.capability and self.kind!='platform':raise ValueError('capability_requires_platform_blocker')
        return self


class GoalCheckpoint(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    turn_id: Identifier
    grant: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=1)
    outcome: Literal['continue', 'completed', 'needs_input', 'blocked', 'paused', 'waiting', 'cancelled']
    summary: str = Field(min_length=1, max_length=1200)
    next_action: str = Field(default='', max_length=1200)
    completion_criteria: list[str] = Field(default_factory=list, max_length=8)
    evidence: GoalEvidence = Field(default_factory=GoalEvidence)
    answer_only: bool = False
    wait_for: GoalWait | None = None
    blocker: GoalBlocker | None = None

    @model_validator(mode='after')
    def shape(self):
        if self.blocker and self.outcome!='blocked':raise ValueError('blocker_requires_blocked_outcome')
        if self.outcome == 'continue' and not self.next_action:
            raise ValueError('next_action_required')
        if (self.outcome == 'waiting') != (self.wait_for is not None):
            raise ValueError('registered_wait_reference_required')
        if self.answer_only and self.outcome != 'completed':
            raise ValueError('answer_only_is_completion')
        if any(not x.strip() or len(x)>500 for x in self.completion_criteria):
            raise ValueError('invalid_completion_criteria')
        return self


class GoalControl(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    action: Literal['pause', 'resume', 'revise', 'cancel']
    objective: str | None = Field(default=None, min_length=1, max_length=16000)
    max_turns: int | None = Field(default=None, ge=1, le=40)
    reasoning_effort: ReasoningEffort | None = None

    @model_validator(mode='after')
    def resume_settings(self):
        if self.reasoning_effort is not None and self.action!='resume':
            raise ValueError('goal_effort_requires_resume')
        return self


class GoalView(BaseModel):
    schema_version: Literal['pathoreason.goal/1'] = 'pathoreason.goal/1'
    id: str
    conversation_id: str
    project_id: str
    revision: int
    objective: str
    state: Literal['active','paused','blocked','waiting_input','waiting','completed','budget_exhausted','cancelled']
    blocker: GoalBlocker | None = None
    suggested_reasoning_effort: Literal['low','none'] | None = None
    summary: str = ''
    next_action: str = ''
    reason: str | None = None
    wait_for: GoalWait | None = None
    completion_criteria: list[str] = Field(default_factory=list)
    turns_used: int = 0
    max_turns: int = 8
    last_turn_id: str
    evidence: list[dict] = Field(default_factory=list)
    completion_scope: Literal['not_complete','answer_only','evidence_bytes_verified'] = 'not_complete'
    scientific_approval: Literal[False] = False
    created_at: str
    updated_at: str
    continued_from: str|None=None
    continued_in: str|None=None
    limit_revision:int=0


class Goals:
    def __init__(self, service):
        self.s = service
        self.worker = None
        self.tick_lock = asyncio.Lock()
        with service.store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS research_goals(
                  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                  project_id TEXT NOT NULL REFERENCES projects(id), document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS goal_turns(
                  turn_id TEXT PRIMARY KEY REFERENCES turns(id), goal_id TEXT NOT NULL REFERENCES research_goals(id),
                  origin TEXT NOT NULL, goal_revision INTEGER NOT NULL, parent_turn_id TEXT,
                  processed INTEGER NOT NULL DEFAULT 0, checkpoint TEXT,
                  UNIQUE(goal_id,parent_turn_id));
                CREATE TABLE IF NOT EXISTS goal_events(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL REFERENCES research_goals(id),
                  document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS goal_context_recoveries(
                  source_conversation TEXT NOT NULL, goal_id TEXT NOT NULL, revision INTEGER NOT NULL,
                  action TEXT NOT NULL, document TEXT NOT NULL,
                  PRIMARY KEY(source_conversation,goal_id,revision));
            ''')
        # Preserve first-release receipts while repairing the cross-goal key.
        with service.store.connect(True) as db:
            if 'goal_id' not in {r['name'] for r in db.execute('PRAGMA table_info(goal_context_recoveries)')}:
                db.execute('ALTER TABLE goal_context_recoveries RENAME TO goal_context_recoveries_legacy')
                db.execute('CREATE TABLE goal_context_recoveries(source_conversation TEXT NOT NULL,goal_id TEXT NOT NULL,revision INTEGER NOT NULL,action TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(source_conversation,goal_id,revision))')
                for row in db.execute('SELECT * FROM goal_context_recoveries_legacy').fetchall():
                    receipt=json.loads(row['document']);gid=receipt.get('source_goal',{}).get('id')
                    if not gid:
                        matches=db.execute("SELECT DISTINCT goal_id FROM goal_events WHERE json_extract(document,'$.snapshot.conversation_id')=? AND json_extract(document,'$.revision')=? AND json_extract(document,'$.event')=?",(row['source_conversation'],row['revision']+1,'context_'+row['action']+'_requested')).fetchall()
                        if len(matches)==1:gid=matches[0][0]
                    if gid:db.execute('INSERT INTO goal_context_recoveries VALUES(?,?,?,?,?)',(row['source_conversation'],gid,row['revision'],row['action'],row['document']))

    def _latest(self, db, cid):
        row = db.execute('SELECT document FROM research_goals WHERE conversation_id=? ORDER BY rowid DESC LIMIT 1', (cid,)).fetchone()
        return json.loads(row[0]) if row else None

    def view(self, cid):
        self.s.store.conversation(cid)
        with self.s.store.connect() as db:
            goal = self._latest(db, cid)
            moved=db.execute("SELECT document FROM goal_context_recoveries WHERE source_conversation=? AND action='new_conversation' ORDER BY rowid DESC LIMIT 1",(cid,)).fetchone()
            if moved:
                move=json.loads(moved[0])
                if goal is None or move['source_goal']['created_at']>goal['created_at']:
                    goal=move['source_goal']
                    goal.update(state='paused',reason='goal_continued_elsewhere',continued_in=move['conversation_id'])
        if goal:
            goal['suggested_reasoning_effort']=None
            request=goal.get('request_template',{})
            if goal.get('reason')=='runtime_output_limit':
                current=request.get('reasoning_effort') or 'high'
                suggestion='low' if current in ('high','max') else 'none' if current=='low' else None
                if suggestion and any(o['model']==request.get('model') and suggestion in o['efforts'] for o in self.s.reasoning_options()):
                    goal['suggested_reasoning_effort']=suggestion
        return GoalView.model_validate(goal) if goal else None

    def recover_interrupted_context(self):
        with self.s.store.connect(True) as db:
            for row in db.execute('SELECT document FROM research_goals').fetchall():
                goal=json.loads(row[0])
                if goal.get('reason')=='context_recovery_running':
                    goal.update(state='blocked',reason='context_operation_unresolved')
                    self._save(db,goal,'context_recovery_interrupted')

    async def recover_context(self,cid,body):
        """Explicit user recovery; never reset counters or dispatch an unknown operation."""
        async with self.s.lock:
            conv=self.s.store.conversation(cid,writable=True)
            with self.s.store.connect() as db:
                prior=db.execute('SELECT action,document FROM goal_context_recoveries WHERE source_conversation=? AND goal_id=? AND revision=?',(cid,body.goal_id,body.expected_revision)).fetchone()
                if prior:
                    if prior['action']!=body.action:raise Conflict('goal_changed')
                    saved=json.loads(prior['document']);return self.view(saved['conversation_id'])
                goal=self._latest(db,cid)
            if not goal or goal['id']!=body.goal_id or goal['revision']!=body.expected_revision:raise Conflict('goal_changed')
            if goal.get('reason') not in CONTEXT_BLOCKERS or goal['state']!='blocked':raise Conflict('goal_context_recovery_not_available')
            if self.s.store.active():raise Conflict('runtime_busy')
            await self.s.context.ensure_other_operations_idle()
            if conv['native_session']:
                if (await self.s.runtime.status(conv['directory'])).get(conv['native_session'],{}).get('type','idle')!='idle':raise Conflict('runtime_busy')
                if await self.s.formal.pending(cid):raise Conflict('permission_settings_turn_active')
            study=self.s.formal.view(conv['project_id'])
            if study.used_turns>=study.budget.max_turns or study.used_budget_seconds>=study.budget.max_wall_seconds:raise Conflict('acceptance_budget_exhausted')
            if goal['turns_used']>=goal['max_turns']:raise Conflict('goal_turn_limit')
            if body.action=='new_conversation':
                # Same project and goal. Only the native conversation window changes.
                from .contracts import Conversation
                dest=Conversation(id=uid('conv'),project_id=conv['project_id'],title='接续目标 · '+json.loads(conv['document'])['title'][:100],status='open',active_runtime_binding_id=uid('bind'),created_at=now())
                recent=self.s.store.turns(cid)[-3:]
                transfer={'source_conversation':cid,'recent_dialogue':[{'turn_id':t['id'],'origin':(self.link(t['id']) or {}).get('origin','user'),'user_text':t['user_text'][:2000],'reply':t['text'][-4000:]} for t in recent]}
                with self.s.store.connect(True) as db:
                    self.s.store.check_conversation(db,cid,writable=True)
                    db.execute('INSERT INTO conversations VALUES(?,?,?,?,?)',(dest.id,dest.project_id,encoded(dest),None,conv['directory']))
                    for table in ['conversation_permission_settings','conversation_gpu_settings']:
                        setting=db.execute('SELECT revision,document FROM '+table+' WHERE conversation_id=? ORDER BY revision DESC LIMIT 1',(cid,)).fetchone()
                        if setting:db.execute('INSERT INTO '+table+' VALUES(?,?,?,?)',(dest.id,setting['revision'],setting['document'],now()))
                    receipt={'conversation_id':dest.id,'source_goal':dict(goal)}
                    goal.update(conversation_id=dest.id,continued_from=cid,state='active',reason='context_new_conversation',context_transfer=transfer)
                    db.execute('UPDATE research_goals SET conversation_id=? WHERE id=?',(dest.id,goal['id']))
                    self._save(db,goal,'context_new_conversation')
                    db.execute('INSERT INTO goal_context_recoveries VALUES(?,?,?,?,?)',(cid,goal['id'],body.expected_revision,body.action,encoded(receipt)))
                self.start()
                return self.view(dest.id)
            model=goal['request_template']['model']
            key='goal_context_'+goal['id']+'_'+str(body.expected_revision)
            with self.s.store.connect(True) as db:
                goal.update(state='paused',reason='context_recovery_running')
                self._save(db,goal,'context_'+body.action+'_requested')
                db.execute('INSERT INTO goal_context_recoveries VALUES(?,?,?,?,?)',(cid,goal['id'],body.expected_revision,body.action,encoded({'conversation_id':cid})))
            revision=goal['revision']
        reason=None
        try:
            if body.action=='compact':
                result=await self.s.context.compact(cid,key,model)
                if result['status']!='completed':reason='context_operation_unresolved' if result['status']=='recovery_required' else 'context_recovery_failed'
            else:await self.s.context.reconcile(cid)
            view=self.s.context.view(cid)
            if any(o['status'] in ('running','recovery_required') for o in view.operations):reason='context_operation_unresolved'
            if reason is None and view.source!='post_compaction_bytes_estimate':reason='context_usage_unverified'
        except asyncio.CancelledError:
            self._set_state(goal,'blocked','context_operation_unresolved');raise
        except Exception as exc:
            reason=str(exc) if isinstance(exc,Conflict) else 'context_recovery_failed'
        async with self.s.lock:
            with self.s.store.connect(True) as db:
                current=self._latest(db,cid)
                # A pause, cancellation, archive or revision always wins over recovery.
                if current and current['id']==goal['id'] and current['revision']==revision and current['reason']=='context_recovery_running':
                    current.update(state='blocked' if reason else 'active',reason=reason or 'context_recovered')
                    self._save(db,current,'context_recovery_checked')
        self.start()
        return self.view(cid)

    def link(self, tid):
        with self.s.store.connect() as db:
            row = db.execute('SELECT * FROM goal_turns WHERE turn_id=?', (tid,)).fetchone()
        return dict(row) if row else None

    def _save(self, db, goal, event):
        goal['revision'] += 1
        goal['updated_at'] = now()
        GoalView.model_validate(goal)
        db.execute('UPDATE research_goals SET document=? WHERE id=?', (encoded(goal), goal['id']))
        db.execute('INSERT INTO goal_events(goal_id,document) VALUES(?,?)',
                   (goal['id'], encoded({'at': now(), 'event': event, 'revision': goal['revision'],
                                        'state': goal['state'], 'reason': goal['reason'], 'snapshot':goal})))

    def prepare(self, cid, request, automatic=None):
        with self.s.store.connect() as db: goal = self._latest(db, cid)
        if automatic:
            if not goal or goal['id'] != automatic['id'] or goal['revision'] != automatic['revision'] or goal['state']!='active':
                raise Conflict('goal_changed')
            return {'automatic': True, 'goal': goal}
        mode = request.get('goal_mode', 'single')
        if mode=='continuous' and not self.s.formal.record(self.s.store.conversation(cid)['project_id']):
            raise Conflict('formal_study_required')
        # A pause survives ordinary chat/status questions. Resume is an explicit
        # control; new text alone must not undo the user's pause.
        return {'automatic': False, 'goal': goal, 'continuous': mode=='continuous' and (not goal or goal['state']!='paused')}

    def bind(self, db, context, turn, request):
        """Atomic with turn creation: no phantom goal or duplicate continuation."""
        current = self._latest(db, turn.conversation_id)
        expected = context['goal']
        if (current or {}).get('revision') != (expected or {}).get('revision') or (current or {}).get('id') != (expected or {}).get('id'):
            raise Conflict('goal_changed')
        automatic = context['automatic']
        if not automatic and not context['continuous']:
            if current and current['state'] not in ('completed','cancelled','paused'):
                current.update(state='paused', reason='single_turn_selected')
                self._save(db, current, 'single_turn_selected')
            return
        if not current or current['state'] in ('completed','cancelled'):
            current = GoalView(id=uid('goal'), conversation_id=turn.conversation_id, project_id=turn.project_id,
                revision=1, objective=request['text'], state='active', last_turn_id=turn.id,
                created_at=now(), updated_at=now()).model_dump(mode='json')
            current.update(stagnant_turns=0, processed_evidence=[], request_template={}, user_instructions=[])
            db.execute('INSERT INTO research_goals VALUES(?,?,?,?)', (current['id'],turn.conversation_id,turn.project_id,encoded(current)))
        if current['turns_used'] >= current['max_turns']:
            raise Conflict('goal_turn_limit')
        parent = current['last_turn_id'] if automatic else None
        if automatic and (current['state']!='active' or current['revision']!=expected['revision']):
            raise Conflict('goal_changed')
        current.update(state='active', reason=None, last_turn_id=turn.id, turns_used=current['turns_used']+1)
        if not automatic:
            current['user_instructions'] = [*current.get('user_instructions',[]), {'turn_id':turn.id,'text':request['text']}][-12:]
            current['request_template'] = {k:request.get(k) for k in ('model','reasoning_effort','skill_id','execution_mode')}
            current['stagnant_turns'] = 0
        self._save(db, current, 'auto_turn_created' if automatic else 'user_turn_created')
        db.execute('INSERT INTO goal_turns(turn_id,goal_id,origin,goal_revision,parent_turn_id) VALUES(?,?,?,?,?)',
                   (turn.id,current['id'],'goal' if automatic else 'user',current['revision'],parent))

    def evidence(self, pid, evidence):
        result = []
        workspace = Path(self.s.formal.record(pid)['workspace']).resolve()
        for aid in evidence.artifact_ids:
            artifact = self.s.store.artifact(aid, pid)
            self.s.artifact_bytes(artifact)
            result.append({'kind':'artifact','id':aid,'sha256':artifact['sha256'],'scope':'bytes_verified'})
        for name in evidence.files:
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts:
                raise ValueError('goal_evidence_path_invalid')
            path = workspace / relative
            if not path.resolve().is_relative_to(workspace) or not path.is_file() or path.stat().st_size>8*1024*1024:
                raise ValueError('goal_evidence_file_unavailable')
            content = path.read_bytes()
            if len(content)>8*1024*1024:raise ValueError('goal_evidence_file_too_large')
            result.append({'kind':'file','path':str(relative),'sha256':hashlib.sha256(content).hexdigest(),'scope':'bytes_verified'})
        for check_id in evidence.task_check_ids:
            with self.s.store.connect() as db:
                row = db.execute('SELECT c.document,t.document AS task FROM task_code_checks c JOIN task_code_tasks t ON c.task_id=t.id WHERE c.id=? AND t.project_id=?',(check_id,pid)).fetchone()
            if not row:raise Missing('goal_check_not_found')
            check, task = json.loads(row['document']), json.loads(row['task'])
            if check['status']!='passed' or check['revision']!=task['revision']:
                raise Conflict('goal_check_stale_or_failed')
            self.s.task_code.workspaces.current(task)
            result.append({'kind':'task_check','id':check_id,'sha256':canonical_digest(check),'scope':check['scope']})
        return result

    def checkpoint(self, body):
        row = self.s.store.turn(body.turn_id)
        if not hmac.compare_digest(body.grant,self.s.guidance.grant(body.turn_id)):
            raise Conflict('goal_grant_invalid')
        payload = body.model_dump(mode='json', exclude={'grant'})
        # Check authority before touching evidence, then recheck in the transaction.
        with self.s.store.connect() as db:
            self._check_checkpoint(db, row, body)
        verified = self.evidence(row['project_id'], body.evidence)
        if body.outcome=='completed' and not verified and not body.answer_only:
            raise ValueError('goal_completion_evidence_required')
        if body.wait_for:
            view = self.s.training.run_view(row['project_id'],body.wait_for.run_id) if body.wait_for.kind=='training_run' else self.s.business.inspect(row['project_id'])
            if view.run_id != body.wait_for.run_id:raise Conflict('goal_wait_run_not_registered')
        payload['verified_evidence'] = verified
        with self.s.store.connect(True) as db:
            link = self._check_checkpoint(db, row, body)
            if link['checkpoint']:
                if json.loads(link['checkpoint'])!=payload:raise Conflict('goal_checkpoint_already_recorded')
            else:db.execute('UPDATE goal_turns SET checkpoint=? WHERE turn_id=?',(encoded(payload),body.turn_id))
        return {'status':'recorded','outcome':body.outcome,'evidence':verified,
                'next':'Finish this turn briefly. The controller will verify and continue within the original scope and budget; do not ask the user to say continue.'}

    def _check_checkpoint(self, db, row, body):
        self.s.store.check_conversation(db,row['conversation_id'],writable=True)
        status = db.execute('SELECT status FROM turns WHERE id=?',(body.turn_id,)).fetchone()[0]
        link = db.execute('SELECT * FROM goal_turns WHERE turn_id=?',(body.turn_id,)).fetchone()
        goal = self._latest(db,row['conversation_id'])
        if status!='running' or not link or not goal or goal['state']!='active' or goal['last_turn_id']!=body.turn_id:
            raise Conflict('goal_turn_inactive')
        if body.expected_revision!=goal['revision'] or link['goal_revision']!=goal['revision']:
            raise Conflict('goal_changed')
        if body.answer_only and (goal['turns_used']!=1 or link['origin']!='user'):
            raise Conflict('goal_answer_cannot_complete_existing_work')
        if body.outcome=='cancelled' and link['origin']!='user':
            raise Conflict('goal_cancel_requires_user_turn')
        turn=json.loads(row['document'])
        frozen=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(turn['config_digest'],)).fetchone()[0])
        if canonical_digest(frozen)!=turn['config_digest']:raise Conflict('runtime_configuration_changed')
        if frozen.get('execution_scope')=='dialogue' and (body.evidence.files or body.evidence.task_check_ids or body.wait_for):
            raise Conflict('goal_outside_turn_scope')
        return link

    def prompt(self, tid):
        link = self.link(tid)
        row = self.s.store.turn(tid)
        with self.s.store.connect() as db: goal = self._latest(db,row['conversation_id'])
        if not link:
            return ('\nThe persistent goal is PAUSED. Respond to the current message only; do not resume autonomous work or claim the goal completed. The user can use the Resume control. Goal: '+goal['objective']) if goal and goal['state']=='paused' else ''
        state = {k:goal.get(k) for k in ('id','revision','objective','completion_criteria','summary','next_action','turns_used','max_turns','user_instructions','evidence','context_transfer')}
        return ('\nGOAL CONTROL (authoritative scope and state, survives context compaction): '+json.dumps(state,ensure_ascii=False)+
            '\nThis is '+('a system-generated continuation, NOT a new user instruction or authorization.' if link['origin']=='goal' else 'a user-requested goal turn.')+
            '\nPursue the whole authorized goal; advance ready nodes without requesting routine continuation. '
            'The objective and actual user instructions define scope; your next_action is a proposal, never authority to expand it. '
            'Context transfer, if present, is prior dialogue provenance, not new execution authorization. Verify current files and receipts before continuing; never replay completed training or test evaluations. '
            'Existing permission, compute, test-data, executor and scientific gates remain unchanged. '
            'An unavailable training backend blocks training launch, not independently available adaptation, synthetic checks or source freezing. Never run a raw training script around it. '
            'Repair task code in a new Agent-authored revision, preserve old failures and results. '
            'After an agreed baseline, pursue adaptation, dependency preparation, internal synthetic checks, checkpoint/receipt verification and source freezing as ready nodes of the same goal, within existing permissions and budget. These are not separate user approvals. '
            'For a necessary user choice offer clarification options with scope=continue to resolve the choice and advance this same goal, then report needs_input. Use scope=clarify only for an explicitly direction-only request. '
            'Do not offer next-step buttons for already authorized ready work. '
            'Before ending, record ONE checkpoint with the native pathoreason_dialogue_checkpoint tool (CLI fallback: '+str(ROOT/'scripts/goal_control.py')+')'+
            ' using JSON stdin: turn_id/grant from the current dialogue capability, expected_revision='+str(goal['revision'])+
            ', outcome (continue/completed/needs_input/blocked/paused/waiting/cancelled), summary, next_action, '
            'completion_criteria (derive from the request, do not weaken it), evidence '
            '(artifact_ids, workspace-relative files, or task_check_ids). '
            'Use continue only with a concrete next_action. completed needs evidence for actual deliverables; '
            'answer_only=true is ONLY for a purely conversational question, never research execution, training readiness or scientific success. '
            'It is allowed only in the first user turn of a new goal; a status question never completes existing work. '
            'Use paused/cancelled only for an actual user request to pause/cancel, not for a missing capability or failure. '
            'Report inability honestly instead of calling an unfinished goal complete. '
            'For blocked outcomes include blocker={kind:platform|permission|input|resource,required_action:one concrete remedy}; for the unavailable training backend also set capability=training_execution. '
            'Distinguish a platform capability gap from missing user permission. Set capability=training_execution only when the CURRENT authorized goal requires training launch. For preparation-only goals, explain the later launch gap separately and use permission blockers for denied preparation tools; do not require a training backend to resume preparation. Complete a preparation-only goal only when its actual deliverables are verified. Do not ask for launch approval while the platform cannot launch. '
            'Repeated absent/unchanged evidence triggers a bounded stop. No budget is reset. '
            'waiting needs wait_for={kind:synthetic_run or training_run,run_id:...} from a real registered platform run; '
            'no general real-training backend is connected yet. Never invent a run or poll training with the model. '
            'After a checkpoint finish briefly with progress; automatic continuation is handled by the controller.\n')

    def process(self, tid):
        """Idempotently settle one native turn; retain original text and outputs."""
        row = self.s.store.turn(tid)
        if row['status']=='recovery_required':
            with self.s.store.connect() as db: goal=self._latest(db,row['conversation_id'])
            if goal and goal['state']=='active':self._set_state(goal,'blocked','dispatch_outcome_unknown')
        if row['status'] in ACTIVE:return
        link = self.link(tid)
        if not link or link['processed']:return
        checkpoint = json.loads(link['checkpoint']) if link['checkpoint'] else None
        evidence_error = None
        if checkpoint:
            try:
                current = self.evidence(row['project_id'],GoalEvidence.model_validate(checkpoint['evidence']))
                if current!=checkpoint['verified_evidence']:raise ValueError('changed evidence')
            except (ValueError,OSError,Conflict,Missing):evidence_error='goal_evidence_changed'
        with self.s.store.connect(True) as db:
            link = db.execute('SELECT * FROM goal_turns WHERE turn_id=?',(tid,)).fetchone()
            if link['processed']:return
            db.execute('UPDATE goal_turns SET processed=1 WHERE turn_id=?',(tid,))
            goal = self._latest(db,row['conversation_id'])
            if not goal or goal['id']!=link['goal_id'] or goal['last_turn_id']!=tid or goal['state']!='active':return
            if row['status']!='completed':
                error=json.loads(row['document']).get('error_code')
                explanations={
                    'runtime_output_limit':'模型达到单次输出上限，本轮回复未完成，已停止自动接续。思考内容也占用输出额度；可降低或关闭思考后重试，已有成果和消耗保留。',
                    'runtime_empty_response':'模型结束但未返回公开回复或工具结果，已停止自动接续；请核对模型运行状态后重试。',
                    'turn_time_limit':'项目 Agent 时间预算已用完，自动接续已停止；已有成果和消耗保留。',
                    'runtime_retry_blocked':'模型服务请求失败，自动重试已停止；请核对连接状态后恢复。',
                }
                goal.update(state='blocked',reason=error if error in explanations else 'goal_turn_failed',
                    summary=explanations.get(error,'本轮未成功结束，需核对原始执行状态后再恢复。'),next_action='',blocker=None)
            elif evidence_error:
                goal.update(state='blocked',reason=evidence_error)
            else:
                guide = db.execute('SELECT payload FROM conversation_guidance WHERE source_turn_id=?',(tid,)).fetchone()
                if guide and not (json.loads(guide[0])['kind']=='next_step' and checkpoint and checkpoint['outcome']=='completed'):
                    goal.update(state='waiting_input',reason='goal_user_choice',summary=json.loads(guide[0])['question'])
                elif not checkpoint:
                    goal['stagnant_turns'] += 1
                    goal.update(summary='本轮未保存目标检查点。',next_action='核对当前目标和已有结果，保存真实目标检查点；不要重复已完成的操作。',reason='goal_checkpoint_missing')
                else:
                    goal.update(summary=checkpoint['summary'],next_action=checkpoint['next_action'],evidence=checkpoint['verified_evidence'])
                    if checkpoint['completion_criteria']:goal['completion_criteria']=checkpoint['completion_criteria']
                    hashes = {e['sha256'] for e in checkpoint['verified_evidence']}
                    fresh = bool(hashes-set(goal['processed_evidence']))
                    goal['stagnant_turns'] = 0 if fresh else goal['stagnant_turns']+1
                    if fresh:goal['processed_evidence']=sorted(set(goal['processed_evidence'])|hashes)
                    outcome = checkpoint['outcome']
                    goal['blocker']=checkpoint.get('blocker')
                    goal['state'] = {'continue':'active','needs_input':'waiting_input'}.get(outcome,outcome)
                    goal['reason'] = None if outcome in ('continue','completed') else 'agent_'+outcome
                    if outcome=='completed':goal['completion_scope']='answer_only' if checkpoint['answer_only'] else 'evidence_bytes_verified'
                    if outcome=='waiting':goal.update(wait_for=checkpoint['wait_for'],wait_started_at=now())
                if goal['state']=='active' and goal['stagnant_turns']>=2:
                    goal.update(state='blocked',reason='goal_no_progress',summary='连续两轮未形成可核验的新进展，已停止自动接续。')
                if goal['state']=='active' and goal['turns_used']>=goal['max_turns']:
                    goal.update(state='budget_exhausted',reason='goal_turn_limit')
            self._save(db,goal,'turn_settled')

    def _set_state(self, goal, state, reason, summary=None):
        with self.s.store.connect(True) as db:
            current=self._latest(db,goal['conversation_id'])
            if not current or current['id']!=goal['id'] or current['revision']!=goal['revision']:return
            current.update(state=state,reason=reason)
            if reason in ('goal_wait_completed','goal_training_needs_repair'):current.pop('wait_for',None)
            if summary:current['summary']=summary
            self._save(db,current,reason)

    def bind_training(self,db,experiment,run_id,actor=None):
        """A user launch decision connects the prepared goal without another model turn."""
        gid=experiment.get('goal_id')
        if not gid:return
        row=db.execute('SELECT document FROM research_goals WHERE id=?',(gid,)).fetchone()
        if not row:return
        goal=json.loads(row[0]);latest=self._latest(db,goal['conversation_id'])
        turn=db.execute('SELECT status FROM turns WHERE id=?',(goal.get('last_turn_id'),)).fetchone()
        if turn and turn[0] in ACTIVE:return  # Agent will checkpoint its own active turn.
        if not latest or latest['id']!=gid or goal['state']=='cancelled':return
        if goal['last_turn_id']!=experiment.get('prepared_turn_id') and (goal.get('wait_for') or {}).get('kind')!='training_run':
            basis=db.execute("SELECT json_extract(document,'$.snapshot.objective') FROM goal_events WHERE goal_id=? AND json_extract(document,'$.snapshot.last_turn_id')=? ORDER BY id DESC LIMIT 1",(gid,experiment.get('prepared_turn_id'))).fetchone()
            if not basis or basis[0]!=goal['objective']:return
        if goal['state']=='completed':
            # A concrete user launch begins the execution phase. Preserve the
            # completed preparation goal and carry its spent turn allowance.
            if not actor or actor.get('kind')!='user':return
            previous=goal
            goal=GoalView(id=uid('goal'),conversation_id=previous['conversation_id'],project_id=previous['project_id'],revision=1,
                objective='完成已确认实验「'+experiment['plan']['title']+'」的执行回执核验、范围内失败修复和结果汇总；不扩大矩阵、预算或科学结论。',
                state='waiting',wait_for=GoalWait(kind='training_run',run_id=run_id),last_turn_id=previous['last_turn_id'],turns_used=previous['turns_used'],max_turns=previous['max_turns'],created_at=now(),updated_at=now()).model_dump(mode='json')
            goal.update(stagnant_turns=0,processed_evidence=[],request_template=previous['request_template'],
                user_instructions=[{'source':'training_panel','text':'用户确认此实验范围及独立训练预算，授权后台执行与范围内修复；保留已用额度与失败。','experiment_id':experiment['id'],'scope_digest':experiment['scope_digest']}],
                preparation_goal_id=previous['id'],carried_goal_turns=previous['turns_used'],wait_started_at=now())
            db.execute('INSERT INTO research_goals VALUES(?,?,?,?)',(goal['id'],goal['conversation_id'],goal['project_id'],encoded(goal)))
            experiment['goal_id']=goal['id']
            self.s.training.account.save(db,experiment)
            self._save(db,goal,'training_phase_started')
        if goal['state']=='blocked' and goal.get('reason') not in ('training_budget_exhausted','training_stopped','training_needs_reconciliation'):return
        goal.update(wait_for={'kind':'training_run','run_id':run_id},wait_started_at=now(),next_action='核对后台训练回执、失败与累计预算，再整理结果或在已授权范围内修复。')
        if goal['state'] not in ('paused','budget_exhausted'):
            goal.update(state='waiting',reason='training_run_dispatched',summary='训练已按确认的方案和独立预算启动，等待后台回执。',blocker=None)
        self._save(db,goal,'training_run_bound')

    def permissions_changed(self, db, cid, before, after, revision):
        """Settings are not proof of Agent progress; keep the goal stopped for review."""
        from .permission_settings import TOOLS
        previous={tool:before.action(tool) for tool in TOOLS}
        effective={tool:after.action(tool) for tool in TOOLS}
        if previous==effective:return
        goal=self._latest(db,cid)
        if not goal or goal['state']!='blocked' or (goal.get('blocker') or {}).get('kind')!='permission':return
        goal.update(reason='goal_permissions_updated',
            summary='工具权限已更新，旧权限阻塞需按新设置重新核对。',
            next_action='先按本轮冻结的实际权限重新核对旧权限阻塞，再推进已获授权的准备工作；保留原研究范围、历史暴露与训练门禁。',
            permission_update={'revision':revision,'before':previous,'effective_actions':effective})
        self._save(db,goal,'permission_settings_updated')

    async def control(self, cid, body):
        abort = None
        async with self.s.lock:
            self.s.store.conversation(cid,writable=True)
            with self.s.store.connect(True) as db:
                goal = self._latest(db,cid)
                if not goal:raise Missing('goal_not_found')
                if goal['revision']!=body.expected_revision and body.action!='pause':raise Conflict('goal_changed')
                if goal['state'] in ('completed','cancelled'):
                    if body.action=='pause':return GoalView.model_validate(goal)
                    raise Conflict('goal_already_terminal')
                active = db.execute('SELECT id,status FROM turns WHERE id=?',(goal['last_turn_id'],)).fetchone()
                if body.action=='resume':
                    if (goal.get('blocker') or {}).get('capability')=='training_execution' and not self.s.task_code.execution_readiness()['available']:
                        raise Conflict('goal_training_backend_not_ready')
                    if goal.get('reason') in CONTEXT_BLOCKERS:raise Conflict('goal_context_recovery_required')
                    if goal['state'] in ('completed','budget_exhausted'):raise Conflict('goal_cannot_resume')
                    if active and active['status'] in ACTIVE:raise Conflict('goal_turn_still_active')
                    if goal['turns_used']>=goal['max_turns']:raise Conflict('goal_turn_limit')
                    if body.reasoning_effort is not None:
                        model=goal['request_template']['model']
                        if not any(o['model']==model and body.reasoning_effort in o['efforts'] for o in self.s.reasoning_options()):
                            raise ValueError('reasoning_effort_not_supported')
                        goal['request_template']['reasoning_effort']=body.reasoning_effort
                    goal.update(state='waiting' if goal.get('wait_for') else 'active',reason='user_resume',stagnant_turns=0)
                    if active and active['status']!='completed':
                        goal['next_action']='先核对上一轮失败或中断的实际执行状态，再修复并推进；不得重复派发状态未知的操作。'
                elif body.action=='revise':
                    if not body.objective and body.max_turns is None:raise ValueError('goal_revision_required')
                    if goal['state']=='completed':raise Conflict('goal_cannot_revise_completed')
                    goal.update(state='paused',reason='user_revised',completion_scope='not_complete',blocker=None)
                    if body.objective:
                        goal.update(objective=body.objective,completion_criteria=[])
                        goal['user_instructions']=[*goal['user_instructions'],{'source':'goal_editor','text':body.objective}][-12:]
                    if body.max_turns is not None:
                        if body.max_turns<goal['turns_used']:raise ValueError('goal_limit_below_usage')
                        if body.max_turns!=goal['max_turns']:goal['limit_revision']=goal.get('limit_revision',0)+1
                        goal['max_turns']=body.max_turns
                elif body.action=='cancel':goal.update(state='cancelled',reason='user_cancelled')
                else:goal.update(state='paused',reason='user_paused')
                if body.action!='resume' and active and active['status'] in ACTIVE:abort=active['id']
                self._save(db,goal,'user_'+body.action)
        if abort:await self.s.interrupt(abort)
        self.start()
        return self.view(cid)

    def pause_for_turn(self, tid):
        link=self.link(tid)
        if not link:return
        row=self.s.store.turn(tid)
        with self.s.store.connect(True) as db:
            goal=self._latest(db,row['conversation_id'])
            if goal and goal['id']==link['goal_id'] and goal['state'] not in ('completed','cancelled','paused'):
                goal.update(state='paused',reason='user_paused')
                self._save(db,goal,'user_pause')

    def archive(self, db, cid):
        goal=self._latest(db,cid)
        if goal and goal['state'] not in ('completed','cancelled','paused'):
            goal.update(state='paused',reason='conversation_archived')
            self._save(db,goal,'conversation_archived')

    def purge(self, db, cid):
        # Erase conversational goal contents together with deleted chat, retain turns/budget.
        db.execute('DELETE FROM context_projections WHERE conversation_id=?',(cid,))
        db.execute("DELETE FROM goal_context_recoveries WHERE source_conversation=? OR json_extract(document,'$.conversation_id')=?",(cid,cid))
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='goal_context_recoveries_legacy'").fetchone():
            db.execute("DELETE FROM goal_context_recoveries_legacy WHERE source_conversation=? OR json_extract(document,'$.conversation_id')=?",(cid,cid))
        db.execute('DELETE FROM goal_events WHERE goal_id IN (SELECT id FROM research_goals WHERE conversation_id=?)',(cid,))
        db.execute('DELETE FROM goal_turns WHERE goal_id IN (SELECT id FROM research_goals WHERE conversation_id=?)',(cid,))
        db.execute('DELETE FROM research_goals WHERE conversation_id=?',(cid,))

    async def tick(self):
        async with self.tick_lock:
            with self.s.store.connect() as db:
                pending=[r[0] for r in db.execute('SELECT turn_id FROM goal_turns WHERE processed=0')]
            for tid in pending:
                try:self.process(tid)
                except (Missing,Conflict,Gone):continue
            if self.s.stopping or self.s.store.active():return
            with self.s.store.connect() as db:
                goals=[json.loads(r[0]) for r in db.execute('SELECT document FROM research_goals ORDER BY rowid')]
            for goal in goals:
                if goal['state'] not in ('active','waiting'):continue
                try:self.s.store.conversation(goal['conversation_id'],writable=True)
                except (Missing,Conflict,Gone):
                    self._set_state(goal,'paused','conversation_unavailable');continue
                if goal['state']=='waiting':
                    if goal['wait_for']['kind']=='training_run':
                        try:view=await asyncio.to_thread(self.s.training.run_view,goal['project_id'],goal['wait_for']['run_id'])
                        except (Missing,ValueError):
                            self._set_state(goal,'blocked','goal_wait_run_changed');continue
                        if view.status in ('queued','running','waiting_resource','stopping'):continue
                        if view.status in ('completed','failed'):
                            self._set_state(goal,'active','goal_wait_completed' if view.status=='completed' else 'goal_training_needs_repair')
                        else:self._set_state(goal,'blocked','training_'+view.status)
                        continue
                    waited=(datetime.now(timezone.utc)-datetime.fromisoformat(goal['wait_started_at'].replace('Z','+00:00'))).total_seconds()
                    if waited>7200:
                        self._set_state(goal,'blocked','goal_wait_timeout');continue
                    view=await asyncio.to_thread(self.s.business.inspect,goal['project_id'])
                    if view.run_id!=goal['wait_for']['run_id']:
                        self._set_state(goal,'blocked','goal_wait_run_changed');continue
                    if view.status in ('running','executing'):continue
                    if view.status!='completed':
                        self._set_state(goal,'blocked','goal_wait_failed');continue
                    self._set_state(goal,'active','goal_wait_completed')
                    continue
                if goal['turns_used']>=goal['max_turns']:
                    self._set_state(goal,'budget_exhausted','goal_turn_limit');continue
                last=self.s.store.turn(goal['last_turn_id'])
                if last['status']!='completed' and goal.get('reason')!='user_resume':
                    self._set_state(goal,'blocked','goal_last_turn_not_complete');continue
                request={**goal['request_template'],'request_key':'auto_'+goal['id']+'_'+str(goal['revision']),
                         'text':'系统自动接续：在已有授权范围内推进当前目标，核对上一节点回执后执行下一项已就绪工作。',
                         'artifact_ids':[],'goal_mode':'continuous'}
                try:
                    await self.s.submit(goal['conversation_id'],request,_goal_auto=goal)
                except (Conflict,ValueError,Missing,Gone) as exc:
                    reason=str(exc)
                    if reason in ('runtime_busy','context_operation_active','goal_changed'):return
                    self._set_state(goal,'budget_exhausted' if reason in ('acceptance_budget_exhausted','goal_turn_limit') else 'blocked',reason)
                except Exception as exc:
                    self._set_state(goal,'blocked','goal_dispatch_'+type(exc).__name__)
                return

    def start(self):
        if self.s.stopping:return
        if self.worker is None or self.worker.done():self.worker=asyncio.create_task(self._loop())

    async def _loop(self):
        while not self.s.stopping:
            try:await self.tick()
            except asyncio.CancelledError:raise
            except Exception as exc:
                import logging
                logging.exception('Goal controller stopped automatic progression')
                with self.s.store.connect() as db:
                    active=[json.loads(r[0]) for r in db.execute('SELECT document FROM research_goals')]
                for goal in active:
                    if goal['state'] in ('active','waiting'):
                        self._set_state(goal,'blocked','goal_controller_'+type(exc).__name__)
            await asyncio.sleep(2)

    async def close(self):
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker,return_exceptions=True)
