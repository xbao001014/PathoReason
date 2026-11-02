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


class GoalEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artifact_ids: list[Identifier] = Field(default_factory=list, max_length=10)
    files: list[str] = Field(default_factory=list, max_length=8)
    task_check_ids: list[Identifier] = Field(default_factory=list, max_length=8)


class GoalWait(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['synthetic_run']
    run_id: Identifier


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

    @model_validator(mode='after')
    def shape(self):
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


class GoalView(BaseModel):
    schema_version: Literal['pathoreason.goal/1'] = 'pathoreason.goal/1'
    id: str
    conversation_id: str
    project_id: str
    revision: int
    objective: str
    state: Literal['active','paused','blocked','waiting_input','waiting','completed','budget_exhausted','cancelled']
    summary: str = ''
    next_action: str = ''
    reason: str | None = None
    completion_criteria: list[str] = Field(default_factory=list)
    turns_used: int = 0
    max_turns: int = 8
    last_turn_id: str
    evidence: list[dict] = Field(default_factory=list)
    completion_scope: Literal['not_complete','answer_only','evidence_bytes_verified'] = 'not_complete'
    scientific_approval: Literal[False] = False
    created_at: str
    updated_at: str


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
            ''')

    def _latest(self, db, cid):
        row = db.execute('SELECT document FROM research_goals WHERE conversation_id=? ORDER BY rowid DESC LIMIT 1', (cid,)).fetchone()
        return json.loads(row[0]) if row else None

    def view(self, cid):
        self.s.store.conversation(cid)
        with self.s.store.connect() as db: goal = self._latest(db, cid)
        return GoalView.model_validate(goal) if goal else None

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
            view = self.s.business.inspect(row['project_id'])
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
        state = {k:goal.get(k) for k in ('id','revision','objective','completion_criteria','summary','next_action','turns_used','max_turns','user_instructions','evidence')}
        return ('\nGOAL CONTROL (authoritative scope and state, survives context compaction): '+json.dumps(state,ensure_ascii=False)+
            '\nThis is '+('a system-generated continuation, NOT a new user instruction or authorization.' if link['origin']=='goal' else 'a user-requested goal turn.')+
            '\nPursue the whole authorized goal; advance ready nodes without requesting routine continuation. '
            'The objective and actual user instructions define scope; your next_action is a proposal, never authority to expand it. '
            'Existing permission, compute, test-data, executor and scientific gates remain unchanged. '
            'For an unavailable execution backend report blocked; do not run a raw script around it. '
            'Repair task code in a new Agent-authored revision, preserve old failures and results. '
            'For a necessary user choice offer the existing dialogue choices and report needs_input. '
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
            'Repeated absent/unchanged evidence triggers a bounded stop. No budget is reset. '
            'waiting needs wait_for={kind:synthetic_run,run_id:...} from a real registered platform run; '
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
                goal.update(state='blocked',reason='goal_turn_failed',summary='本轮未成功结束，需核对原始执行状态后再恢复。')
            elif evidence_error:
                goal.update(state='blocked',reason=evidence_error)
            else:
                guide = db.execute('SELECT payload FROM conversation_guidance WHERE source_turn_id=?',(tid,)).fetchone()
                if guide:
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
            if reason=='goal_wait_completed':current.pop('wait_for',None)
            if summary:current['summary']=summary
            self._save(db,current,reason)

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
                    if goal['state'] in ('completed','budget_exhausted'):raise Conflict('goal_cannot_resume')
                    if active and active['status'] in ACTIVE:raise Conflict('goal_turn_still_active')
                    if goal['turns_used']>=goal['max_turns']:raise Conflict('goal_turn_limit')
                    goal.update(state='waiting' if goal.get('wait_for') else 'active',reason='user_resume',stagnant_turns=0)
                    if active and active['status']!='completed':
                        goal['next_action']='先核对上一轮失败或中断的实际执行状态，再修复并推进；不得重复派发状态未知的操作。'
                elif body.action=='revise':
                    if not body.objective and body.max_turns is None:raise ValueError('goal_revision_required')
                    if goal['state']=='completed':raise Conflict('goal_cannot_revise_completed')
                    goal.update(state='paused',reason='user_revised',completion_scope='not_complete')
                    if body.objective:
                        goal.update(objective=body.objective,completion_criteria=[])
                        goal['user_instructions']=[*goal['user_instructions'],{'source':'goal_editor','text':body.objective}][-12:]
                    if body.max_turns is not None:
                        if body.max_turns<goal['turns_used']:raise ValueError('goal_limit_below_usage')
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
