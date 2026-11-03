import asyncio,hashlib,json,os,signal,sys,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from test_p1_service import fixture,settled
from test_p5_entry import study,formal_runtime
from test_task_workspaces import commit
from pathoreason.training_contracts import TrainingBudget,TrainingPlan,TrainingToolInput,TrainingDecision
from pathoreason.training_files import freeze_environment,file_digest
from pathoreason.training_account import TrainingAccount,identity
from pathoreason.training_service import Training
from pathoreason.task_workspaces import TaskWorkspaces
from pathoreason.persistence import Conflict

@pytest.fixture(scope='session')
def environment(tmp_path_factory):
    root=tmp_path_factory.mktemp('training-environment')
    return freeze_environment(root/'env',sys.executable,[],[sys.executable],root)


def setup_plan(fixture,environment,script=None,units=2):
    s,_,request,r=fixture;formal_runtime(r);v=study(s);pid=v.project_id;cid=s.store.conversations(pid)[0]['id']
    root=s.data/'templates'/'fixture'/'1';root.mkdir(parents=True)
    script=script or '''import json,os,pathlib
out=pathlib.Path(os.environ['PATHOREASON_OUTPUT_DIR'])
spec=json.load(open(os.environ['PATHOREASON_INPUT_MANIFEST']))
(out/'checkpoint.json').write_text(json.dumps({'synthetic':True,'parameter':0.125}))
(out/'result.json').write_text(json.dumps({'synthetic':True,'unit':spec['parameters']}))
'''
    files={'runner.py':script,'requirements.lock':'# stdlib-only synthetic fixture\n'}
    spec={'template_id':'fixture','version':'1','entrypoints':['runner.py'],'files':[]}
    for name,text in files.items():
        (root/name).write_text(text);spec['files'].append({'source':name,'destination':name,'sha256':hashlib.sha256(text.encode()).hexdigest()})
    (root/'manifest.json').write_text(json.dumps(spec))
    s.task_code.workspaces=TaskWorkspaces(s.store,s.data,s.data/'templates')
    actor={'kind':'engineering_fixture'}
    def taskop(op,key,**kwargs):return s.task_code.workspaces.act(pid,{'operation':op,'idempotency_key':key,'template':'fixture/1','objective':'Isolated synthetic executor test',**kwargs},actor)
    task=taskop('create','create');params={'task_id':task['id'],'expected_revision':task['revision']};check=taskop('check','check',**params);snapshot=taskop('freeze','freeze',check_id=check['id'],**params)
    with s.training.account.db() as db:db.execute('INSERT INTO training_environments VALUES(?,?,?)',(environment['id'],pid,json.dumps(environment)))
    plan=TrainingPlan(title='Synthetic matrix',task_id=task['id'],snapshot_id=snapshot['id'],environment_id=environment['id'],protocol='Synthetic worker validation; no scientific approval',units=[{'id':'unit_'+str(i),'label':'Synthetic '+str(i),'entrypoint':'runner.py','output_files':['checkpoint.json','result.json'],'parameters':{'seed':i}} for i in range(units)])
    body=TrainingToolInput(turn_id='turn_fixture',grant='fixture',operation='prepare',idempotency_key='prepare',plan=plan)
    prepared=s.training.prepare(pid,cid,body,actor)
    return s,r,v,cid,request,task,prepared,body,taskop


