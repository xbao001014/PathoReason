import asyncio,json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pathoreason.persistence import Conflict,Gone,Store,encoded
from pathoreason.service import Service
from pathoreason.project_lifecycle import ProjectActionInput,DeleteProjectInput
from test_p1_service import fixture
from test_conversation_lifecycle import finish,install_delete

def body(s,pid,assets=True):
    p=s.store.project(pid,include_removed=True)
    return DeleteProjectInput(confirm=True,confirmation_title=p['title'],expected_revision=p['revision'],delete_assets=assets)
def action(s,pid):return ProjectActionInput(expected_revision=s.store.project(pid)['revision'])
def owned(s,pid):
    paths=[]
    for root in ['projects','studies','research','artifacts']:
        p=s.data/root/pid;p.mkdir(parents=True,exist_ok=True);(p/'owned.txt').write_text('project-owned');paths.append(p)
    return paths

def test_archive_inherits_readonly_without_changing_child_archive_flags(fixture):
    s,c,request,runtime=fixture;pid=c['project_id'];install_delete(runtime)
    async def run():
        await finish(s,c,request);other=s.new_conversation(pid,'Already archived')
        await s.conversations.archive(other['id'])
        before=s.store.conversations(pid)
        v=await s.projects.archive(pid,action(s,pid));assert v.state=='archived'
        assert s.store.conversations(pid)==before
        assert s.projects.list()==[];p=s.projects.list(True)[0];assert p.open_conversations==1 and p.archived_conversations==1
        assert s.store.turns(c['id'])
        for fn in [lambda:s.new_conversation(pid,'Blocked'),lambda:s.store.conversation(c['id'],writable=True)]:
            with pytest.raises(Conflict,match='project_archived'):fn()
        with pytest.raises(Conflict,match='project_archived'):await s.submit(c['id'],request)
        from pathoreason.conversation_titles import ConversationTitleUpdate
        with pytest.raises(Conflict,match='project_archived'):await s.titles.rename(c['id'],ConversationTitleUpdate(title='Blocked rename',expected_revision=0))
        with pytest.raises(Conflict,match='project_archived'):await s.conversations.archive(other['id'],restore=True)
        with pytest.raises(Conflict,match='project_changed'):await s.projects.archive(pid,ProjectActionInput(expected_revision=1),restore=True)
        assert (await s.projects.archive(pid,action(s,pid),restore=True)).state=='active'
        assert s.store.conversations(pid)==before;assert len(runtime.calls)==1
    asyncio.run(run())

def test_delete_cleans_owned_files_and_chats_but_keeps_other_projects_and_budget(fixture):
    s,c,request,runtime=fixture;pid=c['project_id'];install_delete(runtime)
    async def run():
        tid=await finish(s,c,request);sibling=s.new_conversation(pid,'Sibling');paths=owned(s,pid)
        other=s.store.create_project('Other','Keep');other_paths=owned(s,other['id'])
        shared=s.data/'training/environments/shared';shared.mkdir(parents=True);(shared/'python').write_text('shared')
        with s.store.connect() as db:budget=[dict(r) for r in s.store.budget_rows(db)]
        result=await s.projects.delete(pid,body(s,pid));assert result.state=='deleted' and result.assets_removed
        assert result.conversations_deleted==2 and len(runtime.deleted)==1
        assert all(not p.exists() for p in paths);assert all(p.exists() for p in other_paths);assert shared.exists()
        assert (s.data/'artifacts/result.json').exists() # unowned source outside pid stays
        assert [p.id for p in s.projects.list(True)]==[other['id']]
        for read in [lambda:s.store.project(pid),lambda:s.store.conversation(c['id']),lambda:s.store.turn(tid),lambda:s.store.artifacts(pid),lambda:s.new_conversation(pid,'No')]:
            with pytest.raises(Gone,match='project_deleted'):read()
        with s.store.connect() as db:
            assert [dict(r) for r in s.store.budget_rows(db)]==budget
            assert db.execute('SELECT text FROM turns WHERE id=?',(tid,)).fetchone()[0]==''
        assert (await s.projects.delete(pid,body(s,pid))).state=='deleted'
    asyncio.run(run())

def test_keep_assets_option_is_explicit(fixture):
    s,c,_,runtime=fixture;install_delete(runtime);pid=c['project_id'];paths=owned(s,pid)
    result=asyncio.run(s.projects.delete(pid,body(s,pid,False)))
    assert result.state=='deleted' and not result.assets_removed and not result.delete_assets
    assert all(p.exists() for p in paths)

@pytest.mark.parametrize('state',['queued','running','waiting_resource','stopping','needs_reconciliation'])
def test_project_actions_refuse_active_or_unknown_training(fixture,state):
    s,c,_,runtime=fixture;install_delete(runtime);pid=c['project_id'];owned(s,pid)
    with s.store.connect(True) as db:db.execute('INSERT INTO training_experiments VALUES(?,?,?)',('exp_fixture',pid,encoded({'id':'exp_fixture','status':state})))
    async def run():
        for operation in [lambda:s.projects.archive(pid,action(s,pid)),lambda:s.projects.delete(pid,body(s,pid))]:
            with pytest.raises(Conflict,match='project_training_busy'):await operation()
        assert s.projects.view(pid).state=='active';assert not runtime.deleted
    asyncio.run(run())

