"""Agent preparation plus one user-owned launch/budget decision per scope."""
import hashlib,hmac,json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
from .contracts import canonical_digest
from .persistence import ACTIVE,Conflict,Missing
from .settings import ROOT
from .training_account import TrainingAccount
from .training_contracts import TrainingView,TrainingBudget,TrainingPlan
from pydantic import ValidationError
from .training_files import canonical,digest,file_digest,freeze_environment,manifest,relative,atomic,verify_tree,verify_requirements
from .training_sandbox import availability


class Training:
    def __init__(self,service):
        self.s=service;self.account=TrainingAccount(service.store.path)
        self.root=canonical(service.data/'training');self.root.mkdir(exist_ok=True)
        (self.root/'gpu-locks').mkdir(exist_ok=True)
    def readiness(self):return availability()
    def list(self,pid):
        self.s.store.project(pid)
        with self.account.db() as db:ids=[x[0] for x in db.execute('SELECT id FROM training_experiments WHERE project_id=? ORDER BY rowid DESC',(pid,))]
        return [self.view(eid,pid) for eid in ids]
    def view(self,eid,pid=None):
        with self.account.db() as db:self.account.get(db,eid,pid)
        self.account.reconcile(eid)
        raw=self.account.view(eid,pid)
        ready=True
        if raw.get('prepared_turn_id'):
            ready=self.s.store.turn(raw['prepared_turn_id'])['status'] not in ACTIVE
        return TrainingView.model_validate({**{k:v for k,v in raw.items() if k in TrainingView.model_fields},'approval_ready':ready})
    def run_view(self,pid,run_id):
        for v in self.list(pid):
            if v.run_id==run_id:return v
        raise Missing('training_run_not_found')
    def _authority(self,body):
        row=self.s.store.turn(body.turn_id);self.s.store.conversation(row['conversation_id'],writable=True)
        if row['status']!='running' or not hmac.compare_digest(body.grant,self.s.guidance.grant(body.turn_id)):raise Conflict('training_turn_authority_required')
        if not self.s.formal.record(row['project_id']):raise Conflict('formal_study_required')
        turn=json.loads(row['document'])
        with self.s.store.connect() as db:frozen=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(turn['config_digest'],)).fetchone()[0])
        if canonical_digest(frozen)!=turn['config_digest']:raise Conflict('runtime_configuration_changed')
        if frozen.get('execution_scope')=='dialogue' or (frozen.get('execution_scope')=='inspection' and body.operation not in ('list','inspect')):raise Conflict('training_outside_turn_scope')
        with self.s.store.connect() as db:
            context=db.execute('SELECT document FROM turn_guidance_context WHERE turn_id=?',(body.turn_id,)).fetchone()
        if context:
            context=json.loads(context[0]);option=next((x for x in context['proposal']['options'] if x['id']==context.get('selected_option_id')),None)
            scope=option['scope'] if option else None
            if scope=='clarify' or (scope=='inspect' and body.operation not in ('list','inspect')):raise Conflict('training_outside_turn_scope')
        return row
    def receipt(self,view,full=False):
        value=view.model_dump()
        subjects={f.subject_id for f in view.plan.inputs if f.role=='sealed'}
        exposure={}
        with self.s.store.connect() as db:
            for subject in sorted(subjects):
                row=db.execute('SELECT document FROM training_exposure WHERE project_id=? AND subject_id=?',(view.project_id,subject)).fetchone()
                exposure[subject]=json.loads(row[0])['count'] if row else None
        if full:return {**value,'test_exposure':exposure}
        known=[n for n in exposure.values() if n is not None]
        value['test_exposure_summary']={'subjects':len(subjects),'unknown_subjects':sum(n is None for n in exposure.values()),'minimum':min(known) if known else None,'maximum':max(known) if known else None}
        plan=value.pop('plan');attempts=value.pop('attempts');events=value.pop('events')
        value.update(plan_summary={k:plan[k] for k in ('title','task_id','snapshot_id','environment_id','protocol','evaluation','gpu_uuid','memory_gib','proposed_budget')},
            input_count=len(plan['inputs']),fit_units=sum(u['phase']=='fit' for u in plan['units']),evaluation_units=sum(u['phase']=='evaluate' for u in plan['units']),
            unit_count=len(plan['units']),attempt_count=len(attempts),recent_attempts=[{**{k:v for k,v in a.items() if k!='files'},'output_count':len(a.get('files',{}))} for a in attempts[-3:]],recent_events=events[:3],
            detail_hint='inspect with include_plan=true returns the full registered plan; prepare accepts a project-local plan_path without embedding the plan or saving a grant in that file.')
        return value
    def load_plan(self,pid,body):
        if not body.plan_path:return body
        if body.operation!='prepare' or body.plan is not None:raise ValueError('training_use_plan_or_plan_path')
        path=canonical(body.plan_path)
        if not path.is_relative_to(self.s.data/'projects'/pid):raise ValueError('training_plan_file_outside_project')
        if path.stat().st_size>32*1024*1024:raise ValueError('training_plan_file_too_large')
        before=file_digest(path)
        try:plan=TrainingPlan.model_validate(json.loads(path.read_bytes()))
        except (ValidationError,ValueError) as exc:
            fields=','.join('.'.join(map(str,x['loc'])) for x in exc.errors(include_input=False,include_context=False)[:8]) if isinstance(exc,ValidationError) else 'json'
            raise ValueError('training_plan_file_invalid:'+fields) from None
        if file_digest(path)!=before:raise Conflict('training_plan_file_changed')
        return body.model_copy(update={'plan':plan,'plan_path':None})
    def call(self,body):
        row=self._authority(body);pid=row['project_id'];actor={'kind':'agent','turn_id':row['id'],'conversation_id':row['conversation_id']}
        body=self.load_plan(pid,body)
        if body.operation=='list':
            with self.account.db() as db:envs=[{'id':x[0],'runtime':json.loads(x[1])['binding']['runtime']} for x in db.execute('SELECT id,document FROM training_environments WHERE project_id=?',(pid,))]
            return {'experiments':[self.receipt(v,body.include_plan) for v in self.list(pid)],'environments':envs,'runtime_catalog':self.python_catalog(),'readiness':self.readiness()}
        if body.operation=='inspect':return self.receipt(self.view(body.experiment_id,pid),body.include_plan)
        if not body.idempotency_key:raise ValueError('training_idempotency_key_required')
        key='agent:'+body.idempotency_key;signature=digest(body.model_dump(exclude={'grant','turn_id','plan_path','include_plan'}))
        with self.account.db() as db:
            old=db.execute('SELECT digest,result FROM training_requests WHERE project_id=? AND key=?',(pid,key)).fetchone()
            if old:
                if old[0]!=signature:raise Conflict('training_request_conflict')
                if old[1] is None:raise Conflict('training_operation_pending_inspect_before_retry')
                previous=json.loads(old[1])
                if not body.include_plan and 'plan' in previous and 'attempts' in previous:previous=self.receipt(TrainingView.model_validate({k:v for k,v in previous.items() if k in TrainingView.model_fields}))
                return previous
            db.execute('INSERT INTO training_requests VALUES(?,?,?,NULL)',(pid,key,signature))
        try:
            if body.operation=='environment':
                if not body.python:raise ValueError('training_python_required')
                result=freeze_environment(self.root/'environments',body.python,body.extra_paths,self.python_catalog(),self.s.data/'projects'/pid)
                self._authority(body)  # A stopped/expired turn cannot register a late result.
                with self.account.db() as db:
                    # Same immutable bytes can be registered independently by projects.
                    db.execute('INSERT OR IGNORE INTO training_environments VALUES(?,?,?)',(result['id'],pid,json.dumps(result)))
                result={'environment_id':result['id'],'runtime':result['binding']['runtime'],'scope':'frozen_python_environment'}
            elif body.operation=='prepare':result=self.receipt(self.prepare(pid,row['conversation_id'],body,actor),body.include_plan)
            else:
                v=self.view(body.experiment_id,pid)
                if body.expected_revision!=v.revision:raise Conflict('training_revision_conflict')
                if body.operation=='stop':
                    self._stop(pid,v.id,body.expected_revision,'stopping',actor);result=self.receipt(self.view(v.id,pid),body.include_plan)
                else:
                    if not v.authorized:raise Conflict('training_user_budget_and_launch_decision_required')
                    if v.status in ('queued','running','waiting_resource','stopping'):result=self.receipt(v,body.include_plan)
                    elif v.status in ('stopped','cancelled','budget_exhausted','needs_reconciliation'):raise Conflict('training_user_resume_required')
                    else:result=self.receipt(self.launch(v.id,pid,actor,body.expected_revision),body.include_plan)
        except Exception as exc:
            with self.account.db() as db:db.execute('UPDATE training_requests SET result=? WHERE project_id=? AND key=?',(json.dumps({'status':'failed','error':str(exc)}),pid,key))
            raise
        with self.account.db() as db:db.execute('UPDATE training_requests SET result=? WHERE project_id=? AND key=?',(json.dumps(result),pid,key))
        return result
    def _actor_running(self,db,actor):
        if actor.get('kind')=='agent':
            turn=db.execute('SELECT status FROM turns WHERE id=?',(actor.get('turn_id'),)).fetchone()
            if not turn or turn[0]!='running':raise Conflict('training_turn_authority_required')
    def python_catalog(self):
        candidates=[str(ROOT/'.venv/bin/python'),str(Path(self.s.config.get('legacy_root','/nonexistent'))/'.venv/bin/python'),*self.s.config.get('training_python_catalog',[])]
        return [p for p in dict.fromkeys(candidates) if Path(p).is_file()]
    def prepare(self,pid,cid,body,actor):
        if body.plan is None:raise ValueError('training_plan_required')
        plan=body.plan.model_dump();task=self.s.task_code.workspaces.get(pid,plan['task_id'])
        snapshot=self.s.task_code.workspaces.verify_snapshot(task,plan['snapshot_id'])
        with self.account.db() as db:
            row=db.execute('SELECT document FROM training_environments WHERE id=? AND project_id=?',(plan['environment_id'],pid)).fetchone()
            if not row:raise ValueError('training_environment_not_registered')
            environment=json.loads(row[0])
        verify_tree(Path(environment['path'])/'runtime',environment['binding']['files'])
        verify_requirements(Path(snapshot['path'])/'code',environment['binding'])
        allowed=[self.s.data/'projects'/pid,self.s.data/'studies'/pid,*[Path(p) for p in self.s.config.get('training_input_roots',[])]]
        for f in plan['inputs']:
            p=canonical(f['path'])
            if not any(p.is_relative_to(root) for root in allowed):raise ValueError('training_input_outside_project')
            if file_digest(p)!=f['sha256']:raise ValueError('training_input_digest_changed')
        for unit in plan['units']:
            entry=relative(unit['entrypoint'])
            if not entry.endswith('.py') or entry not in snapshot['code']['files']:raise ValueError('training_entrypoint_not_in_snapshot')
            for name in unit['output_files']:relative(name)
            if any(len(arg)>4096 or '\x00' in arg for arg in unit['args']):raise ValueError('training_argument_invalid')
        # Scientific scope is stable across implementation repairs. Any dataset,
        # matrix, protocol, resource or explicit parameter change needs a new review.
        scope={k:plan[k] for k in ['task_id','protocol','evaluation','inputs','gpu_uuid','memory_gib']}
        scope['units']=[{k:u[k] for k in ['id','label','phase','input_ids','parameters','args','output_files','depends_on']} for u in plan['units']]
        scope_id=digest(scope)
        link=self.s.goals.link(actor['turn_id']) if actor.get('turn_id') else None
        with self.account.db() as db:
            self._actor_running(db,actor)
            previous_inputs={}
            if body.experiment_id:
                d=self.account.get(db,body.experiment_id,pid)
                previous_inputs={(f['id'],f['sha256'],f['subject_id'],f['role']):f['prior_test_exposures'] for f in d['plan']['inputs']}
                if d['revision']!=body.expected_revision:raise Conflict('training_revision_conflict')
                if d['status'] in ('queued','running','waiting_resource','stopping','completed','cancelled'):raise Conflict('training_plan_not_editable')
                if d['scope_digest']!=scope_id:d.update(authorized=False,status='draft')
                else:d['status']='ready' if d['authorized'] else 'draft'
                d.update(revision=d['revision']+1,plan=plan,plan_digest=digest(plan),scope_digest=scope_id,error=None)
                self.account.save(db,d)
            else:
                eid='exp_'+uuid.uuid4().hex
                d={'id':eid,'project_id':pid,'conversation_id':cid,'revision':1,'plan':plan,'plan_digest':digest(plan),'scope_digest':scope_id,'status':'draft','authorized':False,'budget':None,'run_id':None,'error':None,'created_at':time.time()}
                db.execute('INSERT INTO training_experiments VALUES(?,?,?)',(eid,pid,json.dumps(d)))
            if actor.get('turn_id'):
                d['prepared_turn_id']=actor['turn_id']
                if link:d['goal_id']=link['goal_id']
                self.account.save(db,d)
            # Never reset prior exposure when a new manifest or experiment appears.
            for f in plan['inputs']:
                identity=db.execute('SELECT subject_id FROM training_input_registry WHERE project_id=? AND sha256=?',(pid,f['sha256'])).fetchone()
                if identity and identity[0]!=f['subject_id']:raise Conflict('training_input_subject_identity_changed')
                db.execute('INSERT OR IGNORE INTO training_input_registry VALUES(?,?,?)',(pid,f['sha256'],f['subject_id']))
                row=db.execute('SELECT document FROM training_exposure WHERE project_id=? AND subject_id=?',(pid,f['subject_id'])).fetchone()
                previous=json.loads(row[0]) if row else None
                if previous:
                    if previous.get('sealed') and f['role']=='development':raise Conflict('training_subject_previously_sealed_requires_protocol_review')
                    count=previous['count'];incoming=f['prior_test_exposures']
                    identity=(f['id'],f['sha256'],f['subject_id'],f['role'])
                    same_baseline=identity in previous_inputs and incoming==previous_inputs[identity]
                    # Repairing this experiment keeps its original declaration;
                    # live exposures from its attempts are never overwritten.
                    if not same_baseline and ((count is None and incoming is not None) or (count is not None and incoming is not None and incoming<count)):raise Conflict('training_test_exposure_cannot_be_reset')
                    previous['sealed']=previous.get('sealed',False) or f['role']=='sealed'
                    if incoming is None or (count is not None and incoming>count):previous['count']=incoming
                    db.execute('UPDATE training_exposure SET document=? WHERE project_id=? AND subject_id=?',(json.dumps(previous),pid,f['subject_id']))
                else:
                    db.execute('INSERT INTO training_exposure VALUES(?,?,?)',(pid,f['subject_id'],json.dumps({'count':f['prior_test_exposures'],'sealed':f['role']=='sealed','attempts':[]})))
            db.execute('INSERT INTO training_plan_revisions VALUES(?,?,?)',(d['id'],d['revision'],json.dumps({'plan':plan,'actor':actor,'at':time.time()})))
            self.account.event(db,d['id'],'plan_prepared',actor=actor,plan_digest=d['plan_digest'],scope_digest=scope_id,revision=d['revision'])
        return self.view(d['id'],pid)
    def decide(self,cid,eid,body):
        conv=self.s.store.conversation(cid,writable=True);self.s.formal.mode(cid);pid=conv['project_id'];actor={'kind':'user','conversation_id':cid}
        if body.action in ('authorize','resume'):
            if not self.view(eid,pid).approval_ready:raise Conflict('training_preparation_turn_active')
            source=self.account.view(eid).get('prepared_turn_id')
            if source:self.s.goals.process(source)
        key='user:'+body.request_key;sig=digest({'experiment_id':eid,**body.model_dump()})
        with self.account.db() as db:
            old=db.execute('SELECT digest,result FROM training_requests WHERE project_id=? AND key=?',(pid,key)).fetchone()
            if old:
                if old[0]!=sig:raise Conflict('training_request_conflict')
                raw=self.account.get(db,eid,pid);wall,gpu=self.account.usage(db,eid)
                return TrainingView.model_validate({**{k:v for k,v in raw.items() if k in TrainingView.model_fields},'used_wall_seconds':wall,'used_gpu_seconds':gpu,'attempts':self.account.attempts(db,eid),'events':[]})
            d=self.account.get(db,eid,pid)
            if body.expected_revision!=d['revision']:raise Conflict('training_revision_conflict')
            if body.action in ('authorize','budget'):
                if body.budget is None:raise ValueError('training_budget_required')
                b=body.budget.model_dump();wall,gpu=self.account.usage(db,eid)
                if b['max_wall_seconds']<wall or b['max_gpu_seconds']<gpu:raise ValueError('training_budget_below_consumption')
                attempts=self.account.attempts(db,eid)
                if any(sum(x['unit_id']==a['unit_id'] for x in attempts)>b['max_attempts_per_unit'] for a in attempts):raise ValueError('training_attempt_limit_below_usage')
                if d['plan']['gpu_uuid'] and b['max_gpu_seconds']<=0:raise ValueError('training_gpu_budget_required')
                before=d['budget'];d['budget']=b
                self.account.event(db,eid,'budget_changed',actor=actor,before=before,after=b,used_wall_seconds=wall,used_gpu_seconds=gpu)
            if body.action=='authorize':
                if d['status'] not in ('draft','ready','failed'):raise Conflict('training_not_awaiting_approval')
                d.update(authorized=True,approved_scope=d['scope_digest'],status='ready')
            elif body.action=='stop':d['status']='stopping' if d['status'] in ('running','waiting_resource') else 'stopped'
            elif body.action=='cancel':d.update(status='cancelled',authorized=False)
            elif body.action=='resume':
                if not d['authorized'] or d['status'] not in ('stopped','failed','budget_exhausted','needs_reconciliation','ready'):raise Conflict('training_not_resumable')
                if any(a['status']=='unknown' for a in self.account.attempts(db,eid)) and not body.acknowledge_unknown:raise Conflict('training_unknown_attempt_acknowledgement_required')
                d['status']='ready'
            d['revision']+=1;self.account.save(db,d);self.account.event(db,eid,'user_'+body.action,actor=actor,revision=d['revision'],scope_digest=d['scope_digest'])
            db.execute('INSERT INTO training_requests VALUES(?,?,?,?)',(pid,key,sig,json.dumps({'accepted':True})))
        if body.action in ('authorize','resume'):return self.launch(eid,pid,actor,d['revision'])
        return self.view(eid,pid)
    def _pending_decision(self,eid,pid):raise Conflict('training_decision_pending')
    def _stop(self,pid,eid,revision,status,actor):
        with self.account.db() as db:
            d=self.account.get(db,eid,pid)
            if d['revision']!=revision:raise Conflict('training_revision_conflict')
            d.update(status=status if d['status'] in ('running','waiting_resource') else 'stopped',revision=d['revision']+1);self.account.save(db,d);self.account.event(db,eid,'stop_requested',actor=actor)
    def launch(self,eid,pid,actor,revision):
        if not self.readiness()['available']:raise Conflict('training_backend_unavailable')
        with self.account.db() as db:
            d=self.account.get(db,eid,pid)
            if d['revision']!=revision:raise Conflict('training_revision_conflict')
            if not d['authorized'] or d.get('approved_scope')!=d['scope_digest'] or not d['budget']:raise Conflict('training_user_budget_and_launch_decision_required')
            if d['status'] not in ('ready','failed'):raise Conflict('training_not_launchable')
            wall,gpu=self.account.usage(db,eid)
            if wall>=d['budget']['max_wall_seconds'] or (d['plan']['gpu_uuid'] and gpu>=d['budget']['max_gpu_seconds']):raise Conflict('training_budget_exhausted')
            row=db.execute('SELECT document FROM training_environments WHERE id=? AND project_id=?',(d['plan']['environment_id'],pid)).fetchone();environment=json.loads(row[0])
        task=self.s.task_code.workspaces.get(pid,d['plan']['task_id']);snapshot=self.s.task_code.workspaces.verify_snapshot(task,d['plan']['snapshot_id'])
        run_id='train_'+uuid.uuid4().hex;run=canonical(self.root/'runs'/run_id);run.mkdir(parents=True)
        controller=run/'controller'/'pathoreason';controller.mkdir(parents=True);(controller/'__init__.py').write_text('')
        for name in ['training_worker.py','training_account.py','training_files.py','training_sandbox.py','training_restrictions.py']:shutil.copy2(ROOT/'src/pathoreason'/name,controller/name)
        request={'experiment_id':eid,'run_id':run_id,'database':str(self.s.store.path),'plan':d['plan'],'budget_at_start':d['budget'],'gpu_locks':str(self.root/'gpu-locks'),'snapshot':snapshot,'environment':environment,'source_files':{k:{q:v[q] for q in ['sha256','size']} for k,v in snapshot['code']['files'].items()},'controller_files':manifest(controller)}
        atomic(run/'request.json',request)
        with self.account.db() as db:
            self._actor_running(db,actor)
            current=self.account.get(db,eid,pid)
            if current['revision']!=revision or current['status']!=d['status']:raise Conflict('training_revision_conflict')
            current.update(status='queued',run_id=run_id,revision=revision+1,controller=None,queued_at=time.time());self.account.save(db,current);self.s.goals.bind_training(db,current,run_id,actor);self.account.event(db,eid,'run_queued',actor=actor,run_id=run_id,plan_digest=d['plan_digest'],controller=request['controller_files'])
        command=[sys.executable,'-I','-B','-c','import sys;sys.path.insert(0,'+repr(str(run/'controller'))+');from pathoreason.training_worker import main;main('+repr(str(run))+')']
        try:
            with open(run/'supervisor.log','xb') as log:subprocess.Popen(command,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,close_fds=True,start_new_session=True)
        except Exception as exc:self.account.state(eid,run_id,'failed','training_spawn_failed:'+type(exc).__name__);raise
        return self.view(eid,pid)
    def prompt(self,pid):
        rows=[{'id':v.id,'title':v.plan.title,'status':v.status,'revision':v.revision,'run_id':v.run_id,'authorized':v.authorized,'budget':v.budget.model_dump() if v.budget else None,'used_wall_seconds':v.used_wall_seconds,'used_gpu_seconds':v.used_gpu_seconds,'error':v.error} for v in self.list(pid)]
        return '\nTraining experiments (independent of Agent allowance): '+json.dumps(rows,ensure_ascii=False)+'\nUse scripts/training.py and skills/training-execution/SKILL.md for the public executor. Prepare internally; the user reviews one concrete plan plus training budget in the Training panel. Never treat permission auto-approval or compute.json as training authority. A background run continues without model calls; checkpoint waiting with kind=training_run and the registered run_id, then stop polling.\n'