def wait(s,eid,pid,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        v=s.training.view(eid,pid)
        if v.status not in ('queued','running','stopping','waiting_resource'):return v
        time.sleep(.1)
    raise AssertionError('worker did not terminate: '+str(v))


def budget(wall=30,unit=10,attempts=2):return TrainingBudget(max_wall_seconds=float(wall),max_gpu_seconds=0.,max_unit_seconds=float(unit),max_attempts_per_unit=attempts)


def approve(s,cid,v,b=None,key='approve'):
    return s.training.decide(cid,v.id,TrainingDecision(expected_revision=v.revision,request_key=key,action='authorize',budget=b or budget()))


def test_explicit_budget_required_and_real_frozen_matrix_survives_service_recreation(fixture,environment):
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment)
    before=s.formal.view(v.project_id).model_dump()
    assert p.status=='draft' and p.budget is None and not p.authorized
    with pytest.raises(Conflict,match='user_budget'):s.training.launch(p.id,v.project_id,{},p.revision)
    started=approve(s,cid,p);run=started.run_id
    duplicate=approve(s,cid,p);assert duplicate.run_id==run
    # An ordinary task edit cannot change the snapshotted worker.
    (Path(task['code_path'])/'runner.py').write_text('raise RuntimeError("mutable task must not run")')
    s.training=Training(s)
    done=wait(s,p.id,v.project_id)
    assert done.status=='completed',done.model_dump()
    assert len(done.attempts)==2 and all(a['status']=='completed' for a in done.attempts)
    assert done.used_wall_seconds>0 and done.used_gpu_seconds==0
    assert not r.calls and s.formal.view(v.project_id).model_dump()==before
    for a in done.attempts:
        assert json.loads((Path(a['output'])/'isolation.json').read_text())['backend']=='landlock_seccomp_v1'
        assert json.loads((Path(a['output'])/'result.json').read_text())['synthetic']


def test_stop_timeout_and_retry_preserve_consumption(fixture,environment):
    script='import time,pathlib,os\nout=pathlib.Path(os.environ["PATHOREASON_OUTPUT_DIR"])\n(out/"checkpoint.json").write_text("partial")\ntime.sleep(30)\n(out/"result.json").write_text("done")\n'
    s,r,v,cid,request,task,p,body,op=setup_plan(fixture,environment,script,units=1)
    started=approve(s,cid,p,budget(wall=8,unit=1))
    failed=wait(s,p.id,v.project_id)
    assert failed.status in ('budget_exhausted','failed')
    assert failed.used_wall_seconds>0 and len(failed.attempts)==1
    original=failed.attempts[0].copy();used=failed.used_wall_seconds
    with pytest.raises(ValueError,match='below_consumption'):s.training.decide(cid,p.id,TrainingDecision(expected_revision=failed.revision,request_key='shrink',action='budget',budget=budget(wall=.01,unit=.01)))
    changed=s.training.decide(cid,p.id,TrainingDecision(expected_revision=failed.revision,request_key='extend',action='budget',budget=budget(wall=20,unit=10)))
    assert changed.used_wall_seconds==used and changed.status==failed.status
    restarted=s.training.decide(cid,p.id,TrainingDecision(expected_revision=changed.revision,request_key='resume',action='resume'))
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        current=s.training.view(p.id,v.project_id)
        if len(current.attempts)==2:break
        time.sleep(.1)
    stopped=s.training.decide(cid,p.id,TrainingDecision(expected_revision=current.revision,request_key='stop',action='stop'))
    stopped=wait(s,p.id,v.project_id)
    assert stopped.status=='stopped' and stopped.used_wall_seconds>=used
    assert stopped.attempts[0]==original and len(stopped.attempts)==2
    assert (Path(stopped.attempts[0]['output'])/'checkpoint.json').exists()


def test_worker_cannot_read_sealed_or_ledger_write_source_connect_or_fork(fixture,environment):
    s=fixture[0];secret=s.data/'sealed-probe';secret.write_text('not for training')
    script=f'''import os,json,pathlib,socket,subprocess
out=pathlib.Path(os.environ['PATHOREASON_OUTPUT_DIR'])
checks={{}}
for name,fn in [
 ('sealed',lambda:open({str(secret)!r}).read()),
 ('ledger',lambda:open({str(s.store.path)!r}).read()),
 ('source_write',lambda:open(__file__,'a').write('tampered')),
 ('network',lambda:socket.create_connection(('127.0.0.1',8520),timeout=1)),
 ('fork',lambda:subprocess.run(['/bin/true'],check=True))]:
 try:fn();checks[name]=False
 except OSError:checks[name]=True
assert all(checks.values()),checks
(out/'checkpoint.json').write_text(json.dumps(checks))
(out/'result.json').write_text('synthetic isolation passed')
'''
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,script,units=1)
    approve(s,cid,p);done=wait(s,p.id,v.project_id)
    assert done.status=='completed',done.model_dump()
    assert secret.read_text()=='not for training'