def test_active_conversation_rejects_whole_archive_atomically(fixture):
    s,c,request,runtime=fixture;install_delete(runtime);pid=c['project_id']
    async def run():
        tid=await finish(s,c,request);s.new_conversation(pid,'Idle sibling');s.state(tid,'recovery_required')
        with pytest.raises(Conflict,match='conversation_busy'):await s.projects.archive(pid,action(s,pid))
        assert all(x['status']=='open' for x in s.store.conversations(pid));assert s.projects.view(pid).state=='active'
    asyncio.run(run())

def test_cleanup_failure_is_durable_and_resumes_without_repeating_native_delete(fixture,monkeypatch):
    s,c,request,runtime=fixture;install_delete(runtime);pid=c['project_id']
    async def run():
        await finish(s,c,request);paths=owned(s,pid)
        def fail(paths):raise OSError('private path')
        monkeypatch.setattr(s.projects,'_remove_assets',fail)
        result=await s.projects.delete(pid,body(s,pid));assert result.state=='failed' and result.conversations_deleted==1
        assert result.error_code=='project_cleanup_incomplete';assert s.projects.list(True)[0].deletion_state=='failed'
        with pytest.raises(Conflict,match='project_deletion_pending'):s.new_conversation(pid,'No')
        restored=Service(Store(s.store.path),runtime,s.config)
        assert (await restored.projects.delete(pid,body(restored,pid))).state=='deleted'
        assert len(runtime.deleted)==1 and not any(p.exists() for p in paths)
    asyncio.run(run())

def test_symlink_root_rejected_before_deleting_any_conversation(fixture,tmp_path):
    s,c,_,runtime=fixture;install_delete(runtime);pid=c['project_id'];outside=tmp_path/'outside';outside.mkdir();(outside/'keep').write_text('keep')
    target=s.data/'studies'/pid;target.parent.mkdir(exist_ok=True);target.symlink_to(outside,target_is_directory=True)
    with pytest.raises(Conflict,match='project_asset_symlink'):asyncio.run(s.projects.delete(pid,body(s,pid)))
    assert (outside/'keep').exists() and s.projects.view(pid).state=='active' and not runtime.deleted

def test_child_symlink_removed_without_following_it(fixture,tmp_path):
    s,c,_,runtime=fixture;install_delete(runtime);pid=c['project_id'];paths=owned(s,pid);outside=tmp_path/'outside';outside.mkdir();(outside/'keep').write_text('keep');(paths[0]/'linked').symlink_to(outside,target_is_directory=True)
    assert asyncio.run(s.projects.delete(pid,body(s,pid))).state=='deleted';assert (outside/'keep').exists()

def test_shared_input_blocks_file_cleanup_but_allows_explicit_file_retention(fixture):
    s,c,_,runtime=fixture;install_delete(runtime);pid=c['project_id'];paths=owned(s,pid);other=s.store.create_project('Other','Keep')
    with s.store.connect(True) as db:db.execute('INSERT INTO training_experiments VALUES(?,?,?)',('exp_other',other['id'],encoded({'plan':{'inputs':[{'path':str(paths[0]/'owned.txt')}]}})))
    with pytest.raises(Conflict,match='project_assets_shared'):asyncio.run(s.projects.delete(pid,body(s,pid)))
    assert asyncio.run(s.projects.delete(pid,body(s,pid,False))).state=='deleted';assert paths[0].exists()

def test_registered_historical_training_runs_are_removed_but_shared_environment_stays(fixture):
    s,c,_,runtime=fixture;install_delete(runtime);pid=c['project_id'];owned(s,pid)
    paths=[]
    for run in ['train_previous','train_current']:
        p=s.data/'training/runs'/run;p.mkdir(parents=True);(p/'output').write_text('result');paths.append(p)
    with s.store.connect(True) as db:
        db.execute('INSERT INTO training_experiments VALUES(?,?,?)',('exp_fixture',pid,encoded({'id':'exp_fixture','status':'completed','run_id':'train_current'})))
        db.execute('INSERT INTO training_events(experiment_id,document) VALUES(?,?)',('exp_fixture',encoded({'run_id':'train_previous'})))
    assert asyncio.run(s.projects.delete(pid,body(s,pid))).state=='deleted';assert not any(p.exists() for p in paths)
    with s.store.connect() as db:assert db.execute('SELECT COUNT(*) FROM training_experiments').fetchone()[0]==1

