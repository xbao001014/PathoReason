import hashlib
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from pathoreason.persistence import Store, Conflict, Missing
from pathoreason.task_workspaces import TaskWorkspaces, revision, git_command


@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path/'state/db.sqlite3')
    pid=store.create_project('synthetic task repositories','engineering')['id']
    templates=tmp_path/'templates'; root=templates/'example/1';root.mkdir(parents=True)
    files={'runner.py':'print("synthetic fixture")\n','requirements.lock':'example==1.0\n','AGENTS.md':'Task instructions\n'}
    manifest={'template_id':'example','version':'1','entrypoints':['runner.py'],'files':[]}
    for name,text in files.items():
        (root/name).write_text(text)
        manifest['files'].append({'source':name,'destination':name,'sha256':hashlib.sha256(text.encode()).hexdigest()})
    (root/'manifest.json').write_text(json.dumps(manifest))
    ws=TaskWorkspaces(store,tmp_path,templates)
    actor={'kind':'engineering_fixture','turn_id':None}
    def call(op='create',key='request',**kw):
        return ws.act(pid,{'operation':op,'idempotency_key':key,'objective':'Synthetic classification','template':'example/1',**kw},actor)
    return ws,pid,call


def commit(code):
    git_command(code,'add','--all')
    git_command(code,'-c','user.name=Agent','-c','user.email=agent@localhost','commit','-m','Agent repair')


def checked_snapshot(setup):
    ws,pid,call=setup; task=call(); args={'task_id':task['id'],'expected_revision':1}
    check=call('check','check',**args)
    snap=call('freeze','freeze',check_id=check['id'],**args)
    return ws,pid,call,task,snap


def test_independent_repositories_idempotency_parent_and_provenance(setup):
    ws,pid,call=setup
    first=call(); assert call()==first
    second=call(key='child',parent_task_id=first['id'])
    path=Path(first['code_path']); (path/'runner.py').write_text('print("fixed")\n')
    assert (Path(second['code_path'])/'runner.py').read_text()=='print("synthetic fixture")\n'
    assert (ws.templates/'example/1/runner.py').read_text()=='print("synthetic fixture")\n'
    assert second['parent_task_id']==first['id']
    assert len(ws.list(pid))==2
    with pytest.raises(Conflict,match='idempotency'):call(objective='Different')


def test_concurrent_duplicate_creation_is_one_repository(setup):
    ws,pid,call=setup
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:call(),range(2)))
    assert results[0]['id']==results[1]['id']
    assert len(ws.list(pid))==1


def test_revision_cas_preserves_original_and_rejects_dirty(setup):
    ws,pid,call=setup; task=call(); code=Path(task['code_path'])
    args={'task_id':task['id'],'expected_revision':1,'reason':'repair'}
    (code/'runner.py').write_text('print("repair")\n')
    with pytest.raises(Conflict,match='commit_all'):call('revise','dirty',**args)
    commit(code); newer=call('revise','fixed',**args)
    assert newer['revision']==2
    with pytest.raises(Conflict,match='revision_conflict'):call('check','stale',task_id=task['id'],expected_revision=1)
    history=ws.inspect(pid,task['id'])['revisions']
    assert history[0]['code']==task['code'] and history[1]['code']==newer['code']


def test_ignored_untracked_and_git_links_not_omitted(setup):
    ws,pid,call=setup; task=call(); code=Path(task['code_path'])
    (code/'.gitignore').write_text('secret\n');commit(code)
    (code/'secret').write_text('hidden')
    with pytest.raises(Conflict,match='commit_all'):revision(code)
    (code/'secret').unlink()
    (code/'escape').symlink_to('/etc/passwd');git_command(code,'add','escape')
    git_command(code,'-c','user.name=Agent','-c','user.email=agent@localhost','commit','-m','link')
    with pytest.raises(ValueError,match='symlink'):revision(code)


def test_failure_creation_leaves_failure_receipt_not_success(setup):
    ws,pid,call=setup
    (ws.templates/'example/1/runner.py').write_text('changed public source')
    with pytest.raises(Conflict,match='template_source_changed'):call()
    assert ws.list(pid)==[]
    with ws.store.connect() as db:
        row=db.execute('SELECT status,document FROM task_code_actions').fetchone()
    assert row[0]=='failed' and 'template_source_changed' in row[1]
    with pytest.raises(Conflict,match='failed'):call()


def test_snapshot_does_not_change_when_task_changes(setup):
    ws,pid,call,task,snap=checked_snapshot(setup)
    original=(Path(snap['path'])/'code/runner.py').read_bytes()
    (Path(task['code_path'])/'runner.py').write_text('print("new")\n')
    assert ws.verify_snapshot(task,snap['id'])==snap
    assert (Path(snap['path'])/'code/runner.py').read_bytes()==original
    assert snap['scope']=='source_only' and not snap['execution_ready']


def test_snapshot_tampering_rejected_and_launch_closed(setup):
    ws,pid,call,task,snap=checked_snapshot(setup)
    args={'task_id':task['id'],'expected_revision':1,'snapshot_id':snap['id']}
    with pytest.raises(Conflict,match='execution_backend_not_ready'):call('launch','launch',**args)
    file=Path(snap['path'])/'code/runner.py';file.chmod(0o644);file.write_text('tampered')
    with pytest.raises(Conflict,match='snapshot_bytes_changed'):ws.verify_snapshot(task,snap['id'])