def test_user_budget_cas_project_binding_and_no_agent_budget_field(fixture,environment):
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,units=1)
    with pytest.raises(ValidationError):TrainingToolInput(turn_id='turn_x',grant='x',operation='authorize')
    with pytest.raises(Conflict,match='revision_conflict'):s.training.decide(cid,p.id,TrainingDecision(expected_revision=99,request_key='stale',action='authorize',budget=budget()))
    other=study(s,key='other');othercid=s.store.conversations(other.project_id)[0]['id']
    with pytest.raises(ValueError,match='not_found'):s.training.decide(othercid,p.id,TrainingDecision(expected_revision=p.revision,request_key='cross',action='authorize',budget=budget()))
    with pytest.raises(ValidationError):TrainingBudget(max_wall_seconds=True,max_gpu_seconds=0,max_unit_seconds=1,max_attempts_per_unit=1)
    assert s.training.view(p.id,v.project_id).status=='draft'


def test_failure_repair_reuses_budget_and_plan_scope_but_keeps_original(fixture,environment):
    s,r,v,cid,request,task,p,body,op=setup_plan(fixture,environment,'raise ValueError("synthetic first failure")\n',units=1)
    approve(s,cid,p);failed=wait(s,p.id,v.project_id);assert failed.status=='failed'
    old=failed.attempts[0].copy()
    code=Path(task['code_path']);(code/'runner.py').write_text('import os,pathlib\np=pathlib.Path(os.environ["PATHOREASON_OUTPUT_DIR"])\n(p/"checkpoint.json").write_text("checkpoint")\n(p/"result.json").write_text("synthetic repair")\n');commit(code)
    revised=op('revise','repair',task_id=task['id'],expected_revision=1,reason='Synthetic repair')
    check=op('check','repair-check',task_id=task['id'],expected_revision=2)
    snap=op('freeze','repair-freeze',task_id=task['id'],expected_revision=2,check_id=check['id'])
    body=body.model_copy(update={'experiment_id':p.id,'expected_revision':failed.revision,'plan':body.plan.model_copy(update={'snapshot_id':snap['id']})})
    repaired=s.training.prepare(v.project_id,cid,body,{'kind':'engineering_fixture'})
    assert repaired.authorized and repaired.used_wall_seconds==failed.used_wall_seconds
    s.training.launch(p.id,v.project_id,{'kind':'engineering_fixture'},repaired.revision)
    done=wait(s,p.id,v.project_id);assert done.status=='completed',done.model_dump()
    assert done.attempts[0]==old and done.used_wall_seconds>failed.used_wall_seconds
    with s.training.account.db() as db:assert db.execute('SELECT count(*) FROM training_plan_revisions WHERE experiment_id=?',(p.id,)).fetchone()[0]==2


def test_agent_exhaustion_does_not_spend_or_stop_training(fixture,environment):
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,units=1)
    async def case():
        await s.submit(cid,{**request,'request_key':'agent_one','skill_id':None,'artifact_ids':[]})
        while s.store.active():await asyncio.sleep(.02)
        await s.submit(cid,{**request,'request_key':'agent_two','skill_id':None,'artifact_ids':[]})
        while s.store.active():await asyncio.sleep(.02)
        with pytest.raises(Conflict,match='budget_exhausted'):await s.submit(cid,{**request,'request_key':'no_agent_budget','skill_id':None,'artifact_ids':[]})
        before=s.formal.view(v.project_id).model_dump()
        approve(s,cid,p)
        await s.close()
        done=await asyncio.to_thread(wait,s,p.id,v.project_id)
        assert done.status=='completed',done.model_dump()
        assert s.formal.view(v.project_id).model_dump()==before and len(r.calls)==2
    asyncio.run(case())