def test_api_confirmation_readonly_and_removed_routes(fixture):
    from pathoreason.api import app
    s,c,_,runtime=fixture;install_delete(runtime);pid=c['project_id'];app.state.service=s;client=TestClient(app);url='/api/v1/research-projects/'+pid
    assert client.post(url+'/archive',json={'expected_revision':1}).json()['state']=='archived'
    assert client.get('/api/v1/research-projects').json()==[]
    assert client.get('/api/v1/research-projects?include_archived=true').json()[0]['open_conversations']==1
    assert client.post(url+'/conversations',json={'title':'No'}).status_code==409
    payload=body(s,pid).model_dump()
    assert client.request('DELETE',url,json={**payload,'confirm':False}).status_code==422
    assert client.request('DELETE',url,json={**payload,'confirmation_title':'wrong'}).status_code==409
    assert client.request('DELETE',url,json=payload,headers={'Origin':'https://untrusted.invalid'}).status_code==403
    assert client.request('DELETE',url,json=payload).json()['state']=='deleted'
    for path in ['/conversations','/artifacts','/workbench']:
        assert client.get(url+path).status_code==410
    assert client.get('/api/v1/conversations/'+c['id']).status_code==410
    assert client.get(url+'/lifecycle').json()['state']=='deleted'
    assert client.get('/api/v1/research-projects?include_archived=true').json()==[]

def test_all_deleted_does_not_reseed_legacy_data(fixture):
    s,c,_,runtime=fixture;install_delete(runtime);asyncio.run(s.projects.delete(c['project_id'],body(s,c['project_id'])))
    s.seed();assert s.projects.list(True)==[]

def test_delete_minimizes_research_records_and_keeps_exact_training_usage(fixture):
    s,c,_,runtime=fixture;install_delete(runtime);pid=c['project_id'];other=s.store.create_project('Other','Keep')
    with s.store.connect(True) as db:
        db.execute('INSERT INTO training_experiments VALUES(?,?,?)',('exp_private',pid,encoded({'id':'exp_private','status':'completed','budget':{'max_wall_seconds':100},'plan':{'private':'research content'},'error':'private log'})))
        db.execute('INSERT INTO training_attempts VALUES(?,?,?,?)',('a_private','exp_private','unit',encoded({'id':'a_private','status':'completed','charged_seconds':17.25,'gpu':True,'output':'private output','launch_spec':{'argv':['private command']}})))
        db.execute('INSERT INTO training_plan_revisions VALUES(?,?,?)',('exp_private',1,encoded({'private':'old plan'})))
        db.execute('INSERT INTO training_input_registry VALUES(?,?,?)',(pid,'sha','private subject'))
        db.execute('INSERT INTO training_exposure VALUES(?,?,?)',(pid,'private subject',encoded({'private':'test exposures'})))
        db.execute('INSERT INTO task_code_tasks VALUES(?,?,?,?)',('task_private',pid,1,encoded({'private':'source manifest'})))
        db.execute('INSERT INTO task_code_revisions VALUES(?,?,?)',('task_private',1,encoded({'private':'source code'})))
        db.execute('INSERT INTO training_input_registry VALUES(?,?,?)',(other['id'],'other_sha','other subject'))
    before=s.training.account.view('exp_private')
    assert asyncio.run(s.projects.delete(pid,body(s,pid))).state=='deleted'
    after=s.training.account.view('exp_private')
    assert before['used_wall_seconds']==after['used_wall_seconds']==17.25
    assert before['used_gpu_seconds']==after['used_gpu_seconds']==17.25
    assert before['budget']==after['budget'];assert 'plan' not in after and 'error' not in after
    assert 'output' not in after['attempts'][0] and 'launch_spec' not in after['attempts'][0]
    with s.store.connect() as db:
        for table in ['training_exposure','task_code_tasks','task_code_revisions','training_plan_revisions']:
            assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
        assert db.execute('SELECT project_id FROM training_input_registry').fetchone()[0]==other['id']

def test_formal_budget_partition_survives_deletion(fixture):
    s,c,request,runtime=fixture;install_delete(runtime);pid=c['project_id']
    async def run():
        await finish(s,c,request)
        with s.store.connect(True) as db:
            db.execute('INSERT INTO formal_studies VALUES(?,?,?,?)',(pid,'formal-key','digest',encoded({'project_id':pid,'budget':{'max_turns':40,'max_wall_seconds':7200},'revision':1,'workspace':'private path','objective':'private research'})))
        with s.store.connect() as db:
            global_before=[dict(x) for x in s.store.budget_rows(db)]
            formal_before=[dict(x) for x in s.store.budget_rows(db,pid)]
        assert (await s.projects.delete(pid,body(s,pid))).state=='deleted'
        with s.store.connect() as db:
            assert [dict(x) for x in s.store.budget_rows(db)]==global_before
            assert [dict(x) for x in s.store.budget_rows(db,pid)]==formal_before
            doc=json.loads(db.execute('SELECT document FROM formal_studies WHERE project_id=?',(pid,)).fetchone()[0]);assert 'objective' not in doc and 'workspace' not in doc
    asyncio.run(run())
