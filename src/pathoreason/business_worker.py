"""Fixed legacy bridge. Invoked only with the legacy Python, never with shell input.

All writes use PathoReason's independent storage profile. The existing repair
controller and complete-matrix controller remain the execution authorities.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
CFG = json.loads((ROOT/'config/pathoreason.local.json').read_text())
LEGACY = Path(CFG['legacy_root'])
DATA = Path(CFG['data_root'])
sys.path.insert(0, str(LEGACY/'packages/core'))
os.environ['AUTORESEARCH_COMPUTE_CONFIG'] = str(ROOT/'config/p2-compute.local.json')
from experiment_agent.workbench.contracts import Capability, RepairConflict, digest
from experiment_agent.workbench.controller import RepairController
from experiment_agent.workbench.registry import RepairRegistry
from experiment_agent.workbench.journal import RepairJournal
from experiment_agent.performance_loop.development_mil import _write
from experiment_agent.storage_paths import validate_output

OPERATIONS = {'intake':'任务接入','plan':'生成方案','revise':'反馈修订','execute':'执行完整矩阵','recover':'恢复原任务','stop':'停止任务'}

def check_source():
    manifest=json.loads((ROOT/'config/p2-legacy-source.json').read_text())
    for rel, expected in manifest.items():
        path=LEGACY/rel
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise RepairConflict('原业务源码版本已变化，需重新验证适配器')

def task_root(pid):
    if not re.fullmatch(r'prj_[A-Za-z0-9_-]{1,80}',pid):raise ValueError('Invalid project identity')
    path=DATA/'research'/pid
    validate_output(path)
    path.mkdir(parents=True, exist_ok=True)
    return path

def document(root):
    path=root/'task.json'
    return json.loads(path.read_text()) if path.exists() else {'project_id':root.name,'status':'not_started','revision_number':0,'scope':'synthetic','run_id':None,'plan':None,'history':[]}

def save(root, doc, event, turn, action):
    doc['revision_number']+=1
    doc['updated_at']=time.time()
    doc['history'].append({'seq':doc['revision_number'],'scope':'domain','producer':'legacy_adapter',
        'kind':event,'status':doc['status'],'turn_id':turn,'action_id':action,'at':doc['updated_at']})
    _write(root/'task.json',doc)
    return doc

@contextmanager
def locked(path):
    with path.open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        yield


def build_plan(root, learning_rate, question):
    import numpy as np
    from experiment_agent.task_contracts import TaskSpec
    from experiment_agent.performance_loop.preflight import CohortManifest
    from experiment_agent.performance_loop.local_plan import build_local_plan
    features=root/'features';features.mkdir(exist_ok=True)
    bags=[];generator=np.random.default_rng(101)
    for i in range(4):
        path=features/f'p{i}.npy'
        if not path.exists():np.save(path,generator.normal(size=(8,4)).astype(np.float32))
        else:generator.normal(size=(8,4))
        bags.append(dict(patient_id=f'p{i}',split='val' if i%2==0 else 'train',feature_path=path.name,
            feature_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),target=(i+1)/5))
    feature_digest=digest([{k:v for k,v in b.items() if k!='split'} for b in bags])
    metric=dict(name='rmse',target_id='outcome',split='val',direction='minimize',prediction='value')
    task=TaskSpec.model_validate(dict(family='regression',target_level='patient',bag_level='case',split_group='patient_id',
        targets=[dict(id='outcome',column='outcome',kind='continuous',missing='error')],objective={'loss':'mse'},
        selection={'metric':metric},evaluation=[{**metric,'split':'test'}]))
    cohort=CohortManifest.model_validate(dict(dataset_manifest_sha256=digest(bags),feature_manifest_sha256=feature_digest,
        development_unit_ids=[f'p{i}' for i in range(4)],locked_unit_ids=['p4','p5'],memberships=[
        dict(fold=f,unit_id=f'p{i}',split='val' if i%2==f else 'train') for f in range(2) for i in range(4)],
        exposure=dict(coverage='complete',checked_unit_ids=[f'p{i}' for i in range(6)],exposed_unit_ids=[],
        source=dict(artifact_id='synthetic-intake',sha256=digest({'synthetic':True,'bags':bags}),data_scope='unscoped'))))
    return build_local_plan(task=task,cohort=cohort,bags=bags,features_root=features,
        recipes=[dict(model='AB_MIL',learning_rate=rate,dropout=.1,max_patches_per_bag=5) for rate in (.0002,learning_rate)],
        parents=[None,0],epochs=1,seeds=[17,29],question=question,
        performance=dict(min_accept_delta=.01,target_delta=.05,min_improved_seeds=2,min_improved_folds=2),
        budget=dict(max_gpu_seconds=600.,max_wall_seconds=600.,max_model_calls=0,max_candidates=1,
            max_repairs_per_hypothesis=1,reserved_confirmation_gpu_seconds=60.),unit_timeout_seconds=45.).model_dump(mode='json')

class Adapter:
    id='pathoreason.synthetic_mil';version='0.1.0'
    def snapshot(self,pid):
        doc=document(task_root(pid))
        return {'revision':digest(doc),'state':doc}
    def lock(self,pid):return locked(task_root(pid)/'task.lock')
    def offers(self,pid,snapshot):
        status=snapshot['state']['status']
        allowed={'intake':status=='not_started','plan':status=='admitted','revise':status=='awaiting_review',
            'execute':status=='awaiting_review','recover':status in ('needs_repair','needs_reconciliation'),
            'stop':status=='running'}
        return {key:{'available':ok,'reason':'' if ok else '当前阶段不允许此操作'} for key,ok in allowed.items()}
    def preview(self,pid,capability,action_id,parameters):
        if set(parameters)-{'question','learning_rate','feedback','turn_id'}:raise RepairConflict('Unsupported parameters')
        if not re.fullmatch(r'turn_[A-Za-z0-9_-]+',parameters.get('turn_id','')):raise RepairConflict('Missing originating turn')
        if capability=='intake' and not 1<=len(parameters.get('question',''))<=4000:raise RepairConflict('研究问题不能为空')
        if capability=='revise' and not parameters.get('feedback','').strip():raise RepairConflict('修订必须保留反馈')
        rate=parameters.get('learning_rate',.0004)
        if isinstance(rate,bool) or not isinstance(rate,(int,float)) or not .00001<=rate<=.001:raise RepairConflict('合成验收学习率超出范围')
        if len(parameters.get('feedback',''))>4000:raise RepairConflict('反馈过长')
        return {'parameters':parameters,'scope':'synthetic_cpu_only','matrix':'2 candidates × 2 folds × 2 seeds × 1 epoch',
            'budget':{'max_wall_seconds':600,'max_repairs_per_hypothesis':1,'gpu':False,'model_planner_calls':0}}
    def apply(self,pid,capability,plan):
        root=task_root(pid);doc=document(root);p=plan['detail']['parameters'];action=plan['id']
        receipt={'action_id':action,'project_id':pid,'operation':capability,'turn_id':p['turn_id'],'run_id':doc['run_id']}
        if capability=='intake':
            doc.update(status='admitted',question=p['question'],evidence_role='synthetic')
        elif capability in ('plan','revise'):
            raw=build_plan(root,p.get('learning_rate',.0004),doc['question'])
            plan_digest=digest(raw);path=root/'plans'/f'{plan_digest}.json';path.parent.mkdir(exist_ok=True)
            if not path.exists():_write(path,raw)
            previous=doc['plan']
            doc.update(status='awaiting_review',plan=plan_digest,learning_rate=p.get('learning_rate',.0004))
            doc.setdefault('revisions',[]).append({'before':previous,'after':plan_digest,'feedback':p.get('feedback'),
                'learning_rate':doc['learning_rate'],'action_id':action,'turn_id':p['turn_id']})
        elif capability=='execute':
            doc.update(status='running',run_id='run_'+action,approved_plan=doc['plan'],approval_turn_id=p['turn_id'])
            receipt['run_id']=doc['run_id']
        elif capability=='recover':
            if doc.get('recovery_count',0)>=1:raise RepairConflict('本任务恢复额度已用完')
            doc.update(status='running',recovery_count=doc.get('recovery_count',0)+1)
        elif capability=='stop':
            run=root/'runs'/doc['run_id'];(run/'stop.requested').touch()
            # Existing controller observes this signal and retains its budget/evidence.
        receipt['plan_digest']=doc['plan']
        receipts=root/'receipts';receipts.mkdir(exist_ok=True)
        # The task records the durable receipt atomically, covering the journal gap.
        doc.setdefault('receipts',{})[action]=receipt
        save(root,doc,'workflow_state_changed',p['turn_id'],action)
        _write(receipts/f'{action}.json',receipt)
        return receipt
    def dispatch(self,pid,capability,receipt):
        if capability not in ('execute','recover'):return
        root=task_root(pid);run=root/'runs'/receipt['run_id'];run.mkdir(parents=True,exist_ok=True)
        with (run/'bridge.log').open('ab') as log:
            subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'run',pid,receipt['action_id']],
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
                env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','AUTORESEARCH_COMPUTE_CONFIG')} | {
                    'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
    def recover_receipt(self,pid,capability,plan):return document(task_root(pid)).get('receipts',{}).get(plan['id'])
    def verify(self,pid,capability,receipt):
        doc=document(task_root(pid));status=doc['status']
        if capability in ('execute','recover'):
            run=task_root(pid)/'runs'/receipt['run_id']
            if status=='running':
                # A vanished bridge cannot be interpreted as successful execution.
                marker=run/f"started-{receipt['action_id']}.json"
                if marker.exists():
                    owner=json.loads(marker.read_text());proc=Path('/proc')/str(owner['pid'])/'stat'
                    alive=proc.exists() and proc.read_text().split()[21]==owner['start'] and proc.read_text().split()[2]!='Z'
                    if not alive:
                        with self.lock(pid):
                            doc=document(task_root(pid));doc['status']='needs_reconciliation'
                            save(task_root(pid),doc,'workflow_state_changed',receipt['turn_id'],receipt['action_id'])
                        status=doc['status']
                elif time.time()-doc['updated_at']>15:
                    with self.lock(pid):
                        doc=document(task_root(pid));doc['status']='needs_reconciliation'
                        save(task_root(pid),doc,'dispatch_not_observed',receipt['turn_id'],receipt['action_id'])
                    status=doc['status']
            return {'action_status':'waiting_for_workflow' if status=='running' else 'succeeded',
                'workflow_status':status,'tool_succeeded':status=='completed','scientific_status':'not_assessed',
                'message':'执行结束不代表研究目标或科学结论通过'}
        return {'action_status':'succeeded','workflow_status':status,'scientific_status':'not_assessed'}

class ControlAdapter(Adapter):
    # Stop signals must not contend with the journal's running dispatch resource.
    # They retain the same domain lock/revision and their own durable action receipt.
    id='pathoreason.synthetic_control'
    def offers(self,pid,snapshot):return {'stop':super().offers(pid,snapshot)['stop']}

def controller():
    registry=RepairRegistry();adapter=Adapter();registry.register_adapter(adapter);registry.register_adapter(ControlAdapter())
    for name,title in OPERATIONS.items():registry.register_capability(Capability(name,'0.1.0',title,'synthetic_project_operator'))
    return RepairController(registry,RepairJournal(DATA/'research/journal',max_executions_per_day=12),'pathoreason-p2-synthetic')

def run(pid,action):
    from experiment_agent.performance_loop.local_plan import LocalLoopPlan
    from experiment_agent.performance_loop.controller import LoopController
    root=task_root(pid);receipt=document(root)['receipts'][action];run_root=root/'runs'/receipt['run_id']
    with locked(run_root/'bridge.lock'):
        # A distinct explicit recovery action may resume; the same dispatch never does.
        started=run_root/f'started-{action}.json'
        if started.exists():return
        owner={'pid':os.getpid(),'start':Path('/proc/self/stat').read_text().split()[21]}
        _write(started,owner);_write(run_root/'owner.json',owner)
        try:
            check_source()
            plan=LocalLoopPlan.model_validate_json((root/'plans'/f"{receipt['plan_digest']}.json").read_text())
            from experiment_agent.performance_loop.jobs import LocalJobs
            class CpuJobs(LocalJobs):
                def _launch(self,path,**kwargs):
                    with (path/'driver.log').open('ab') as log:
                        return subprocess.Popen([sys.executable,str(Path(__file__).with_name('business_job.py')),str(path)],
                            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
                            env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','LANG':'C.UTF-8',
                                'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
            ctl=LoopController(run_root/'loop',plan,jobs=CpuJobs(run_root/'loop/jobs'))
            previous=[None]
            def progress(controller):
                snapshot=controller.store.snapshot()
                counts={s:sum(u['status']==s for u in snapshot['units']) for s in ('completed','running','failed','pending')}
                value={'counts':counts,'spent':snapshot['spent'],'reserved':snapshot['reserved']}
                if value!=previous[0]:
                    with Adapter().lock(pid):
                        doc=document(root);doc['progress']=value
                        save(root,doc,'execution_progress',receipt['turn_id'],action)
                    previous[0]=value
            result=ctl.run(poll_seconds=.25,retry_failed=receipt['operation']=='recover',
                cancelled=lambda:(run_root/'stop.requested').exists(),after_step=progress)
            result['unit_evidence']=ctl.store.snapshot()['units']
            _write(run_root/'result.json',result)
            with Adapter().lock(pid):
                doc=document(root);doc.update(status=result['status'],result=result)
                save(root,doc,'workflow_state_changed',receipt['turn_id'],action)
        except Exception as exc:
            with Adapter().lock(pid):
                doc=document(root);doc.update(status='needs_reconciliation',error_type=type(exc).__name__)
                save(root,doc,'execution_exception',receipt['turn_id'],action)
            raise

def main():
    check_source()
    if sys.argv[1]=='run':run(sys.argv[2],sys.argv[3]);return
    request=json.load(sys.stdin);pid=request['project_id'];ctl=controller();target={'adapter':ControlAdapter.id if request.get('operation')=='stop' else Adapter.id,'id':pid}
    if request['method']=='inspect':
        with ctl.journal.connection() as db:
            ids=[r[0] for r in db.execute('SELECT id FROM repairs WHERE owner=? ORDER BY created',(pid,))]
        actions=[]
        for ident in ids:
            item=ctl.journal.get(ident,pid)
            if item['status'] in ('executing','waiting_for_workflow','needs_reconciliation'):
                try:item=ctl.reconcile(pid,ident,item['digest'])
                except RepairConflict:pass
            actions.append(item)
        result={**ctl.discover(target),'actions':actions}
    else:
        p=request.get('parameters',{});p['turn_id']=request['turn_id']
        item=ctl.plan(pid,target,request['expected_revision'],request['operation'],request['idempotency_key'],p)
        if item['status']=='pending_approval':item=ctl.decide(pid,item['id'],item['digest'],'approve')
        if item['status']=='approved':item=ctl.execute(pid,item['id'],item['digest'])
        result={**ctl.discover(target),'action':item}
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'error':str(exc) if isinstance(exc,(RepairConflict,ValueError)) else type(exc).__name__}))
        sys.exit(1)