def test_frozen_input_change_is_failure_not_false_completion(fixture,environment):
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,units=1)
    file=s.data/'projects'/v.project_id/'input.json';file.write_text('[1,2,3]')
    raw=body.plan.model_dump();raw['inputs']=[dict(id='feature',path=str(file),sha256=file_digest(file),role='development',subject_id='synthetic_subject',prior_test_exposures=0)]
    raw['units'][0]['input_ids']=['feature']
    body=body.model_copy(update={'experiment_id':p.id,'expected_revision':p.revision,'plan':TrainingPlan.model_validate(raw)})
    p=s.training.prepare(v.project_id,cid,body,{'kind':'fixture'});file.write_text('[9,9,9]')
    approve(s,cid,p);failed=wait(s,p.id,v.project_id)
    assert failed.status=='failed' and failed.error=='training_input_changed'
    assert failed.used_wall_seconds>0 and len(failed.attempts)==1


def test_sealed_inputs_and_exposure_cannot_be_renamed_or_reset(fixture,environment):
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,units=1)
    file=s.data/'projects'/v.project_id/'test.json';file.write_text('synthetic sealed')
    raw=body.plan.model_dump();raw['inputs']=[dict(id='sealed',path=str(file),sha256=file_digest(file),role='sealed',subject_id='synthetic_subject',prior_test_exposures=4)]
    body=body.model_copy(update={'experiment_id':p.id,'expected_revision':p.revision,'plan':TrainingPlan.model_validate(raw)})
    p=s.training.prepare(v.project_id,cid,body,{'kind':'fixture'})
    raw['inputs'][0]['prior_test_exposures']=0
    with pytest.raises(Conflict,match='cannot_be_reset'):s.training.prepare(v.project_id,cid,body.model_copy(update={'expected_revision':p.revision,'plan':TrainingPlan.model_validate(raw)}),{'kind':'fixture'})
    raw['inputs'][0]['subject_id']='renamed'
    with pytest.raises(Conflict,match='identity_changed'):s.training.prepare(v.project_id,cid,body.model_copy(update={'expected_revision':p.revision,'plan':TrainingPlan.model_validate(raw)}),{'kind':'fixture'})
    raw['units'][0]['input_ids']=['sealed']
    with pytest.raises(ValidationError,match='sealed_input_in_fit'):TrainingPlan.model_validate(raw)


def test_lost_controller_retains_reservation_and_never_replays(fixture,environment):
    script='import time,pathlib,os\np=pathlib.Path(os.environ["PATHOREASON_OUTPUT_DIR"])\n(p/"checkpoint.json").write_text("partial")\ntime.sleep(30)\n(p/"result.json").write_text("late")\n'
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,script,units=1)
    approve(s,cid,p,budget(wall=40,unit=10))
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        d=s.training.account.view(p.id)
        if d['attempts'] and (Path(d['attempts'][0]['output'])/'isolation.json').exists():break
        time.sleep(.1)
    controller=d['controller'];assert identity(controller['pid'])==controller['identity']
    os.kill(controller['pid'],signal.SIGKILL)
    deadline=time.monotonic()+5
    while identity(controller['pid']) and time.monotonic()<deadline:time.sleep(.05)
    lost=s.training.view(p.id,v.project_id)
    assert lost.status=='needs_reconciliation' and lost.attempts[0]['status']=='unknown'
    assert lost.used_wall_seconds>=lost.attempts[0]['allowance']
    with pytest.raises(Conflict,match='acknowledgement'):s.training.decide(cid,p.id,TrainingDecision(expected_revision=lost.revision,request_key='blind',action='resume'))
    time.sleep(.2)
    assert not (Path(lost.attempts[0]['output'])/'result.json').exists()


def test_dependency_receipts_and_full_fit_matrix_precede_evaluation(fixture,environment):
    script='''import json,os,pathlib
out=pathlib.Path(os.environ['PATHOREASON_OUTPUT_DIR'])
spec=json.load(open(os.environ['PATHOREASON_INPUT_MANIFEST']))
if spec['phase']=='evaluate':
 assert len(spec['dependencies'])==4
 for f in spec['dependencies']:
  assert pathlib.Path(f['path']).read_text()
  try:open(f['path'],'w').write('bad');raise AssertionError('mutable dependency')
  except PermissionError:pass
(out/'checkpoint.json').write_text('synthetic checkpoint')
(out/'result.json').write_text(json.dumps({'phase':spec['phase']}))
'''
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,script)
    raw=body.plan.model_dump();raw['evaluation']='previously_exposed'
    raw['units'].insert(0,dict(id='evaluation',label='Evaluate',phase='evaluate',entrypoint='runner.py',output_files=['checkpoint.json','result.json'],depends_on=['unit_0','unit_1']))
    p=s.training.prepare(v.project_id,cid,body.model_copy(update={'experiment_id':p.id,'expected_revision':p.revision,'plan':TrainingPlan.model_validate(raw)}),{'kind':'fixture'})
    approve(s,cid,p);done=wait(s,p.id,v.project_id)
    assert done.status=='completed',done.model_dump()
    assert [a['phase'] for a in done.attempts]==['fit','fit','evaluate']
    raw['units'][1]['depends_on']=['evaluation']
    with pytest.raises(ValidationError,match='dependency'):TrainingPlan.model_validate(raw)