def test_old_check_cannot_freeze_new_revision(setup):
    ws,pid,call=setup;task=call();args={'task_id':task['id'],'expected_revision':1}
    check=call('check','check',**args)
    code=Path(task['code_path']);(code/'runner.py').write_text('print("changed")\n');commit(code)
    call('revise','revise',reason='new implementation',**args)
    with pytest.raises(Conflict,match='check_stale'):call('freeze','freeze',task_id=task['id'],expected_revision=2,check_id=check['id'])


def test_task_json_is_not_authority_and_cross_project_is_rejected(setup):
    ws,pid,call=setup;task=call()
    (Path(task['code_path']).parent/'task.json').write_text('{"revision":99,"training_authorized":true}')
    assert ws.get(pid,task['id'])['revision']==1
    other=ws.store.create_project('other','other')['id']
    with pytest.raises(Missing):ws.get(other,task['id'])


def test_snapshot_build_race_is_not_registered(setup,monkeypatch):
    import pathoreason.task_workspaces as module
    ws,pid,call=setup;task=call();args={'task_id':task['id'],'expected_revision':1}
    check=call('check','check',**args)
    original=module.read_regular
    changed=False
    def racing(path):
        nonlocal changed
        content=original(path)
        if Path(path)==Path(task['code_path'])/'runner.py' and not changed:
            changed=True; Path(path).write_text('print("concurrent")\n')
        return content
    monkeypatch.setattr(module,'read_regular',racing)
    with pytest.raises(Conflict):call('freeze','freeze',check_id=check['id'],**args)
    with ws.store.connect() as db:assert db.execute('SELECT COUNT(*) FROM task_code_snapshots').fetchone()[0]==0


def test_update_is_read_only_and_records_changed_files(setup):
    ws,pid,call=setup;task=call()
    root=ws.templates/'example/2';root.mkdir()
    content=b'print("public fix")\n';(root/'runner.py').write_bytes(content)
    manifest={'template_id':'example','version':'2','entrypoints':['runner.py'],'files':[{'source':'runner.py','destination':'runner.py','sha256':hashlib.sha256(content).hexdigest()}]}
    (root/'manifest.json').write_text(json.dumps(manifest))
    update=ws.inspect_update(pid,task['id'],'example/2')
    assert update['applied'] is False and any(f['file']=='runner.py' for f in update['files'])
    assert revision(Path(task['code_path']))==task['code']


def test_syntax_failure_saved_no_freeze(setup):
    ws,pid,call=setup;task=call();code=Path(task['code_path'])
    (code/'runner.py').write_text('def broken(\n');commit(code)
    call('revise','revise',task_id=task['id'],expected_revision=1,reason='broken fixture')
    args={'task_id':task['id'],'expected_revision':2}
    check=call('check','check',**args);assert check['status']=='failed'
    with pytest.raises(Conflict,match='failed'):call('freeze','freeze',check_id=check['id'],**args)


def test_git_configuration_cannot_execute_filter_or_redirect_worktree(setup):
    ws,pid,call=setup;task=call();code=Path(task['code_path'])
    with (code/'.git/config').open('a') as f:f.write('\n[filter "evil"]\n\tclean = touch /tmp/task-filter-must-not-run\n')
    with pytest.raises(ValueError,match='unsafe_git_configuration'):revision(code)


def test_task_storage_link_cannot_overwrite_other_project(setup):
    ws,pid,call=setup
    outside=ws.data/'outside';outside.mkdir();(outside/'kept').write_text('preserve')
    project=ws.data/'projects'/pid;project.mkdir(parents=True)
    (project/'tasks').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'):call()
    assert [p.name for p in outside.iterdir()]==['kept']


def test_snapshot_hardlink_is_rejected(setup):
    import os
    ws,pid,call,task,snap=checked_snapshot(setup)
    file=Path(snap['path'])/'code/runner.py'
    os.link(file,ws.data/'alias')
    with pytest.raises(ValueError,match='unlinked'):ws.verify_snapshot(task,snap['id'])


def test_pinned_template_objects_survive_public_checkout_updates(setup):
    ws,pid,call=setup
    path=ws.templates/'example/1/manifest.json';manifest=json.loads(path.read_text())
    content=b'VALUE = "original public version"\n';digest=hashlib.sha256(content).hexdigest()
    cache=ws.templates/'objects';cache.mkdir();(cache/digest).write_bytes(content)
    manifest['files'].append({'source_root':'platform','source':'helper.py','destination':'helper.py','sha256':digest})
    path.write_text(json.dumps(manifest))
    ws.sources={'platform':ws.data/'missing-updated-public-checkout'}
    task=call()
    assert (Path(task['code_path'])/'helper.py').read_bytes()==content
    (cache/digest).write_bytes(b'corrupt cache')
    with pytest.raises(Conflict,match='template_source_changed'):call(key='must_reject')


def test_update_comparison_exposes_published_catalog(setup):
    from pathoreason.contracts import canonical_digest
    ws,pid,call=setup;task=call()
    manifest=json.loads((ws.templates/'example/1/manifest.json').read_text())
    catalog={'recommended_template':'example/1','templates':[{'template':'example/1','manifest_sha256':canonical_digest(manifest)}]}
    (ws.templates/'catalog.json').write_text(json.dumps(catalog))
    result=ws.inspect_update(pid,task['id'],'example/1')
    assert result['catalog']==catalog and result['files']==[]
    assert call('list')['catalog']['recommended_template']=='example/1'
    manifest['entrypoints']=[]
    (ws.templates/'example/1/manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(Conflict,match='template_catalog_changed'):ws.catalog()