def test_runtime_dependency_pin_mismatch_is_visible(fixture,environment):
    from pathoreason.training_files import verify_requirements
    root=fixture[0].data/'pin-check';root.mkdir();(root/'requirements.lock').write_text('example_pkg==1.2.3\n')
    verify_requirements(root,{'distributions':{'example-pkg':'1.2.3'}})
    with pytest.raises(ValueError,match='pin_mismatch'):verify_requirements(root,{'distributions':{'example-pkg':'1.2.4'}})


def test_user_confirmation_binds_goal_and_receipt_continues_automatically(fixture,environment):
    from test_goals import accepted,finish
    from pathoreason.goals import GoalCheckpoint
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,units=1)
    async def case():
        s.goals.start=lambda:None;r.hold=True
        first=await s.submit(cid,{**request,'request_key':'prepare_goal','skill_id':None,'artifact_ids':[],'goal_mode':'continuous'})
        tid=first['turn']['id'];await accepted(s,tid)
        linked=s.training.prepare(v.project_id,cid,body.model_copy(update={'experiment_id':p.id,'expected_revision':p.revision}),{'kind':'agent','turn_id':tid})
        assert not linked.approval_ready
        with pytest.raises(Conflict,match='preparation_turn_active'):approve(s,cid,linked)
        s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,outcome='needs_input',summary='Review the prepared plan and independent training budget in Training.'))
        await finish(s,r,tid);assert s.goals.view(cid).state=='waiting_input'
        linked=s.training.view(p.id,v.project_id);assert linked.approval_ready
        launched=approve(s,cid,linked)
        assert s.goals.view(cid).state=='waiting' and s.goals.view(cid).wait_for.run_id==launched.run_id
        done=await asyncio.to_thread(wait,s,p.id,v.project_id);assert done.status=='completed'
        await s.goals.tick();assert s.goals.view(cid).state=='active'
        await s.goals.tick();auto=s.store.turns(cid)[-1];await accepted(s,auto['id'])
        assert s.view(auto)['origin']=='goal' and len(r.calls)==2
        assert done.run_id in r.calls[-1][3]
        await s.close()
    asyncio.run(case())


def test_agent_launch_during_goal_turn_does_not_invalidate_checkpoint(fixture,environment):
    from test_goals import accepted,finish
    from pathoreason.goals import GoalCheckpoint
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,'raise ValueError("synthetic repair required")',units=1)
    approve(s,cid,p);failed=wait(s,p.id,v.project_id)
    async def case():
        s.goals.start=lambda:None;r.hold=True
        first=await s.submit(cid,{**request,'request_key':'retry_goal','skill_id':None,'artifact_ids':[],'goal_mode':'continuous'})
        tid=first['turn']['id'];await accepted(s,tid)
        linked=s.training.prepare(v.project_id,cid,body.model_copy(update={'experiment_id':p.id,'expected_revision':failed.revision}),{'kind':'agent','turn_id':tid})
        revision=s.goals.view(cid).revision
        launched=s.training.launch(p.id,v.project_id,{'kind':'agent','turn_id':tid},linked.revision)
        assert s.goals.view(cid).revision==revision
        s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=revision,outcome='waiting',summary='Waiting for receipt',wait_for={'kind':'training_run','run_id':launched.run_id}))
        await finish(s,r,tid)
        assert s.goals.view(cid).state=='waiting'
        done=await asyncio.to_thread(wait,s,p.id,v.project_id);assert done.status=='failed'
        await s.goals.tick();assert s.goals.view(cid).reason=='goal_training_needs_repair'
        await s.close()
    asyncio.run(case())


def test_training_mcp_contract_rejects_agent_approval_and_routes_registered_tool(monkeypatch,tmp_path):
    from test_guidance_mcp import run_bridge,request
    results,calls=run_bridge(monkeypatch,tmp_path,[{'jsonrpc':'2.0','id':1,'method':'tools/list'},request({'turn_id':'turn_fixture','grant':'PRIVATE_GRANT_VALUE','operation':'authorize'},ident=2,name='training'),request({'turn_id':'turn_fixture','grant':'PRIVATE_GRANT_VALUE','operation':'list'},ident=3,name='training')],responder={'experiments':[]})
    tool=next(t for t in results[0]['result']['tools'] if t['name']=='training')
    assert 'authorize' not in tool['inputSchema']['properties']['operation']['enum']
    assert results[1]['result']['isError'] and not results[2]['result']['isError']
    assert len(calls)==1 and calls[0].full_url.endswith('/internal/training')


@pytest.mark.skipif(not os.environ.get('PATHOREASON_TEST_TORCH_PYTHON'),reason='Explicit synthetic torch integration runtime required')
def test_frozen_torch_environment_executes_cpu_synthetic_optimizer(fixture,tmp_path):
    python=os.environ['PATHOREASON_TEST_TORCH_PYTHON']
    env=freeze_environment(tmp_path/'torch-env',python,[],[python],tmp_path)
    script='''import os,pathlib,json,torch
out=pathlib.Path(os.environ['PATHOREASON_OUTPUT_DIR'])
torch.manual_seed(7)
x=torch.randn(12,8);y=torch.tensor([0,1]*6)
model=torch.nn.Linear(8,2);before=model.weight.detach().clone();optimizer=torch.optim.SGD(model.parameters(),lr=0.05)
losses=[]
for _ in range(3):
 optimizer.zero_grad();loss=torch.nn.functional.cross_entropy(model(x),y);loss.backward();optimizer.step();losses.append(float(loss.detach()))
assert torch.isfinite(torch.tensor(losses)).all()
assert not torch.equal(before,model.weight)
torch.save(model.state_dict(),out/'checkpoint.json')
(out/'result.json').write_text(json.dumps({'synthetic':True,'device':'cpu','losses':losses,'torch':torch.__version__}))
'''
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,env,script,units=1)
    approve(s,cid,p,budget(wall=90,unit=60));done=wait(s,p.id,v.project_id,seconds=180)
    assert done.status=='completed',done.model_dump()
    assert done.used_gpu_seconds==0 and not r.calls


def test_training_tool_rechecks_active_grant_and_inspection_scope(fixture):
    from test_goals import accepted
    async def case():
        s,_,request,r=fixture;formal_runtime(r);v=study(s);cid=s.store.conversations(v.project_id)[0]['id'];r.hold=True
        first=await s.submit(cid,{**request,'request_key':'scope','skill_id':None,'artifact_ids':[]});tid=first['turn']['id'];await accepted(s,tid)
        body=TrainingToolInput(turn_id=tid,grant=s.guidance.grant(tid),operation='list')
        assert s.training.call(body)['experiments']==[]
        with pytest.raises(Conflict,match='authority'):s.training.call(body.model_copy(update={'grant':'wrong'}))
        with s.store.connect(True) as db:db.execute('INSERT INTO turn_guidance_context VALUES(?,?)',(tid,json.dumps({'selected_option_id':'read','proposal':{'options':[{'id':'read','scope':'inspect'}]}})))
        with pytest.raises(Conflict,match='outside_turn_scope'):s.training.call(body.model_copy(update={'operation':'environment','idempotency_key':'mutate','python':sys.executable}))
        r.hold=False;await settled(s,tid)
        with pytest.raises(Conflict,match='authority'):s.training.call(body)
        await s.close()
    asyncio.run(case())


def test_compact_receipts_and_project_plan_file_preserve_plan_and_idempotency(fixture,environment):
    from test_goals import accepted
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,units=1)
    async def case():
        r.hold=True
        first=await s.submit(cid,{**request,'request_key':'plan_file','skill_id':None,'artifact_ids':[]});tid=first['turn']['id'];await accepted(s,tid)
        path=Path(v.workspace)/'prepared-plan.json';path.write_text(body.plan.model_dump_json())
        tool=TrainingToolInput(turn_id=tid,grant=s.guidance.grant(tid),operation='prepare',idempotency_key='from_file',plan_path=str(path))
        result=s.training.call(tool);assert result['status']=='draft' and 'plan' not in result and result['unit_count']==1
        assert s.training.call(tool)==result
        inspect=tool.model_copy(update={'operation':'inspect','experiment_id':result['id'],'plan_path':None,'include_plan':True})
        full=s.training.call(inspect);assert full['plan']==body.plan.model_dump()
        path.write_text(body.plan.model_copy(update={'title':'Changed plan'}).model_dump_json())
        with pytest.raises(Conflict,match='request_conflict'):s.training.call(tool)
        outside=s.data/'other.json';outside.write_text(body.plan.model_dump_json())
        with pytest.raises(ValueError,match='outside_project'):s.training.call(tool.model_copy(update={'plan_path':str(outside),'idempotency_key':'outside'}))
        link=Path(v.workspace)/'plan-link.json';link.symlink_to(path)
        with pytest.raises(ValueError,match='links'):s.training.call(tool.model_copy(update={'plan_path':str(link),'idempotency_key':'symlink'}))
        long=p.model_copy(deep=True);long.plan.inputs=[]
        for i in range(1000):
            from pathoreason.training_contracts import TrainingInput
            long.plan.inputs.append(TrainingInput(id='input_'+str(i),path='/example/'+str(i),sha256='a'*64,role='development',subject_id='subject_'+str(i)))
        receipt=s.training.receipt(long);assert receipt['input_count']==1000 and len(json.dumps(receipt))<5000
        r.hold=False;await settled(s,tid);await s.close()
    asyncio.run(case())


def test_completed_preparation_kept_and_launch_phase_carries_used_goal_turns(fixture,environment):
    from test_goals import accepted,finish
    from pathoreason.goals import GoalCheckpoint
    s,r,v,cid,request,task,p,body,_=setup_plan(fixture,environment,units=1)
    async def case():
        s.goals.start=lambda:None;r.hold=True
        first=await s.submit(cid,{**request,'request_key':'complete_prep','skill_id':None,'artifact_ids':[],'goal_mode':'continuous'})
        tid=first['turn']['id'];await accepted(s,tid)
        linked=s.training.prepare(v.project_id,cid,body.model_copy(update={'experiment_id':p.id,'expected_revision':p.revision}),{'kind':'agent','turn_id':tid})
        note=Path(v.workspace)/'outputs/prepared.json';note.write_text('{"scope":"prepared_only"}')
        s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,outcome='completed',summary='Preparation complete',evidence={'files':['outputs/prepared.json']}))
        await finish(s,r,tid);old=s.goals.view(cid);assert old.state=='completed'
        with s.store.connect() as db:original=db.execute('SELECT document FROM research_goals WHERE id=?',(old.id,)).fetchone()[0]
        launched=approve(s,cid,linked);new=s.goals.view(cid)
        assert new.id!=old.id and new.state=='waiting' and new.turns_used==old.turns_used and new.max_turns==old.max_turns
        assert new.wait_for.run_id==launched.run_id
        with s.store.connect() as db:assert db.execute('SELECT document FROM research_goals WHERE id=?',(old.id,)).fetchone()[0]==original
        assert approve(s,cid,linked).run_id==launched.run_id and s.goals.view(cid).id==new.id
        done=await asyncio.to_thread(wait,s,p.id,v.project_id);assert done.status=='completed'
        await s.goals.tick();await s.goals.tick();auto=s.store.turns(cid)[-1];await accepted(s,auto['id'])
        assert s.view(auto)['origin']=='goal' and s.view(auto)['goal_id']==new.id
        assert s.goals.view(cid).turns_used==old.turns_used+1
        await s.close()
    asyncio.run(case())
